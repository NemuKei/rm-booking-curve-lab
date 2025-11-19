"""Simple forecasting utilities for booking curves.

This module provides logic helpers that work with LT (lead time) data in the
form of DataFrames (index = stay dates, columns = LT).  The functions defined
here are intentionally UI-agnostic so that the plotting layer can import and
reuse them.
"""
from __future__ import annotations

from typing import Iterable

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


if __name__ == "__main__":  # pragma: no cover - optional dev test
    # Simple self-check using mock data for three months.
    date_index = pd.date_range("2025-04-01", periods=2, freq="D")
    df_apr = pd.DataFrame({-1: [5, 6], 0: [10, 8], 1: [15, 14]}, index=date_index)
    df_may = df_apr + 1
    df_jun = df_apr + 2

    avg = moving_average_3months([df_apr, df_may, df_jun], lt_min=-1, lt_max=2)
    print("Average curve:\n", avg)
