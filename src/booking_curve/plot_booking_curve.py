"""Plot booking curves grouped by weekday using predefined lead time pitches."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LEAD_TIME_PITCHES: list[int] = [
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


def _normalize_datetime_index(lt_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``lt_df`` whose index is ``DatetimeIndex``."""

    normalized = lt_df.copy()
    normalized.index = pd.to_datetime(normalized.index)
    return normalized


def _ensure_integer_columns(lt_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``lt_df`` whose columns are integers sorted ascending."""

    coerced = lt_df.copy()
    coerced.columns = pd.Index([int(col) for col in coerced.columns])
    coerced = coerced.sort_index(axis=1)
    return coerced


def filter_by_weekday(lt_df: pd.DataFrame, weekday: int) -> pd.DataFrame:
    """Filter ``lt_df`` to stays whose weekday matches ``weekday``."""

    if weekday < 0 or weekday > 6:
        raise ValueError("weekday must be between 0 (Mon) and 6 (Sun)")

    normalized = _normalize_datetime_index(lt_df)
    mask = normalized.index.weekday == weekday
    filtered = normalized.loc[mask].copy()
    return filtered


def compute_average_curve(lt_df: pd.DataFrame) -> pd.Series:
    """Compute the mean number of rooms per lead time."""

    if lt_df.empty:
        return pd.Series(dtype=float)

    coerced = _ensure_integer_columns(lt_df)
    return coerced.mean(axis=0, skipna=True)


def _extract_y_values(row: pd.Series, lead_times: Iterable[int]) -> list[float]:
    """Extract y-values for ``lead_times`` using NaN for missing LTs."""

    return [row.get(lt, np.nan) for lt in lead_times]


def plot_booking_curves_for_weekday(
    lt_df: pd.DataFrame,
    weekday: int,
    title: str = "",
    output_path: str | None = None,
) -> None:
    """Plot booking curves for ``weekday`` stays along with their average curve."""

    normalized = _normalize_datetime_index(lt_df)
    df_week = filter_by_weekday(normalized, weekday)
    df_week = _ensure_integer_columns(df_week)

    if df_week.empty:
        raise ValueError("No booking data for the specified weekday.")

    x_positions = list(range(len(LEAD_TIME_PITCHES)))
    fig, ax = plt.subplots(figsize=(12, 6))

    label_added = False
    for _, row in df_week.iterrows():
        y_values = _extract_y_values(row, LEAD_TIME_PITCHES)
        label = "Daily curves" if not label_added else None
        ax.plot(
            x_positions,
            y_values,
            color="lightgray",
            linewidth=1,
            label=label,
        )
        label_added = True

    avg_curve = compute_average_curve(df_week)
    y_values_avg = avg_curve.reindex(LEAD_TIME_PITCHES).to_list()
    ax.plot(
        x_positions,
        y_values_avg,
        color="tab:blue",
        linewidth=2.5,
        label="Average curve",
    )

    labels = ["ACT" if lt == -1 else str(lt) for lt in LEAD_TIME_PITCHES]
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Lead Time (days)")
    ax.set_ylabel("Rooms")
    ax.set_ylim(0, 180)
    ax.set_yticks(range(0, 181, 20))
    ax.set_title(title)
    ax.legend()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plot weekday booking curves from CSV.")
    parser.add_argument("csv_path", type=str, help="Path to LT data CSV file")
    parser.add_argument("weekday", type=int, help="Weekday number (0=Mon, 6=Sun)")
    parser.add_argument("--title", type=str, default="", help="Title of the plot")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save the figure instead of showing it",
    )
    args = parser.parse_args()

    lt_df = pd.read_csv(args.csv_path, index_col=0)
    plot_booking_curves_for_weekday(
        lt_df,
        weekday=args.weekday,
        title=args.title,
        output_path=args.output,
    )
