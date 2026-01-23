from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import build_calendar_features
import run_build_lt_csv
import run_forecast_batch
from booking_curve import monthly_rounding
from booking_curve.config import HOTEL_CONFIG, OUTPUT_DIR, get_hotel_rounding_units
from booking_curve.daily_snapshots import (
    get_daily_snapshots_path,
    get_latest_asof_date,
    list_stay_months_from_daily_snapshots,
    read_daily_snapshots,
    read_daily_snapshots_for_month,
    rebuild_asof_dates_from_daily_snapshots,
)
from booking_curve.forecast_simple import (
    build_curve_from_final,
    compute_market_pace_7d,
    forecast_final_from_pace14,
    forecast_final_from_pace14_market,
    moving_average_3months,
    moving_average_recent_90days,
    moving_average_recent_90days_weighted,
)
from booking_curve.missing_report import build_missing_report, find_unconverted_raw_pairs
from booking_curve.pms_adapter_nface import (
    build_daily_snapshots_fast,
    build_daily_snapshots_for_pairs,
    build_daily_snapshots_from_folder_partial,
    build_daily_snapshots_full_all,
    build_daily_snapshots_full_months,
)
from booking_curve.raw_inventory import RawInventory, build_raw_inventory
from booking_curve.utils import apply_nocb_along_lt
from run_full_evaluation import resolve_asof_dates_for_month, run_full_evaluation_for_gui

_EVALUATION_DETAIL_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_TOPDOWN_ACT_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
logger = logging.getLogger(__name__)


def _drop_all_na_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(axis=1, how="all")


def generate_month_range(start_yyyymm: str, end_yyyymm: str) -> list[str]:
    """
    開始月・終了月 (YYYYMM) から、両端を含む月リストを生成する。
    例: "202401", "202403" -> ["202401", "202402", "202403"]
    """

    def _parse_yyyymm(value: str) -> tuple[int, int]:
        if len(value) != 6:
            raise ValueError(f"Invalid YYYYMM format: {value}")
        try:
            year = int(value[:4])
            month = int(value[4:])
        except ValueError:
            raise ValueError(f"Invalid YYYYMM format: {value}") from None
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month in YYYYMM: {value}")
        return year, month

    start_year, start_month = _parse_yyyymm(start_yyyymm)
    end_year, end_month = _parse_yyyymm(end_yyyymm)

    if (start_year, start_month) > (end_year, end_month):
        raise ValueError("start_yyyymm must not be later than end_yyyymm")

    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year}{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

    return months


def build_calendar_for_gui(hotel_tag: str) -> str:
    """
    GUI からのカレンダー再生成ボタン用ラッパ。

    当年1月1日〜翌年12月31日までの期間で、指定ホテルのカレンダーCSVを生成する。

    戻り値:
        生成されたカレンダーファイルの絶対パス文字列。
    """
    today = date.today()
    start = date(today.year, 1, 1)
    end = date(today.year + 1, 12, 31)

    # build_calendar_features 側のユーティリティで生成
    out_path = build_calendar_features.build_calendar_for_hotel(
        hotel_tag=hotel_tag,
        start_date=start,
        end_date=end,
    )
    return str(out_path)


def get_calendar_coverage(hotel_tag: str) -> Dict[str, Optional[str]]:
    """
    calendar_features_<hotel_tag>.csv の日付範囲を返すヘルパー。

    戻り値:
        {
            "min_date": "YYYY-MM-DD" または None,
            "max_date": "YYYY-MM-DD" または None,
        }

    ファイルが存在しない、もしくは内容が不正な場合は両方とも None を返す。
    """

    csv_path = OUTPUT_DIR / f"calendar_features_{hotel_tag}.csv"
    if not csv_path.exists():
        return {"min_date": None, "max_date": None}

    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
    except Exception:
        return {"min_date": None, "max_date": None}

    if df.empty or "date" not in df.columns:
        return {"min_date": None, "max_date": None}

    # date 列から最小・最大を取得
    min_dt = df["date"].min()
    max_dt = df["date"].max()

    if pd.isna(min_dt) or pd.isna(max_dt):
        return {"min_date": None, "max_date": None}

    min_str = pd.to_datetime(min_dt).normalize().strftime("%Y-%m-%d")
    max_str = pd.to_datetime(max_dt).normalize().strftime("%Y-%m-%d")

    return {"min_date": min_str, "max_date": max_str}


def _get_evaluation_detail_df(hotel_tag: str, *, force_reload: bool = False) -> pd.DataFrame:
    cached = _EVALUATION_DETAIL_CACHE.get(hotel_tag)

    csv_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"evaluation detail csv not found: {csv_path}")

    mtime = csv_path.stat().st_mtime
    if not force_reload and cached is not None:
        cached_mtime, cached_df = cached
        if cached_mtime == mtime:
            return cached_df.copy()

    df_detail = pd.read_csv(csv_path)
    df_detail = df_detail.copy()
    df_detail["target_month"] = df_detail["target_month"].astype(str)
    df_detail["model"] = df_detail["model"].astype(str)
    if "asof_type" in df_detail.columns:
        df_detail["asof_type"] = df_detail["asof_type"].astype(str)

    df_detail["error_pct"] = pd.to_numeric(df_detail["error_pct"], errors="coerce")
    df_detail["abs_error_pct"] = pd.to_numeric(df_detail["abs_error_pct"], errors="coerce")

    _EVALUATION_DETAIL_CACHE[hotel_tag] = (mtime, df_detail)
    return df_detail.copy()


def clear_evaluation_detail_cache(hotel_tag: str | None = None) -> None:
    """evaluation detail のキャッシュをクリアする。"""

    if hotel_tag is None:
        _EVALUATION_DETAIL_CACHE.clear()
        return

    _EVALUATION_DETAIL_CACHE.pop(hotel_tag, None)


def _get_topdown_actual_monthly_revenue(hotel_tag: str) -> pd.DataFrame:
    daily_path = get_daily_snapshots_path(hotel_tag)
    if not daily_path.exists():
        return pd.DataFrame(columns=["stay_month", "revenue_total", "days_in_month"])

    mtime = daily_path.stat().st_mtime
    cached = _TOPDOWN_ACT_CACHE.get(hotel_tag)
    if cached is not None:
        cached_mtime, cached_df = cached
        if cached_mtime == mtime:
            return cached_df.copy()

    df = read_daily_snapshots(hotel_tag)
    if df.empty:
        empty_df = pd.DataFrame(columns=["stay_month", "revenue_total", "days_in_month"])
        _TOPDOWN_ACT_CACHE[hotel_tag] = (mtime, empty_df)
        return empty_df.copy()

    df = df.copy()
    df["stay_date"] = pd.to_datetime(df["stay_date"], errors="coerce").dt.normalize()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["stay_date", "as_of_date"])
    if df.empty:
        empty_df = pd.DataFrame(columns=["stay_month", "revenue_total", "days_in_month"])
        _TOPDOWN_ACT_CACHE[hotel_tag] = (mtime, empty_df)
        return empty_df.copy()

    df = df.sort_values(["stay_date", "as_of_date"])
    latest = df.groupby("stay_date").tail(1).copy()
    if "revenue_oh" not in latest.columns:
        empty_df = pd.DataFrame(columns=["stay_month", "revenue_total", "days_in_month"])
        _TOPDOWN_ACT_CACHE[hotel_tag] = (mtime, empty_df)
        return empty_df.copy()

    latest["revenue_oh"] = pd.to_numeric(latest["revenue_oh"], errors="coerce")
    latest = latest.dropna(subset=["revenue_oh"])
    if latest.empty:
        empty_df = pd.DataFrame(columns=["stay_month", "revenue_total", "days_in_month"])
        _TOPDOWN_ACT_CACHE[hotel_tag] = (mtime, empty_df)
        return empty_df.copy()

    latest["stay_month"] = latest["stay_date"].dt.to_period("M")
    monthly = latest.groupby("stay_month", as_index=False)["revenue_oh"].sum().rename(columns={"revenue_oh": "revenue_total"})
    monthly["days_in_month"] = monthly["stay_month"].dt.days_in_month
    _TOPDOWN_ACT_CACHE[hotel_tag] = (mtime, monthly)
    return monthly.copy()


def _get_hotel_config(hotel_tag: str) -> dict:
    try:
        return HOTEL_CONFIG[hotel_tag]
    except KeyError as exc:
        raise ValueError(f"Unknown hotel_tag: {hotel_tag}; check HOTEL_CONFIG") from exc


def _get_capacity(hotel_tag: str, capacity: Optional[float]) -> float:
    """GUIから渡された capacity があればそれを優先し、
    なければ HOTEL_CONFIG の設定を返す。
    """
    if capacity is not None:
        return float(capacity)
    hotel_cfg = _get_hotel_config(hotel_tag)
    return float(hotel_cfg["capacity"])


def _build_raw_inventory_or_raise(hotel_tag: str) -> RawInventory:
    raw_inventory = build_raw_inventory(hotel_tag)
    if raw_inventory.health.severity == "WARN":
        logging.warning(raw_inventory.health.message)
    return raw_inventory


def _normalize_ymd_timestamp(value: str) -> pd.Timestamp:
    stripped = value.strip()
    if not stripped:
        raise ValueError("RAWに最新ASOFが見つからない")
    if stripped.isdigit() and len(stripped) == 8:
        ts = pd.to_datetime(stripped, format="%Y%m%d", errors="coerce")
    else:
        ts = pd.to_datetime(stripped, errors="coerce")
    if pd.isna(ts):
        raise ValueError("RAWに最新ASOFが見つからない")
    return pd.Timestamp(ts).normalize()


def _build_range_rebuild_plan(
    hotel_tag: str,
    *,
    buffer_days: int = 30,
    lookahead_days: int = 120,
    raw_inventory: RawInventory | None = None,
) -> dict[str, object]:
    inventory = raw_inventory or _build_raw_inventory_or_raise(hotel_tag)
    latest_asof_raw = inventory.health.latest_asof_ymd
    if not latest_asof_raw:
        raise ValueError("RAWに最新ASOFが見つからない")

    asof_max = _normalize_ymd_timestamp(latest_asof_raw)
    asof_min = _calculate_asof_min(asof_max, buffer_days)

    stay_end = asof_max + pd.Timedelta(days=lookahead_days)
    stay_months = {f"{period.year}{period.month:02d}" for period in pd.period_range(start=asof_max, end=stay_end, freq="M")}
    previous_month = (asof_max.to_period("M") - 1).strftime("%Y%m")
    stay_months.add(previous_month)

    stay_months_list = sorted(stay_months)
    stay_min = pd.Timestamp(f"{stay_months_list[0]}01").normalize()
    stay_max = (pd.Timestamp(f"{stay_months_list[-1]}01") + pd.offsets.MonthEnd(0)).normalize()

    return {
        "mode": "RANGE_REBUILD",
        "buffer_days": buffer_days,
        "lookahead_days": lookahead_days,
        "asof_min": asof_min,
        "asof_max": asof_max,
        "stay_months": stay_months_list,
        "stay_min": stay_min,
        "stay_max": stay_max,
    }


def build_range_rebuild_plan_for_gui(
    hotel_tag: str,
    *,
    buffer_days: int = 30,
    lookahead_days: int = 120,
) -> dict[str, object]:
    return _build_range_rebuild_plan(
        hotel_tag,
        buffer_days=buffer_days,
        lookahead_days=lookahead_days,
    )


def get_latest_asof_for_hotel(hotel_tag: str) -> Optional[str]:
    """ホテル別の最新 ASOF 日付を asof_dates_<hotel_tag>.csv から取得する。"""

    csv_path = OUTPUT_DIR / f"asof_dates_{hotel_tag}.csv"
    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path, parse_dates=["as_of_date"])
    except Exception:
        return None

    if "as_of_date" not in df.columns:
        return None

    asof_series = df["as_of_date"]
    if asof_series.empty:
        return None

    latest_asof = asof_series.max()
    if pd.isna(latest_asof):
        return None

    return pd.to_datetime(latest_asof).normalize().strftime("%Y-%m-%d")


def _load_lt_data(hotel_tag: str, target_month: str) -> pd.DataFrame:
    """LT_DATA CSV を読み込み、stay_date を DatetimeIndex に揃える。"""

    csv_path = OUTPUT_DIR / f"lt_data_{target_month}_{hotel_tag}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"LT_DATA csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)
    df.index = pd.to_datetime(df.index)

    # 列を int 化できるものだけに限定する
    col_map: dict[str, int] = {}
    for col in df.columns:
        try:
            col_map[col] = int(col)
        except Exception:
            continue

    if not col_map:
        raise ValueError("LT 列が見つかりませんでした。")

    lt_df = df[list(col_map.keys())].copy()
    lt_df.columns = [col_map[c] for c in lt_df.columns]

    # 念のため対象月でフィルタ
    year = int(target_month[:4])
    month = int(target_month[4:])
    lt_df = lt_df[(lt_df.index.year == year) & (lt_df.index.month == month)]

    return lt_df


def _get_latest_asof_from_lt(hotel_tag: str, target_month: str) -> Optional[str]:
    """
    asof_dates_xxx.csv が無い場合用のフォールバック。
    LT_DATA から「今日以前に存在する ASOF 日付」の最大値を推定して返す。
    """
    try:
        lt_df = _load_lt_data(hotel_tag=hotel_tag, target_month=target_month)
    except FileNotFoundError:
        return None

    if lt_df.empty:
        return None

    # LT >= 0 の列だけを対象にする
    lt_cols = [c for c in lt_df.columns if isinstance(c, (int, float)) and c >= 0]
    if not lt_cols:
        return None

    today = pd.Timestamp.today().normalize()
    latest_asof: Optional[pd.Timestamp] = None

    for stay_date, row in lt_df[lt_cols].iterrows():
        for lt, val in row.items():
            if pd.isna(val):
                continue
            try:
                lt_int = int(lt)
            except Exception:
                continue
            asof = stay_date.normalize() - pd.Timedelta(days=lt_int)
            # 未来日付は無視
            if asof > today:
                continue
            if (latest_asof is None) or (asof > latest_asof):
                latest_asof = asof

    if latest_asof is None:
        return None
    return latest_asof.normalize().strftime("%Y-%m-%d")


