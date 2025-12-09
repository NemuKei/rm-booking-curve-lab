from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from booking_curve.config import OUTPUT_DIR

STANDARD_COLUMNS = [
    "hotel_id",
    "as_of_date",
    "stay_date",
    "rooms_oh",
    "pax_oh",
    "revenue_oh",
]


def get_daily_snapshots_path(hotel_id: str) -> Path:
    """Return the standard CSV path for the provided hotel identifier."""
    if not hotel_id:
        raise ValueError("hotel_id must be a non-empty string")
    return OUTPUT_DIR / f"daily_snapshots_{hotel_id}.csv"


def _ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the dataframe includes all STANDARD_COLUMNS, filling missing ones with pd.NA."""
    df_copy = df.copy()
    for column in STANDARD_COLUMNS:
        if column not in df_copy.columns:
            df_copy[column] = pd.NA
    return df_copy


def normalize_daily_snapshots_df(
    df: pd.DataFrame,
    hotel_id: Optional[str] = None,
    as_of_date: "pd.Timestamp | str | None" = None,
) -> pd.DataFrame:
    """Normalize a daily snapshots dataframe for safe CSV I/O."""
    df_normalized = _ensure_standard_columns(df.copy())

    if hotel_id is not None:
        df_normalized["hotel_id"] = hotel_id

    if as_of_date is not None:
        as_of_ts = pd.to_datetime(as_of_date, errors="coerce")
        if pd.isna(as_of_ts):
            raise ValueError("as_of_date must be convertible to a valid date")
        df_normalized["as_of_date"] = as_of_ts

    if "stay_date" in df_normalized.columns:
        df_normalized["stay_date"] = pd.to_datetime(
            df_normalized["stay_date"], errors="coerce"
        )
    if "as_of_date" in df_normalized.columns:
        df_normalized["as_of_date"] = pd.to_datetime(
            df_normalized["as_of_date"], errors="coerce"
        )

    remaining_columns = [
        column for column in df_normalized.columns if column not in STANDARD_COLUMNS
    ]
    df_normalized = df_normalized[STANDARD_COLUMNS + remaining_columns]
    df_normalized.index.name = None
    return df_normalized


def append_daily_snapshots(
    df_new: pd.DataFrame,
    hotel_id: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """Append new snapshot rows to the hotel's standard CSV file, creating parent dirs if needed."""
    if not hotel_id:
        raise ValueError("hotel_id must be a non-empty string")

    output_root = output_dir or OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"daily_snapshots_{hotel_id}.csv"

    df_new_norm = normalize_daily_snapshots_df(df_new, hotel_id=hotel_id, as_of_date=None)

    if df_new_norm.empty or (
        "stay_date" in df_new_norm.columns and df_new_norm["stay_date"].isna().all()
    ):
        return path

    if path.exists():
        df_existing = pd.read_csv(path)
        if "stay_date" in df_existing.columns:
            df_existing["stay_date"] = pd.to_datetime(
                df_existing["stay_date"], errors="coerce"
            )
        if "as_of_date" in df_existing.columns:
            df_existing["as_of_date"] = pd.to_datetime(
                df_existing["as_of_date"], errors="coerce"
            )
        df_existing = _ensure_standard_columns(df_existing)
        df_combined = pd.concat([df_existing, df_new_norm], ignore_index=True)
        df_combined = df_combined.drop_duplicates(
            subset=["hotel_id", "as_of_date", "stay_date"], keep="last"
        )
    else:
        df_combined = df_new_norm

    if "stay_date" in df_combined.columns:
        df_combined["stay_date"] = pd.to_datetime(
            df_combined["stay_date"], errors="coerce"
        )
    if "as_of_date" in df_combined.columns:
        df_combined["as_of_date"] = pd.to_datetime(
            df_combined["as_of_date"], errors="coerce"
        )

    df_combined = df_combined.sort_values(["hotel_id", "as_of_date", "stay_date"])

    if "stay_date" in df_combined.columns:
        df_combined["stay_date"] = df_combined["stay_date"].dt.strftime("%Y-%m-%d")
    if "as_of_date" in df_combined.columns:
        df_combined["as_of_date"] = df_combined["as_of_date"].dt.strftime("%Y-%m-%d")

    df_combined.to_csv(path, index=False)
    return path


def read_daily_snapshots(
    hotel_id: str,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Read the hotel's standard daily snapshots CSV as a dataframe."""
    if not hotel_id:
        raise ValueError("hotel_id must be a non-empty string")

    output_root = output_dir or OUTPUT_DIR
    path = output_root / f"daily_snapshots_{hotel_id}.csv"

    if not path.exists():
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_csv(path)
    if "stay_date" in df.columns:
        df["stay_date"] = pd.to_datetime(df["stay_date"], errors="coerce")
    if "as_of_date" in df.columns:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")

    return _ensure_standard_columns(df)


def read_daily_snapshots_for_month(
    hotel_id: str,
    target_month: str,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Return snapshots filtered to the stay dates within the given target month (YYYYMM)."""
    if len(target_month) != 6 or not target_month.isdigit():
        raise ValueError("target_month must be a 6-digit string in the format YYYYMM")

    year = int(target_month[:4])
    month = int(target_month[4:])
    start_date = pd.Timestamp(year=year, month=month, day=1)
    end_date = start_date + pd.offsets.MonthEnd(0)

    df = read_daily_snapshots(hotel_id, output_dir=output_dir)

    if "stay_date" not in df.columns:
        return df

    df = df[df["stay_date"].notna()].copy()
    mask = (df["stay_date"] >= start_date) & (df["stay_date"] <= end_date)
    return df.loc[mask]


__all__ = [
    "STANDARD_COLUMNS",
    "get_daily_snapshots_path",
    "normalize_daily_snapshots_df",
    "append_daily_snapshots",
    "read_daily_snapshots",
    "read_daily_snapshots_for_month",
]
