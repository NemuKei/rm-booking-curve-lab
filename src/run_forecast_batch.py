from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.forecast_simple import (
    compute_market_pace_7d,
    forecast_final_from_pace14,
    forecast_final_from_pace14_market,
    forecast_final_from_avg,
    forecast_month_from_recent90,
    moving_average_3months,
    moving_average_recent_90days,
    moving_average_recent_90days_weighted,
)
from booking_curve.plot_booking_curve import filter_by_weekday

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"

# 評価したい宿泊月 (YYYYMM)。必要に応じて増減可。
TARGET_MONTHS = [
    "202311",
    "202312",
    "202401",
    "202402",
    "202403",
    "202404",
    "202405",
    "202406",
    "202407",
    "202408",
    "202409",
    "202410",
    "202411",
    "202412",
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
]

# LTの範囲など、既存スクリプトと揃える
LT_MIN = -1
LT_MAX = 90
CAPACITY = 168.0  # デフォルトキャパシティ


# 指定があれば引数の値を使い、なければデフォルトCAPACITYを返す
def _resolve_capacity(capacity: float | None) -> float:
    """
    capacity が None の場合はグローバル CAPACITY を返し、
    それ以外は float(capacity) を返すヘルパー。
    """
    if capacity is None:
        return CAPACITY
    try:
        return float(capacity)
    except Exception:
        return CAPACITY


# ===== 設定ここまで =====


def get_history_months_around_asof(
    as_of_ts: pd.Timestamp,
    months_back: int = 4,
    months_forward: int = 4,
) -> list[str]:
    """
    ASOF 日付を中心に、前後の月を YYYYMM 文字列リストで返す。
    例: as_of=2025-09-30, months_back=4, months_forward=4
      -> ["202505", "202506", ..., "202601"] （9ヶ月分）
    """
    center = as_of_ts.to_period("M")
    months: list[str] = []
    for offset in range(-months_back, months_forward + 1):
        p = center + offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_avg_history_months(target_month: str, months_back: int = 3) -> list[str]:
    """
    avgモデル用の履歴月リストを返す。
    target_month (YYYYMM) を基準に、前 months_back ヶ月分 (M-1〜M-months_back) を
    YYYYMM 文字列のリストとして返す。
    例: target_month="202510", months_back=3 -> ["202509", "202508", "202507"]
    """
    period = pd.Period(target_month, freq="M")
    months: list[str] = []
    for offset in range(1, months_back + 1):
        p = period - offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_asof_dates_for_month(target_month: str) -> list[str]:
    """
    対象月 YYYYMM に対して、
    - 前月末
    - 当月10日
    - 当月20日
    の3つの as_of 日付(YYYYMMDD)を返す。
    """
    year = int(target_month[:4])
    month = int(target_month[4:])

    # 当月1日
    first = date(year, month, 1)

    # 前月末 = 当月1日から1日引く
    prev_month_end = first - timedelta(days=1)

    # 当月10日, 20日
    asof_10 = date(year, month, 10)
    asof_20 = date(year, month, 20)

    return [
        prev_month_end.strftime("%Y%m%d"),
        asof_10.strftime("%Y%m%d"),
        asof_20.strftime("%Y%m%d"),
    ]


LT_VALUE_TYPES = ("rooms", "pax", "revenue")
PHASE_FACTOR_DEFAULT = 1.0
PHASE_FACTOR_CLIP_PCT_DEFAULT = 0.05
ADR_EPS = 1e-6
DOR_MIN_DEFAULT = 1.0
DOR_MAX_DEFAULT = 3.0
DOR_K_MAX_DEFAULT = 1.0
DOR_K_MIN_DEFAULT = 0.2


def _resolve_lt_csv_path(month: str, hotel_tag: str, value_type: str) -> Path:
    if value_type not in LT_VALUE_TYPES:
        raise ValueError(f"Unsupported lt value type: {value_type}")

    candidates = []
    if value_type == "rooms":
        candidates.append(f"lt_data_rooms_{month}_{hotel_tag}.csv")
        candidates.append(f"lt_data_{month}_{hotel_tag}.csv")
    elif value_type == "pax":
        candidates.append(f"lt_data_pax_{month}_{hotel_tag}.csv")
    elif value_type == "revenue":
        candidates.append(f"lt_data_revenue_{month}_{hotel_tag}.csv")

    for name in candidates:
        path = Path(OUTPUT_DIR) / name
        if path.exists():
            return path

    raise FileNotFoundError(
        f"LT_DATA csv not found for {value_type}: month={month} hotel={hotel_tag}"
    )


