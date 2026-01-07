from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

import build_calendar_features
import run_build_lt_csv
import run_forecast_batch
from booking_curve.config import HOTEL_CONFIG, OUTPUT_DIR
from booking_curve.daily_snapshots import (
    get_daily_snapshots_path,
    get_latest_asof_date,
    list_stay_months_from_daily_snapshots,
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

    for ym in target_months:
        phase_factor = None
        if phase_factors:
            phase_factor = phase_factors.get(ym)
        if base_model == "avg":
            run_forecast_batch.run_avg_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
            )
        elif base_model == "recent90":
            run_forecast_batch.run_recent90_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
            )
        elif base_model == "recent90w":
            run_forecast_batch.run_recent90_weighted_forecast(
                target_month=ym,
                as_of=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
            )
        elif base_model == "pace14":
            run_forecast_batch.run_pace14_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
            )
        elif base_model == "pace14_market":
            run_forecast_batch.run_pace14_market_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
                phase_factor=phase_factor,
            )
        else:
            raise ValueError(f"Unsupported gui_model: {gui_model}")


def get_daily_forecast_table(
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
    capacity: Optional[float] = None,
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

    Returns
    -------
    pd.DataFrame
        日別行 + 最終行に TOTAL 行 を含むテーブル
    """
    cap = _get_capacity(hotel_tag, capacity)

    def _round_int_series(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").round().astype("Int64")

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
    if not csv_path.exists():
        raise FileNotFoundError(f"forecast csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    if "actual_rooms" not in df.columns:
        raise ValueError(f"{csv_path} に actual_rooms 列がありません。")
    if col_name not in df.columns:
        raise ValueError(f"{csv_path} に {col_name} 列がありません。")

    out = pd.DataFrame(index=df.index.copy())
    out["stay_date"] = out.index
    out["weekday"] = out["stay_date"].dt.weekday
    out["actual_rooms"] = _round_int_series(df["actual_rooms"])
    out["forecast_rooms"] = _round_int_series(df[col_name])
    if "actual_pax" in df.columns:
        out["actual_pax"] = _round_int_series(df["actual_pax"])
    else:
        out["actual_pax"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    if "forecast_pax" in df.columns:
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
        out["revenue_oh_now"] = pd.NA
    if "adr_oh_now" in df.columns:
        out["adr_oh_now"] = pd.to_numeric(df["adr_oh_now"], errors="coerce").astype(float)
    else:
        out["adr_oh_now"] = pd.NA
    if "adr_pickup_est" in df.columns:
        out["adr_pickup_est"] = pd.to_numeric(df["adr_pickup_est"], errors="coerce").astype(float)
    else:
        out["adr_pickup_est"] = pd.NA
    if "forecast_revenue" in df.columns:
        out["forecast_revenue"] = pd.to_numeric(df["forecast_revenue"], errors="coerce").astype(float)
    else:
        out["forecast_revenue"] = pd.NA

    snap_all = read_daily_snapshots_for_month(hotel_id=hotel_tag, target_month=target_month)
    required_cols = {"stay_date", "as_of_date", "rooms_oh"}

    if snap_all is None or snap_all.empty or not required_cols.issubset(snap_all.columns):
        out["asof_oh_rooms"] = _round_int_series(out["actual_rooms"])
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

    out["diff_rooms_vs_actual"] = out["forecast_rooms"] - out["actual_rooms"]
    denom_actual = out["actual_rooms"].replace(0, pd.NA)
    out["diff_pct_vs_actual"] = (out["diff_rooms_vs_actual"] / denom_actual * 100.0).astype(float)
    out["pickup_expected_from_asof"] = out["forecast_rooms"] - out["asof_oh_rooms"]

    out["diff_rooms"] = out["diff_rooms_vs_actual"]
    out["diff_pct"] = out["diff_pct_vs_actual"]

    out["occ_actual_pct"] = (out["actual_rooms"] / cap * 100.0).astype(float)
    out["occ_asof_pct"] = (out["asof_oh_rooms"] / cap * 100.0).astype(float)
    out["occ_forecast_pct"] = (out["forecast_rooms"] / cap * 100.0).astype(float)

    num_days = out["stay_date"].nunique()

    actual_total = out["actual_rooms"].fillna(0).sum()
    asof_total = out["asof_oh_rooms"].fillna(0).sum()
    forecast_total = out["forecast_rooms"].fillna(0).sum()
    actual_pax_total = out["actual_pax"].fillna(0).sum()
    forecast_pax_total = out["forecast_pax"].fillna(0).sum()
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

    total_row = {
        "stay_date": pd.NaT,
        "weekday": "",
        "actual_rooms": actual_total,
        "asof_oh_rooms": asof_total,
        "forecast_rooms": forecast_total,
        "actual_pax": actual_pax_total,
        "forecast_pax": forecast_pax_total,
        "projected_pax": pd.NA,
        "revenue_oh_now": revenue_oh_total,
        "adr_oh_now": pd.NA,
        "adr_pickup_est": pd.NA,
        "forecast_revenue": forecast_revenue_total,
        "diff_rooms_vs_actual": diff_total_vs_actual,
        "diff_pct_vs_actual": diff_total_pct_vs_actual,
        "pickup_expected_from_asof": pickup_total_from_asof,
        "diff_rooms": diff_total_vs_actual,
        "diff_pct": diff_total_pct_vs_actual,
        "occ_actual_pct": occ_actual_month,
        "occ_asof_pct": occ_asof_month,
        "occ_forecast_pct": occ_forecast_month,
    }

    out = out.reset_index(drop=True)
    out = pd.concat([out, pd.DataFrame([total_row])], ignore_index=True)

    def _round_display(series: pd.Series, unit: float) -> pd.Series:
        values = pd.to_numeric(series, errors="coerce")
        return (values / unit).round() * unit

    out["actual_rooms_display"] = out["actual_rooms"].copy()
    out["asof_oh_rooms_display"] = out["asof_oh_rooms"].copy()
    out["forecast_rooms_display"] = out["forecast_rooms"].copy()
    out["actual_pax_display"] = out["actual_pax"].copy()
    out["forecast_pax_display"] = out["forecast_pax"].copy()
    out["forecast_revenue_display"] = out["forecast_revenue"].copy()

    total_mask = out["stay_date"].isna()
    if total_mask.any():
        out.loc[total_mask, "actual_rooms_display"] = _round_display(
            out.loc[total_mask, "actual_rooms"],
            100.0,
        )
        out.loc[total_mask, "asof_oh_rooms_display"] = _round_display(
            out.loc[total_mask, "asof_oh_rooms"],
            100.0,
        )
        out.loc[total_mask, "forecast_rooms_display"] = _round_display(
            out.loc[total_mask, "forecast_rooms"],
            100.0,
        )
        out.loc[total_mask, "actual_pax_display"] = _round_display(
            out.loc[total_mask, "actual_pax"],
            100.0,
        )
        out.loc[total_mask, "forecast_pax_display"] = _round_display(
            out.loc[total_mask, "forecast_pax"],
            100.0,
        )
        out.loc[total_mask, "forecast_revenue_display"] = _round_display(
            out.loc[total_mask, "forecast_revenue"],
            100000.0,
        )

    column_order = [
        "stay_date",
        "weekday",
        "actual_rooms",
        "asof_oh_rooms",
        "forecast_rooms",
        "actual_pax",
        "forecast_pax",
        "projected_pax",
        "revenue_oh_now",
        "adr_oh_now",
        "adr_pickup_est",
        "forecast_revenue",
        "actual_rooms_display",
        "asof_oh_rooms_display",
        "forecast_rooms_display",
        "actual_pax_display",
        "forecast_pax_display",
        "forecast_revenue_display",
        "diff_rooms_vs_actual",
        "diff_pct_vs_actual",
        "pickup_expected_from_asof",
        "diff_rooms",
        "diff_pct",
        "occ_actual_pct",
        "occ_asof_pct",
        "occ_forecast_pct",
    ]

    out = out[column_order]

    return out


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
    source: str = "timeseries",
) -> None:
    """
    Tkinter GUI から LT_DATA 生成バッチを実行するための薄いラッパー。

    hotel_tag ごとに config.HOTEL_CONFIG で定義された時系列Excelを読み込み、
    run_build_lt_csv.run_build_lt_for_gui() を呼び出す。

    source: "timeseries" または "daily_snapshots" を指定する。デフォルトは "timeseries"。
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