def get_latest_asof_for_month(hotel_tag: str, target_month: str) -> Optional[str]:
    """
    指定ホテル・指定宿泊月の「最新ASOF」を返す。

    優先順位:
    1. output/asof_dates_{hotel_tag}.csv の as_of_date 最大値
    2. asof_dates が無い場合は、LT_DATA からのフォールバック推定
    """
    latest_asof = get_latest_asof_for_hotel(hotel_tag)
    if latest_asof is not None:
        return latest_asof

    # asof_dates が無い場合は、LT_DATA から推定
    return _get_latest_asof_from_lt(hotel_tag, target_month)


def _get_history_months_around_asof(
    as_of_ts: pd.Timestamp,
    months_back: int = 4,
    months_forward: int = 4,
) -> list[str]:
    """
    ASOF 日付を中心に、前後の月を YYYYMM 文字列リストで返す。
    例: as_of=2025-09-30 -> ["202505", ..., "202601"]
    """
    center = as_of_ts.to_period("M")
    months: list[str] = []
    for offset in range(-months_back, months_forward + 1):
        p = center + offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_booking_curve_data(
    hotel_tag: str,
    target_month: str,
    weekday: int,
    model: str,
    as_of_date: str,
    *,
    fill_missing: bool = True,
) -> dict:
    """曜日別ブッキングカーブ画面向けのデータセットを返す。"""

    lt_cache: dict[str, pd.DataFrame] = {}

    def _get_lt_cached(month_str: str) -> pd.DataFrame:
        if month_str not in lt_cache:
            lt_cache[month_str] = _load_lt_data(hotel_tag=hotel_tag, target_month=month_str)
        return lt_cache[month_str]

    lt_df = _get_lt_cached(target_month)

    # 曜日でフィルタ（0=Mon..6=Sun）
    df_week = lt_df[lt_df.index.weekday == weekday].copy()
    df_week.sort_index(inplace=True)

    df_week_plot = df_week.copy()
    if fill_missing and not df_week_plot.empty:
        df_week_plot = apply_nocb_along_lt(df_week_plot, axis="columns", max_gap=None)

    lt_ticks = sorted(df_week_plot.columns) if not df_week_plot.empty else sorted(lt_df.columns)
    lt_min, lt_max = (lt_ticks[0], lt_ticks[-1]) if lt_ticks else (-1, 90)

    # NOCB 適用済みのカーブをベースに、ASOF 境界で未来側をトリミングする
    asof_ts = pd.to_datetime(as_of_date)

    # ASOF を中心に前後4ヶ月の LT_DATA を読み込み、同曜日だけを連結
    history_months = _get_history_months_around_asof(
        as_of_ts=asof_ts,
        months_back=4,
        months_forward=4,
    )

    history_dfs: list[pd.DataFrame] = []
    for ym in history_months:
        try:
            df_m = _get_lt_cached(ym)
        except FileNotFoundError:
            continue
        df_m_wd = df_m[df_m.index.weekday == weekday].copy()
        if not df_m_wd.empty:
            history_dfs.append(df_m_wd)

    if history_dfs:
        history_all = pd.concat(history_dfs, axis=0)
        history_all.sort_index(inplace=True)
    else:
        # 履歴が取れない場合はフォールバックとして target_month の曜日データを使う
        history_all = df_week.copy()

    has_act_column = -1 in df_week_plot.columns
    asof_normalized = asof_ts.normalize()

    for stay_date in df_week_plot.index:
        delta_days = (stay_date.normalize() - asof_ts).days
        if delta_days > 0:
            for lt in df_week_plot.columns:
                if lt < delta_days:
                    df_week_plot.at[stay_date, lt] = pd.NA

        if has_act_column and stay_date.normalize() >= asof_normalized:
            df_week_plot.at[stay_date, -1] = pd.NA

    # stay_date ごとのカーブ
    curves = {}
    for stay_date, row in df_week_plot.iterrows():
        curves[stay_date] = row.reindex(lt_ticks)

    # --- 3ヶ月平均カーブの計算 ---
    target_period = pd.Period(target_month, freq="M")
    history_dfs: list[pd.DataFrame] = []

    for offset in (1, 2, 3):
        past_period = target_period - offset
        past_month_str = f"{past_period.year}{past_period.month:02d}"
        try:
            past_lt = _get_lt_cached(past_month_str)
        except FileNotFoundError:
            continue

        past_week = past_lt[past_lt.index.weekday == weekday].copy()
        if not past_week.empty:
            history_dfs.append(past_week)

    if history_dfs:
        avg_curve_3m = moving_average_3months(
            lt_df_list=history_dfs,
            lt_min=lt_min,
            lt_max=lt_max,
        )
    else:
        if not df_week_plot.empty:
            avg_curve_3m = df_week_plot.reindex(columns=lt_ticks).mean(axis=0, skipna=True)
        else:
            avg_curve_3m = None

    baseline_curve_recent90 = None
    if history_all is not None and not history_all.empty:
        baseline_curve_recent90 = moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=asof_ts,
            lt_min=lt_min,
            lt_max=lt_max,
        )

    forecast_curve = None
    forecast_curves = None
    pace14_detail = None

    if model == "recent90":
        if baseline_curve_recent90 is not None:
            forecast_curve = baseline_curve_recent90
    elif model == "recent90w":
        if not history_all.empty:
            forecast_curve = moving_average_recent_90days_weighted(
                lt_df=history_all,
                as_of_date=asof_ts,
                lt_min=lt_min,
                lt_max=lt_max,
            )
    elif model == "avg":
        forecast_curve = avg_curve_3m
    elif model in {"pace14", "pace14_market"}:
        baseline_curves: dict[int, pd.Series] = {}
        history_by_weekday: dict[int, pd.DataFrame] = {}

        for wd in range(7):
            history_dfs_wd: list[pd.DataFrame] = []
            for ym in history_months:
                try:
                    df_m = _get_lt_cached(ym)
                except FileNotFoundError:
                    continue
                df_m_wd = df_m[df_m.index.weekday == wd].copy()
                if not df_m_wd.empty:
                    history_dfs_wd.append(df_m_wd)

            if not history_dfs_wd:
                continue

            history_all_wd = pd.concat(history_dfs_wd, axis=0)
            history_all_wd.sort_index(inplace=True)
            history_all_wd.index = pd.to_datetime(history_all_wd.index)
            baseline_curve = moving_average_recent_90days(
                lt_df=history_all_wd,
                as_of_date=asof_ts,
                lt_min=lt_min,
                lt_max=lt_max,
            )
            baseline_curves[wd] = baseline_curve
            history_by_weekday[wd] = history_all_wd

        baseline_curve = baseline_curves.get(weekday)
        history_all = history_by_weekday.get(weekday)
        if baseline_curve is not None and history_all is not None and not df_week.empty:
            if model == "pace14_market":
                market_pace_7d, mp_detail = compute_market_pace_7d(
                    lt_df=lt_df,
                    as_of_ts=asof_ts,
                    history_by_weekday=history_by_weekday,
                    lt_min=lt_min,
                    lt_max=lt_max,
                )
                final_series, detail_df = forecast_final_from_pace14_market(
                    lt_df=df_week,
                    baseline_curve=baseline_curve,
                    history_df=history_all,
                    as_of_date=asof_ts,
                    capacity=_get_capacity(hotel_tag, None),
                    market_pace_7d=market_pace_7d,
                    lt_min=0,
                    lt_max=lt_max,
                )
                if not detail_df.empty:
                    detail_df = detail_df.copy()
                    detail_df["market_pace_7d"] = market_pace_7d
                    pace14_detail = detail_df
                    pace14_detail.attrs["market_pace_detail"] = mp_detail
            else:
                final_series, detail_df = forecast_final_from_pace14(
                    lt_df=df_week,
                    baseline_curve=baseline_curve,
                    history_df=history_all,
                    as_of_date=asof_ts,
                    capacity=_get_capacity(hotel_tag, None),
                    lt_min=0,
                    lt_max=lt_max,
                )
                pace14_detail = detail_df if not detail_df.empty else None

            forecast_curve = baseline_curve
            forecast_curves = {}
            for stay_date, final_value in final_series.items():
                if pd.isna(final_value):
                    continue
                curve = build_curve_from_final(baseline_curve, float(final_value))
                if not curve.empty:
                    forecast_curves[stay_date] = curve

    dates: List[pd.Timestamp] = list(df_week.index)

    return {
        "curves": curves,
        "avg_curve": baseline_curve_recent90,
        "forecast_curve": forecast_curve,
        "forecast_curves": forecast_curves,
        "pace14_detail": pace14_detail,
        "lt_ticks": lt_ticks,
        "dates": dates,
    }


def get_monthly_curve_data(
    hotel_tag: str,
    target_month: str,
    as_of_date: Optional[str] = None,
    *,
    fill_missing: bool = True,
) -> pd.DataFrame:
    """月次ブッキングカーブ画面向けに、月次カーブ用の DataFrame を返す。

    優先順位:
    1. monthly_curve_{target_month}_{hotel_tag}.csv が存在すればそれを読み込む。
    2. 無ければ daily_snapshots_{hotel_tag}.csv から monthly_curve を生成して保存し、そのデータを返す。

    daily_snapshots / monthly_curve が無い、もしくは生成結果が空の場合は ValueError または FileNotFoundError を送出する。
    as_of_date 引数が与えられた場合は、その日付以前の daily_snapshots にトリミングして集計する。
    """

    csv_path = OUTPUT_DIR / f"monthly_curve_{target_month}_{hotel_tag}.csv"
    cutoff_ts = pd.to_datetime(as_of_date).normalize() if as_of_date else None

    if csv_path.exists():
        df_source = _load_monthly_curve_csv(csv_path)
    else:
        df_source = _build_monthly_curve_from_daily_snapshots(
            hotel_tag=hotel_tag,
            target_month=target_month,
            cutoff_ts=cutoff_ts,
        )
        _save_monthly_curve_csv(df_source, csv_path, hotel_tag, target_month)

    if cutoff_ts is not None:
        year = int(target_month[:4])
        month = int(target_month[4:])
        last_day = monthrange(year, month)[1]
        month_end = datetime(year, month, last_day)
        act_asof = pd.Timestamp(month_end + timedelta(days=1)).normalize()
        lt_cutoff = (act_asof - cutoff_ts).days - 1
        if "lt" in df_source.columns:
            df_source = df_source[df_source["lt"] >= lt_cutoff]
        else:
            df_trim = df_source.reset_index()
            if "lt" not in df_trim.columns:
                df_trim = df_trim.rename(columns={"index": "lt"})
            df_source = df_trim[df_trim["lt"] >= lt_cutoff]

    return _prepare_monthly_curve_df(df_source, csv_path, fill_missing=fill_missing)


def _build_monthly_curve_from_daily_snapshots(
    hotel_tag: str,
    target_month: str,
    cutoff_ts: pd.Timestamp | None,
) -> pd.DataFrame:
    csv_path = OUTPUT_DIR / f"daily_snapshots_{hotel_tag}.csv"
    if not csv_path.exists():
        raise ValueError(f"daily_snapshots_{hotel_tag}.csv が存在しないため monthly_curve を生成できません。")

    try:
        df_month = read_daily_snapshots_for_month(hotel_id=hotel_tag, target_month=target_month, output_dir=OUTPUT_DIR)
    except Exception as exc:
        raise ValueError(f"daily_snapshots_{hotel_tag}.csv の読み込みに失敗しました: {exc}") from exc

    required_cols = {"stay_date", "as_of_date", "rooms_oh"}
    missing = required_cols.difference(df_month.columns)
    if missing:
        raise ValueError(f"daily_snapshots_{hotel_tag}.csv に必須列が不足しています: {sorted(missing)}")

    df_month = df_month.copy()
    df_month["stay_date"] = pd.to_datetime(df_month["stay_date"], errors="coerce").dt.normalize()
    df_month["as_of_date"] = pd.to_datetime(df_month["as_of_date"], errors="coerce").dt.normalize()
    df_month["rooms_oh"] = pd.to_numeric(df_month["rooms_oh"], errors="coerce")
    df_month = df_month.dropna(subset=["stay_date", "as_of_date"])
    if df_month.empty:
        raise ValueError(f"daily_snapshots_{hotel_tag}.csv に対象月 {target_month} のデータが見つかりません。")

    if cutoff_ts is not None:
        df_month = df_month[df_month["as_of_date"] <= cutoff_ts]
        if df_month.empty:
            raise ValueError(f"ASOF {cutoff_ts.date()} 以前の daily_snapshots にデータが無いため monthly_curve を生成できません。")

    year = int(target_month[:4])
    month = int(target_month[4:])
    last_day = monthrange(year, month)[1]
    month_end = datetime(year, month, last_day)
    act_asof = month_end + timedelta(days=1)

    df_monthly = df_month.groupby("as_of_date")["rooms_oh"].sum(min_count=1).reset_index()
    df_monthly = df_monthly.rename(columns={"rooms_oh": "rooms_total"})
    df_monthly["lt"] = (act_asof - df_monthly["as_of_date"]).dt.days - 1

    max_lt = getattr(run_build_lt_csv, "MAX_LT", None)
    if max_lt is not None:
        df_monthly = df_monthly[(df_monthly["lt"] >= -1) & (df_monthly["lt"] <= max_lt)]
    else:
        df_monthly = df_monthly[df_monthly["lt"] >= -1]

    if df_monthly.empty:
        raise ValueError(f"monthly_curve が存在せず、daily_snapshots から {target_month}（{hotel_tag}）向けに生成できません。")

    df_out = df_monthly.groupby("lt")["rooms_total"].sum(min_count=1).reset_index().sort_values("lt").reset_index(drop=True)

    has_act_lt = (df_out["lt"] == -1).any()
    if not has_act_lt:
        latest_by_stay = df_month.sort_values(["stay_date", "as_of_date"]).groupby("stay_date").tail(1)
        if not latest_by_stay.empty:
            act_total_raw = latest_by_stay["rooms_oh"].sum(min_count=1)
            if not pd.isna(act_total_raw):
                df_out = pd.concat(
                    [df_out, pd.DataFrame([{"lt": -1, "rooms_total": float(act_total_raw)}])],
                    ignore_index=True,
                )

    if df_out.empty:
        raise ValueError(f"monthly_curve が存在せず、daily_snapshots から {target_month}（{hotel_tag}）向けに生成できません。")

    df_out["lt"] = df_out["lt"].astype(int)
    return df_out.sort_values("lt").reset_index(drop=True)


