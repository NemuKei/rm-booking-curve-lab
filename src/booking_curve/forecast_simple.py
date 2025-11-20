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

    normalized_list = [
        normalize_lt_columns(df, lt_min=lt_min, lt_max=lt_max) for df in lt_df_list
    ]

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
) -> pd.Series:
    """Compute LT-wise averages using a moving 90-day stay-date window."""

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

        if values.empty:
            result[lt] = np.nan
        else:
            result[lt] = values.mean(skipna=True)

    result_series = pd.Series(result, dtype=float)
    result_series.index.name = "LT"
    result_series.sort_index(inplace=True)
    return result_series


if __name__ == "__main__":  # pragma: no cover - optional dev test
    # Simple self-check using mock data for three months.
    date_index = pd.date_range("2025-04-01", periods=2, freq="D")
    df_apr = pd.DataFrame({-1: [5, 6], 0: [10, 8], 1: [15, 14]}, index=date_index)
    df_may = df_apr + 1
    df_jun = df_apr + 2

    avg = moving_average_3months([df_apr, df_may, df_jun], lt_min=-1, lt_max=2)
    print("Average curve:\n", avg)
