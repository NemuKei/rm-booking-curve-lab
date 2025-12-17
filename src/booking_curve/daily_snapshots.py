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


def _ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    df_copy = df.copy()
    for column in STANDARD_COLUMNS:
        if column not in df_copy.columns:
            df_copy[column] = pd.NA
    remaining_columns = [column for column in df_copy.columns if column not in STANDARD_COLUMNS]
    return df_copy[STANDARD_COLUMNS + remaining_columns]


def normalize_daily_snapshots_df(
    df: pd.DataFrame,
    hotel_id: Optional[str] = None,
    as_of_date: "pd.Timestamp | str | None" = None,
) -> pd.DataFrame:
    df_normalized = _ensure_standard_columns(df)

    if hotel_id is not None:
        if not hotel_id:
            raise ValueError("hotel_id must be a non-empty string")
        df_normalized["hotel_id"] = hotel_id

    if as_of_date is not None:
        asof_ts = pd.to_datetime(as_of_date, errors="coerce")
        if pd.isna(asof_ts):
            raise ValueError("as_of_date must be convertible to a valid date")
        df_normalized["as_of_date"] = asof_ts

    if "stay_date" in df_normalized.columns:
        df_normalized["stay_date"] = pd.to_datetime(df_normalized["stay_date"], errors="coerce")
    if "as_of_date" in df_normalized.columns:
        df_normalized["as_of_date"] = pd.to_datetime(df_normalized["as_of_date"], errors="coerce")

    df_normalized.index.name = None
    return df_normalized


def read_daily_snapshots_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_csv(path)
    if "stay_date" in df.columns:
        df["stay_date"] = pd.to_datetime(df["stay_date"], errors="coerce")
    if "as_of_date" in df.columns:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    return _ensure_standard_columns(df)


def _format_dates_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    df_copy = df.copy()
    if "stay_date" in df_copy.columns:
        stay_series = pd.to_datetime(df_copy["stay_date"], errors="coerce")
        df_copy["stay_date"] = stay_series.dt.strftime("%Y-%m-%d")
        df_copy.loc[stay_series.isna(), "stay_date"] = pd.NA
    if "as_of_date" in df_copy.columns:
        asof_series = pd.to_datetime(df_copy["as_of_date"], errors="coerce")
        df_copy["as_of_date"] = asof_series.dt.strftime("%Y-%m-%d")
        df_copy.loc[asof_series.isna(), "as_of_date"] = pd.NA
    return df_copy