def _save_monthly_curve_csv(df: pd.DataFrame, output_path: Path, hotel_tag: str, target_month: str) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    except Exception as exc:
        logging.exception(
            "Failed to save monthly_curve CSV for %s (%s) to %s.",
            hotel_tag,
            target_month,
            output_path,
        )
        raise FileNotFoundError(f"monthly_curve を {output_path} に保存できませんでした: {exc}") from exc

    logging.info(
        "Monthly curve generated from daily_snapshots and saved to %s for %s (%s).",
        output_path,
        hotel_tag,
        target_month,
    )


def _load_monthly_curve_csv(csv_path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to read monthly_curve csv: {csv_path}") from exc
    return df


def _prepare_monthly_curve_df(df: pd.DataFrame, csv_path: Path, *, fill_missing: bool) -> pd.DataFrame:
    if df is None or df.empty:
        raise FileNotFoundError(f"monthly_curve が存在せず、daily_snapshots からも生成できませんでした: {csv_path}")

    if "lt" in df.columns:
        df = df.set_index("lt")
    elif df.columns[0] != "lt":
        df = df.set_index(df.columns[0])

    try:
        df.index = df.index.astype(int)
    except Exception as exc:
        raise ValueError(f"Invalid LT index in monthly curve csv: {csv_path}") from exc

    if "rooms_total" in df.columns:
        df = df[["rooms_total"]]
    elif len(df.columns) == 1:
        df.columns = ["rooms_total"]
    else:
        raise ValueError(f"Unexpected columns in monthly curve csv: {list(df.columns)}")

    df = df.sort_index()
    if df.empty:
        raise FileNotFoundError(f"monthly_curve が存在せず、daily_snapshots からも生成できませんでした: {csv_path}")

    act_row = df.loc[[-1]] if -1 in df.index else None
    df_no_act = df.loc[df.index != -1]
    if fill_missing and not df_no_act.empty:
        max_lt = df_no_act.index.max()
        if pd.isna(max_lt) or max_lt < 0:
            df_no_act = df_no_act.copy()
        else:
            df_no_act = df_no_act.reindex(index=range(0, int(max_lt) + 1))
        rooms_series = df_no_act["rooms_total"].astype(float)
        rooms_series = rooms_series.interpolate(method="linear", limit_area="inside")
        df_no_act["rooms_total"] = rooms_series
    parts = [df_no_act]
    if act_row is not None:
        parts.append(act_row)
    return pd.concat(parts)


def run_forecast_for_gui(
    hotel_tag: str,
    target_months: list[str],
    as_of_date: str,
    gui_model: str,
    capacity: float | None = None,
    phase_factors: dict[str, float] | None = None,
    phase_clip_pct: float | None = None,
    pax_capacity: float | None = None,
) -> None:
    """
    日別フォーキャストタブから Forecast を実行するための薄いラッパー。

    - target_months: 対象宿泊月の YYYYMM リスト。
      （現時点では GUI からは 1要素リストを渡す想定だが、
       将来的に「当月＋先3ヶ月」などの複数月対応も見越す）
    - as_of_date: "YYYY-MM-DD" 形式。run_forecast_batch 側では
      pd.to_datetime で解釈される前提。
    - gui_model: GUI のコンボボックス値
      ("avg", "recent90", "recent90_adj", "recent90w", "recent90w_adj", "pace14", "pace14_market")
    - capacity: 予測キャップ (None の場合は run_forecast_batch 側のデフォルトを使用)
    """
    # GUI からは "YYYY-MM-DD" が渡されるので、
    # run_forecast_batch 側の想定に合わせて "YYYYMMDD" に変換する。
    asof_ts = pd.to_datetime(as_of_date)
    asof_tag = asof_ts.strftime("%Y%m%d")

    # _adj 付きは、元 CSV の adjusted_projected_rooms 列を使うだけなので
    # 計算としては base モデルと同じでよい。
    base_model = gui_model.replace("_adj", "")

    asof_norm = asof_ts.normalize()
    for ym in target_months:
        try:
            period = pd.Period(ym, freq="M")
        except Exception:
            period = None
        if period is not None:
            month_end = period.end_time.normalize()
            if asof_norm > month_end:
                logger.info(
                    "Skipping settled target month forecast: hotel_tag=%s target_month=%s as_of=%s",
                    hotel_tag,
                    ym,
                    asof_norm.date(),
                )
                continue
        phase_factor = None
        if phase_factors:
            phase_factor = phase_factors.get(ym)
        if base_model == "avg":
            run_forecast_batch.run_avg_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                pax_capacity=pax_capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
                phase_clip_pct=phase_clip_pct,
            )
        elif base_model == "recent90":
            run_forecast_batch.run_recent90_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                pax_capacity=pax_capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
                phase_clip_pct=phase_clip_pct,
            )
        elif base_model == "recent90w":
            run_forecast_batch.run_recent90_weighted_forecast(
                target_month=ym,
                as_of=asof_tag,
                capacity=capacity,
                pax_capacity=pax_capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
                phase_clip_pct=phase_clip_pct,
            )
        elif base_model == "pace14":
            run_forecast_batch.run_pace14_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                pax_capacity=pax_capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
                phase_clip_pct=phase_clip_pct,
            )
        elif base_model == "pace14_market":
            run_forecast_batch.run_pace14_market_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                pax_capacity=pax_capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
                phase_clip_pct=phase_clip_pct,
            )
        else:
            raise ValueError(f"Unsupported gui_model: {gui_model}")


def _get_forecast_csv_prefix(gui_model: str) -> tuple[str, str]:
    model_map = {
        "avg": ("forecast", "projected_rooms"),
        "recent90": ("forecast_recent90", "projected_rooms"),
        "recent90w": ("forecast_recent90w", "projected_rooms"),
        "recent90_adj": ("forecast_recent90", "adjusted_projected_rooms"),
        "recent90w_adj": ("forecast_recent90w", "adjusted_projected_rooms"),
        "pace14": ("forecast_pace14", "projected_rooms"),
        "pace14_market": ("forecast_pace14_market", "projected_rooms"),
    }
    if gui_model not in model_map:
        raise ValueError(f"Unsupported gui_model: {gui_model}")
    return model_map[gui_model]


def _read_forecast_csv_safely(csv_path: Path) -> tuple[pd.DataFrame | None, str | None]:
    try:
        df = pd.read_csv(csv_path, index_col=0)
    except Exception as exc:  # noqa: BLE001
        return None, f"read failed: {exc}"

    index_str = df.index.astype(str)
    parsed_index = pd.to_datetime(index_str, errors="coerce")

    if parsed_index.isna().any():
        numeric_index = pd.to_numeric(index_str, errors="coerce")
        if numeric_index.notna().all():
            in_range = numeric_index.between(30000, 60000)
            if in_range.all():
                parsed_index = pd.to_datetime(
                    numeric_index,
                    unit="D",
                    origin="1899-12-30",
                    errors="coerce",
                )

    invalid_mask = parsed_index.isna()
    if invalid_mask.any():
        invalid_values = list(dict.fromkeys(index_str[invalid_mask].tolist()))[:5]
        sample_text = ", ".join(invalid_values) if invalid_values else "unknown"
        return None, f"INVALID stay_date index in {csv_path}: {sample_text}"

    df = df.copy()
    df.index = parsed_index.normalize()
    return df, None


def _summarize_forecast_error(err_msg: str, max_len: int = 120) -> str:
    err_msg = err_msg.strip()
    if len(err_msg) <= max_len:
        return err_msg

    if "INVALID stay_date index" in err_msg:
        if " in " in err_msg and ":" in err_msg:
            prefix, _, tail = err_msg.partition(" in ")
            path_part, _, sample_part = tail.partition(":")
            file_name = Path(path_part.strip()).name
            summarized = f"{prefix} in {file_name}: {sample_part.strip()}"
            if len(summarized) <= max_len:
                return summarized
    return f"{err_msg[: max_len - 3]}..."


def _check_forecast_csv_complete_for_month(
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
) -> tuple[bool, str]:
    prefix, _ = _get_forecast_csv_prefix(gui_model)
    asof_ts = pd.to_datetime(as_of_date)
    asof_tag = asof_ts.strftime("%Y%m%d")
    csv_name = f"{prefix}_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    csv_path = OUTPUT_DIR / csv_name
    if not csv_path.exists():
        return False, "CSV not found"

    df, err_msg = _read_forecast_csv_safely(csv_path)
    if df is None:
        return False, f"CSV read failed: {err_msg}"

    if df.empty:
        return False, "CSV empty"
    if "forecast_revenue" not in df.columns:
        return False, "forecast_revenue missing"

    try:
        year = int(target_month[:4])
        month = int(target_month[4:])
    except Exception:
        return False, "invalid target_month"
    _, num_days = monthrange(year, month)
    expected_dates = pd.date_range(
        start=pd.Timestamp(year=year, month=month, day=1),
        end=pd.Timestamp(year=year, month=month, day=num_days),
        freq="D",
    )

    index_dates = df.index.normalize()
    if index_dates.empty:
        return False, "stay_date missing"

    revenue_series = pd.to_numeric(df["forecast_revenue"], errors="coerce")
    revenue_series.index = index_dates
    revenue_series = revenue_series[~pd.isna(revenue_series.index)]
    revenue_by_date = revenue_series.groupby(level=0).max()
    revenue_by_date = revenue_by_date.reindex(expected_dates)
    if revenue_by_date.isna().any():
        return False, "forecast_revenue incomplete"

    if len(expected_dates) != num_days:
        return False, "unexpected days"
    return True, "complete"


def _get_projected_monthly_revpar(
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
    rooms_cap: float,
    missing_ok: bool = False,
) -> tuple[float | None, str | None]:
    prefix, _ = _get_forecast_csv_prefix(gui_model)
    asof_ts = pd.to_datetime(as_of_date)
    asof_tag = asof_ts.strftime("%Y%m%d")
    csv_name = f"{prefix}_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    csv_path = OUTPUT_DIR / csv_name
    if not csv_path.exists():
        if missing_ok:
            return None, f"CSV not found: {csv_path}"
        raise FileNotFoundError(f"forecast csv not found: {csv_path}")

    df, err_msg = _read_forecast_csv_safely(csv_path)
    if df is None:
        return None, err_msg
    if "forecast_revenue" not in df.columns:
        if missing_ok:
            return None, "forecast_revenue missing"
        return None, "forecast_revenue missing"

    revenue = pd.to_numeric(df["forecast_revenue"], errors="coerce")

    try:
        year = int(target_month[:4])
        month = int(target_month[4:])
    except Exception:
        return None, "invalid target_month"
    _, num_days = monthrange(year, month)
    expected_dates = pd.date_range(
        start=pd.Timestamp(year=year, month=month, day=1),
        end=pd.Timestamp(year=year, month=month, day=num_days),
        freq="D",
    )

    index_dates = df.index.normalize()
    if index_dates.empty:
        return None, "stay_date missing"

    revenue.index = index_dates
    revenue = revenue[~pd.isna(revenue.index)]
    revenue_by_date = revenue.groupby(level=0).max()
    revenue_by_date = revenue_by_date.reindex(expected_dates)
    if revenue_by_date.isna().any():
        return None, "forecast_revenue incomplete"

    revenue_total = revenue_by_date.sum(min_count=1)
    if pd.isna(revenue_total):
        return None, "forecast_revenue missing"
    denom = rooms_cap * num_days
    if denom <= 0:
        return None, "rooms capacity missing"
    return float(revenue_total / denom), None


def _compute_monthly_forecast_basis_from_daily_table(
    *,
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    model_key: str,
    capacity: float,
    phase_factors: dict[str, float] | None,
    phase_clip_pct: float | None,
) -> dict[str, float | int | None]:
    df = _load_daily_df_for_topdown(
        hotel_tag=hotel_tag,
        target_month=target_month,
        as_of_date=as_of_date,
        gui_model=model_key,
        capacity=capacity,
        pax_capacity=None,
    )
    if df is None or df.empty or "stay_date" not in df.columns:
        raise ValueError("daily forecast table missing")

    daily_rows = df[df["stay_date"].notna()].copy()
    if daily_rows.empty:
        raise ValueError("daily forecast table has no rows")

    try:
        asof_ts = pd.to_datetime(as_of_date).normalize()
    except Exception:
        asof_ts = None

    stay_dates = pd.to_datetime(daily_rows["stay_date"], errors="coerce").dt.normalize()
    if asof_ts is None or pd.isna(asof_ts):
        asof_ts = stay_dates.min()

    mask_past = stay_dates < asof_ts
    rooms_actual = daily_rows.get("actual_rooms")
    rooms_asof = daily_rows.get("asof_oh_rooms")
    rooms_forecast = daily_rows.get("forecast_rooms")
    rev_forecast = daily_rows.get("forecast_revenue")
    rev_oh = daily_rows.get("revenue_oh_now")
    if rooms_forecast is None or rev_forecast is None:
        raise ValueError("daily forecast table missing forecast rooms/revenue")

    forecast_rooms_total = float(pd.to_numeric(rooms_forecast, errors="coerce").fillna(0).sum())
    forecast_rev_total = float(pd.to_numeric(rev_forecast, errors="coerce").fillna(0).sum())
    days = int(stay_dates.notna().sum())
    denom_cap = capacity * days
    forecast_revpar = forecast_rev_total / denom_cap if denom_cap > 0 else None
    forecast_adr = forecast_rev_total / forecast_rooms_total if forecast_rooms_total > 0 else None
    forecast_occ = forecast_rooms_total / denom_cap if denom_cap > 0 else None

    rooms_past = rooms_actual.where(rooms_actual.notna(), rooms_asof)
    rooms_past = rooms_past.where(rooms_past.notna(), rooms_forecast)
    rev_past = rev_oh.where(rev_oh.notna(), rev_forecast)

    basis_rooms_series = pd.Series(index=daily_rows.index, dtype=float)
    basis_rev_series = pd.Series(index=daily_rows.index, dtype=float)
    basis_rooms_series.loc[mask_past] = rooms_past.loc[mask_past]
    basis_rooms_series.loc[~mask_past] = rooms_forecast.loc[~mask_past]
    basis_rev_series.loc[mask_past] = rev_past.loc[mask_past]
    basis_rev_series.loc[~mask_past] = rev_forecast.loc[~mask_past]

    basis_rooms = float(pd.to_numeric(basis_rooms_series, errors="coerce").fillna(0).sum())
    basis_rev = float(pd.to_numeric(basis_rev_series, errors="coerce").fillna(0).sum())
    basis_revpar = basis_rev / denom_cap if denom_cap > 0 else None
    basis_adr = basis_rev / basis_rooms if basis_rooms > 0 else None
    basis_occ = basis_rooms / denom_cap if denom_cap > 0 else None
    return {
        "forecast_rev": forecast_rev_total,
        "forecast_rooms": forecast_rooms_total,
        "forecast_revpar": forecast_revpar,
        "forecast_adr": forecast_adr,
        "forecast_occ": forecast_occ,
        "basis_rev": basis_rev,
        "basis_rooms": basis_rooms,
        "basis_revpar": basis_revpar,
        "basis_adr": basis_adr,
        "basis_occ": basis_occ,
        "days": days,
        "capacity": capacity,
    }


