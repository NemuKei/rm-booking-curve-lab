"""Simple forecasting utilities for booking curves.

This module provides logic helpers that work with LT (lead time) data in the
form of DataFrames (index = stay dates, columns = LT).  The functions defined
here are intentionally UI-agnostic so that the plotting layer can import and
reuse them.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from booking_curve.segment_adjustment import apply_segment_adjustment

HOTEL_TAG = "daikokucho"
PACE14_LOWER_LT_MIN = 7
PACE14_UPPER_LT = 14
PACE14_CLIP = (0.70, 1.30)
PACE14_CLIP_SPIKE = (0.85, 1.15)
PACE14_SPIKE_Q_LO = 0.01
PACE14_SPIKE_Q_HI = 0.995
PACE14_SPIKE_MIN_N = 20
PACE14_EPSILON = 1e-6

MARKET_PACE_LT_MIN = 15
MARKET_PACE_LT_MAX = 30
MARKET_PACE_CLIP = (0.95, 1.05)
MARKET_PACE_DECAY_K = 0.2


def _ensure_int_columns(columns: Iterable) -> list[int]:
    """Convert the provided column labels to integers."""

    try:
        return [int(col) for col in columns]
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError("Columns must be castable to int for LT alignment") from exc


def normalize_lt_columns(
    lt_df: pd.DataFrame,
    lt_min: int = -1,
    lt_max: int = 90,
) -> pd.DataFrame:
    """Normalize LT columns to the specified range.

    Parameters
    ----------
    lt_df:
        DataFrame whose index represents stay dates and whose columns represent
        lead times (LT).
    lt_min, lt_max:
        Inclusive bounds for the LT range to align against.

    Returns
    -------
    pd.DataFrame
        A copy of ``lt_df`` whose columns cover ``lt_min`` through ``lt_max`` in
        order. Missing LT columns are filled with ``NaN``.
    """

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    lt_range = list(range(lt_min, lt_max + 1))
    normalized = lt_df.copy()
    normalized.columns = _ensure_int_columns(normalized.columns)
    # Reindex the columns to the desired LT range; missing columns become NaN.
    normalized = normalized.reindex(columns=lt_range)
    return normalized


def _recent90_weight(age_days: int) -> float:
    """Weight helper for recent90 observations based on absolute age in days."""

    d = abs(age_days)
    if 0 <= d <= 14:
        return 3.0
    elif 15 <= d <= 30:
        return 2.0
    elif 31 <= d <= 90:
        return 1.0
    else:
        return 0.0


def _safe_divide(numerator: float, denominator: float, epsilon: float = PACE14_EPSILON) -> float:
    if pd.isna(numerator) or pd.isna(denominator):
        return np.nan
    if abs(denominator) <= epsilon:
        return np.nan
    return numerator / denominator


def _clip_value(value: float, low: float, high: float) -> float:
    if pd.isna(value):
        return np.nan
    return float(np.clip(value, low, high))


def build_pace14_spike_thresholds(
    history_df: pd.DataFrame,
    *,
    upper_lt: int = PACE14_UPPER_LT,
    lower_lt_min: int = PACE14_LOWER_LT_MIN,
    q_lo: float = PACE14_SPIKE_Q_LO,
    q_hi: float = PACE14_SPIKE_Q_HI,
    min_n: int = PACE14_SPIKE_MIN_N,
) -> dict[int, dict[str, float]]:
    """Build spike thresholds per lower LT for pace14 pickup deltas."""

    if history_df.empty:
        return {}

    df = history_df.copy()
    df.columns = _ensure_int_columns(df.columns)

    thresholds: dict[int, dict[str, float]] = {}
    for lower_lt in range(lower_lt_min, upper_lt + 1):
        if lower_lt not in df.columns or upper_lt not in df.columns:
            continue
        deltas = df[lower_lt] - df[upper_lt]
        deltas = pd.to_numeric(deltas, errors="coerce").dropna()
        n = int(deltas.shape[0])
        if n < min_n:
            continue
        thresholds[lower_lt] = {
            "q_lo": float(deltas.quantile(q_lo)),
            "q_hi": float(deltas.quantile(q_hi)),
            "n": float(n),
        }
    return thresholds


def _calc_pace14_pf(
    row: pd.Series,
    *,
    baseline_curve: pd.Series,
    lt_now: int,
    thresholds: dict[int, dict[str, float]] | None = None,
    lower_lt_min: int = PACE14_LOWER_LT_MIN,
    upper_lt: int = PACE14_UPPER_LT,
    clip_range: tuple[float, float] = PACE14_CLIP,
    clip_spike: tuple[float, float] = PACE14_CLIP_SPIKE,
    epsilon: float = PACE14_EPSILON,
) -> dict[str, float | int | bool]:
    """Calculate pace14 pickup factor and related diagnostics."""

    if lt_now > upper_lt:
        return {
            "lower_lt": lt_now,
            "upper_lt": upper_lt,
            "delta_actual": np.nan,
            "delta_base": np.nan,
            "pf_raw": 1.0,
            "pf_shrunk": 1.0,
            "pf_clipped": 1.0,
            "is_spike": False,
        }

    lower_lt = max(lt_now, lower_lt_min)
    if lower_lt > upper_lt:
        return {
            "lower_lt": lower_lt,
            "upper_lt": upper_lt,
            "delta_actual": np.nan,
            "delta_base": np.nan,
            "pf_raw": 1.0,
            "pf_shrunk": 1.0,
            "pf_clipped": 1.0,
            "is_spike": False,
        }

    actual_lower = pd.to_numeric(row.get(lower_lt, np.nan), errors="coerce")
    actual_upper = pd.to_numeric(row.get(upper_lt, np.nan), errors="coerce")
    delta_actual = actual_lower - actual_upper

    base_lower = pd.to_numeric(baseline_curve.get(lower_lt, np.nan), errors="coerce")
    base_upper = pd.to_numeric(baseline_curve.get(upper_lt, np.nan), errors="coerce")
    delta_base = base_lower - base_upper

    pf_raw = _safe_divide(float(delta_actual), float(delta_base), epsilon=epsilon)
    if pd.isna(pf_raw):
        pf_raw = 1.0

    alpha = (upper_lt - lower_lt) / 7.0
    pf_shrunk = 1.0 + alpha * (pf_raw - 1.0)

    is_spike = False
    thresholds = thresholds or {}
    threshold = thresholds.get(lower_lt)
    if threshold is not None and not pd.isna(delta_actual):
        q_lo = threshold.get("q_lo", np.nan)
        q_hi = threshold.get("q_hi", np.nan)
        if not pd.isna(q_lo) and not pd.isna(q_hi):
            is_spike = bool(delta_actual < q_lo or delta_actual > q_hi)

    if is_spike:
        pf_clipped = _clip_value(pf_shrunk, *clip_spike)
    else:
        pf_clipped = _clip_value(pf_shrunk, *clip_range)

    return {
        "lower_lt": lower_lt,
        "upper_lt": upper_lt,
        "delta_actual": float(delta_actual) if not pd.isna(delta_actual) else np.nan,
        "delta_base": float(delta_base) if not pd.isna(delta_base) else np.nan,
        "pf_raw": float(pf_raw),
        "pf_shrunk": float(pf_shrunk),
        "pf_clipped": float(pf_clipped),
        "is_spike": bool(is_spike),
    }


def build_curve_from_final(
    baseline_curve: pd.Series,
    final_forecast: float,
    *,
    epsilon: float = PACE14_EPSILON,
) -> pd.Series:
    """Scale a baseline curve so that LT=-1 matches the final forecast."""

    baseline_curve = baseline_curve.copy()
    baseline_curve.index = baseline_curve.index.astype(int)
    base_final = pd.to_numeric(baseline_curve.get(-1, np.nan), errors="coerce")
    if pd.isna(base_final) or abs(float(base_final)) <= epsilon:
        return pd.Series(dtype=float)
    ratios = baseline_curve / float(base_final)
    return ratios * float(final_forecast)


def forecast_final_from_pace14(
    lt_df: pd.DataFrame,
    baseline_curve: pd.Series,
    history_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    capacity: float,
    *,
    lt_min: int = 0,
    lt_max: int = 90,
) -> tuple[pd.Series, pd.DataFrame]:
    """Forecast final rooms per stay date using pace14 adjustments."""

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    working_df = lt_df.copy()
    working_df.index = pd.to_datetime(working_df.index)
    working_df.columns = _ensure_int_columns(working_df.columns)
    as_of_ts = pd.Timestamp(as_of_date)

    baseline_curve = baseline_curve.copy()
    baseline_curve.index = baseline_curve.index.astype(int)
    base_final = pd.to_numeric(baseline_curve.get(-1, np.nan), errors="coerce")

    thresholds = build_pace14_spike_thresholds(history_df)

    forecasts: dict[pd.Timestamp, float] = {}
    details: dict[pd.Timestamp, dict[str, float | int | bool]] = {}

    future_df = working_df.loc[working_df.index >= as_of_ts]
    for stay_date, row in future_df.iterrows():
        lt_now = (stay_date - as_of_ts).days
        if lt_now < lt_min or lt_now > lt_max:
            forecasts[stay_date] = np.nan
            continue

        current_oh = pd.to_numeric(row.get(lt_now, np.nan), errors="coerce")
        base_now = pd.to_numeric(baseline_curve.get(lt_now, np.nan), errors="coerce")

        if any(pd.isna(val) for val in (current_oh, base_now, base_final)):
            forecasts[stay_date] = np.nan
            continue

        pf_info = _calc_pace14_pf(
            row,
            baseline_curve=baseline_curve,
            lt_now=lt_now,
            thresholds=thresholds,
        )

        base_delta = float(base_final - base_now)
        final_forecast = float(current_oh + pf_info["pf_clipped"] * base_delta)

        if not pd.isna(final_forecast):
            final_forecast = min(final_forecast, capacity)

        forecasts[stay_date] = final_forecast
        pf_info.update({"lt_now": lt_now})
        details[stay_date] = pf_info

    return pd.Series(forecasts, dtype=float), pd.DataFrame.from_dict(details, orient="index")


def _market_pace_raw(
    lt_df: pd.DataFrame,
    baseline_curves: dict[int, pd.Series],
    as_of_ts: pd.Timestamp,
    *,
    upper_lt: int = PACE14_UPPER_LT,
) -> float:
    total_actual = 0.0
    total_base = 0.0

    df = lt_df.copy()
    df.index = pd.to_datetime(df.index)
    df.columns = _ensure_int_columns(df.columns)

    for stay_date, row in df.iterrows():
        lt_now = (stay_date - as_of_ts).days
        if lt_now < 0 or lt_now > upper_lt:
            continue
        if lt_now not in df.columns or (lt_now + 1) not in df.columns:
            continue
        current_oh = pd.to_numeric(row.get(lt_now, np.nan), errors="coerce")
        next_oh = pd.to_numeric(row.get(lt_now + 1, np.nan), errors="coerce")
        if pd.isna(current_oh) or pd.isna(next_oh):
            continue
        pickup = float(current_oh - next_oh)

        baseline_curve = baseline_curves.get(stay_date.weekday())
        if baseline_curve is None:
            continue
        base_now = pd.to_numeric(baseline_curve.get(lt_now, np.nan), errors="coerce")
        base_next = pd.to_numeric(baseline_curve.get(lt_now + 1, np.nan), errors="coerce")
        if pd.isna(base_now) or pd.isna(base_next):
            continue
        base_pickup = float(base_now - base_next)

        total_actual += pickup
        total_base += base_pickup

    if abs(total_base) <= PACE14_EPSILON:
        return np.nan
    return total_actual / total_base


def compute_market_pace_7d(
    lt_df: pd.DataFrame,
    as_of_ts: pd.Timestamp,
    *,
    history_by_weekday: dict[int, pd.DataFrame] | None = None,
    baseline_curves: dict[int, pd.Series] | None = None,
    lt_min: int = -1,
    lt_max: int = 90,
    min_count: int = 1,
    days: int = 7,
) -> tuple[float, pd.DataFrame]:
    """Compute 7-day market pace average and daily diagnostics."""

    records = []
    for offset in range(days):
        target_date = as_of_ts - pd.Timedelta(days=offset)
        if history_by_weekday:
            baseline_curves_for_date = {}
            for weekday, history_df in history_by_weekday.items():
                if history_df.empty:
                    continue
                baseline_curves_for_date[weekday] = moving_average_recent_90days(
                    lt_df=history_df,
                    as_of_date=target_date,
                    lt_min=lt_min,
                    lt_max=lt_max,
                    min_count=min_count,
                )
        else:
            baseline_curves_for_date = baseline_curves or {}

        mp_raw = _market_pace_raw(lt_df, baseline_curves_for_date, target_date)
        records.append({"as_of_date": target_date.normalize(), "mp_raw": mp_raw})

    df = pd.DataFrame(records).sort_values("as_of_date")
    mp_7d = float(df["mp_raw"].mean(skipna=True)) if not df.empty else np.nan
    return mp_7d, df


def forecast_final_from_pace14_market(
    lt_df: pd.DataFrame,
    baseline_curve: pd.Series,
    history_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    capacity: float,
    *,
    market_pace_7d: float,
    lt_min: int = 0,
    lt_max: int = 90,
    decay_k: float = MARKET_PACE_DECAY_K,
) -> tuple[pd.Series, pd.DataFrame]:
    """Forecast final rooms per stay date using pace14 + market pace adjustments."""

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    working_df = lt_df.copy()
    working_df.index = pd.to_datetime(working_df.index)
    working_df.columns = _ensure_int_columns(working_df.columns)
    as_of_ts = pd.Timestamp(as_of_date)

    baseline_curve = baseline_curve.copy()
    baseline_curve.index = baseline_curve.index.astype(int)
    base_final = pd.to_numeric(baseline_curve.get(-1, np.nan), errors="coerce")

    thresholds = build_pace14_spike_thresholds(history_df)

    forecasts: dict[pd.Timestamp, float] = {}
    details: dict[pd.Timestamp, dict[str, float | int | bool]] = {}
    market_pace_value = 1.0 if pd.isna(market_pace_7d) else float(market_pace_7d)

    future_df = working_df.loc[working_df.index >= as_of_ts]
    for stay_date, row in future_df.iterrows():
        lt_now = (stay_date - as_of_ts).days
        if lt_now < lt_min or lt_now > lt_max:
            forecasts[stay_date] = np.nan
            continue

        current_oh = pd.to_numeric(row.get(lt_now, np.nan), errors="coerce")
        base_now = pd.to_numeric(baseline_curve.get(lt_now, np.nan), errors="coerce")

        if any(pd.isna(val) for val in (current_oh, base_now, base_final)):
            forecasts[stay_date] = np.nan
            continue

        base_delta = float(base_final - base_now)
        pf_info = _calc_pace14_pf(
            row,
            baseline_curve=baseline_curve,
            lt_now=lt_now,
            thresholds=thresholds,
        )
        pf_value = pf_info["pf_clipped"]

        market_factor = 1.0
        market_beta = np.nan
        if MARKET_PACE_LT_MIN <= lt_now <= MARKET_PACE_LT_MAX:
            market_beta = float(np.exp(-decay_k * (lt_now - MARKET_PACE_LT_MIN)))
            raw_factor = 1.0 + market_beta * (market_pace_value - 1.0)
            market_factor = _clip_value(raw_factor, *MARKET_PACE_CLIP)

        if lt_now <= PACE14_UPPER_LT:
            final_forecast = float(current_oh + pf_value * base_delta)
        elif MARKET_PACE_LT_MIN <= lt_now <= MARKET_PACE_LT_MAX:
            final_forecast = float(current_oh + market_factor * base_delta)
        else:
            final_forecast = float(current_oh + base_delta)

        if not pd.isna(final_forecast):
            final_forecast = min(final_forecast, capacity)

        forecasts[stay_date] = final_forecast
        pf_info.update(
            {
                "lt_now": lt_now,
                "market_pace_7d": float(market_pace_7d)
                if not pd.isna(market_pace_7d)
                else np.nan,
                "market_beta": market_beta,
                "market_factor": market_factor,
            }
        )
        details[stay_date] = pf_info

    return pd.Series(forecasts, dtype=float), pd.DataFrame.from_dict(details, orient="index")


def moving_average_3months(
    lt_df_list: list[pd.DataFrame],
    lt_min: int = -1,
    lt_max: int = 90,
) -> pd.Series:
    """Compute a simple average booking curve from multiple months of LT data.

    Parameters
    ----------
    lt_df_list:
        List of LT DataFrames (already filtered to a specific weekday). Each
        DataFrame should contain data for a single month.
    lt_min, lt_max:
        Inclusive bounds for the LT range to include in the average.

    Returns
    -------
    pd.Series
        Series whose index represents LTs (``lt_min`` to ``lt_max``) and whose
        values represent the average number of rooms.
    """

    if not lt_df_list:
        raise ValueError("lt_df_list must contain at least one DataFrame")

    normalized_list = [normalize_lt_columns(df, lt_min=lt_min, lt_max=lt_max) for df in lt_df_list]

    combined = pd.concat(normalized_list, axis=0)
    avg_curve = combined.mean(axis=0, skipna=True)
    avg_curve.index = pd.Index(range(lt_min, lt_max + 1), dtype=int)
    return avg_curve


def forecast_final_from_avg(
    lt_df: pd.DataFrame,
    avg_curve: pd.Series,
    as_of_date: pd.Timestamp,
    capacity: float,
    lt_min: int = 0,
    lt_max: int = 90,
) -> pd.Series:
    """Forecast final rooms per stay date using an average curve and a cap."""

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    working_df = lt_df.copy()
    working_df.index = pd.to_datetime(working_df.index)
    working_df.columns = _ensure_int_columns(working_df.columns)
    as_of_ts = pd.Timestamp(as_of_date)

    future_df = working_df.loc[working_df.index >= as_of_ts]
    forecasts: dict[pd.Timestamp, float] = {}

    avg_final = avg_curve.get(-1, np.nan)

    for stay_date, row in future_df.iterrows():
        lt_now = (stay_date - as_of_ts).days

        if lt_now < lt_min or lt_now > lt_max:
            forecasts[stay_date] = np.nan
            continue

        current_oh = row.get(lt_now, np.nan)
        avg_now = avg_curve.get(lt_now, np.nan)

        if any(pd.isna(val) for val in (current_oh, avg_now, avg_final)):
            forecasts[stay_date] = np.nan
            continue

        delta = avg_final - avg_now
        forecast = current_oh + delta

        if not pd.isna(forecast):
            forecast = min(forecast, capacity)

        forecasts[stay_date] = forecast

    return pd.Series(forecasts, dtype=float)


def moving_average_recent_90days(
    lt_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    lt_min: int = -1,
    lt_max: int = 90,
    min_count: int = 1,
) -> pd.Series:
    """Compute LT-wise averages using a moving 90-day stay-date window.

    ``min_count`` requires a minimum number of non-missing observations per LT
    before emitting an average; insufficient samples yield ``NaN``.
    """

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    df = lt_df.copy()
    df.index = pd.to_datetime(df.index)

    lt_col_map: dict[int, str] = {}
    for col in df.columns:
        try:
            lt_value = int(col)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError("LT columns must be castable to int") from exc
        lt_col_map[lt_value] = col

    as_of_ts = pd.to_datetime(as_of_date)

    result: dict[int, float] = {}
    for lt in range(lt_min, lt_max + 1):
        if lt not in lt_col_map:
            result[lt] = np.nan
            continue

        start = as_of_ts - pd.Timedelta(days=90 - lt)
        end = as_of_ts + pd.Timedelta(days=lt)

        mask = (df.index >= start) & (df.index <= end)
        values = df.loc[mask, lt_col_map[lt]]

        count = values.notna().sum()
        mean = values.mean(skipna=True)

        if count < min_count:
            result[lt] = np.nan
        else:
            result[lt] = mean

    result_series = pd.Series(result, dtype=float)
    result_series.index.name = "LT"
    result_series.sort_index(inplace=True)
    return result_series


def moving_average_recent_90days_weighted(
    lt_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    lt_min: int = -1,
    lt_max: int = 90,
    weights: tuple[float, float, float] | None = None,
    min_count: int = 1,
) -> pd.Series:
    """Compute LT-wise weighted averages using a moving 90-day stay-date window.

    Observations are weighted by their absolute age in days relative to
    ``as_of_date`` with the following scheme: 0–14 days = 3.0, 15–30 days =
    2.0, 31–90 days = 1.0. Observations outside that range are ignored. The
    ``weights`` argument can be used to override these defaults by passing a
    tuple ``(w_recent, w_mid, w_old)``; when omitted, ``(3.0, 2.0, 1.0)`` is
    applied. ``min_count`` requires a minimum number of non-missing
    observations per LT before computing the weighted mean; insufficient
    samples yield ``NaN``.
    """

    if lt_min > lt_max:
        raise ValueError("lt_min must be less than or equal to lt_max")

    df = lt_df.copy()
    df.index = pd.to_datetime(df.index)

    lt_col_map: dict[int, str] = {}
    for col in df.columns:
        try:
            lt_value = int(col)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError("LT columns must be castable to int") from exc
        lt_col_map[lt_value] = col

    as_of_ts = pd.to_datetime(as_of_date)

    if weights is None:
        weight_func = _recent90_weight
    else:
        if len(weights) != 3:
            raise ValueError("weights must contain exactly three values")
        w_recent, w_mid, w_old = weights

        def weight_func(age_days: int) -> float:
            d = abs(age_days)
            if 0 <= d <= 14:
                return w_recent
            elif 15 <= d <= 30:
                return w_mid
            elif 31 <= d <= 90:
                return w_old
            else:
                return 0.0

    result: dict[int, float] = {}
    for lt in range(lt_min, lt_max + 1):
        if lt not in lt_col_map:
            result[lt] = np.nan
            continue

        start = as_of_ts - pd.Timedelta(days=90 - lt)
        end = as_of_ts + pd.Timedelta(days=lt)

        mask = (df.index >= start) & (df.index <= end)
        values = df.loc[mask, lt_col_map[lt]]

        count = values.notna().sum()
        if count < min_count:
            result[lt] = np.nan
            continue

        weighted_sum = 0.0
        weight_sum = 0.0
        for obs_date, value in values.items():
            diff_days = (obs_date - as_of_ts).days
            weight = weight_func(diff_days)
            if weight == 0.0 or pd.isna(value):
                continue
            weighted_sum += value * weight
            weight_sum += weight

        if weight_sum == 0.0:
            result[lt] = np.nan
        else:
            result[lt] = weighted_sum / weight_sum

    result_series = pd.Series(result, dtype=float)
    result_series.index.name = "LT"
    result_series.sort_index(inplace=True)
    return result_series


def forecast_month_from_recent90(
    df_target: pd.DataFrame,
    forecasts: dict[pd.Timestamp, float],
    as_of_ts: pd.Timestamp,
    hotel_tag: str | None = None,
) -> pd.DataFrame:
    """Assemble daily forecasts for the recent90 model with segment adjustment."""

    result = pd.Series(forecasts, dtype=float)
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
        except Exception:  # pragma: no cover - defensive
            continue

    if act_col is not None:
        actual_series = df_target[act_col]
        actual_series.index = all_dates
        out_df["actual_rooms"] = pd.to_numeric(actual_series, errors="coerce").astype("Float64")
    else:
        out_df["actual_rooms"] = pd.Series(pd.NA, index=all_dates, dtype="Float64")

    out_df["forecast_rooms"] = result.reindex(all_dates)
    out_df["forecast_rooms_int"] = out_df["forecast_rooms"].round().astype("Int64")

    out_df["projected_rooms"] = out_df["actual_rooms"].where(
        out_df.index < as_of_ts,
        out_df["forecast_rooms_int"].astype("Float64"),
    )
    out_df["projected_rooms"] = pd.to_numeric(out_df["projected_rooms"], errors="coerce").astype("Float64")

    hotel_tag_value = hotel_tag or HOTEL_TAG
    out_df = apply_segment_adjustment(out_df, hotel_tag=hotel_tag_value)

    return out_df


if __name__ == "__main__":  # pragma: no cover - optional dev test
    # Simple self-check using mock data for three months.
    date_index = pd.date_range("2025-04-01", periods=2, freq="D")
    df_apr = pd.DataFrame({-1: [5, 6], 0: [10, 8], 1: [15, 14]}, index=date_index)
    df_may = df_apr + 1
    df_jun = df_apr + 2

    avg = moving_average_3months([df_apr, df_may, df_jun], lt_min=-1, lt_max=2)
    print("Average curve:\n", avg)
