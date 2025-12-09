from __future__ import annotations

from pathlib import Path

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
    """Return the path to the daily snapshots CSV for the given hotel."""
    return OUTPUT_DIR / f"daily_snapshots_{hotel_id}.csv"


def _ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the dataframe contains all standard columns, filling missing ones with NaN."""
    df_copy = df.copy()
    for column in STANDARD_COLUMNS:
        if column not in df_copy.columns:
            df_copy[column] = pd.NA
    return df_copy


def normalize_daily_snapshots_df(
    df: pd.DataFrame,
    hotel_id: str | None = None,
    as_of_date: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Normalize a daily snapshots dataframe before writing to the standard CSV."""
    df_normalized = _ensure_standard_columns(df.copy())

    if hotel_id is not None:
        df_normalized["hotel_id"] = hotel_id

    if as_of_date is not None:
        df_normalized["as_of_date"] = pd.to_datetime(as_of_date)

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
    output_dir: Path | None = None,
) -> Path:
    """Append new daily snapshots to the hotel's standard CSV, creating it if missing."""
    output_root = output_dir or OUTPUT_DIR
    path = output_root / f"daily_snapshots_{hotel_id}.csv"

    df_new_norm = normalize_daily_snapshots_df(df_new, hotel_id=hotel_id, as_of_date=None)

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
        df_combined = pd.concat([df_existing, df_new_norm], ignore_index=True)
        df_combined = df_combined.drop_duplicates(
            subset=["hotel_id", "as_of_date", "stay_date"], keep="last"
        )
    else:
        df_combined = df_new_norm

    if "stay_date" in df_combined.columns:
        df_combined["stay_date"] = pd.to_datetime(df_combined["stay_date"], errors="coerce")
    if "as_of_date" in df_combined.columns:
        df_combined["as_of_date"] = pd.to_datetime(df_combined["as_of_date"], errors="coerce")

    df_sorted = df_combined.sort_values(["hotel_id", "as_of_date", "stay_date"])
    df_out = df_sorted.copy()

    if "stay_date" in df_out.columns:
        df_out["stay_date"] = df_out["stay_date"].dt.strftime("%Y-%m-%d")
    if "as_of_date" in df_out.columns:
        df_out["as_of_date"] = df_out["as_of_date"].dt.strftime("%Y-%m-%d")

    df_out.to_csv(path, index=False)
    return path


def read_daily_snapshots(
    hotel_id: str,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """Read the standard daily snapshots CSV for the specified hotel."""
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
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """Read daily snapshots for the specified hotel filtered to the target month (YYYYMM)."""
    df = read_daily_snapshots(hotel_id, output_dir=output_dir)

    if "stay_date" not in df.columns:
        return df

    df = df[df["stay_date"].notna()].copy()

    year = int(target_month[:4])
    month = int(target_month[4:])
    start_date = pd.Timestamp(year=year, month=month, day=1)
    end_date = start_date + pd.offsets.MonthEnd(0)

    mask = (df["stay_date"] >= start_date) & (df["stay_date"] <= end_date)
    return df.loc[mask]