def _load_daily_df_for_topdown(
    *,
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
    capacity: float,
    pax_capacity: float | None,
) -> pd.DataFrame:
    daily_df = get_daily_forecast_table(
        hotel_tag=hotel_tag,
        target_month=target_month,
        as_of_date=as_of_date,
        gui_model=gui_model,
        capacity=capacity,
        pax_capacity=pax_capacity,
        apply_monthly_rounding=False,
    )
    return daily_df.copy(deep=True)


def build_topdown_revpar_panel(
    *,
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    latest_asof_date: str | None = None,
    model_key: str,
    rooms_cap: float,
    phase_factors: dict[str, float] | None,
    phase_clip_pct: float | None,
    forecast_horizon_months: int = 3,
    show_years: list[int] | None = None,
    fiscal_year_start_month: int = 6,
) -> dict[str, object]:
    if forecast_horizon_months <= 0:
        raise ValueError("forecast_horizon_months must be a positive integer")

    try:
        target_period = pd.Period(target_month, freq="M")
    except Exception as exc:
        raise ValueError(f"Invalid target_month: {target_month}") from exc

    try:
        asof_period = pd.Period(as_of_date, freq="M")
    except Exception as exc:
        raise ValueError(f"Invalid as_of_date: {as_of_date}") from exc

    asof_ts = pd.to_datetime(as_of_date).normalize()
    latest_asof_ts = asof_ts
    if latest_asof_date:
        try:
            parsed_latest = pd.to_datetime(latest_asof_date).normalize()
        except Exception:
            parsed_latest = None
        if parsed_latest is not None and not pd.isna(parsed_latest):
            latest_asof_ts = parsed_latest

    def _get_fiscal_year(year: int, month: int) -> int:
        if month >= fiscal_year_start_month:
            return year
        return year - 1

    current_fy = _get_fiscal_year(target_period.year, target_period.month)
    if show_years is None:
        show_years = list(range(current_fy - 5, current_fy + 1))

    months_order = [(fiscal_year_start_month + offset - 1) % 12 + 1 for offset in range(12)]
    fiscal_month_labels = [f"{month}月" for month in months_order]
    fiscal_month_strs = [f"{current_fy if month >= fiscal_year_start_month else current_fy + 1}{month:02d}" for month in months_order]
    target_month_idx = months_order.index(target_period.month)

    monthly_actual = _get_topdown_actual_monthly_revenue(hotel_tag)
    revpar_by_period: dict[pd.Period, float] = {}
    month_revpar_map: dict[tuple[int, int], float] = {}
    if not monthly_actual.empty:
        for _, row in monthly_actual.iterrows():
            stay_month = row["stay_month"]
            if pd.isna(stay_month):
                continue
            if isinstance(stay_month, pd.Period):
                stay_period = stay_month.asfreq("M")
            else:
                stay_period = pd.Period(stay_month, freq="M")
            year = int(stay_period.year)
            month = int(stay_period.month)
            fy = _get_fiscal_year(year, month)
            if month >= fiscal_year_start_month:
                fiscal_index = month - fiscal_year_start_month
            else:
                fiscal_index = month + (12 - fiscal_year_start_month)
            days = float(row.get("days_in_month") or 0)
            if days <= 0 or rooms_cap <= 0:
                continue
            revenue_total = float(row.get("revenue_total") or 0)
            revpar = revenue_total / (rooms_cap * days)
            revpar_by_period[stay_period] = revpar
            month_revpar_map[(fy, fiscal_index)] = revpar

    lines_by_fy: dict[int, list[float | None]] = {}
    for fy in show_years:
        if fy == current_fy:
            continue
        values: list[float | None] = [None] * 12
        for idx in range(12):
            value = month_revpar_map.get((fy, idx))
            if value is not None:
                values[idx] = float(value)
        lines_by_fy[fy] = values

    current_fy_actual: list[float | None] = [None] * 12
    for idx in range(12):
        value = month_revpar_map.get((current_fy, idx))
        if value is None:
            continue
        month_num = months_order[idx]
        year = current_fy if month_num >= fiscal_year_start_month else current_fy + 1
        month_end = pd.Timestamp(year=year, month=month_num, day=1) + pd.offsets.MonthEnd(0)
        if month_end <= asof_ts:
            current_fy_actual[idx] = float(value)

    start_period = pd.Period(latest_asof_ts, freq="M")
    end_ts = latest_asof_ts + timedelta(days=90)
    end_period = pd.Period(end_ts, freq="M")
    if start_period > end_period:
        end_period = start_period
    forecast_month_strs_range = generate_month_range(
        start_period.strftime("%Y%m"),
        end_period.strftime("%Y%m"),
    )
    rotation_month_strs = [(target_period + offset).strftime("%Y%m") for offset in range(-5, 7)]
    view_months_set = set(fiscal_month_strs) | set(rotation_month_strs)
    band_month_candidates = set(forecast_month_strs_range)
    band_month_candidates.update(rotation_month_strs)
    computable_months: list[str] = []
    skipped_months: dict[str, str] = {}
    for month_str in forecast_month_strs_range:
        try:
            run_forecast_for_gui(
                hotel_tag=hotel_tag,
                target_months=[month_str],
                as_of_date=as_of_date,
                gui_model=model_key,
                capacity=None,
                pax_capacity=None,
                phase_factors=phase_factors,
                phase_clip_pct=phase_clip_pct,
            )
            is_complete, reason = _check_forecast_csv_complete_for_month(
                hotel_tag=hotel_tag,
                target_month=month_str,
                as_of_date=as_of_date,
                gui_model=model_key,
            )
            if is_complete:
                computable_months.append(month_str)
            else:
                skipped_months[month_str] = f"INCOMPLETE: {_summarize_forecast_error(reason)}"
        except Exception as exc:  # noqa: BLE001
            logging.warning("Skipping forecast month %s due to error: %s", month_str, exc)
            skipped_months[month_str] = str(exc)

    current_fy_forecast: list[float | None] = [None] * 12
    forecast_revpar_map: dict[str, float | None] = {}
    forecast_basis_map: dict[str, dict[str, float | int | None]] = {}
    effective_forecast_months: list[str] = []
    for month_str in computable_months:
        try:
            basis = _compute_monthly_forecast_basis_from_daily_table(
                hotel_tag=hotel_tag,
                target_month=month_str,
                as_of_date=as_of_date,
                model_key=model_key,
                capacity=rooms_cap,
                phase_factors=phase_factors,
                phase_clip_pct=phase_clip_pct,
            )
        except Exception as exc:  # noqa: BLE001
            skipped_months.setdefault(
                month_str,
                f"INCOMPLETE: {_summarize_forecast_error(str(exc))}",
            )
            continue
        revpar_value = basis.get("forecast_revpar")
        if revpar_value is not None:
            revpar_value = float(revpar_value)
        forecast_basis_map[month_str] = basis
        if revpar_value is None:
            continue
        forecast_revpar_map[month_str] = revpar_value
        effective_forecast_months.append(month_str)
        try:
            month_period = pd.Period(month_str, freq="M")
        except Exception:
            continue
        idx = months_order.index(month_period.month)
        if _get_fiscal_year(month_period.year, month_period.month) == current_fy:
            current_fy_forecast[idx] = revpar_value

    anchor_idx = None
    anchor_value = None
    anchor_month_end = None
    for idx in range(12):
        value = month_revpar_map.get((current_fy, idx))
        if value is None:
            continue
        month_num = months_order[idx]
        year = current_fy if month_num >= fiscal_year_start_month else current_fy + 1
        month_end = pd.Timestamp(year=year, month=month_num, day=1) + pd.offsets.MonthEnd(0)
        if month_end <= asof_ts and (anchor_month_end is None or month_end > anchor_month_end):
            anchor_idx = idx
            anchor_value = float(value)
            anchor_month_end = month_end

    band_p10: list[float | None] = [None] * 12
    band_p90: list[float | None] = [None] * 12
    band_by_month: dict[str, tuple[float, float]] = {}
    band_p10_prev_anchor: list[float | None] = [None] * 12
    band_p90_prev_anchor: list[float | None] = [None] * 12
    band_by_month_prev_anchor: dict[str, tuple[float, float]] = {}
    reference_years = [fy for fy in show_years if fy != current_fy]
    anchor_period_latest = pd.Period(anchor_month_end, freq="M") if anchor_month_end is not None else None
    anchor_month_str = anchor_period_latest.strftime("%Y%m") if anchor_period_latest is not None else None
    if anchor_month_str is not None:
        band_month_candidates.add(anchor_month_str)
    if anchor_period_latest is not None and anchor_value is not None and anchor_idx is not None:
        band_by_month[anchor_month_str] = (anchor_value, anchor_value)
        month_num_anchor = months_order[anchor_idx]
        end_month = fiscal_year_start_month - 1 or 12
        end_year = current_fy + 1 if end_month < fiscal_year_start_month else current_fy
        fy_end_period = pd.Period(f"{end_year}{end_month:02d}", freq="M")
        if anchor_period_latest + 1 <= fy_end_period:
            for period in generate_month_range(
                (anchor_period_latest + 1).strftime("%Y%m"),
                fy_end_period.strftime("%Y%m"),
            ):
                band_month_candidates.add(period)
        band_months_sorted = sorted(
            band_month_candidates,
            key=lambda value: pd.Period(value, freq="M").ordinal,
        )
        for month_str in band_months_sorted:
            try:
                target_period = pd.Period(month_str, freq="M")
            except Exception:
                continue
            step = int(target_period.ordinal - anchor_period_latest.ordinal)
            if step <= 0:
                continue
            ratios = []
            for fy in reference_years:
                year_anchor_ref = fy if month_num_anchor >= fiscal_year_start_month else fy + 1
                anchor_ref_period = pd.Period(f"{year_anchor_ref}{month_num_anchor:02d}", freq="M")
                target_ref_period = anchor_ref_period + step
                anchor_ref_val = revpar_by_period.get(anchor_ref_period)
                target_ref_val = revpar_by_period.get(target_ref_period)
                if anchor_ref_val in (None, 0) or target_ref_val is None:
                    continue
                ratios.append(float(target_ref_val) / float(anchor_ref_val))
            if not ratios:
                continue
            p10_ratio = float(np.percentile(ratios, 10))
            p90_ratio = float(np.percentile(ratios, 90))
            band_by_month[month_str] = (anchor_value * p10_ratio, anchor_value * p90_ratio)

        for idx in range(12):
            month_num = months_order[idx]
            year = current_fy if month_num >= fiscal_year_start_month else current_fy + 1
            month_str = f"{year}{month_num:02d}"
            band_values = band_by_month.get(month_str)
            if band_values is not None:
                band_p10[idx] = band_values[0]
                band_p90[idx] = band_values[1]

    def _month_end(period: pd.Period) -> pd.Timestamp:
        return pd.Timestamp(year=period.year, month=period.month, day=1) + pd.offsets.MonthEnd(0)

    def _get_current_revpar(period: pd.Period) -> float | None:
        month_end = _month_end(period)
        actual_val = revpar_by_period.get(period)
        if actual_val is not None and month_end <= asof_ts:
            return float(actual_val)
        forecast_val = forecast_revpar_map.get(period.strftime("%Y%m"))
        if forecast_val is not None:
            return float(forecast_val)
        return None

    min_actual_period = min(revpar_by_period) if revpar_by_period else None

    def _find_anchor_period(target_period: pd.Period) -> tuple[pd.Period | None, float | None]:
        candidate_ordinal = int(target_period.ordinal) - 1
        for _ in range(120):
            candidate = pd.Period(ordinal=candidate_ordinal, freq="M")
            if min_actual_period is not None and candidate < min_actual_period:
                return None, None
            anchor_val = _get_current_revpar(candidate)
            if anchor_val is not None:
                return candidate, anchor_val
            candidate_ordinal -= 1
        return None, None

    band_months_sorted = sorted(
        band_month_candidates,
        key=lambda value: pd.Period(value, freq="M").ordinal,
    )
    ratio_fallback_months: set[str] = set()
    last_ratio_band: tuple[float, float] | None = None
    min_ratio_samples = 3
    for month_str in band_months_sorted:
        try:
            target_period = pd.Period(month_str, freq="M")
        except Exception:
            continue
        if anchor_period_latest is not None and target_period < anchor_period_latest:
            continue
        if anchor_period_latest is not None and target_period == anchor_period_latest:
            if anchor_value is not None:
                band_by_month_prev_anchor[month_str] = (anchor_value, anchor_value)
            continue
        anchor_period_candidate, anchor_value_prev = _find_anchor_period(target_period)
        if anchor_period_candidate is None or anchor_value_prev is None:
            continue
        anchor_month_str = anchor_period_candidate.strftime("%Y%m")
        band_by_month_prev_anchor.setdefault(
            anchor_month_str,
            (anchor_value_prev, anchor_value_prev),
        )
        step = int(target_period.ordinal - anchor_period_candidate.ordinal)
        if step <= 0:
            continue
        ratios = []
        month_num_anchor = anchor_period_candidate.month
        for fy in reference_years:
            year_anchor_ref = fy if month_num_anchor >= fiscal_year_start_month else fy + 1
            anchor_ref_period = pd.Period(f"{year_anchor_ref}{month_num_anchor:02d}", freq="M")
            target_ref_period = anchor_ref_period + step
            anchor_ref_val = revpar_by_period.get(anchor_ref_period)
            target_ref_val = revpar_by_period.get(target_ref_period)
            if anchor_ref_val in (None, 0) or target_ref_val is None:
                continue
            ratios.append(float(target_ref_val) / float(anchor_ref_val))
        if len(ratios) >= min_ratio_samples:
            p10_ratio = float(np.percentile(ratios, 10))
            p90_ratio = float(np.percentile(ratios, 90))
            last_ratio_band = (p10_ratio, p90_ratio)
        elif last_ratio_band is not None:
            p10_ratio, p90_ratio = last_ratio_band
            ratio_fallback_months.add(month_str)
        else:
            p10_ratio = 1.0
            p90_ratio = 1.0
            ratio_fallback_months.add(month_str)
        band_by_month_prev_anchor[month_str] = (
            anchor_value_prev * p10_ratio,
            anchor_value_prev * p90_ratio,
        )

    for idx in range(12):
        month_num = months_order[idx]
        year = current_fy if month_num >= fiscal_year_start_month else current_fy + 1
        month_str = f"{year}{month_num:02d}"
        band_values = band_by_month_prev_anchor.get(month_str)
        if band_values is not None:
            band_p10_prev_anchor[idx] = band_values[0]
            band_p90_prev_anchor[idx] = band_values[1]

    band_prev_segments: list[dict[str, list[float] | list[str]]] = []
    if anchor_period_latest is not None:
        for month_str in sorted(
            effective_forecast_months,
            key=lambda value: pd.Period(value, freq="M").ordinal,
        ):
            if month_str not in view_months_set:
                continue
            try:
                target_period = pd.Period(month_str, freq="M")
            except Exception:
                continue
            band_values = band_by_month_prev_anchor.get(month_str)
            if band_values is None:
                continue
            anchor_period_candidate, anchor_value_prev = _find_anchor_period(target_period)
            if anchor_period_candidate is None or anchor_value_prev is None:
                continue
            anchor_month_str = anchor_period_candidate.strftime("%Y%m")
            if anchor_month_str not in view_months_set:
                continue
            band_prev_segments.append(
                {
                    "months": [anchor_month_str, month_str],
                    "low": [float(anchor_value_prev), float(band_values[0])],
                    "high": [float(anchor_value_prev), float(band_values[1])],
                }
            )

        if effective_forecast_months:
            last_forecast_period = max(
                (pd.Period(month_str, freq="M") for month_str in effective_forecast_months),
                key=lambda period: period.ordinal,
            )
            last_forecast_month = last_forecast_period.strftime("%Y%m")
            anchor_value_forecast = forecast_revpar_map.get(last_forecast_month)
            if anchor_value_forecast is not None:
                future_months = [
                    month_str
                    for month_str in (fiscal_month_strs + rotation_month_strs)
                    if pd.Period(month_str, freq="M") > last_forecast_period and month_str in band_by_month_prev_anchor
                ]
                future_months = sorted(
                    future_months,
                    key=lambda value: pd.Period(value, freq="M").ordinal,
                )
                if len(future_months) >= 2:
                    months_values = [last_forecast_month] + future_months
                    low_values = [float(anchor_value_forecast)]
                    high_values = [float(anchor_value_forecast)]
                    for month_str in future_months:
                        band_values = band_by_month_prev_anchor.get(month_str)
                        if band_values is None:
                            continue
                        low_values.append(float(band_values[0]))
                        high_values.append(float(band_values[1]))
                    if len(months_values) == len(low_values) == len(high_values) and len(months_values) >= 3:
                        band_prev_segments.append(
                            {
                                "months": months_values,
                                "low": low_values,
                                "high": high_values,
                            }
                        )

    forecast_indices = {
        months_order.index(pd.Period(month_str, freq="M").month)
        for month_str in effective_forecast_months
        if _get_fiscal_year(int(month_str[:4]), int(month_str[4:])) == current_fy
    }
    band_start_idx = months_order.index(asof_period.month)
    forecast_end_idx = max(forecast_indices) if forecast_indices else band_start_idx - 1

    diagnostics: list[dict[str, object]] = []
    for month_str in band_months_sorted:
        try:
            month_period = pd.Period(month_str, freq="M")
        except Exception:
            month_period = None
        if month_period is not None and month_period < asof_period:
            continue
        if anchor_period_latest is not None and month_period is not None and month_period <= anchor_period_latest:
            continue
        revpar_value = forecast_revpar_map.get(month_str)
        band_values = band_by_month.get(month_str)
        if anchor_period_latest is not None:
            if month_period is not None and month_period < anchor_period_latest:
                band_prev_values = None
            else:
                band_prev_values = band_by_month_prev_anchor.get(month_str)
        else:
            band_prev_values = band_by_month_prev_anchor.get(month_str)
        p10_latest = band_values[0] if band_values else None
        p90_latest = band_values[1] if band_values else None
        p10_prev = band_prev_values[0] if band_prev_values else None
        p90_prev = band_prev_values[1] if band_prev_values else None
        if revpar_value is None and p10_latest is None and p90_latest is None and p10_prev is None and p90_prev is None:
            continue
        out_of_range_latest = False
        out_of_range_prev = False
        if revpar_value is not None and p10_latest is not None and p90_latest is not None:
            out_of_range_latest = revpar_value < p10_latest or revpar_value > p90_latest
        if revpar_value is not None and p10_prev is not None and p90_prev is not None:
            out_of_range_prev = revpar_value < p10_prev or revpar_value > p90_prev
        notes: list[str] = []
        if month_str in ratio_fallback_months:
            notes.append("(C:ratio_fallback)")
        basis = forecast_basis_map.get(month_str, {})
        diagnostics.append(
            {
                "month": month_str,
                "revpar": revpar_value,
                "forecast_adr": basis.get("forecast_adr"),
                "forecast_occ": basis.get("forecast_occ"),
                "forecast_rooms": basis.get("forecast_rooms"),
                "forecast_rev": basis.get("forecast_rev"),
                "capacity": basis.get("capacity"),
                "days": basis.get("days"),
                "basis_adr": basis.get("basis_adr"),
                "basis_occ": basis.get("basis_occ"),
                "basis_rev": basis.get("basis_rev"),
                "basis_rooms": basis.get("basis_rooms"),
                "p10_latest": p10_latest,
                "p90_latest": p90_latest,
                "p10_prev": p10_prev,
                "p90_prev": p90_prev,
                "out_of_range_latest": out_of_range_latest,
                "out_of_range_prev": out_of_range_prev,
                "notes": notes,
            }
        )

    return {
        "fiscal_month_labels": fiscal_month_labels,
        "month_labels": fiscal_month_labels,
        "lines_by_fy": lines_by_fy,
        "current_fy": current_fy,
        "current_fy_actual": current_fy_actual,
        "current_fy_forecast": current_fy_forecast,
        "band_p10": band_p10,
        "band_p90": band_p90,
        "band_by_month": band_by_month,
        "band_p10_prev_anchor": band_p10_prev_anchor,
        "band_p90_prev_anchor": band_p90_prev_anchor,
        "band_by_month_prev_anchor": band_by_month_prev_anchor,
        "band_prev_segments": band_prev_segments,
        "fiscal_month_strs": fiscal_month_strs,
        "rotation_month_strs": rotation_month_strs,
        "band_start_idx": band_start_idx,
        "forecast_end_idx": forecast_end_idx,
        "diagnostics": diagnostics,
        "target_month_index": target_month_idx,
        "forecast_months_range": forecast_month_strs_range,
        "forecast_months": effective_forecast_months,
        "skipped_months": skipped_months,
        "anchor_idx": anchor_idx,
    }