def load_lt_csv(month: str, hotel_tag: str, value_type: str = "rooms") -> pd.DataFrame:
    file_path = _resolve_lt_csv_path(month, hotel_tag, value_type=value_type)
    return pd.read_csv(file_path, index_col=0)


def _load_history_raw(
    months: list[str],
    hotel_tag: str,
    value_type: str,
) -> dict[str, pd.DataFrame]:
    history_raw: dict[str, pd.DataFrame] = {}
    for ym in months:
        try:
            df_m = load_lt_csv(ym, hotel_tag=hotel_tag, value_type=value_type)
        except FileNotFoundError:
            continue
        if df_m.empty:
            continue
        history_raw[ym] = df_m
    return history_raw


def infer_pax_capacity_p99(
    hotel_tag: str,
    as_of_ts: pd.Timestamp,
    lookback_months: int = 24,
    q: float = 0.99,
) -> float | None:
    months = get_history_months_around_asof(
        as_of_ts=as_of_ts,
        months_back=lookback_months,
        months_forward=0,
    )
    values: list[float] = []
    for ym in months:
        try:
            df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="pax")
        except FileNotFoundError:
            continue
        if df.empty:
            continue
        act_col = None
        for col in df.columns:
            try:
                if int(col) == -1:
                    act_col = col
                    break
            except Exception:
                continue
        if act_col is None:
            continue
        series = pd.to_numeric(df[act_col], errors="coerce")
        series = series[(series >= 0) & series.notna()]
        if not series.empty:
            values.extend(series.to_numpy(dtype=float))

    if not values:
        return None

    estimate = np.nanquantile(np.asarray(values, dtype=float), q)
    if np.isnan(estimate):
        return None
    return max(0.0, float(estimate))


def _normalize_lt_df(df: pd.DataFrame) -> pd.DataFrame:
    working = df.copy()
    working.index = pd.to_datetime(working.index)
    col_map: dict[int, str] = {}
    for col in working.columns:
        try:
            col_map[int(col)] = col
        except Exception:
            continue
    if col_map:
        ordered = sorted(col_map.items(), key=lambda x: x[0])
        working = working[[col for _, col in ordered]]
        working.columns = [lt for lt, _ in ordered]
    return working


def _extract_asof_oh_series(lt_df: pd.DataFrame, as_of_ts: pd.Timestamp) -> pd.Series:
    if lt_df is None or lt_df.empty:
        return pd.Series(dtype=float)

    working = _normalize_lt_df(lt_df)
    result: dict[pd.Timestamp, float] = {}
    for stay_date, row in working.iterrows():
        lt_now = (stay_date - as_of_ts).days
        if lt_now in working.columns:
            value = row.get(lt_now, float("nan"))
        elif lt_now < 0 and -1 in working.columns:
            value = row.get(-1, float("nan"))
        else:
            value = float("nan")
        result[stay_date] = value
    return pd.Series(result, dtype=float)


def _extract_act_series(lt_df: pd.DataFrame) -> pd.Series:
    if lt_df is None or lt_df.empty:
        return pd.Series(dtype=float)

    working = _normalize_lt_df(lt_df)
    if -1 not in working.columns:
        return pd.Series(dtype=float)

    series = pd.to_numeric(working[-1], errors="coerce")
    series.index = pd.to_datetime(series.index)
    return series


