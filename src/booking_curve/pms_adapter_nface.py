from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import logging
import re

import pandas as pd

from booking_curve.daily_snapshots import (
    normalize_daily_snapshots_df,
    append_daily_snapshots,
)

PatternType = Literal["raw", "A", "B", "C"]

logger = logging.getLogger(__name__)


def _parse_target_month(df: pd.DataFrame, file_path: Path) -> Optional[pd.Timestamp]:
    """Parse the target month from cell C2 (row 1, col 2)."""
    try:
        raw_value = df.iloc[1, 2]
    except IndexError:
        raw_value = pd.NA
    dt = pd.to_datetime(raw_value, errors="coerce")
    if pd.isna(dt):
        logger.error("%s: target_month (C2) を解釈できません", file_path)
        return None
    return pd.Timestamp(year=dt.year, month=dt.month, day=1).normalize()


def _parse_asof_date(df: pd.DataFrame, file_path: Path) -> Optional[pd.Timestamp]:
    """Parse the as-of date from cell Q1 or fallback to filename."""
    try:
        raw_value = df.iloc[0, 16]
    except IndexError:
        raw_value = pd.NA
    dt = pd.to_datetime(raw_value, errors="coerce")

    if pd.isna(dt):
        m = re.search(r"(20\d{6})", file_path.name)
        if m:
            dt = pd.to_datetime(m.group(1), format="%Y%m%d", errors="coerce")

    if pd.isna(dt):
        logger.error("%s: ASOF 日付を取得できませんでした", file_path)
        return None

    return pd.Timestamp(dt).normalize()


def _iter_stay_rows(df: pd.DataFrame) -> list[tuple[int, pd.Timestamp]]:
    """Return list of (row_idx, stay_date) where column A is a valid date."""
    stay_rows: list[tuple[int, pd.Timestamp]] = []
    for i in range(df.shape[0]):
        stay_raw = df.iloc[i, 0] if df.shape[1] > 0 else pd.NA
        stay_dt = pd.to_datetime(stay_raw, errors="coerce")
        if pd.isna(stay_dt):
            continue
        stay_rows.append((i, pd.Timestamp(stay_dt).normalize()))
    return stay_rows


def _extract_oh_values_for_row(
    df: pd.DataFrame,
    row_idx: int,
    pattern: PatternType,
    file_path: Path,
) -> tuple[object, object, object]:
    """Extract OH values for a stay row according to the pattern."""
    if pattern in {"raw", "A", "B"}:
        oh_idx = row_idx + 1
        if oh_idx >= df.shape[0]:
            logger.warning("%s: OH行がシート末尾を超えています (row=%s)", file_path, row_idx)
            rooms_oh = pax_oh = revenue_oh = pd.NA
        else:
            rooms_oh = df.iloc[oh_idx, 4] if df.shape[1] > 4 else pd.NA
            pax_oh = df.iloc[oh_idx, 5] if df.shape[1] > 5 else pd.NA
            revenue_oh = df.iloc[oh_idx, 6] if df.shape[1] > 6 else pd.NA
    else:  # pattern == "C"
        rooms_oh = df.iloc[row_idx, 4] if df.shape[1] > 4 else pd.NA
        pax_oh = df.iloc[row_idx, 5] if df.shape[1] > 5 else pd.NA
        revenue_oh = df.iloc[row_idx, 6] if df.shape[1] > 6 else pd.NA

    values = [rooms_oh, pax_oh, revenue_oh]
    if all(pd.isna(v) or v == 0 for v in values):
        logger.warning("%s: OH値が全て0/NaNです (row=%s)", file_path, row_idx)

    return rooms_oh, pax_oh, revenue_oh


def parse_nface_file(
    file_path: str | Path,
    hotel_id: str,
    pattern: PatternType,
    output_dir: Optional[Path] = None,
    save: bool = True,
) -> pd.DataFrame:
    """Parse a N@FACE Excel file into standard daily snapshots format.

    Args:
        file_path: Path to the Excel file.
        hotel_id: Hotel identifier to populate in the output.
        pattern: Excel layout pattern ("raw", "A", "B", or "C").
        output_dir: Optional output directory for saving appended CSV.
        save: When True, append results to the standard CSV.

    Returns:
        Normalized dataframe of daily snapshots extracted from the file.
    """
    path = Path(file_path)
    df_raw = pd.read_excel(path, header=None)

    target_month = _parse_target_month(df_raw, path)
    if target_month is None:
        logger.error("%s: target_month が取得できないためスキップします", path)
        return normalize_daily_snapshots_df(pd.DataFrame(), hotel_id=hotel_id)

    as_of_date = _parse_asof_date(df_raw, path)
    if as_of_date is None:
        logger.error("%s: ASOF不明のためこのファイルはスキップします", path)
        return normalize_daily_snapshots_df(pd.DataFrame(), hotel_id=hotel_id)

    stay_rows = _iter_stay_rows(df_raw)
    records: list[dict] = []
    n_total = 0
    n_kept = 0
    skipped_count = 0

    for row_idx, stay_date in stay_rows:
        n_total += 1
        if stay_date.year != target_month.year or stay_date.month != target_month.month:
            skipped_count += 1
            continue

        rooms_oh, pax_oh, revenue_oh = _extract_oh_values_for_row(
            df_raw, row_idx, pattern, path
        )
        records.append(
            {
                "hotel_id": hotel_id,
                "as_of_date": as_of_date,
                "stay_date": stay_date,
                "rooms_oh": rooms_oh,
                "pax_oh": pax_oh,
                "revenue_oh": revenue_oh,
            }
        )
        n_kept += 1

    if n_total > 0 and n_kept / n_total < 0.5:
        logger.warning(
            "%s: target_month に属さない行が多数あります (kept=%s / total=%s)",
            path,
            n_kept,
            n_total,
        )

    if skipped_count > 0:
        logger.warning("%s: target_month 外の行を %s 件スキップしました", path, skipped_count)

    if not records:
        logger.warning(
            "%s: 宿泊日行が見つからないか、target_month に一致する行がありません", path
        )
        return normalize_daily_snapshots_df(pd.DataFrame(), hotel_id=hotel_id)

    df = pd.DataFrame(records)
    df_norm = normalize_daily_snapshots_df(df, hotel_id=hotel_id, as_of_date=as_of_date)

    if save:
        output_path = append_daily_snapshots(
            df_norm, hotel_id=hotel_id, output_dir=output_dir
        )
        logger.info("%s: 標準CSVに追記しました -> %s", path, output_path)

    return df_norm


def build_daily_snapshots_from_folder(
    input_dir: str | Path,
    hotel_id: str,
    pattern: PatternType,
    output_dir: Optional[Path] = None,
    glob: str = "*.xlsx",
) -> None:
    """Process all Excel files in a folder and append to standard CSV."""
    input_path = Path(input_dir)
    files = sorted(input_path.glob(glob))

    if not files:
        logger.warning("%s 配下に対象ファイルが見つかりません", input_path)
        return

    for file in files:
        try:
            parse_nface_file(
                file, hotel_id=hotel_id, pattern=pattern, output_dir=output_dir, save=True
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s の処理中にエラーが発生しました: %s", file, exc)

    logger.info("%s 配下の処理が完了しました", input_path)


__all__ = ["parse_nface_file", "build_daily_snapshots_from_folder"]