def get_daily_forecast_table(
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
    capacity: Optional[float] = None,
    pax_capacity: Optional[float] = None,
    apply_monthly_rounding: bool = True,
) -> pd.DataFrame:
    """日別フォーキャスト一覧画面向けのテーブルを構築する。

    Parameters
    ----------
    hotel_tag : str
        ホテル識別子 (例: "daikokucho")
    target_month : str
        対象宿泊月 "YYYYMM"
    as_of_date : str
        予測基準日 "YYYY-MM-DD"
    gui_model : str
        GUI上で選択されたモデル名
        ("avg", "recent90", "recent90_adj", "recent90w", "recent90w_adj", "pace14", "pace14_market")
    capacity : float, optional
        None の場合は HOTEL_CONFIG の設定を使用
    pax_capacity : float, optional
        pax の日別キャップ。None の場合は自動推定値を使用
    apply_monthly_rounding : bool, optional
        True の場合、Forecast 系の *_display を資料向けに丸める

    Returns
    -------
    pd.DataFrame
        日別行 + 最終行に TOTAL 行 を含むテーブル
    """
    cap = _get_capacity(hotel_tag, capacity)
    rounding_units = get_hotel_rounding_units(hotel_tag)
    round_rooms_unit = float(rounding_units["rooms"])
    round_pax_unit = float(rounding_units["pax"])
    round_revenue_unit = float(rounding_units["revenue"])

    def _round_int_series(series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        mask = values.isna().to_numpy()
        arr = values.to_numpy(dtype=float)
        arr2 = np.where(mask, 0.0, arr)
        rounded = np.rint(arr2).astype(np.int64, copy=False)
        out_arr = pd.array(rounded, dtype="Int64")
        out_arr[mask] = pd.NA
        return pd.Series(out_arr, index=series.index, name=series.name)

    model_map = {
        "avg": ("forecast", "projected_rooms"),
        "recent90": ("forecast_recent90", "projected_rooms"),
        "recent90w": ("forecast_recent90w", "projected_rooms"),
        "recent90_adj": ("forecast_recent90", "adjusted_projected_rooms"),
        "recent90w_adj": ("forecast_recent90w", "adjusted_projected_rooms"),
        "pace14": ("forecast_pace14", "projected_rooms"),
        "pace14_market": ("forecast_pace14_market", "projected_rooms"),
    }
    if gui_model not in model_map:
        raise ValueError(f"Unsupported gui_model: {gui_model}")

    prefix, col_name = model_map[gui_model]

    asof_ts_raw = pd.to_datetime(as_of_date)
    asof_ts = asof_ts_raw.normalize()
    asof_tag = asof_ts_raw.strftime("%Y%m%d")

    csv_name = f"{prefix}_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    csv_path = OUTPUT_DIR / csv_name
    snap_all = read_daily_snapshots_for_month(hotel_id=hotel_tag, target_month=target_month)
    if not csv_path.exists():
        period = pd.Period(target_month, freq="M")
        stay_dates = pd.date_range(
            start=date(period.year, period.month, 1),
            end=date(period.year, period.month, period.days_in_month),
            freq="D",
        )
        out = pd.DataFrame(index=stay_dates)
        out["stay_date"] = out.index
        out["weekday"] = out["stay_date"].dt.weekday.astype("Int64")

        stay_dates_norm = out["stay_date"].dt.normalize()
        mask_past = stay_dates_norm < asof_ts
        if snap_all is None or snap_all.empty or not {"stay_date", "as_of_date", "rooms_oh"}.issubset(snap_all.columns):
            out["actual_rooms"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
            out["actual_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
            out["revenue_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")
            out["adr_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")
        else:
            snap = snap_all.copy()
            snap["stay_date"] = pd.to_datetime(snap["stay_date"], errors="coerce").dt.normalize()
            snap["as_of_date"] = pd.to_datetime(snap["as_of_date"], errors="coerce").dt.normalize()
            snap = snap.dropna(subset=["stay_date", "as_of_date"])
            snap = snap.sort_values(["stay_date", "as_of_date"])

            last_snap = snap.groupby("stay_date").tail(1)
            rooms_map = pd.to_numeric(last_snap.set_index("stay_date")["rooms_oh"], errors="coerce")
            actual_rooms_series = stay_dates_norm.map(rooms_map)
            actual_rooms_series = actual_rooms_series.where(mask_past)
            out["actual_rooms"] = _round_int_series(actual_rooms_series)

            if "pax_oh" in snap_all.columns:
                pax_map = pd.to_numeric(last_snap.set_index("stay_date")["pax_oh"], errors="coerce")
                actual_pax_series = stay_dates_norm.map(pax_map)
                actual_pax_series = actual_pax_series.where(mask_past)
                out["actual_pax"] = _round_int_series(actual_pax_series)
            else:
                out["actual_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")

            if "revenue_oh" in snap_all.columns:
                snap_asof = snap[snap["as_of_date"] <= asof_ts]
                if snap_asof.empty:
                    revenue_oh_now = pd.Series(np.nan, index=out.index, dtype="float")
                    rooms_oh_now = pd.Series(np.nan, index=out.index, dtype="float")
                else:
                    snap_asof = snap_asof.sort_values(["stay_date", "as_of_date"])
                    last_snap_asof = snap_asof.groupby("stay_date").tail(1)
                    revenue_map = pd.to_numeric(last_snap_asof.set_index("stay_date")["revenue_oh"], errors="coerce")
                    rooms_oh_map = pd.to_numeric(last_snap_asof.set_index("stay_date")["rooms_oh"], errors="coerce")
                    revenue_oh_now = stay_dates_norm.map(revenue_map)
                    rooms_oh_now = stay_dates_norm.map(rooms_oh_map)
                out["revenue_oh_now"] = pd.to_numeric(revenue_oh_now, errors="coerce").astype(float)
                rooms_oh_now = pd.to_numeric(rooms_oh_now, errors="coerce").astype(float)
                rooms_for_div = rooms_oh_now.replace(0, np.nan)
                out["adr_oh_now"] = (out["revenue_oh_now"] / rooms_for_div).astype(float)
            else:
                out["revenue_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")
                out["adr_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")

        out["forecast_rooms"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["forecast_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["projected_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["adr_pickup_est"] = pd.Series(np.nan, index=out.index, dtype="float")
        out["forecast_revenue"] = pd.Series(np.nan, index=out.index, dtype="float")
        apply_monthly_rounding = False
    else:
        df = pd.read_csv(csv_path, index_col=0)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        if "actual_rooms" not in df.columns:
            raise ValueError(f"{csv_path} に actual_rooms 列がありません。")
        if col_name not in df.columns:
            raise ValueError(f"{csv_path} に {col_name} 列がありません。")

        out = pd.DataFrame(index=df.index.copy())
        out["stay_date"] = out.index
        out["weekday"] = out["stay_date"].dt.weekday.astype("Int64")
        out["actual_rooms"] = _round_int_series(df["actual_rooms"])
        out["forecast_rooms"] = _round_int_series(df[col_name])
        if "actual_pax" in df.columns:
            out["actual_pax"] = _round_int_series(df["actual_pax"])
        else:
            out["actual_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        if "projected_pax" in df.columns:
            out["forecast_pax"] = _round_int_series(df["projected_pax"])
        elif "forecast_pax" in df.columns:
            out["forecast_pax"] = _round_int_series(df["forecast_pax"])
        else:
            out["forecast_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        if "projected_pax" in df.columns:
            out["projected_pax"] = _round_int_series(df["projected_pax"])
        else:
            out["projected_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        if "revenue_oh_now" in df.columns:
            out["revenue_oh_now"] = pd.to_numeric(df["revenue_oh_now"], errors="coerce").astype(float)
        else:
            out["revenue_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")
        if "adr_oh_now" in df.columns:
            out["adr_oh_now"] = pd.to_numeric(df["adr_oh_now"], errors="coerce").astype(float)
        else:
            out["adr_oh_now"] = pd.Series(np.nan, index=out.index, dtype="float")
        if "adr_pickup_est" in df.columns:
            out["adr_pickup_est"] = pd.to_numeric(df["adr_pickup_est"], errors="coerce").astype(float)
        else:
            out["adr_pickup_est"] = pd.Series(np.nan, index=out.index, dtype="float")
        if "forecast_revenue" in df.columns:
            out["forecast_revenue"] = pd.to_numeric(df["forecast_revenue"], errors="coerce").astype(float)
        else:
            out["forecast_revenue"] = pd.Series(np.nan, index=out.index, dtype="float")

    if snap_all is None or snap_all.empty or not {"stay_date", "as_of_date", "rooms_oh"}.issubset(snap_all.columns):
        out["asof_oh_rooms"] = _round_int_series(out["actual_rooms"])
        out["asof_oh_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    else:
        snap = snap_all.copy()
        snap["stay_date"] = pd.to_datetime(snap["stay_date"], errors="coerce").dt.normalize()
        snap["as_of_date"] = pd.to_datetime(snap["as_of_date"], errors="coerce").dt.normalize()
        snap = snap.dropna(subset=["stay_date", "as_of_date"])

        snap_asof = snap[snap["as_of_date"] <= asof_ts]
        if snap_asof.empty:
            asof_oh_series = pd.Series(0.0, index=out.index)
            out["asof_oh_rooms"] = _round_int_series(asof_oh_series)
        else:
            snap_asof = snap_asof.sort_values(["stay_date", "as_of_date"])
            last_snap = snap_asof.groupby("stay_date").tail(1)
            oh_map = pd.to_numeric(last_snap.set_index("stay_date")["rooms_oh"], errors="coerce")

            stay_dates_norm = out["stay_date"].dt.normalize()
            asof_oh_series = stay_dates_norm.map(oh_map)

            mask_past = stay_dates_norm < asof_ts
            mask_fallback = asof_oh_series.isna() & mask_past & out["actual_rooms"].notna()
            asof_oh_series.loc[mask_fallback] = out.loc[mask_fallback, "actual_rooms"].to_numpy()
            asof_oh_series = asof_oh_series.fillna(0.0)
            out["asof_oh_rooms"] = _round_int_series(asof_oh_series)

        if "pax_oh" not in snap_all.columns:
            logging.warning("daily_snapshots に pax_oh 列がありません。asof_oh_pax は NaN で継続します。")
            out["asof_oh_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        else:
            snap_asof = snap[snap["as_of_date"] <= asof_ts]
            if snap_asof.empty:
                asof_oh_pax_series = pd.Series(pd.NA, index=out.index, dtype="float")
            else:
                snap_asof = snap_asof.sort_values(["stay_date", "as_of_date"])
                last_snap = snap_asof.groupby("stay_date").tail(1)
                pax_oh_map = pd.to_numeric(last_snap.set_index("stay_date")["pax_oh"], errors="coerce")

                stay_dates_norm = out["stay_date"].dt.normalize()
                asof_oh_pax_series = stay_dates_norm.map(pax_oh_map)

                mask_past = stay_dates_norm < asof_ts
                mask_fallback = asof_oh_pax_series.isna() & mask_past & out["actual_pax"].notna()
                asof_oh_pax_series.loc[mask_fallback] = out.loc[mask_fallback, "actual_pax"].to_numpy()

            out["asof_oh_pax"] = _round_int_series(asof_oh_pax_series)

    out["diff_rooms_vs_actual"] = out["forecast_rooms"] - out["actual_rooms"]
    denom_actual = out["actual_rooms"].replace(0, pd.NA)
    out["diff_pct_vs_actual"] = (out["diff_rooms_vs_actual"] / denom_actual * 100.0).astype(float)
    out["pickup_expected_from_asof"] = out["forecast_rooms"] - out["asof_oh_rooms"]

    out["diff_rooms"] = out["diff_rooms_vs_actual"]
    out["diff_pct"] = out["diff_pct_vs_actual"]

    out["occ_actual_pct"] = (out["actual_rooms"] / cap * 100.0).astype(float)
    out["occ_asof_pct"] = (out["asof_oh_rooms"] / cap * 100.0).astype(float)
    out["occ_forecast_pct"] = (out["forecast_rooms"] / cap * 100.0).astype(float)
    denom_forecast_rooms = out["forecast_rooms"].replace(0, pd.NA)
    out["forecast_adr"] = (out["forecast_revenue"] / denom_forecast_rooms).astype(float)
    denom_cap = pd.Series(cap, index=out.index, dtype="float")
    denom_cap = denom_cap.replace(0, pd.NA)
    out["forecast_revpar"] = (out["forecast_revenue"] / denom_cap).astype(float)

    num_days = out["stay_date"].nunique()

    actual_total = out["actual_rooms"].fillna(0).sum()
    asof_total = out["asof_oh_rooms"].fillna(0).sum()
    forecast_total = out["forecast_rooms"].fillna(0).sum()
    actual_pax_total = out["actual_pax"].fillna(0).sum()
    forecast_pax_total = out["forecast_pax"].fillna(0).sum()
    asof_pax_total = out["asof_oh_pax"].fillna(0).sum()
    revenue_oh_total = out["revenue_oh_now"].fillna(0).sum()
    forecast_revenue_total = out["forecast_revenue"].fillna(0).sum()

    diff_total_vs_actual = forecast_total - actual_total
    if actual_total > 0:
        diff_total_pct_vs_actual = diff_total_vs_actual / actual_total * 100.0
    else:
        diff_total_pct_vs_actual = float("nan")

    pickup_total_from_asof = forecast_total - asof_total

    if num_days > 0:
        occ_actual_month = actual_total / (cap * num_days) * 100.0
        occ_asof_month = asof_total / (cap * num_days) * 100.0
        occ_forecast_month = forecast_total / (cap * num_days) * 100.0
    else:
        occ_actual_month = float("nan")
        occ_asof_month = float("nan")
        occ_forecast_month = float("nan")

    denom_asof_total = asof_total if asof_total > 0 else float("nan")
    denom_forecast_total = forecast_total if forecast_total > 0 else float("nan")
    denom_cap_total = cap * num_days if cap > 0 and num_days > 0 else float("nan")
    adr_oh_total = revenue_oh_total / denom_asof_total
    forecast_adr_total = forecast_revenue_total / denom_forecast_total
    forecast_revpar_total = forecast_revenue_total / denom_cap_total
    if pickup_total_from_asof > 0:
        adr_pickup_total = (forecast_revenue_total - revenue_oh_total) / pickup_total_from_asof
    else:
        adr_pickup_total = pd.NA

    out["actual_rooms_display"] = out["actual_rooms"].copy()
    out["asof_oh_rooms_display"] = out["asof_oh_rooms"].copy()
    out["forecast_rooms_display"] = out["forecast_rooms"].copy()
    out["actual_pax_display"] = out["actual_pax"].copy()
    out["forecast_pax_display"] = out["forecast_pax"].copy()
    out["asof_oh_pax_display"] = out["asof_oh_pax"].copy()
    out["forecast_revenue_display"] = out["forecast_revenue"].copy()

    apply_monthly_rounding = apply_monthly_rounding and monthly_rounding.should_apply_monthly_rounding(
        target_month,
        asof_ts,
        out["stay_date"],
    )

    if apply_monthly_rounding:
        forecast_total_goal = monthly_rounding.round_total_goal(forecast_total, round_rooms_unit)
        reconciled_rooms, adjusted_rooms_total = monthly_rounding.apply_remainder_rounding(
            out["forecast_rooms"],
            out["stay_date"],
            asof_ts=asof_ts,
            target_yyyymm=target_month,
            goal_total=float(forecast_total_goal),
            cap_value=cap,
        )
        out["forecast_rooms_display"] = reconciled_rooms
        forecast_rooms_total_display = adjusted_rooms_total

        if out["forecast_pax"].notna().any():
            if pax_capacity is None:
                pax_capacity = run_forecast_batch.infer_pax_capacity_p99(hotel_tag, asof_ts)
            forecast_pax_total_goal = monthly_rounding.round_total_goal(forecast_pax_total, round_pax_unit)
            reconciled_pax, adjusted_pax_total = monthly_rounding.apply_remainder_rounding(
                out["forecast_pax"],
                out["stay_date"],
                asof_ts=asof_ts,
                target_yyyymm=target_month,
                goal_total=float(forecast_pax_total_goal),
                cap_value=pax_capacity,
            )
            out["forecast_pax_display"] = reconciled_pax
            forecast_pax_total_display = adjusted_pax_total
        else:
            forecast_pax_total_display = float(out["forecast_pax_display"].fillna(0).sum())
    else:
        forecast_rooms_total_display = float(out["forecast_rooms_display"].fillna(0).sum())
        forecast_pax_total_display = float(out["forecast_pax_display"].fillna(0).sum())

    forecast_revenue_display_total = forecast_revenue_total
    if apply_monthly_rounding:
        forecast_revenue_total_goal = monthly_rounding.round_total_goal(
            forecast_revenue_total,
            round_revenue_unit,
        )
        reconciled_revenue, adjusted_revenue_total = monthly_rounding.apply_remainder_rounding(
            out["forecast_revenue"],
            out["stay_date"],
            asof_ts=asof_ts,
            target_yyyymm=target_month,
            goal_total=float(forecast_revenue_total_goal),
            cap_value=None,
        )
        out.loc[:, "forecast_revenue_display"] = reconciled_revenue
        forecast_revenue_display_total = adjusted_revenue_total

    out["pickup_expected_from_asof_display"] = out["forecast_rooms_display"] - out["asof_oh_rooms_display"]
    out["occ_forecast_pct_display"] = (out["forecast_rooms_display"] / cap * 100.0).astype(float)
    denom_forecast_display = out["forecast_rooms_display"].replace(0, pd.NA)
    out["forecast_adr_display"] = (out["forecast_revenue_display"] / denom_forecast_display).astype(float)
    denom_cap = pd.Series(cap, index=out.index, dtype="float").replace(0, pd.NA)
    out["forecast_revpar_display"] = (out["forecast_revenue_display"] / denom_cap).astype(float)

    forecast_rooms_total_display = float(forecast_rooms_total_display)
    forecast_pax_total_display = float(forecast_pax_total_display)

    pickup_total_display = forecast_rooms_total_display - asof_total
    if num_days > 0:
        occ_forecast_month_display = forecast_rooms_total_display / (cap * num_days) * 100.0
    else:
        occ_forecast_month_display = float("nan")

    denom_forecast_total_display = forecast_rooms_total_display if forecast_rooms_total_display > 0 else float("nan")
    forecast_adr_total_display = forecast_revenue_display_total / denom_forecast_total_display
    forecast_revpar_total_display = forecast_revenue_display_total / denom_cap_total

    total_row = {
        "stay_date": pd.NaT,
        "weekday": pd.NA,
        "actual_rooms": actual_total,
        "asof_oh_rooms": asof_total,
        "forecast_rooms": forecast_total,
        "actual_pax": actual_pax_total,
        "forecast_pax": forecast_pax_total,
        "asof_oh_pax": asof_pax_total,
        "projected_pax": pd.NA,
        "revenue_oh_now": revenue_oh_total,
        "adr_oh_now": adr_oh_total,
        "adr_pickup_est": adr_pickup_total,
        "forecast_revenue": forecast_revenue_total,
        "forecast_adr": forecast_adr_total,
        "forecast_revpar": forecast_revpar_total,
        "actual_rooms_display": actual_total,
        "asof_oh_rooms_display": asof_total,
        "forecast_rooms_display": forecast_rooms_total_display,
        "actual_pax_display": actual_pax_total,
        "forecast_pax_display": forecast_pax_total_display,
        "asof_oh_pax_display": asof_pax_total,
        "forecast_revenue_display": forecast_revenue_display_total,
        "diff_rooms_vs_actual": diff_total_vs_actual,
        "diff_pct_vs_actual": diff_total_pct_vs_actual,
        "pickup_expected_from_asof": pickup_total_from_asof,
        "pickup_expected_from_asof_display": pickup_total_display,
        "diff_rooms": diff_total_vs_actual,
        "diff_pct": diff_total_pct_vs_actual,
        "occ_actual_pct": occ_actual_month,
        "occ_asof_pct": occ_asof_month,
        "occ_forecast_pct": occ_forecast_month,
        "occ_forecast_pct_display": occ_forecast_month_display,
        "forecast_adr_display": forecast_adr_total_display,
        "forecast_revpar_display": forecast_revpar_total_display,
    }

    out = out.reset_index(drop=True)

    def _missing_value_for_dtype(dtype: pd.api.extensions.ExtensionDtype | np.dtype) -> object:
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return pd.NaT
        if pd.api.types.is_float_dtype(dtype):
            return np.nan
        if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_boolean_dtype(dtype):
            return pd.NA
        if pd.api.types.is_string_dtype(dtype):
            return ""
        return pd.NA

    missing_row = {col: _missing_value_for_dtype(out[col].dtype) for col in out.columns}
    missing_row.update(total_row)

    def _build_total_row_df(
        base_df: pd.DataFrame,
        row_values: dict[str, object],
    ) -> pd.DataFrame:
        series_by_col: dict[str, pd.Series] = {}
        for col in base_df.columns:
            value = row_values.get(col, _missing_value_for_dtype(base_df[col].dtype))
            dtype = base_df[col].dtype
            try:
                series = pd.Series([value], dtype=dtype)
            except (TypeError, ValueError):
                try:
                    series = pd.Series([value]).astype(dtype)
                except (TypeError, ValueError):
                    series = pd.Series([value])
            series_by_col[col] = series
        total_row_df = pd.concat(series_by_col, axis=1)
        return total_row_df[base_df.columns]

    total_row_df = _build_total_row_df(out, missing_row)
    out = pd.concat([out, total_row_df], ignore_index=True)

    column_order = [
        "stay_date",
        "weekday",
        "actual_rooms",
        "asof_oh_rooms",
        "forecast_rooms",
        "actual_pax",
        "forecast_pax",
        "asof_oh_pax",
        "projected_pax",
        "revenue_oh_now",
        "adr_oh_now",
        "adr_pickup_est",
        "forecast_revenue",
        "forecast_adr",
        "forecast_revpar",
        "actual_rooms_display",
        "asof_oh_rooms_display",
        "forecast_rooms_display",
        "actual_pax_display",
        "forecast_pax_display",
        "asof_oh_pax_display",
        "forecast_revenue_display",
        "diff_rooms_vs_actual",
        "diff_pct_vs_actual",
        "pickup_expected_from_asof",
        "pickup_expected_from_asof_display",
        "diff_rooms",
        "diff_pct",
        "occ_actual_pct",
        "occ_asof_pct",
        "occ_forecast_pct",
        "occ_forecast_pct_display",
        "forecast_adr_display",
        "forecast_revpar_display",
    ]

    out = out[column_order]

    return out


def get_daily_forecast_ly_summary(
    hotel_tag: str,
    target_month: str,
    capacity: Optional[float] = None,
) -> dict[str, float | None]:
    try:
        period = pd.Period(target_month, freq="M")
    except Exception:
        return {
            "rooms": None,
            "pax": None,
            "revenue": None,
            "adr": None,
            "dor": None,
            "revpar": None,
        }

    ly_period = period - 12
    ly_month = f"{ly_period.year}{ly_period.month:02d}"

    def _sum_act(value_type: str) -> float | None:
        try:
            df = run_forecast_batch.load_lt_csv(ly_month, hotel_tag=hotel_tag, value_type=value_type)
        except FileNotFoundError:
            return None
        if df.empty:
            return None
        act_col = None
        for col in df.columns:
            try:
                if int(col) == -1:
                    act_col = col
                    break
            except Exception:
                continue
        if act_col is None:
            return None
        series = pd.to_numeric(df[act_col], errors="coerce")
        series = series[series.notna()]
        if series.empty:
            return None
        return float(series.sum())

    rooms_total = _sum_act("rooms")
    pax_total = _sum_act("pax")
    revenue_total = _sum_act("revenue")

    adr = None
    dor = None
    revpar = None
    if rooms_total is not None and rooms_total > 0:
        if pax_total is not None:
            dor = pax_total / rooms_total
        if revenue_total is not None:
            adr = revenue_total / rooms_total

    if revenue_total is not None:
        cap = _get_capacity(hotel_tag, capacity)
        days = monthrange(ly_period.year, ly_period.month)[1]
        denom = cap * days if cap > 0 and days > 0 else None
        if denom:
            revpar = revenue_total / denom

    return {
        "rooms": rooms_total,
        "pax": pax_total,
        "revenue": revenue_total,
        "adr": adr,
        "dor": dor,
        "revpar": revpar,
    }


def get_model_evaluation_table(hotel_tag: str) -> pd.DataFrame:
    """
    評価CSVを読み込み、月別×モデル + モデルTOTAL の評価指標を返す。

    - mean_error_pct : 誤差率の平均（バイアス）
    - mae_pct        : 誤差率絶対値の平均
    - rmse_pct       : 誤差率の二乗平均平方根
    - n_samples      : 集計に使ったサンプル数（ASOF数）

    備考:
    - run_evaluate_forecasts.py が出力する
        evaluation_{hotel_tag}_multi.csv   : 月次サマリ
        evaluation_{hotel_tag}_detail.csv  : ASOF明細
      を利用する。
    """

    summary_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_multi.csv"
    detail_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"evaluation summary csv not found: {summary_path}")

    # --- 月次サマリ (mean_error_pct / mae_pct) 読み込み ---
    df_summary = pd.read_csv(summary_path)

    required_summary_cols = ["target_month", "model", "mean_error_pct", "mae_pct"]
    missing_sum = [c for c in required_summary_cols if c not in df_summary.columns]
    if missing_sum:
        raise ValueError(f"{summary_path} に {', '.join(missing_sum)} 列がありません。")

    df_summary = df_summary.copy()
    df_summary["target_month"] = df_summary["target_month"].astype(str)
    df_summary["model"] = df_summary["model"].astype(str)
    df_summary["mean_error_pct"] = pd.to_numeric(df_summary["mean_error_pct"], errors="coerce")
    df_summary["mae_pct"] = pd.to_numeric(df_summary["mae_pct"], errors="coerce")

    # --- 明細から rmse_pct / n_samples を計算 ---
    if detail_path.exists():
        df_detail = pd.read_csv(detail_path)

        required_detail_cols = ["target_month", "model", "error_pct", "abs_error_pct"]
        missing_det = [c for c in required_detail_cols if c not in df_detail.columns]
        if missing_det:
            raise ValueError(f"{detail_path} に {', '.join(missing_det)} 列がありません。")

        df_detail = df_detail.copy()
        df_detail["target_month"] = df_detail["target_month"].astype(str)
        df_detail["model"] = df_detail["model"].astype(str)
        df_detail["error_pct"] = pd.to_numeric(df_detail["error_pct"], errors="coerce")
        df_detail["abs_error_pct"] = pd.to_numeric(df_detail["abs_error_pct"], errors="coerce")

        def _agg_group(g: pd.DataFrame) -> dict:
            err = g["error_pct"].dropna()
            n = int(err.count())
            rmse = err.pow(2).mean() ** 0.5 if not err.empty else float("nan")
            return {
                "rmse_pct": rmse,
                "n_samples": n,
            }

        # 月別×モデルの rmse_pct / n_samples
        records = []
        for (tm, model), g in df_detail.groupby(["target_month", "model"]):
            agg = _agg_group(g)
            records.append({"target_month": tm, "model": model, **agg})

        df_rmse = pd.DataFrame(
            records,
            columns=["target_month", "model", "rmse_pct", "n_samples"],
        )

        # サマリと結合
        df_merged = pd.merge(
            df_summary,
            df_rmse,
            on=["target_month", "model"],
            how="left",
        )

        # モデル別 TOTAL 行（全期間まとめ）
        total_records = []
        for model, g in df_detail.groupby("model"):
            agg = _agg_group(g)
            # TOTAL については mean_error_pct / mae_pct も detail から再計算
            err = g["error_pct"].dropna()
            err_abs = g["abs_error_pct"].dropna()
            mean_error = err.mean() if not err.empty else float("nan")
            mae = err_abs.mean() if not err_abs.empty else float("nan")

            total_records.append(
                {
                    "target_month": "TOTAL",
                    "model": model,
                    "mean_error_pct": mean_error,
                    "mae_pct": mae,
                    "rmse_pct": agg["rmse_pct"],
                    "n_samples": agg["n_samples"],
                }
            )

        df_total = pd.DataFrame(
            total_records,
            columns=[
                "target_month",
                "model",
                "mean_error_pct",
                "mae_pct",
                "rmse_pct",
                "n_samples",
            ],
        )

        df_total = _drop_all_na_columns(df_total)
        out = pd.concat([df_merged, df_total], ignore_index=True)

    else:
        # 明細が無い場合は rmse/n_samples は NaN のまま
        df_summary["rmse_pct"] = float("nan")
        df_summary["n_samples"] = float("nan")
        out = df_summary

    # 並び替え
    def _sort_target_month(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            # "TOTAL" などは最後に回す
            return 999999

    out["target_month"] = out["target_month"].astype(str)
    out["__sort_month"] = out["target_month"].map(_sort_target_month)
    out.sort_values(by=["model", "__sort_month"], inplace=True)
    out.drop(columns=["__sort_month"], inplace=True)

    # 列順を固定
    out = out[
        [
            "target_month",
            "model",
            "mean_error_pct",
            "mae_pct",
            "rmse_pct",
            "n_samples",
        ]
    ]

    return out


def get_best_model_for_month(hotel_tag: str, target_month: str) -> Optional[dict]:
    """
    指定ホテル・対象月について、評価テーブルから MAE が最小のモデル情報を返す。

    戻り値の例:
        {
            "model": "recent90w",
            "mean_error_pct": 1.23,
            "mae_pct": 8.76,
            "rmse_pct": 10.11,
            "n_samples": 24,
        }

    評価CSVが存在しない / 対象月の行が無い / mae_pct がすべてNaN の場合は None を返す。
    """
    # 1. 評価テーブル読み込み
    try:
        df = get_model_evaluation_table(hotel_tag)
    except FileNotFoundError:
        return None

    if df.empty:
        return None

    # 2. 対象月でフィルタ
    tm = str(target_month)
    df_month = df[df["target_month"] == tm].copy()
    if df_month.empty:
        return None

    # 3. mae_pct を数値化して、NaN を落とす
    df_month["mae_pct"] = pd.to_numeric(df_month["mae_pct"], errors="coerce")
    df_month = df_month.dropna(subset=["mae_pct"])
    if df_month.empty:
        return None

    # 4. MAE 最小の行を取得
    best_row = df_month.loc[df_month["mae_pct"].idxmin()]

    def _to_float(value) -> float:
        try:
            v = float(value)
        except Exception:
            return float("nan")
        return v

    def _to_int(value) -> int:
        try:
            v = int(value)
        except Exception:
            return 0
        return v

    return {
        "model": str(best_row.get("model", "")),
        "mean_error_pct": _to_float(best_row.get("mean_error_pct")),
        "mae_pct": _to_float(best_row.get("mae_pct")),
        "rmse_pct": _to_float(best_row.get("rmse_pct")),
        "n_samples": _to_int(best_row.get("n_samples")),
    }


def _get_recent_months_before(target_month: str, window_months: int) -> list[str]:
    try:
        period = pd.Period(str(target_month), freq="M")
    except Exception:
        return []

    months: list[str] = []
    for offset in range(1, window_months + 1):
        p = period - offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_best_model_stats_for_recent_months(hotel: str, ref_month: str, window_months: int) -> dict | None:
    try:
        df = get_model_evaluation_table(hotel)
    except Exception:
        return None

    if df is None or df.empty:
        return None

    df = df.copy()
    df = df[df["target_month"] != "TOTAL"]
    df = df[df["mae_pct"].notna()]
    df = df[df["rmse_pct"].notna()]
    df = df[df["n_samples"].notna()]

    df["target_month_int"] = pd.to_numeric(df["target_month"].astype(str), errors="coerce").astype("Int64")

    ref_int = pd.to_numeric(str(ref_month), errors="coerce")
    if pd.isna(ref_int):
        return None

    df = df[df["target_month_int"] < int(ref_int)]
    if df.empty:
        return None

    recent_months = _get_recent_months_before(str(ref_month), window_months)
    if not recent_months:
        return None

    df = df[df["target_month"].isin(recent_months)]
    if df.empty:
        return None

    candidates = []
    for model, g in df.groupby("model"):
        w = g["n_samples"].fillna(0)
        w_total = float(w.sum())
        if w_total <= 0:
            continue

        mean_error = (g["mean_error_pct"] * w).sum() / w_total
        mae = (g["mae_pct"] * w).sum() / w_total
        rmse = (g["rmse_pct"] * w).sum() / w_total

        candidates.append(
            {
                "model": str(model),
                "mean_error_pct": float(mean_error),
                "mae_pct": float(mae),
                "rmse_pct": float(rmse),
                "n_samples": int(w_total),
                "ref_month": str(ref_month),
                "window_months": len(set(recent_months)),
            }
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: (abs(x["mae_pct"]), abs(x["rmse_pct"])))
    return candidates[0]


def _target_month_to_int(value: object) -> int:
    """target_month を int に正規化する。"""

    try:
        return int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid target_month value: {value}")


def _filter_by_target_month(df: pd.DataFrame, from_ym: Optional[str], to_ym: Optional[str]) -> pd.DataFrame:
    df = df.copy()
    df["target_month_int"] = df["target_month"].map(_target_month_to_int)

    mask = pd.Series([True] * len(df))
    if from_ym is not None:
        mask &= df["target_month_int"] >= _target_month_to_int(from_ym)
    if to_ym is not None:
        mask &= df["target_month_int"] <= _target_month_to_int(to_ym)

    return df.loc[mask].copy()


def get_eval_overview_by_asof(
    hotel_tag: str,
    from_ym: str | None = None,
    to_ym: str | None = None,
    force_reload: bool = False,
) -> pd.DataFrame:
    """
    モデル×ASOFタイプ別の期間トータル評価指標を返す。

    - 入力: evaluation_{hotel_tag}_detail.csv
    - 期間フィルタ:
        * from_ym, to_ym は "YYYYMM" 形式の文字列または None。
        * target_month を int 化して between でフィルタする。
        * None の場合は制限なし。
    - 出力列:
        ["model", "asof_type",
         "mean_error_pct",  # error_pct の平均
         "mae_pct",         # abs_error_pct の平均
         "rmse_pct",        # sqrt(mean(error_pct^2))
         "n_samples"]       # サンプル数
    - 並び順:
        model 昇順, asof_type 昇順。
    """

    df_detail = _get_evaluation_detail_df(hotel_tag, force_reload=force_reload)
    df_detail = _filter_by_target_month(df_detail, from_ym=from_ym, to_ym=to_ym)

    records = []
    for (model, asof_type), g in df_detail.groupby(["model", "asof_type"]):
        err = g["error_pct"].dropna()
        err_abs = g["abs_error_pct"].dropna()
        mean_error = err.mean() if not err.empty else float("nan")
        mae = err_abs.mean() if not err_abs.empty else float("nan")
        rmse = err.pow(2).mean() ** 0.5 if not err.empty else float("nan")
        n = int(err.count())

        records.append(
            {
                "model": model,
                "asof_type": asof_type,
                "mean_error_pct": mean_error,
                "mae_pct": mae,
                "rmse_pct": rmse,
                "n_samples": n,
            }
        )

    out = pd.DataFrame(
        records,
        columns=[
            "model",
            "asof_type",
            "mean_error_pct",
            "mae_pct",
            "rmse_pct",
            "n_samples",
        ],
    )

    out.sort_values(by=["model", "asof_type"], inplace=True)

    return out


def get_eval_monthly_by_asof(
    hotel_tag: str,
    from_ym: str | None = None,
    to_ym: str | None = None,
    asof_types: list[str] | None = None,
    models: list[str] | None = None,
    force_reload: bool = False,
) -> pd.DataFrame:
    """
    月別×ASOF×モデルの評価ログを返す（1行=1 target_month×asof_type×model）。

    - 入力: evaluation_{hotel_tag}_detail.csv
    - 期間フィルタ:
        from_ym/to_ym は get_eval_overview_by_asof と同じ。
    - asof_types フィルタ:
        None の場合は全て、リスト指定時はその asof_type のみ残す。
    - models フィルタ:
        None の場合は全て、リスト指定時はその model のみ残す。
    - 出力列:
        ["target_month", "asof_type", "model",
         "error_pct", "abs_error_pct"]
      必要に応じて GUI 側で mean_error_pct / mae_pct として解釈する。
    - 並び順:
        target_month 昇順, asof_type 昇順, model 昇順。
    """

    df_detail = _get_evaluation_detail_df(hotel_tag, force_reload=force_reload)
    df_detail = _filter_by_target_month(df_detail, from_ym=from_ym, to_ym=to_ym)

    if asof_types is not None:
        df_detail = df_detail[df_detail["asof_type"].isin(asof_types)]
    if models is not None:
        df_detail = df_detail[df_detail["model"].isin(models)]

    df_detail.sort_values(by=["target_month_int", "asof_type", "model"], inplace=True)

    return df_detail[["target_month", "asof_type", "model", "error_pct", "abs_error_pct"]].reset_index(drop=True)


def run_build_lt_data_for_gui(
    hotel_tag: str,
    target_months: list[str],
    source: str = "daily_snapshots",
) -> None:
    """
    Tkinter GUI から LT_DATA 生成バッチを実行するための薄いラッパー。

    hotel_tag ごとに config.HOTEL_CONFIG で定義された時系列Excelを読み込み、
    run_build_lt_csv.run_build_lt_for_gui() を呼び出す。

    source: "timeseries" または "daily_snapshots" を指定する。デフォルトは "daily_snapshots"。
    """

    if not target_months:
        return

    try:
        run_build_lt_csv.run_build_lt_for_gui(
            hotel_tag=hotel_tag,
            target_months=target_months,
            source=source,
        )
    except Exception:
        raise


def get_all_target_months_for_lt_from_daily_snapshots(hotel_tag: str) -> list[str]:
    months = list_stay_months_from_daily_snapshots(hotel_tag, output_dir=OUTPUT_DIR)
    if not months:
        raise ValueError("daily snapshots が存在しないため全期間LT_DATAを生成できません")
    return months


def run_build_lt_data_all_for_gui(hotel_tag: str, source: str = "daily_snapshots") -> list[str]:
    months = get_all_target_months_for_lt_from_daily_snapshots(hotel_tag)
    run_build_lt_data_for_gui(hotel_tag, months, source=source)
    return months


def _calculate_asof_min(asof_max: pd.Timestamp | None, buffer_days: int) -> pd.Timestamp | None:
    if asof_max is None or buffer_days <= 0:
        return None
    return asof_max - pd.Timedelta(days=buffer_days - 1)


def run_daily_snapshots_for_gui(
    hotel_tag: str,
    mode: str = "FAST",
    target_months: list[str] | None = None,
    buffer_days: int = 14,
    lookahead_days: int = 120,
) -> dict[str, object]:
    """Tkinter GUI から daily snapshots 更新を実行するための薄いラッパー。"""

    raw_inventory = _build_raw_inventory_or_raise(hotel_tag)
    layout = HOTEL_CONFIG[hotel_tag].get("layout", "auto")

    if isinstance(mode, (list, tuple, set, dict)):
        raise ValueError("mode must be a string; did you swap positional arguments for mode and target_months?")

    adapter_type = raw_inventory.adapter_type
    if adapter_type != "nface":
        raise ValueError(f"{hotel_tag}: adapter_type '{adapter_type}' is not supported (nface only)")

    mode_normalized = mode.upper()
    if mode_normalized not in {"FAST", "FULL_MONTHS", "FULL_ALL", "RANGE_REBUILD"}:
        raise ValueError(f"Invalid mode: {mode}")

    validated_target_months: list[str] | None = None
    if mode_normalized in {"FAST", "FULL_MONTHS"}:
        if not target_months:
            raise ValueError("target_months must be a non-empty list for FAST or FULL_MONTHS mode")
        validated_target_months = []
        for ym in target_months:
            try:
                period = pd.Period(f"{ym[:4]}-{ym[4:]}", freq="M")
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid target_month format: {ym}") from exc
            validated_target_months.append(period.strftime("%Y%m"))

    glob_pattern = "*.xls*"
    recursive = raw_inventory.include_subfolders

    asof_min = None
    plan: dict[str, object] = {"mode": mode_normalized}
    if mode_normalized == "FAST":
        latest_asof = get_latest_asof_date(hotel_tag, output_dir=OUTPUT_DIR)
        asof_min = _calculate_asof_min(latest_asof, buffer_days)
        plan["asof_min"] = asof_min
    elif mode_normalized == "RANGE_REBUILD":
        plan = _build_range_rebuild_plan(
            hotel_tag,
            buffer_days=buffer_days,
            lookahead_days=lookahead_days,
            raw_inventory=raw_inventory,
        )
        asof_min = plan["asof_min"]

    logging.info(
        "daily snapshots build: mode=%s, hotel_tag=%s, target_months=%s, buffer_days=%s, asof_min=%s",
        mode_normalized,
        hotel_tag,
        validated_target_months,
        buffer_days,
        asof_min,
    )

    try:
        if mode_normalized == "FAST":
            build_daily_snapshots_fast(
                input_dir=raw_inventory.raw_root_dir,
                hotel_id=hotel_tag,
                target_months=validated_target_months or [],
                asof_min=asof_min,
                asof_max=None,
                layout=layout,
                output_dir=OUTPUT_DIR,
                glob=glob_pattern,
                recursive=recursive,
            )
        elif mode_normalized == "FULL_MONTHS":
            build_daily_snapshots_full_months(
                input_dir=raw_inventory.raw_root_dir,
                hotel_id=hotel_tag,
                target_months=validated_target_months or [],
                layout=layout,
                output_dir=OUTPUT_DIR,
                glob=glob_pattern,
                recursive=recursive,
            )
        elif mode_normalized == "FULL_ALL":
            build_daily_snapshots_full_all(
                input_dir=raw_inventory.raw_root_dir,
                hotel_id=hotel_tag,
                layout=layout,
                output_dir=OUTPUT_DIR,
                glob=glob_pattern,
                recursive=recursive,
            )
        else:
            build_daily_snapshots_from_folder_partial(
                input_dir=raw_inventory.raw_root_dir,
                hotel_id=hotel_tag,
                target_months=plan["stay_months"],
                asof_min=plan["asof_min"],
                asof_max=plan["asof_max"],
                stay_min=plan["stay_min"],
                stay_max=plan["stay_max"],
                layout=layout,
                output_dir=OUTPUT_DIR,
                glob=glob_pattern,
                recursive=recursive,
            )
            rebuild_asof_dates_from_daily_snapshots(hotel_tag, output_dir=OUTPUT_DIR)
    except Exception:
        logging.exception("Failed to build daily snapshots for GUI: hotel_tag=%s", hotel_tag)
        raise

    logging.info("Completed daily snapshots build: hotel_tag=%s", hotel_tag)
    return plan


def run_full_evaluation_for_gui_range(
    hotel_tag: str,
    start_yyyymm: str,
    end_yyyymm: str,
) -> tuple[Path, Path]:
    months = generate_month_range(start_yyyymm, end_yyyymm)
    detail_path, summary_path = run_full_evaluation_for_gui(
        hotel_tag=hotel_tag,
        target_months=months,
    )
    return detail_path, summary_path


def run_missing_check_for_gui(hotel_tag: str) -> Path:
    return run_missing_report(hotel_tag, mode="ops")


def run_missing_audit_for_gui(hotel_tag: str) -> Path:
    return run_missing_report(hotel_tag, mode="audit")


def run_missing_report(hotel_tag: str, *, mode: str = "ops") -> Path:
    daily_path = get_daily_snapshots_path(hotel_tag)
    return build_missing_report(
        hotel_tag,
        daily_path,
        mode=mode,
        asof_window_days=180,
        lt_days=120,
        forward_months=3,
        output_dir=OUTPUT_DIR,
    )


def run_import_missing_only(hotel_tag: str) -> dict[str, object]:
    daily_snapshots_path = get_daily_snapshots_path(hotel_tag)
    layout = "auto"

    report_path = run_missing_report(hotel_tag, mode="ops")
    try:
        df_report = pd.read_csv(report_path, dtype=str)
        kind_series = df_report.get("kind", pd.Series([], dtype=str))
    except Exception:
        kind_series = pd.Series([], dtype=str)

    asof_missing_count = int((kind_series == "asof_missing").sum())

    missing_pairs, raw_index, raw_inventory, snapshot_pairs = find_unconverted_raw_pairs(
        hotel_tag,
        daily_snapshots_path,
    )
    total_raw_pairs = len(raw_index.pairs)
    matched_pairs = len(raw_index.pairs & snapshot_pairs)
    coverage_ratio = matched_pairs / total_raw_pairs if total_raw_pairs else 1.0

    if coverage_ratio < 0.30:
        raise ValueError(
            f"{hotel_tag}: daily snapshot coverage {coverage_ratio:.1%} below stop threshold; check {daily_snapshots_path}",
        )

    coverage_warning = coverage_ratio < 0.80
    if coverage_warning:
        logging.warning(
            "%s: daily snapshot coverage %s below warn threshold (raw=%s, matched=%s)",
            hotel_tag,
            f"{coverage_ratio:.1%}",
            total_raw_pairs,
            matched_pairs,
        )

    result: dict[str, object] = {
        "processed_pairs": 0,
        "skipped_missing_raw_pairs": 0,
        "skipped_parse_fail_files": 0,
        "updated_pairs": [],
        "skipped_asof_missing_rows": asof_missing_count,
    }

    if not missing_pairs:
        result["message"] = "no unconverted raw pairs"
        result["missing_report_path"] = report_path
        if coverage_warning:
            result["coverage_warning"] = coverage_ratio
        return result

    glob_pattern = "**/*.xls*" if raw_inventory.include_subfolders else "*.xls*"

    build_result = build_daily_snapshots_for_pairs(
        input_dir=raw_inventory.raw_root_dir,
        hotel_id=hotel_tag,
        pairs=missing_pairs,
        layout=layout,
        output_dir=OUTPUT_DIR,
        glob=glob_pattern,
    )
    result.update(build_result)
    result["message"] = "imported missing raw keys"

    latest_report = run_missing_report(hotel_tag, mode="ops")
    result["missing_report_path"] = latest_report
    result["skipped_asof_missing_rows"] = asof_missing_count
    if coverage_warning:
        result["coverage_warning"] = coverage_ratio
    return result


def get_nearest_asof_type_for_gui(target_month: str, asof_date_str: str, calendar_df: pd.DataFrame | None = None) -> str | None:
    if not asof_date_str:
        return None

    try:
        asof_date = datetime.strptime(asof_date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            asof_date = datetime.strptime(asof_date_str, "%Y%m%d").date()
        except ValueError:
            return None

    try:
        asof_info_list = resolve_asof_dates_for_month(target_month, calendar_df)
    except TypeError:
        asof_info_list = resolve_asof_dates_for_month(target_month)

    nearest_type = None
    nearest_delta = None

    for asof_type, asof_str in asof_info_list:
        parsed_date = None
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                parsed_date = datetime.strptime(asof_str, fmt).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            continue

        delta = abs((parsed_date - asof_date).days)
        if nearest_delta is None or delta < nearest_delta:
            nearest_delta = delta
            nearest_type = asof_type

    return nearest_type


def _calculate_scenario_from_stats(forecast_total_rooms: float, stats: dict | None) -> dict | None:
    if not stats:
        return None

    bias_pct = stats.get("mean_error_pct")
    mape_pct = stats.get("mae_pct")
    n_samples = stats.get("n_samples")

    try:
        if n_samples is None or int(n_samples) <= 0:
            return None
        bias = float(bias_pct) / 100.0
        mape = float(mape_pct) / 100.0
    except Exception:
        return None

    if pd.isna(bias) or pd.isna(mape):
        return None

    total = float(forecast_total_rooms)
    denom = 1.0 + bias
    base = total if abs(denom) < 1e-6 else total / denom

    pessimistic = int(round(base * (1.0 - mape)))
    optimistic = int(round(base * (1.0 + mape)))
    base_int = int(round(base))
    forecast_int = int(round(total))

    return {
        "base": base_int,
        "pessimistic": pessimistic,
        "optimistic": optimistic,
        "forecast": forecast_int,
        "bias_pct": float(bias_pct),
        "mape_pct": float(mape_pct),
        "n": int(n_samples),
    }


def _compute_error_stats_for_window(
    hotel_key: str,
    target_month: str,
    window_months: int,
    model: str | None = None,
    asof_types: list[str] | None = None,
) -> dict | None:
    try:
        df_detail = _get_evaluation_detail_df(hotel_key)
    except Exception:
        return None

    months = _get_recent_months_before(str(target_month), window_months)
    if not months:
        return None

    df_detail = df_detail[df_detail["target_month"].isin(months)]
    if model:
        df_detail = df_detail[df_detail["model"] == model]
    if asof_types:
        if "asof_type" not in df_detail.columns:
            return None
        df_detail = df_detail[df_detail["asof_type"].isin(asof_types)]

    if df_detail.empty:
        return None

    err = df_detail["error_pct"].dropna()
    err_abs = df_detail["abs_error_pct"].dropna()
    if err.empty:
        return None

    mean_error = err.mean()
    mae = err_abs.mean() if not err_abs.empty else float("nan")
    n = int(err.count())

    if pd.isna(mean_error) or pd.isna(mae):
        return None

    return {"mean_error_pct": float(mean_error), "mae_pct": float(mae), "n_samples": n}


def get_monthly_forecast_scenarios(
    hotel_key: str,
    target_month: str,
    forecast_total_rooms: int,
    asof_date_str: str | None = None,
    best_model_stats: dict | None = None,
) -> dict:
    window_months = int(best_model_stats.get("window_months", 3)) if best_model_stats else 3

    best_recent = best_model_stats or get_best_model_stats_for_recent_months(hotel_key, target_month, window_months)
    model_name = best_recent.get("model") if best_recent else None

    avg_scenario = _calculate_scenario_from_stats(
        forecast_total_rooms,
        best_recent,
    )

    nearest_type = get_nearest_asof_type_for_gui(target_month, asof_date_str or "")
    if nearest_type:
        nearest_stats = _compute_error_stats_for_window(
            hotel_key,
            target_month,
            window_months,
            model=model_name,
            asof_types=[nearest_type],
        )
    else:
        nearest_stats = None

    nearest_scenario = _calculate_scenario_from_stats(forecast_total_rooms, nearest_stats)

    return {"avg_asof": avg_scenario, "nearest_asof": nearest_scenario}
