from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from booking_curve import config
from booking_curve.forecast_simple import (
    WEEKSHAPE_LT_MAX,
    WEEKSHAPE_LT_MIN,
    WEEKSHAPE_W,
    compute_weekshape_flow_factors,
    moving_average_recent_90days,
)

logger = logging.getLogger(__name__)


def _load_lt_data_csv(hotel_tag: str, yyyymm: str) -> pd.DataFrame:
    """Load LT_DATA CSV for a single hotel/month (rooms)."""

    csv_path = config.get_hotel_output_dir(hotel_tag) / f"lt_data_{yyyymm}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"LT_DATA csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)
    df.index = pd.to_datetime(df.index)

    col_map: dict[str, int] = {}
    for col in df.columns:
        try:
            col_map[col] = int(col)
        except Exception:
            continue

    if not col_map:
        raise ValueError("LT columns not found in LT_DATA csv.")

    lt_df = df[list(col_map.keys())].copy()
    lt_df.columns = [col_map[c] for c in lt_df.columns]

    year = int(yyyymm[:4])
    month = int(yyyymm[4:])
    lt_df = lt_df[(lt_df.index.year == year) & (lt_df.index.month == month)]

    return lt_df


def _months_around_asof(
    asof_ts: pd.Timestamp,
    months_back: int = 4,
    months_forward: int = 4,
) -> list[str]:
    center = asof_ts.to_period("M")
    months: list[str] = []
    for offset in range(-months_back, months_forward + 1):
        p = center + offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def _normalize_asof(value: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Invalid asof_end value: {value!r}")
    return pd.Timestamp(ts).normalize()


def _resolve_capacity(hotel_tag: str) -> float | None:
    cfg = config.HOTEL_CONFIG.get(hotel_tag)
    if not cfg:
        return None
    try:
        capacity_value = cfg.get("capacity")
        if capacity_value is None:
            return None
        capacity = float(capacity_value)
    except Exception:
        return None
    if capacity <= 0:
        return None
    return capacity


def _build_sample_asof_dates(
    asof_end: pd.Timestamp,
    window_months: int,
    sample_stride_days: int,
) -> list[pd.Timestamp]:
    if window_months <= 0:
        raise ValueError("window_months must be >= 1")
    if sample_stride_days <= 0:
        raise ValueError("sample_stride_days must be >= 1")

    start_ts = (asof_end - pd.DateOffset(months=window_months)).normalize()
    sample_dates: list[pd.Timestamp] = []
    current = asof_end.normalize()
    while current >= start_ts:
        sample_dates.append(current)
        current = current - pd.Timedelta(days=sample_stride_days)
    return sample_dates


def train_weekshape_base_small_quantiles(
    hotel_tag: str,
    asof_end: str | pd.Timestamp,
    window_months: int = 3,
    sample_stride_days: int = 7,
    months_back: int = 4,
    months_forward: int = 4,
) -> dict[str, object]:
    asof_end_ts = _normalize_asof(asof_end)
    capacity = _resolve_capacity(hotel_tag)
    if capacity is None:
        return {
            "reason": "capacity_missing_or_invalid",
            "n_samples": 0,
            "n_unique_stay_dates": 0,
            "trained_until_asof": asof_end_ts.strftime("%Y-%m-%d"),
            "window_months": window_months,
            "sample_stride_days": sample_stride_days,
            "cap_ratio_candidates": [],
        }

    sample_asof_dates = _build_sample_asof_dates(asof_end_ts, window_months, sample_stride_days)
    lt_cache: dict[str, pd.DataFrame] = {}
    residual_rates: list[float] = []
    n_unique_stay_dates = 0

    for asof_ts in sample_asof_dates:
        months = _months_around_asof(asof_ts, months_back=months_back, months_forward=months_forward)
        lt_dfs: list[pd.DataFrame] = []
        for ym in months:
            df_m = lt_cache.get(ym)
            if df_m is None:
                try:
                    df_m = _load_lt_data_csv(hotel_tag, ym)
                except FileNotFoundError:
                    continue
                except Exception as exc:
                    logger.warning("Failed to load lt_data for %s %s: %s", hotel_tag, ym, exc)
                    continue
                lt_cache[ym] = df_m
            if df_m is not None and not df_m.empty:
                lt_dfs.append(df_m)

        if not lt_dfs:
            continue

        lt_all = pd.concat(lt_dfs, axis=0)
        lt_all.index = pd.to_datetime(lt_all.index)

        baseline_curves_by_weekday: dict[int, pd.Series] = {}
        for weekday in range(7):
            history_wd = lt_all[lt_all.index.weekday == weekday]
            if history_wd.empty:
                continue
            baseline_curve = moving_average_recent_90days(
                lt_df=history_wd,
                as_of_date=asof_ts,
                lt_min=WEEKSHAPE_LT_MIN,
                lt_max=WEEKSHAPE_LT_MAX + WEEKSHAPE_W,
            )
            baseline_curves_by_weekday[weekday] = baseline_curve

        if not baseline_curves_by_weekday:
            continue

        try:
            _, detail_df = compute_weekshape_flow_factors(
                lt_df=lt_all,
                as_of_ts=asof_ts,
                baseline_curves_by_weekday=baseline_curves_by_weekday,
                hotel_tag=hotel_tag,
                lt_min=WEEKSHAPE_LT_MIN,
                lt_max=WEEKSHAPE_LT_MAX,
                w=WEEKSHAPE_W,
            )
        except Exception as exc:
            logger.warning("Failed to compute weekshape factors for %s %s: %s", hotel_tag, asof_ts, exc)
            continue

        if detail_df is None or detail_df.empty:
            continue

        # base-small definitions (keep isolated):
        # - gated == True when (n_events < WEEKSHAPE_MIN_EVENTS) or (abs(sum_base) < WEEKSHAPE_MIN_SUM_BASE)
        # - residual_pickup = max(sum_actual, 0.0)  (base unreliable / near-zero)
        # - residual_rate = residual_pickup / capacity
        # - quantiles: p90, p95, p975; cap_ratio_candidates = [p90, p95, p975]
        gated = detail_df.get("gated")
        sum_actual_series = detail_df.get("sum_actual")
        if gated is None or sum_actual_series is None:
            continue

        gated_mask = gated.fillna(False)
        gated_rows = detail_df.loc[gated_mask]
        n_events_series = gated_rows.get("n_events")
        if n_events_series is not None:
            n_events = pd.to_numeric(n_events_series, errors="coerce").fillna(0)
            n_unique_stay_dates += int(n_events.sum())

        for _, row in gated_rows.iterrows():
            sum_actual = pd.to_numeric(row.get("sum_actual", np.nan), errors="coerce")
            if pd.isna(sum_actual):
                continue
            residual_pickup = max(float(sum_actual), 0.0)
            residual_rate = residual_pickup / capacity
            if pd.isna(residual_rate):
                continue
            residual_rates.append(float(residual_rate))

    if not residual_rates:
        return {
            "reason": "no_gated_samples",
            "n_samples": 0,
            "n_unique_stay_dates": 0,
            "trained_until_asof": asof_end_ts.strftime("%Y-%m-%d"),
            "window_months": window_months,
            "sample_stride_days": sample_stride_days,
            "cap_ratio_candidates": [],
        }

    series = pd.Series(residual_rates, dtype=float)
    p90 = float(series.quantile(0.90))
    p95 = float(series.quantile(0.95))
    p975 = float(series.quantile(0.975))

    result: dict[str, Any] = {
        "p90": p90,
        "p95": p95,
        "p975": p975,
        "cap_ratio_candidates": [p90, p95, p975],
        "n_samples": int(series.size),
        "n_unique_stay_dates": int(n_unique_stay_dates),
        "trained_until_asof": asof_end_ts.strftime("%Y-%m-%d"),
        "window_months": window_months,
        "sample_stride_days": sample_stride_days,
    }

    logger.info(
        "base-small weekshape learning: hotel=%s trained_until_asof=%s window_months=%s stride_days=%s "
        "n_samples=%s p90=%.6f p95=%.6f p975=%.6f",
        hotel_tag,
        result["trained_until_asof"],
        window_months,
        sample_stride_days,
        result["n_samples"],
        p90,
        p95,
        p975,
    )

    return result
