"""Utilities for visualizing booking curves grouped by weekday."""
from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.rcParams["font.family"] = "Meiryo"
matplotlib.rcParams["axes.unicode_minus"] = False

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


def _normalize_datetime_index(lt_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``lt_df`` with a DatetimeIndex."""

    normalized = lt_df.copy()
    normalized.index = pd.to_datetime(normalized.index)
    return normalized


def _coerce_lt_columns(lt_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure lead-time columns are integers for consistent lookup."""

    coerced = lt_df.copy()
    coerced.columns = pd.Index([int(col) for col in coerced.columns])
    return coerced


def filter_by_weekday(lt_df: pd.DataFrame, weekday: int) -> pd.DataFrame:
    """Return rows whose stay-date weekday matches ``weekday``."""

    if not 0 <= weekday <= 6:
        raise ValueError("weekday must be between 0 (Mon) and 6 (Sun)")

    normalized = _normalize_datetime_index(lt_df)
    mask = normalized.index.weekday == weekday
    filtered = normalized.loc[mask]
    return _coerce_lt_columns(filtered)


def compute_average_curve(lt_df: pd.DataFrame) -> pd.Series:
    """Return the average room pickup for each lead-time pitch."""

    if lt_df.empty:
        return pd.Series(dtype=float)

    coerced = _coerce_lt_columns(lt_df)
    return coerced.mean(axis=0, skipna=True)


def export_weekday_lt_table(lt_df: pd.DataFrame, weekday: int, output_path: str) -> None:
    """Save the raw LT table filtered by weekday as CSV."""

    normalized = _normalize_datetime_index(lt_df)
    df_week = filter_by_weekday(normalized, weekday)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_week.to_csv(output_file)


def plot_booking_curves_for_weekday(
    lt_df: pd.DataFrame,
    weekday: int,
    title: str = "",
    output_path: str | None = None,
) -> None:
    """Plot booking curves for the specified weekday following Excel-like styling."""

    normalized = _normalize_datetime_index(lt_df)
    df_week = filter_by_weekday(normalized, weekday)

    if df_week.empty:
        print("Warning: no booking data for the specified weekday.")
        return

    x_positions = np.arange(len(LEAD_TIME_PITCHES))
    labels = ["ACT" if lt == -1 else str(lt) for lt in LEAD_TIME_PITCHES]

    fig, ax = plt.subplots(figsize=(12, 5))

    stay_dates = sorted(df_week.index)
    cmap = plt.cm.get_cmap("tab10", len(stay_dates))
    for i, stay_date in enumerate(stay_dates):
        row = df_week.loc[stay_date]
        y_values = [row.get(lt, np.nan) for lt in LEAD_TIME_PITCHES]
        stay_date_label = stay_date.strftime("%m/%d")
        ax.plot(
            x_positions,
            y_values,
            color=cmap(i),
            linewidth=1.1,
            alpha=0.8,
            label=stay_date_label,
        )

    avg_series = compute_average_curve(df_week)
    y_avg = [avg_series.get(lt, np.nan) for lt in LEAD_TIME_PITCHES]
    ax.plot(
        x_positions,
        y_avg,
        linewidth=2.5,
        color="tab:blue",
        label="Average curve",
    )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Lead Time (days)")

    ax.set_ylabel("Rooms")
    ax.set_ylim(0, 180)
    ax.set_yticks(range(0, 181, 20))
    ax.set_yticks(range(0, 181, 10), minor=True)

    ax.grid(axis="y", which="major", linestyle="--", alpha=0.3)
    ax.grid(axis="y", which="minor", linestyle=":", alpha=0.15)
    ax.grid(axis="x", which="major", linestyle=":", alpha=0.15)

    ax.set_title(title)
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
        frameon=True,
        fontsize=8,
    )

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_file, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    csv_path = input("Enter path to LT data CSV: ").strip()
    if not csv_path:
        raise SystemExit("CSV path is required.")

    df = pd.read_csv(csv_path, index_col=0)
    plot_booking_curves_for_weekday(
        df,
        weekday=4,
        title="Friday Booking Curves",
    )