def _estimate_dor_convergence_factor_by_lt(
    history_rooms_df: dict[str, pd.DataFrame],
    history_pax_df: dict[str, pd.DataFrame],
) -> dict[int, float]:
    ratios_by_lt: dict[int, list[float]] = {}

    common_months = set(history_rooms_df.keys()) & set(history_pax_df.keys())
    for ym in sorted(common_months):
        rooms_df = _normalize_lt_df(history_rooms_df[ym])
        pax_df = _normalize_lt_df(history_pax_df[ym])
        if rooms_df.empty or pax_df.empty:
            continue

        rooms_act = _extract_act_series(rooms_df)
        pax_act = _extract_act_series(pax_df)
        if rooms_act.empty or pax_act.empty:
            continue

        rooms_act = rooms_act.reindex(rooms_df.index)
        pax_act = pax_act.reindex(rooms_df.index)

        dor_final = pax_act / rooms_act.replace(0, np.nan)
        dor_final = dor_final.replace([np.inf, -np.inf], np.nan)

        for lt in rooms_df.columns:
            if lt < 0 or lt not in pax_df.columns:
                continue
            rooms_lt = pd.to_numeric(rooms_df[lt], errors="coerce")
            pax_lt = pd.to_numeric(pax_df[lt], errors="coerce")
            dor_at_lt = pax_lt / rooms_lt.replace(0, np.nan)
            ratio = dor_final / dor_at_lt.replace(0, np.nan)
            ratio = ratio.replace([np.inf, -np.inf], np.nan)
            ratio = ratio[(ratio > 0) & ratio.notna()]
            if ratio.empty:
                continue
            ratio = ratio.clip(lower=DOR_K_MIN_DEFAULT, upper=DOR_K_MAX_DEFAULT)
            ratios_by_lt.setdefault(int(lt), []).extend(ratio.to_list())

    k_by_lt: dict[int, float] = {}
    for lt, values in ratios_by_lt.items():
        if not values:
            continue
        median = float(np.nanmedian(np.asarray(values, dtype=float)))
        if np.isnan(median):
            continue
        k_by_lt[int(lt)] = min(median, DOR_K_MAX_DEFAULT)

    if not k_by_lt:
        return {}

    lts = sorted(k_by_lt.keys())
    series = pd.Series([k_by_lt[lt] for lt in lts], index=lts, dtype=float)
    full_index = range(min(lts), max(lts) + 1)
    series = series.reindex(full_index)
    series = series.interpolate(method="linear", limit_area="inside")
    overall_median = float(np.nanmedian(series.to_numpy(dtype=float)))
    if np.isnan(overall_median):
        overall_median = 1.0
    series = series.fillna(overall_median)
    series = series.clip(lower=DOR_K_MIN_DEFAULT, upper=DOR_K_MAX_DEFAULT)
    return {int(lt): float(val) for lt, val in series.items() if not np.isnan(val)}


def _estimate_dor_final_median(
    history_rooms_df: dict[str, pd.DataFrame],
    history_pax_df: dict[str, pd.DataFrame],
) -> float | None:
    values: list[float] = []
    common_months = set(history_rooms_df.keys()) & set(history_pax_df.keys())
    for ym in sorted(common_months):
        rooms_df = _normalize_lt_df(history_rooms_df[ym])
        pax_df = _normalize_lt_df(history_pax_df[ym])
        rooms_act = _extract_act_series(rooms_df)
        pax_act = _extract_act_series(pax_df)
        if rooms_act.empty or pax_act.empty:
            continue
        dor_final = pax_act / rooms_act.replace(0, np.nan)
        dor_final = dor_final.replace([np.inf, -np.inf], np.nan)
        dor_final = dor_final[(dor_final > 0) & dor_final.notna()]
        if not dor_final.empty:
            values.extend(dor_final.to_numpy(dtype=float))
    if not values:
        return None
    median = float(np.nanmedian(np.asarray(values, dtype=float)))
    if np.isnan(median):
        return None
    return median


