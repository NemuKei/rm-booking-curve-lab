"""Utilities for plotting booking curves grouped by weekday."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd

LEAD_TIME_PITCHES = [
    90,
    84,
    78,
    72,
    67,
    60,
    53,
    46,
    39,
    32,
    29,
    26,
    23,
    20,
    18,
    17,
    16,
    15,
    14,
    13,
    12,
    11,
    10,
    9,
    8,
    7,
    6,
    5,
    4,
    3,
    2,
    1,
    0,
    -1,
]


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` whose index is a DatetimeIndex."""

    if isinstance(df.index, pd.DatetimeIndex):
        return df.copy()

    result = df.copy()
    result.index = pd.to_datetime(result.index)
    return result


def _coerce_lt_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with integer-sorted lead time columns."""

    columns = pd.Index([int(col) for col in df.columns])
    result = df.copy()
    result.columns = columns
    result = result.sort_index(axis=1)
    return result


def filter_by_weekday(lt_df: pd.DataFrame, weekday: int) -> pd.DataFrame:
    """Return only the stays whose weekday matches ``weekday``."""

    if weekday < 0 or weekday > 6:
        raise ValueError("weekday must be between 0 (Mon) and 6 (Sun)")

    normalized = _ensure_datetime_index(lt_df)
    mask = normalized.index.weekday == weekday
    filtered = normalized.loc[mask]
    filtered.index = filtered.index.normalize()
    return filtered


def compute_average_curve(lt_df: pd.DataFrame) -> pd.Series:
    """Compute the average curve (mean per lead time) from ``lt_df``."""

    if lt_df.empty:
        return pd.Series(dtype=float)

    coerced = _coerce_lt_columns(lt_df)
    return coerced.mean(axis=0, skipna=True)


@dataclass
class _DailyCurve:
    lead_times: Iterable[int]
    values: pd.Series


def _plot_daily_curves(ax: plt.Axes, daily_curves: list[_DailyCurve]) -> None:
    """Plot daily booking curves using light-weight lines."""

    label_added = False
    for curve in daily_curves:
        label = "Daily curves" if not label_added else "_nolegend_"
        ax.plot(
            curve.lead_times,
            curve.values,
            color="gray",
            linewidth=0.8,
            alpha=0.6,
            label=label,
        )
        label_added = True


def _format_xticks(ax: plt.Axes, lead_time_range: tuple[int, int]) -> None:
    """Configure x-axis ticks using the configured lead-time pitches."""

    min_lt, max_lt = lead_time_range
    ticks = [lt for lt in LEAD_TIME_PITCHES if min_lt <= lt <= max_lt]
    if not ticks:
        ticks = [min_lt, max_lt]

    labels = ["ACT" if lt == -1 else str(lt) for lt in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)


def plot_booking_curves_for_weekday(
    lt_df: pd.DataFrame,
    weekday: int,
    title: str = "",
    output_path: str | None = None,
) -> None:
    """Plot booking curves for a specific weekday and their average."""

    normalized = _ensure_datetime_index(lt_df)
    weekday_df = filter_by_weekday(normalized, weekday)

    if weekday_df.empty:
        raise ValueError("No booking data for the specified weekday.")

    weekday_df = _coerce_lt_columns(weekday_df)

    lead_times = weekday_df.columns
    min_lt = int(lead_times.min())
    max_lt = int(lead_times.max())

    fig, ax = plt.subplots(figsize=(10, 6))

    daily_curves = [
        _DailyCurve(lead_times=lead_times, values=row)
        for _, row in weekday_df.iterrows()
    ]
    _plot_daily_curves(ax, daily_curves)

    avg_curve = compute_average_curve(weekday_df)
    ax.plot(
        avg_curve.index,
        avg_curve.values,
        color="tab:blue",
        linewidth=2.5,
        label="Average curve",
    )

    _format_xticks(ax, (min_lt, max_lt))
    ax.set_xlabel("Lead Time (days)")
    ax.set_ylabel("Rooms")
    if title:
        ax.set_title(title)
    ax.legend()
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)

    if output_path:
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    import numpy as np

    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    columns = list(range(-1, 31))
    data = np.random.randint(0, 100, size=(len(dates), len(columns)))
    sample_df = pd.DataFrame(data, index=dates, columns=columns)
    plot_booking_curves_for_weekday(sample_df, weekday=0, title="Sample Monday curves")