def write_daily_snapshots_csv(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df_to_save = _format_dates_for_csv(_ensure_standard_columns(df))
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df_to_save.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


def append_daily_snapshots(path: Path, df_new: pd.DataFrame) -> Path:
    df_new_norm = normalize_daily_snapshots_df(df_new)
    if df_new_norm.empty:
        return path

    df_existing = read_daily_snapshots_csv(path)
    df_combined = pd.concat([df_existing, df_new_norm], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=["hotel_id", "as_of_date", "stay_date"], keep="last")

    df_combined = df_combined.sort_values(["hotel_id", "as_of_date", "stay_date"])
    write_daily_snapshots_csv(df_combined, path)
    return path


def _build_removal_mask(
    df: pd.DataFrame,
    asof_min: "pd.Timestamp | str | None",
    asof_max: "pd.Timestamp | str | None",
    stay_min: "pd.Timestamp | str | None",
    stay_max: "pd.Timestamp | str | None",
) -> pd.Series:
    mask_active = False
    mask = pd.Series(False, index=df.index)

    if asof_min is not None:
        asof_min_ts = pd.to_datetime(asof_min, errors="coerce")
        if pd.isna(asof_min_ts):
            raise ValueError("asof_min must be convertible to a valid date")
        mask = df["as_of_date"] >= asof_min_ts
        mask_active = True

    if asof_max is not None:
        asof_max_ts = pd.to_datetime(asof_max, errors="coerce")
        if pd.isna(asof_max_ts):
            raise ValueError("asof_max must be convertible to a valid date")
        if not mask_active:
            mask = df["as_of_date"] <= asof_max_ts
            mask_active = True
        else:
            mask &= df["as_of_date"] <= asof_max_ts

    if stay_min is not None:
        stay_min_ts = pd.to_datetime(stay_min, errors="coerce")
        if pd.isna(stay_min_ts):
            raise ValueError("stay_min must be convertible to a valid date")
        if not mask_active:
            mask = df["stay_date"] >= stay_min_ts
            mask_active = True
        else:
            mask &= df["stay_date"] >= stay_min_ts

    if stay_max is not None:
        stay_max_ts = pd.to_datetime(stay_max, errors="coerce")
        if pd.isna(stay_max_ts):
            raise ValueError("stay_max must be convertible to a valid date")
        if not mask_active:
            mask = df["stay_date"] <= stay_max_ts
            mask_active = True
        else:
            mask &= df["stay_date"] <= stay_max_ts

    if not mask_active:
        return pd.Series(False, index=df.index)
    return mask


def upsert_daily_snapshots_range(
    path: Path,
    df_new: pd.DataFrame,
    asof_min: "pd.Timestamp | str | None",
    asof_max: "pd.Timestamp | str | None",
    stay_min: "pd.Timestamp | str | None" = None,
    stay_max: "pd.Timestamp | str | None" = None,
) -> Path:
    if (stay_min is not None or stay_max is not None) and asof_min is None and asof_max is None:
        raise ValueError(
            "stay filter requires asof filter: specify asof_min/asof_max when using stay_min/stay_max",
        )

    df_existing = read_daily_snapshots_csv(path)
    df_new_norm = normalize_daily_snapshots_df(df_new)

    removal_mask = _build_removal_mask(df_existing, asof_min, asof_max, stay_min, stay_max)
    df_filtered = df_existing.loc[~removal_mask]

    df_combined = pd.concat([df_filtered, df_new_norm], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=["hotel_id", "as_of_date", "stay_date"], keep="last")
    df_combined = df_combined.sort_values(["hotel_id", "as_of_date", "stay_date"])

    write_daily_snapshots_csv(df_combined, path)
    return path


def get_daily_snapshots_path(hotel_id: str) -> Path:
    if not hotel_id:
        raise ValueError("hotel_id must be a non-empty string")
    return OUTPUT_DIR / f"daily_snapshots_{hotel_id}.csv"


def get_latest_asof_date(path: Path | str, output_dir: Optional[Path] = None) -> pd.Timestamp | None:
    if isinstance(path, Path):
        csv_path = path
    else:
        hotel_id = path
        if not hotel_id:
            raise ValueError("hotel_id must be a non-empty string")
        base_dir = OUTPUT_DIR if output_dir is None else Path(output_dir)
        csv_path = base_dir / f"daily_snapshots_{hotel_id}.csv"

    if not Path(csv_path).exists():
        return None

    df = pd.read_csv(csv_path, usecols=["as_of_date"])
    asof_max = pd.to_datetime(df["as_of_date"], errors="coerce").max()
    if pd.isna(asof_max):
        return None
    return asof_max


def append_daily_snapshots_by_hotel(
    df_new: pd.DataFrame,
    hotel_id: str,
    output_dir: Optional[Path] = None,
) -> Path:
    base_dir = OUTPUT_DIR if output_dir is None else Path(output_dir)
    path = base_dir / f"daily_snapshots_{hotel_id}.csv"
    df_new_with_hotel = normalize_daily_snapshots_df(df_new, hotel_id=hotel_id)
    return append_daily_snapshots(path, df_new_with_hotel)


def upsert_daily_snapshots_range_by_hotel(
    df_new: pd.DataFrame,
    hotel_id: str,
    asof_min: "pd.Timestamp | str | None",
    asof_max: "pd.Timestamp | str | None",
    stay_min: "pd.Timestamp | str | None" = None,
    stay_max: "pd.Timestamp | str | None" = None,
    output_dir: Optional[Path] = None,
) -> Path:
    base_dir = OUTPUT_DIR if output_dir is None else Path(output_dir)
    path = base_dir / f"daily_snapshots_{hotel_id}.csv"
    df_new_with_hotel = normalize_daily_snapshots_df(df_new, hotel_id=hotel_id)
    return upsert_daily_snapshots_range(path, df_new_with_hotel, asof_min, asof_max, stay_min, stay_max)


def read_daily_snapshots(
    hotel_id: str,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
    if not hotel_id:
        raise ValueError("hotel_id must be a non-empty string")

    base_dir = OUTPUT_DIR if output_dir is None else Path(output_dir)
    path = base_dir / f"daily_snapshots_{hotel_id}.csv"
    return read_daily_snapshots_csv(path)


def read_daily_snapshots_for_month(
    hotel_id: str,
    target_month: str,
    output_dir: Optional[Path] = None,
) -> pd.DataFrame:
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
    "get_latest_asof_date",
    "normalize_daily_snapshots_df",
    "append_daily_snapshots",
    "upsert_daily_snapshots_range",
    "read_daily_snapshots",
    "read_daily_snapshots_for_month",
    "read_daily_snapshots_csv",
    "write_daily_snapshots_csv",
    "append_daily_snapshots_by_hotel",
    "upsert_daily_snapshots_range_by_hotel",
]