def _append_pax_forecast_from_dor(
    out_df: pd.DataFrame,
    df_target_rooms: pd.DataFrame,
    df_target_pax: pd.DataFrame,
    as_of_ts: pd.Timestamp,
    history_rooms: dict[str, pd.DataFrame],
    history_pax: dict[str, pd.DataFrame],
    pax_capacity: float | None,
    dor_min: float = DOR_MIN_DEFAULT,
    dor_max: float = DOR_MAX_DEFAULT,
) -> pd.DataFrame:
    if out_df is None or out_df.empty:
        return out_df

    k_by_lt = _estimate_dor_convergence_factor_by_lt(history_rooms, history_pax)
    overall_k = float(np.nanmedian(list(k_by_lt.values()))) if k_by_lt else 1.0
    if np.isnan(overall_k) or overall_k <= 0:
        overall_k = 1.0
    dor_final_median = _estimate_dor_final_median(history_rooms, history_pax)

    rooms_oh_now = _extract_asof_oh_series(df_target_rooms, as_of_ts)
    pax_oh_now = _extract_asof_oh_series(df_target_pax, as_of_ts)

    rooms_oh_now = rooms_oh_now.reindex(out_df.index)
    pax_oh_now = pax_oh_now.reindex(out_df.index)

    dor_now = pax_oh_now / rooms_oh_now.replace(0, np.nan)
    dor_now = dor_now.replace([np.inf, -np.inf], np.nan)

    lt_now_series = pd.Series(
        [(stay_date - as_of_ts).days for stay_date in out_df.index],
        index=out_df.index,
        dtype="Int64",
    )
    k_series = lt_now_series.map(lambda lt: k_by_lt.get(int(lt), overall_k) if not pd.isna(lt) else overall_k)

    dor_est = dor_now * k_series.astype(float)
    if dor_final_median is not None:
        dor_est = dor_est.fillna(dor_final_median)
    dor_est = dor_est.clip(lower=dor_min, upper=dor_max)

    forecast_rooms = pd.to_numeric(out_df.get("forecast_rooms"), errors="coerce")
    forecast_pax = forecast_rooms * dor_est
    if pax_capacity is not None:
        forecast_pax = forecast_pax.clip(upper=float(pax_capacity))

    actual_pax_series = _extract_act_series(df_target_pax).reindex(out_df.index)
    forecast_pax = forecast_pax.copy()
    mask_past = out_df.index < as_of_ts
    actual_available = actual_pax_series.notna()
    forecast_pax.loc[mask_past & actual_available] = actual_pax_series.loc[mask_past & actual_available]

    def _round_int_series(series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").round().astype("Int64")

    out_df["actual_pax"] = _round_int_series(actual_pax_series)
    out_df["forecast_pax"] = _round_int_series(forecast_pax)

    projected = []
    for dt in out_df.index:
        actual_value = out_df.loc[dt, "actual_pax"]
        forecast_value = out_df.loc[dt, "forecast_pax"]
        if dt < as_of_ts:
            if pd.isna(actual_value):
                projected.append(forecast_value)
            else:
                projected.append(actual_value)
        else:
            projected.append(forecast_value)

    out_df["projected_pax"] = _round_int_series(pd.Series(projected, index=out_df.index))
    return out_df


def _round_int_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def _prepare_output(
    df_target: pd.DataFrame, forecast: dict[pd.Timestamp, float], as_of_ts: pd.Timestamp
) -> pd.DataFrame:
    result = pd.Series(forecast, dtype=float)
    result.sort_index(inplace=True)

    all_dates = pd.to_datetime(df_target.index)
    all_dates = all_dates.sort_values()

    out_df = pd.DataFrame(index=all_dates)
    out_df.index.name = "stay_date"

    act_col = None
    for col in df_target.columns:
        try:
            if int(col) == -1:
                act_col = col
                break
        except Exception:
            continue

    if act_col is not None:
        actual_series = df_target[act_col]
        actual_series.index = all_dates
        out_df["actual_rooms"] = _round_int_series(actual_series)
    else:
        out_df["actual_rooms"] = pd.Series(pd.NA, index=all_dates, dtype="Int64")

    out_df["forecast_rooms"] = _round_int_series(result.reindex(all_dates))

    projected = []
    for dt in out_df.index:
        actual_value = out_df.loc[dt, "actual_rooms"]
        forecast_value = out_df.loc[dt, "forecast_rooms"]
        if dt < as_of_ts:
            if pd.isna(actual_value):
                projected.append(forecast_value)
            else:
                projected.append(actual_value)
        else:
            projected.append(forecast_value)

    out_df["projected_rooms"] = _round_int_series(pd.Series(projected, index=out_df.index))
    return out_df


def _prepare_output_for_pax(
    df_target: pd.DataFrame,
    forecast: dict[pd.Timestamp, float],
    as_of_ts: pd.Timestamp,
) -> pd.DataFrame:
    result = pd.Series(forecast, dtype=float)
    result.sort_index(inplace=True)

    all_dates = pd.to_datetime(df_target.index)
    all_dates = all_dates.sort_values()

    out_df = pd.DataFrame(index=all_dates)
    out_df.index.name = "stay_date"

    act_col = None
    for col in df_target.columns:
        try:
            if int(col) == -1:
                act_col = col
                break
        except Exception:
            continue

    if act_col is not None:
        actual_series = df_target[act_col]
        actual_series.index = all_dates
        out_df["actual_pax"] = _round_int_series(actual_series)
    else:
        out_df["actual_pax"] = pd.Series(pd.NA, index=all_dates, dtype="Int64")

    out_df["forecast_pax"] = _round_int_series(result.reindex(all_dates))

    projected = []
    for dt in out_df.index:
        actual_value = out_df.loc[dt, "actual_pax"]
        forecast_value = out_df.loc[dt, "forecast_pax"]
        if dt < as_of_ts:
            if pd.isna(actual_value):
                projected.append(forecast_value)
            else:
                projected.append(actual_value)
        else:
            projected.append(forecast_value)

    out_df["projected_pax"] = _round_int_series(pd.Series(projected, index=out_df.index))
    return out_df


def _apply_phase_factor(value: float | None, clip_pct: float | None) -> float:
    if value is None:
        return PHASE_FACTOR_DEFAULT
    try:
        factor = float(value)
    except Exception:
        return PHASE_FACTOR_DEFAULT
    if clip_pct is None:
        clip_pct = PHASE_FACTOR_CLIP_PCT_DEFAULT
    try:
        clip_pct = float(clip_pct)
    except Exception:
        clip_pct = PHASE_FACTOR_CLIP_PCT_DEFAULT
    if clip_pct < 0:
        clip_pct = PHASE_FACTOR_CLIP_PCT_DEFAULT
    min_factor = 1.0 - clip_pct
    max_factor = 1.0 + clip_pct
    return min(max(factor, min_factor), max_factor)


def _append_revenue_columns(
    out_df: pd.DataFrame,
    df_rooms: pd.DataFrame,
    df_revenue: pd.DataFrame,
    as_of_ts: pd.Timestamp,
    phase_factor: float | None,
    phase_clip_pct: float | None,
) -> pd.DataFrame:
    if out_df is None or out_df.empty:
        return out_df

    if df_rooms is None or df_rooms.empty or df_revenue is None or df_revenue.empty:
        out_df["revenue_oh_now"] = pd.NA
        out_df["adr_oh_now"] = pd.NA
        out_df["adr_pickup_est"] = pd.NA
        out_df["forecast_revenue"] = pd.NA
        return out_df

    rooms_oh_series = _extract_asof_oh_series(df_rooms, as_of_ts)
    revenue_oh_series = _extract_asof_oh_series(df_revenue, as_of_ts)

    rooms_oh_now = rooms_oh_series.reindex(out_df.index)
    revenue_oh_now = revenue_oh_series.reindex(out_df.index)

    rooms_oh_now = pd.to_numeric(rooms_oh_now, errors="coerce").round().astype(float)
    revenue_oh_now = pd.to_numeric(revenue_oh_now, errors="coerce").astype(float)

    rooms_for_div = rooms_oh_now.clip(lower=ADR_EPS)
    adr_oh_now = revenue_oh_now / rooms_for_div

    forecast_final_rooms = out_df["forecast_rooms"].copy()
    fallback_actual = out_df.get("actual_rooms")
    if fallback_actual is not None:
        forecast_final_rooms = forecast_final_rooms.fillna(fallback_actual)
    forecast_final_rooms = pd.to_numeric(forecast_final_rooms, errors="coerce")

    remaining_rooms = (forecast_final_rooms - rooms_oh_now).clip(lower=0.0)

    factor = _apply_phase_factor(phase_factor, phase_clip_pct)
    adr_pickup_est = adr_oh_now * factor
    forecast_revenue = revenue_oh_now + remaining_rooms * adr_pickup_est

    out_df["revenue_oh_now"] = revenue_oh_now
    out_df["adr_oh_now"] = adr_oh_now
    out_df["adr_pickup_est"] = adr_pickup_est
    out_df["forecast_revenue"] = forecast_revenue
    return out_df


def _merge_pace14_details(
    out_df: pd.DataFrame, detail_df: pd.DataFrame, *, prefix: str
) -> pd.DataFrame:
    if detail_df is None or detail_df.empty:
        return out_df
    detail_df = detail_df.copy()
    detail_df.index = pd.to_datetime(detail_df.index)
    detail_df = detail_df.reindex(out_df.index)
    rename_map = {
        "lt_now": f"{prefix}_lt_now",
        "lower_lt": f"{prefix}_lower_lt",
        "upper_lt": f"{prefix}_upper_lt",
        "delta_actual": f"{prefix}_delta_actual",
        "delta_base": f"{prefix}_delta_base",
        "pf_raw": f"{prefix}_pf_raw",
        "pf_shrunk": f"{prefix}_pf_shrunk",
        "pf_clipped": f"{prefix}_pf",
        "is_spike": f"{prefix}_spike",
        "market_pace_7d": "market_pace_7d",
        "market_beta": "market_beta",
        "market_factor": "market_factor",
    }
    for col, renamed in rename_map.items():
        if col in detail_df.columns:
            out_df[renamed] = detail_df[col]
    return out_df


def run_avg_forecast(
    target_month: str,
    as_of_date: str,
    capacity: float | None = None,
    pax_capacity: float | None = None,
    hotel_tag: str = HOTEL_TAG,
    phase_factor: float | None = None,
    phase_clip_pct: float | None = None,
) -> None:
    """
    avgモデル(3ヶ月平均)で target_month を as_of_date 時点で予測し、
    run_forecast_from_avg.py と同じ形式の CSV を OUTPUT_DIR に出力する。
    """
    cap = _resolve_capacity(capacity)

    df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    df_target_pax: pd.DataFrame | None
    df_target_revenue: pd.DataFrame | None
    try:
        df_target_pax = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="pax")
    except FileNotFoundError:
        df_target_pax = None
    try:
        df_target_revenue = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="revenue")
    except FileNotFoundError:
        df_target_revenue = None

    # avgモデル用の履歴: target_month から見た直近3ヶ月 (M-1〜M-3)
    history_months = get_avg_history_months(target_month=target_month, months_back=3)

    history_raw = _load_history_raw(history_months, hotel_tag, value_type="rooms")
    history_raw_pax = _load_history_raw(history_months, hotel_tag, value_type="pax")

    if not history_raw:
        print(f"[avg] No history LT_DATA for target_month={target_month}")

    all_forecasts: dict[pd.Timestamp, float] = {}
    as_of_ts = pd.to_datetime(as_of_date)
    if pax_capacity is None:
        pax_capacity = infer_pax_capacity_p99(hotel_tag, as_of_ts)

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        avg_curve = moving_average_3months(history_dfs, lt_min=LT_MIN, lt_max=LT_MAX)
        df_target_wd = filter_by_weekday(df_target, weekday=weekday)

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=cap,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")

    out_df = _prepare_output(df_target, all_forecasts, as_of_ts)
    if df_target_pax is not None:
        out_df = _append_pax_forecast_from_dor(
            out_df=out_df,
            df_target_rooms=df_target,
            df_target_pax=df_target_pax,
            as_of_ts=as_of_ts,
            history_rooms=history_raw,
            history_pax=history_raw_pax,
            pax_capacity=pax_capacity,
        )
    if df_target_revenue is not None:
        out_df = _append_revenue_columns(
            out_df,
            df_rooms=df_target,
            df_revenue=df_target_revenue,
            as_of_ts=as_of_ts,
            phase_factor=phase_factor,
            phase_clip_pct=phase_clip_pct,
        )

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def run_recent90_forecast(
    target_month: str,
    as_of_date: str,
    capacity: float | None = None,
    pax_capacity: float | None = None,
    hotel_tag: str = HOTEL_TAG,
    phase_factor: float | None = None,
    phase_clip_pct: float | None = None,
) -> None:
    """
    recent90モデル(観測日から遡る90日平均)で target_month を as_of_date 時点で予測し、
    run_forecast_from_recent90.py と同じ形式の CSV を OUTPUT_DIR に出力する。
    """
    cap = _resolve_capacity(capacity)

    as_of_ts = pd.to_datetime(as_of_date)
    if pax_capacity is None:
        pax_capacity = infer_pax_capacity_p99(hotel_tag, as_of_ts)
    history_months = get_history_months_around_asof(
        as_of_ts=as_of_ts,
        months_back=4,
        months_forward=4,
    )

    history_raw = _load_history_raw(history_months, hotel_tag, value_type="rooms")
    history_raw_pax = _load_history_raw(history_months, hotel_tag, value_type="pax")

    if not history_raw:
        print(f"[recent90] No history LT_DATA for as_of={as_of_date}")

    df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    df_target_pax: pd.DataFrame | None
    df_target_revenue: pd.DataFrame | None
    try:
        df_target_pax = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="pax")
    except FileNotFoundError:
        df_target_pax = None
    try:
        df_target_revenue = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="revenue")
    except FileNotFoundError:
        df_target_revenue = None

    all_forecasts: dict[pd.Timestamp, float] = {}

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=cap,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")

    out_df = forecast_month_from_recent90(
        df_target=df_target,
        forecasts=all_forecasts,
        as_of_ts=as_of_ts,
        hotel_tag=hotel_tag,
    )
    if df_target_pax is not None:
        out_df = _append_pax_forecast_from_dor(
            out_df=out_df,
            df_target_rooms=df_target,
            df_target_pax=df_target_pax,
            as_of_ts=as_of_ts,
            history_rooms=history_raw,
            history_pax=history_raw_pax,
            pax_capacity=pax_capacity,
        )
    if df_target_revenue is not None:
        out_df = _append_revenue_columns(
            out_df,
            df_rooms=df_target,
            df_revenue=df_target_revenue,
            as_of_ts=as_of_ts,
            phase_factor=phase_factor,
            phase_clip_pct=phase_clip_pct,
        )

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_recent90_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def run_recent90_weighted_forecast(
    target_month: str,
    as_of: str,
    capacity: float | None = None,
    pax_capacity: float | None = None,
    hotel_tag: str = HOTEL_TAG,
    phase_factor: float | None = None,
    phase_clip_pct: float | None = None,
) -> None:
    """
    recent90_weightedモデル(観測日から遡る90日平均・重み付き)で
    target_month の予測CSVを出力する。

    出力ファイル名:
      forecast_recent90w_{target_month}_{hotel_tag}_asof_{as_of}.csv
    """
    cap = _resolve_capacity(capacity)

    as_of_ts = pd.to_datetime(as_of, format="%Y%m%d")
    if pax_capacity is None:
        pax_capacity = infer_pax_capacity_p99(hotel_tag, as_of_ts)

    history_months = get_history_months_around_asof(
        as_of_ts=as_of_ts,
        months_back=4,
        months_forward=4,
    )

    history_raw = _load_history_raw(history_months, hotel_tag, value_type="rooms")
    history_raw_pax = _load_history_raw(history_months, hotel_tag, value_type="pax")

    if not history_raw:
        print(f"[recent90_weighted] No history LT_DATA for as_of={as_of}")

    df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    df_target_pax: pd.DataFrame | None
    df_target_revenue: pd.DataFrame | None
    try:
        df_target_pax = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="pax")
    except FileNotFoundError:
        df_target_pax = None
    try:
        df_target_revenue = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="revenue")
    except FileNotFoundError:
        df_target_revenue = None

    all_forecasts: dict[pd.Timestamp, float] = {}

    for weekday in range(7):
        # 履歴側: 該当曜日だけに絞る
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        # ★ここが simple recent90 との違い: weighted 版を使う
        avg_curve = moving_average_recent_90days_weighted(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        # 対象月側も同じ曜日だけに絞る
        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=cap,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print(f"[recent90_weighted] No forecasts for {target_month} as_of={as_of}")

    out_df = forecast_month_from_recent90(
        df_target=df_target,
        forecasts=all_forecasts,
        as_of_ts=as_of_ts,
        hotel_tag=hotel_tag,
    )
    if df_target_pax is not None:
        out_df = _append_pax_forecast_from_dor(
            out_df=out_df,
            df_target_rooms=df_target,
            df_target_pax=df_target_pax,
            as_of_ts=as_of_ts,
            history_rooms=history_raw,
            history_pax=history_raw_pax,
            pax_capacity=pax_capacity,
        )
    if df_target_revenue is not None:
        out_df = _append_revenue_columns(
            out_df,
            df_rooms=df_target,
            df_revenue=df_target_revenue,
            as_of_ts=as_of_ts,
            phase_factor=phase_factor,
            phase_clip_pct=phase_clip_pct,
        )

    out_name = f"forecast_recent90w_{target_month}_{hotel_tag}_asof_{as_of}.csv"
    out_path = Path(OUTPUT_DIR) / out_name
    out_df.to_csv(out_path, index=True)
    print(f"[recent90_weighted][OK] {out_path}")


def run_pace14_forecast(
    target_month: str,
    as_of_date: str,
    capacity: float | None = None,
    pax_capacity: float | None = None,
    hotel_tag: str = HOTEL_TAG,
    phase_factor: float | None = None,
    phase_clip_pct: float | None = None,
) -> None:
    """pace14モデルで target_month を as_of_date 時点で予測し、CSVを出力する。"""
    cap = _resolve_capacity(capacity)

    as_of_ts = pd.to_datetime(as_of_date)
    if pax_capacity is None:
        pax_capacity = infer_pax_capacity_p99(hotel_tag, as_of_ts)
    history_months = get_history_months_around_asof(
        as_of_ts=as_of_ts,
        months_back=4,
        months_forward=4,
    )

    history_raw = _load_history_raw(history_months, hotel_tag, value_type="rooms")
    history_raw_pax = _load_history_raw(history_months, hotel_tag, value_type="pax")

    if not history_raw:
        print(f"[pace14] No history LT_DATA for as_of={as_of_date}")

    df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    df_target_pax: pd.DataFrame | None
    df_target_revenue: pd.DataFrame | None
    try:
        df_target_pax = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="pax")
    except FileNotFoundError:
        df_target_pax = None
    try:
        df_target_revenue = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="revenue")
    except FileNotFoundError:
        df_target_revenue = None

    all_forecasts: dict[pd.Timestamp, float] = {}
    detail_frames: list[pd.DataFrame] = []

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series, detail_df = forecast_final_from_pace14(
            lt_df=df_target_wd,
            baseline_curve=avg_curve,
            history_df=history_all,
            as_of_date=as_of_ts,
            capacity=cap,
            lt_min=0,
            lt_max=LT_MAX,
        )

        if not detail_df.empty:
            detail_frames.append(detail_df)

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")

    out_df = _prepare_output(df_target, all_forecasts, as_of_ts)
    if detail_frames:
        detail_all = pd.concat(detail_frames, axis=0)
        out_df = _merge_pace14_details(out_df, detail_all, prefix="pace14")
    if df_target_pax is not None:
        out_df = _append_pax_forecast_from_dor(
            out_df=out_df,
            df_target_rooms=df_target,
            df_target_pax=df_target_pax,
            as_of_ts=as_of_ts,
            history_rooms=history_raw,
            history_pax=history_raw_pax,
            pax_capacity=pax_capacity,
        )
    if df_target_revenue is not None:
        out_df = _append_revenue_columns(
            out_df,
            df_rooms=df_target,
            df_revenue=df_target_revenue,
            as_of_ts=as_of_ts,
            phase_factor=phase_factor,
            phase_clip_pct=phase_clip_pct,
        )

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_pace14_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def run_pace14_market_forecast(
    target_month: str,
    as_of_date: str,
    capacity: float | None = None,
    pax_capacity: float | None = None,
    hotel_tag: str = HOTEL_TAG,
    phase_factor: float | None = None,
    phase_clip_pct: float | None = None,
) -> None:
    """pace14_marketモデルで target_month を as_of_date 時点で予測し、CSVを出力する。"""
    cap = _resolve_capacity(capacity)

    as_of_ts = pd.to_datetime(as_of_date)
    if pax_capacity is None:
        pax_capacity = infer_pax_capacity_p99(hotel_tag, as_of_ts)
    history_months = get_history_months_around_asof(
        as_of_ts=as_of_ts,
        months_back=4,
        months_forward=4,
    )

    history_raw = _load_history_raw(history_months, hotel_tag, value_type="rooms")
    history_raw_pax = _load_history_raw(history_months, hotel_tag, value_type="pax")

    if not history_raw:
        print(f"[pace14_market] No history LT_DATA for as_of={as_of_date}")

    df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    df_target_pax: pd.DataFrame | None
    df_target_revenue: pd.DataFrame | None
    try:
        df_target_pax = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="pax")
    except FileNotFoundError:
        df_target_pax = None
    try:
        df_target_revenue = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="revenue")
    except FileNotFoundError:
        df_target_revenue = None

    all_forecasts: dict[pd.Timestamp, float] = {}
    detail_frames: list[pd.DataFrame] = []
    baseline_curves: dict[int, pd.Series] = {}
    history_by_weekday: dict[int, pd.DataFrame] = {}

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        baseline_curves[weekday] = avg_curve
        history_by_weekday[weekday] = history_all

    market_pace_7d, mp_df = compute_market_pace_7d(
        lt_df=df_target,
        as_of_ts=as_of_ts,
        history_by_weekday=history_by_weekday,
        lt_min=LT_MIN,
        lt_max=LT_MAX,
    )

    for weekday in range(7):
        history_all = history_by_weekday.get(weekday)
        avg_curve = baseline_curves.get(weekday)
        if history_all is None or avg_curve is None:
            continue

        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series, detail_df = forecast_final_from_pace14_market(
            lt_df=df_target_wd,
            baseline_curve=avg_curve,
            history_df=history_all,
            as_of_date=as_of_ts,
            capacity=cap,
            market_pace_7d=market_pace_7d,
            lt_min=0,
            lt_max=LT_MAX,
        )

        if not detail_df.empty:
            detail_frames.append(detail_df)

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")

    out_df = _prepare_output(df_target, all_forecasts, as_of_ts)
    if detail_frames:
        detail_all = pd.concat(detail_frames, axis=0)
        out_df = _merge_pace14_details(out_df, detail_all, prefix="pace14")
        if not mp_df.empty:
            out_df.attrs["market_pace_7d"] = market_pace_7d
    if df_target_pax is not None:
        out_df = _append_pax_forecast_from_dor(
            out_df=out_df,
            df_target_rooms=df_target,
            df_target_pax=df_target_pax,
            as_of_ts=as_of_ts,
            history_rooms=history_raw,
            history_pax=history_raw_pax,
            pax_capacity=pax_capacity,
        )
    if df_target_revenue is not None:
        out_df = _append_revenue_columns(
            out_df,
            df_rooms=df_target,
            df_revenue=df_target_revenue,
            as_of_ts=as_of_ts,
            phase_factor=phase_factor,
            phase_clip_pct=phase_clip_pct,
        )

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_pace14_market_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def main() -> None:
    for target_month in TARGET_MONTHS:
        asof_list = get_asof_dates_for_month(target_month)
        for as_of in asof_list:
            print(f"[avg]       target={target_month} as_of={as_of}")
            run_avg_forecast(target_month, as_of)

            print(f"[recent90]  target={target_month} as_of={as_of}")
            run_recent90_forecast(target_month, as_of)

            print(f"[recent90w] target={target_month} as_of={as_of}")
            run_recent90_weighted_forecast(target_month, as_of)

            print(f"[pace14]   target={target_month} as_of={as_of}")
            run_pace14_forecast(target_month, as_of)

            print(f"[pace14m]  target={target_month} as_of={as_of}")
            run_pace14_market_forecast(target_month, as_of)

    print("=== batch forecast finished ===")


if __name__ == "__main__":
    main()
