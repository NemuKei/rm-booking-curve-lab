from __future__ import annotations

from typing import Literal, Optional

import numpy as np
import pandas as pd


def _is_int_like(label: object) -> bool:
    """Return True if the label can be interpreted as an integer."""
    if isinstance(label, (int, np.integer)):
        return True
    if isinstance(label, str):
        try:
            int(label)
        except (TypeError, ValueError):
            return False
        return True
    return False


def _apply_nocb_series(series: pd.Series, max_gap: Optional[int]) -> pd.Series:
    """Fill NaN by extending newer LT values toward older LT in ascending order."""
    filled = series.copy()
    last_val: object | None = None
    gap = 0

    for idx in series.index:
        value = series.loc[idx]
        if pd.isna(value):
            if last_val is None:
                continue
            gap += 1
            if max_gap is None or gap <= max_gap:
                filled.loc[idx] = last_val
            continue

        last_val = value
        gap = 0

    return filled


def apply_nocb_along_lt(
    df: pd.DataFrame,
    *,
    axis: Literal["columns", "index"] = "columns",
    max_gap: Optional[int] = None,
) -> pd.DataFrame:
    """Apply LOCF-style NOCB along the LT axis without mutating the input.

    For LT labels, smaller LT (closer stay_date) values are propagated toward older LT
    positions while preserving non-LT labels untouched.
    """

    if df.empty:
        return df.copy()

    if axis not in {"columns", "index"}:
        raise ValueError("axis must be 'columns' or 'index'")

    result = df.copy()

    if axis == "columns":
        lt_columns = [col for col in df.columns if _is_int_like(col)]
        if not lt_columns:
            return result

        lt_sorted = sorted(lt_columns, key=lambda x: int(x))
        for idx in result.index:
            row = result.loc[idx, lt_sorted]
            result.loc[idx, lt_sorted] = _apply_nocb_series(row, max_gap)
        return result

    lt_index = [idx for idx in df.index if _is_int_like(idx)]
    if not lt_index:
        return result

    lt_sorted = sorted(lt_index, key=lambda x: int(x))
    for col in result.columns:
        series = result.loc[lt_sorted, col]
        result.loc[lt_sorted, col] = _apply_nocb_series(series, max_gap)

    return result


def diff_mask_na_before_after(original: pd.DataFrame, filled: pd.DataFrame) -> pd.DataFrame:
    """Return mask where values were NaN in original and filled in the result."""

    return original.isna() & filled.notna()
