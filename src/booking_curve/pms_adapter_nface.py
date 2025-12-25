from __future__ import annotations

import logging
import re
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.daily_snapshots import (
    append_daily_snapshots_by_hotel,
    normalize_daily_snapshots_df,
    upsert_daily_snapshots_range_by_hotel,
)

# layout="auto" 時は A列の宿泊日行から 1行持ち/2行持ちを自動判定する
# "shifted": 宿泊日行(row_idx)の1行下(row_idx+1)に OH があるレイアウト (2行持ち)
# "inline" : 宿泊日行(row_idx)と同じ行に OH があるレイアウト (1行持ち)
# "auto"   : A列の宿泊日行インデックスから自動判定
LayoutType = Literal["shifted", "inline", "auto"]

logger = logging.getLogger(__name__)

MIN_STAY_DATE_ROWS = 5


def _parse_date_cell(value: object) -> pd.Timestamp | None:
    def _normalize(ts: pd.Timestamp | None) -> pd.Timestamp | None:
        if ts is None or pd.isna(ts):
            return None
        return pd.Timestamp(ts).normalize()

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return _normalize(pd.to_datetime(value, errors="coerce"))

    parsed_candidates: list[pd.Timestamp | None] = []

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            parsed_candidates.append(pd.to_datetime(stripped, format=fmt, errors="coerce"))
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Could not infer format.*", category=UserWarning)
            parsed_candidates.append(pd.to_datetime(stripped, errors="coerce"))
        numeric_value = pd.to_numeric(stripped, errors="coerce")
        if pd.notna(numeric_value):
            parsed_candidates.append(
                pd.to_datetime(float(numeric_value), unit="D", origin="1899-12-30", errors="coerce"),
            )
    else:
        numeric_value = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric_value):
            parsed_candidates.append(
                pd.to_datetime(float(numeric_value), unit="D", origin="1899-12-30", errors="coerce"),
            )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Parsing Dates", category=UserWarning)
            parsed_candidates.append(pd.to_datetime(value, errors="coerce"))

    for candidate in parsed_candidates:
        normalized = _normalize(candidate)
        if normalized is not None:
            return normalized
    return None


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


def _parse_asof_date(df: pd.DataFrame, file_path: Path, filename_asof_ymd: str | None) -> Optional[pd.Timestamp]:
    """Parse the as-of date prioritizing the cell value and falling back to filename."""

    try:
        raw_value = df.iloc[0, 16]
    except IndexError:
        raw_value = pd.NA

    cell_ts: pd.Timestamp | None
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Parsing Dates", category=UserWarning)
        dt = pd.to_datetime(raw_value, errors="coerce")
    cell_ts = None if pd.isna(dt) else pd.Timestamp(dt).normalize()

    filename_ts: pd.Timestamp | None = None
    if filename_asof_ymd:
        ts = pd.to_datetime(filename_asof_ymd, format="%Y%m%d", errors="coerce")
        if pd.isna(ts):
            logger.warning("%s: ファイル名のASOF(%s)を日付に変換できません", file_path, filename_asof_ymd)
        else:
            filename_ts = pd.Timestamp(ts).normalize()

    if cell_ts is not None:
        if filename_ts is not None and filename_ts != cell_ts:
            logger.warning(
                "%s: セルASOF(%s)とファイル名ASOF(%s)が一致しません",
                file_path,
                cell_ts.date(),
                filename_ts.date(),
            )
        return cell_ts

    if filename_ts is not None:
        return filename_ts

    logger.error("%s: ASOF 日付を取得できませんでした", file_path)
    return None


def parse_nface_filename(file_path: Path) -> tuple[str | None, str | None]:
    """Extract target month and as-of date from filename.

    The expected pattern is ``YYYYMM_YYYYMMDD``.
    """

    m = re.search(r"(?P<ym>\d{6})_(?P<asof>\d{8})", file_path.name)
    if not m:
        logger.warning("%s: ファイル名から宿泊月/ASOFを解釈できません", file_path)
        return None, None

    return m.group("ym"), m.group("asof")


def _parse_nface_filename(file_path: Path) -> tuple[str | None, str | None]:
    """Backward-compatible wrapper for :func:`parse_nface_filename`.

    Deprecated: use :func:`parse_nface_filename` instead.
    """

    return parse_nface_filename(file_path)


def _discover_excel_files(input_path: Path, glob: str, *, recursive: bool) -> list[Path]:
    """Discover Excel files under the input path with optional recursion."""
    candidates = input_path.rglob(glob) if recursive else input_path.glob(glob)

    files = sorted(
        p
        for p in candidates
        if p.is_file()
        and p.suffix.lower().startswith(".xls")
        and not p.name.startswith("~$")
    )
    return files


def _validate_no_duplicate_keys(files: list[Path]) -> None:
    """Validate that there are no duplicate (target_month, asof_date) keys among files."""
    seen: dict[tuple[str, str], Path] = {}
    for file_path in files:
        target_month, asof_ymd = parse_nface_filename(file_path)
        if target_month is None or asof_ymd is None:
            continue
        key = (target_month, asof_ymd)
        if key in seen:
            existing = seen[key]
            raise ValueError(
                f"Duplicate key detected for {key}: {existing} and {file_path}",
            )
        seen[key] = file_path


def _normalize_boundary_timestamp(value: pd.Timestamp | str | None, param_name: str) -> pd.Timestamp | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d{8}", stripped):
            ts = pd.to_datetime(stripped, format="%Y%m%d", errors="coerce")
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Parsing Dates", category=UserWarning)
                ts = pd.to_datetime(stripped, errors="coerce")
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Parsing Dates", category=UserWarning)
            ts = pd.to_datetime(value, errors="coerce")

    if pd.isna(ts):
        raise ValueError(f"{param_name} must be convertible to a valid date")
    return pd.Timestamp(ts).normalize()


def _extract_date_rows_from_column_a(df: pd.DataFrame, file_path: Path) -> list[tuple[int, pd.Timestamp]]:
    date_rows: list[tuple[int, pd.Timestamp]] = []
    for row_idx, value in enumerate(df.iloc[:, 0]):
        stay_ts = _parse_date_cell(value)
        if stay_ts is None:
            continue
        date_rows.append((row_idx, stay_ts))

    if len(date_rows) < MIN_STAY_DATE_ROWS:
        logger.error(
            "%s: A列の日付行が少なすぎます (found=%s, threshold=%s)",
            file_path,
            len(date_rows),
            MIN_STAY_DATE_ROWS,
        )
        raise ValueError("A列の日付行が少なすぎるため解析を停止します")
    return date_rows


def _is_empty_cell(value: object) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _is_zero_or_na(value: object) -> bool:
    if pd.isna(value):
        return True
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return False
    return float(numeric) == 0.0


def _is_nonzero(value: object) -> bool:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return False
    return float(numeric) != 0.0


def _detect_layout(
    date_rows: list[tuple[int, pd.Timestamp]],
    df: pd.DataFrame,
    file_path: Path,
) -> Literal["inline", "shifted"]:
    if len(date_rows) < 2:
        logger.error("%s: レイアウト判定に必要な日付行が不足しています (rows=%s)", file_path, len(date_rows))
        raise ValueError("layout_unknown")

    sample_rows = date_rows[: min(10, len(date_rows))]
    weekdays = {"月", "火", "水", "木", "金", "土", "日"}
    checked = 0
    matched = 0
    for row_idx, _ in sample_rows:
        candidate_row = row_idx + 1
        if candidate_row >= df.shape[0]:
            continue
        checked += 1
        weekday_cell = df.iloc[candidate_row, 2] if df.shape[1] > 2 else pd.NA
        if _is_empty_cell(df.iloc[candidate_row, 0]) and isinstance(weekday_cell, str):
            weekday_str = weekday_cell.strip()
        else:
            weekday_str = None
        if weekday_str not in weekdays:
            continue
        candidate_values = [
            df.iloc[candidate_row, 4] if df.shape[1] > 4 else pd.NA,
            df.iloc[candidate_row, 5] if df.shape[1] > 5 else pd.NA,
            df.iloc[candidate_row, 6] if df.shape[1] > 6 else pd.NA,
        ]
        stay_values = [
            df.iloc[row_idx, 4] if df.shape[1] > 4 else pd.NA,
            df.iloc[row_idx, 5] if df.shape[1] > 5 else pd.NA,
            df.iloc[row_idx, 6] if df.shape[1] > 6 else pd.NA,
        ]
        if not all(_is_zero_or_na(value) for value in candidate_values):
            continue
        if not any(_is_nonzero(value) for value in stay_values):
            continue
        matched += 1

    if checked > 0 and matched / checked > 0.5:
        logger.info("%s: detected weekday spacer rows; treating as inline layout", file_path)
        return "inline"

    date_idxs = [row_idx for row_idx, _ in date_rows]
    stay_dates = [stay_date for _, stay_date in date_rows]
    diffs = [date_idxs[i + 1] - date_idxs[i] for i in range(len(date_idxs) - 1)]

    has_blank_between_dates = any(diff > 1 for diff in diffs)
    has_consecutive_duplicates = any(stay_dates[i] == stay_dates[i + 1] for i in range(len(stay_dates) - 1))

    if has_blank_between_dates or has_consecutive_duplicates:
        return "shifted"

    if not diffs:
        logger.error("%s: レイアウト判定用の差分が計算できません", file_path)
        raise ValueError("layout_unknown")

    all_inline = all(diff == 1 for diff in diffs)
    all_shifted = all(diff >= 2 for diff in diffs)

    if all_inline:
        return "inline"
    if all_shifted:
        return "shifted"

    logger.error("%s: レイアウトを判定できません (diffs=%s)", file_path, diffs)
    raise ValueError("layout_unknown")


def _resolve_oh_rows(
    date_rows: list[tuple[int, pd.Timestamp]],
    layout: Literal["inline", "shifted"],
    df: pd.DataFrame,
    file_path: Path,
) -> list[tuple[int, pd.Timestamp]]:
    actual_rows: list[tuple[int, pd.Timestamp]] = []

    if layout == "inline":
        for row_idx, stay_date in date_rows:
            actual_rows.append((row_idx, stay_date))
        return actual_rows

    skip_next = False
    for idx, (row_idx, stay_date) in enumerate(date_rows):
        if skip_next:
            skip_next = False
            continue

        oh_row = row_idx + 1

        if oh_row >= df.shape[0]:
            logger.warning(
                "%s: OH行がシート末尾を超えるため宿泊日 %s をスキップします (row=%s)",
                file_path,
                stay_date.date(),
                row_idx,
            )
            continue

        if idx + 1 < len(date_rows) and date_rows[idx + 1][1] == stay_date:
            next_row_idx = date_rows[idx + 1][0]
            if next_row_idx != oh_row:
                logger.error(
                    "%s: 同一日付が連続していますが行インデックスが不正です (stay_row=%s, expected_oh_row=%s, next_date_row=%s)",
                    file_path,
                    row_idx,
                    oh_row,
                    next_row_idx,
                )
                raise ValueError("layout_unknown")
            stay_date_on_oh = _parse_date_cell(df.iloc[oh_row, 0])
            if stay_date_on_oh is None or stay_date_on_oh != stay_date:
                logger.error(
                    "%s: 同一日付連続レイアウトでOH行のA列日付が一致しません (stay_row=%s, oh_row=%s)",
                    file_path,
                    row_idx,
                    oh_row,
                )
                raise ValueError("layout_unknown")
            skip_next = True
        else:
            oh_date_cell = _parse_date_cell(df.iloc[oh_row, 0])
            if oh_date_cell is not None:
                logger.error(
                    "%s: shiftedレイアウト想定だがOH行のA列に日付が入っています (stay_row=%s, oh_row=%s, value=%s)",
                    file_path,
                    row_idx,
                    oh_row,
                    df.iloc[oh_row, 0],
                )
                raise ValueError("layout_unknown")

        actual_rows.append((oh_row, stay_date))
    return actual_rows


def _extract_oh_values(df: pd.DataFrame, row_idx: int, file_path: Path) -> tuple[object, object, object]:
    rooms_oh = df.iloc[row_idx, 4] if df.shape[1] > 4 else pd.NA
    pax_oh = df.iloc[row_idx, 5] if df.shape[1] > 5 else pd.NA
    revenue_oh = df.iloc[row_idx, 6] if df.shape[1] > 6 else pd.NA

    values = [rooms_oh, pax_oh, revenue_oh]
    if all(pd.isna(v) for v in values):
        logger.warning("%s: OH値が全てNaNです (row=%s)", file_path, row_idx)

    return rooms_oh, pax_oh, revenue_oh


def parse_nface_file(
    file_path: str | Path,
    hotel_id: str,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    save: bool = True,
    filename_asof_ymd: str | None = None,
) -> pd.DataFrame:
    """Parse a N@FACE Excel file into standard daily snapshots format.

    Args:
        file_path: Excel ファイルのパス。
        hotel_id: 出力に付与するホテルID。
        layout:
            OH 行の配置を指定する。
            "shifted" は宿泊日行の1行下、
            "inline" は宿泊日行と同じ行、
            "auto" はシート構造から自動判定。
        output_dir: 標準CSVを保存する出力ディレクトリ。
        save: True の場合は標準CSVに追記する。

    Returns:
        Normalized dataframe of daily snapshots extracted from the file.
    """
    path = Path(file_path)
    filename_stay_ym, parsed_filename_asof = parse_nface_filename(path)
    if filename_asof_ymd is None:
        filename_asof_ymd = parsed_filename_asof
    df_raw = pd.read_excel(path, header=None)

    if layout not in ("auto", "shifted", "inline"):
        raise ValueError(f"Unknown layout: {layout!r}")

    target_month = _parse_target_month(df_raw, path)
    if target_month is None:
        raise ValueError("target_month が取得できません")

    if filename_stay_ym is not None:
        stay_ts = pd.to_datetime(f"{filename_stay_ym}01", format="%Y%m%d", errors="coerce")
        if not pd.isna(stay_ts):
            stay_ts = pd.Timestamp(stay_ts).normalize()
            if stay_ts.month != target_month.month or stay_ts.year != target_month.year:
                logger.warning(
                    "%s: ファイル名の宿泊月(%s)とシートの宿泊月(%s)が一致しません",
                    path,
                    stay_ts.strftime("%Y-%m"),
                    target_month.strftime("%Y-%m"),
                )

    as_of_date = _parse_asof_date(df_raw, path, filename_asof_ymd)
    if as_of_date is None:
        raise ValueError("ASOF 日付を取得できませんでした")

    date_rows = _extract_date_rows_from_column_a(df_raw, path)
    if layout == "inline":
        resolved_layout: Literal["inline", "shifted"] = "inline"
    elif layout == "shifted":
        resolved_layout = "shifted"
    else:
        resolved_layout = _detect_layout(date_rows, df_raw, path)
    actual_rows = _resolve_oh_rows(date_rows, resolved_layout, df_raw, path)

    records: list[dict] = []
    n_total = 0
    n_kept = 0

    for row_idx, stay_date in actual_rows:
        n_total += 1
        if stay_date.year != target_month.year or stay_date.month != target_month.month:
            continue

        rooms_oh, pax_oh, revenue_oh = _extract_oh_values(df_raw, row_idx, path)
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

    if n_total > 0 and (n_total - n_kept) / n_total >= 0.8:
        logger.warning("%s: target_month 外の行が多数あります (kept=%s / total=%s)", path, n_kept, n_total)

    if not records:
        raise ValueError("宿泊日行が見つからないか、target_month に一致する行がありません")

    df = pd.DataFrame(records)
    df_norm = normalize_daily_snapshots_df(df, hotel_id=hotel_id, as_of_date=as_of_date)

    if save:
        base_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
        output_path = append_daily_snapshots_by_hotel(df_norm, hotel_id, output_dir=base_dir)
        logger.info("%s: 標準CSVに追記しました -> %s", path, output_path)

    return df_norm


def build_daily_snapshots_from_folder(
    input_dir: str | Path,
    hotel_id: str,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
) -> None:
    """Process all Excel files in a folder and append to standard CSV.

    デフォルトでは layout="auto" としてファイルごとにレイアウトを自動判定する。必要に応じて
    "shifted" / "inline" を明示指定することもできる。
    """
    build_daily_snapshots_full_all(
        input_dir=input_dir,
        hotel_id=hotel_id,
        layout=layout,
        output_dir=output_dir,
        glob=glob,
    )


def build_daily_snapshots_for_pairs(
    input_dir: str | Path,
    hotel_id: str,
    pairs: list[tuple[str, str]],
    *,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "**/*.xls*",
) -> dict[str, object]:
    """Build daily snapshots only for specified (target_month, asof_date) pairs.

    Each pair is processed independently and upserted with tightly scoped
    asof/stay ranges to avoid unintended overwrites.
    """

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        raise FileNotFoundError(f"{input_path} が存在しないかディレクトリではありません")

    target_keys = {(t, a) for t, a in pairs}
    if not target_keys:
        return {
            "processed_pairs": 0,
            "skipped_missing_raw_pairs": 0,
            "skipped_parse_fail_files": 0,
            "updated_pairs": [],
        }

    raw_map: dict[tuple[str, str], Path] = {}
    skipped_parse_fail_files = 0

    for path in input_path.glob(glob):
        if not path.is_file() or not path.suffix.lower().startswith(".xls") or path.name.startswith("~$"):
            continue
        target_month, asof_date = parse_nface_filename(path)
        if target_month is None or asof_date is None:
            skipped_parse_fail_files += 1
            continue
        key = (target_month, asof_date)
        if key not in target_keys:
            continue
        if key in raw_map:
            existing = raw_map[key]
            raise ValueError(f"Duplicate raw files for {key}: {existing} / {path}")
        raw_map[key] = path

    processed_pairs = 0
    skipped_missing_raw_pairs = 0
    updated_pairs: list[dict[str, object]] = []
    base_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR

    for target_month, asof_date in sorted(target_keys):
        raw_path = raw_map.get((target_month, asof_date))
        if raw_path is None:
            skipped_missing_raw_pairs += 1
            continue

        processed_pairs += 1
        asof_ts = pd.to_datetime(asof_date, format="%Y%m%d", errors="coerce")
        if pd.isna(asof_ts):
            raise ValueError(f"Invalid asof_date format: {asof_date}")
        asof_ts = pd.Timestamp(asof_ts).normalize()

        stay_start = pd.to_datetime(f"{target_month}01", format="%Y%m%d", errors="coerce")
        if pd.isna(stay_start):
            raise ValueError(f"Invalid target_month format: {target_month}")
        stay_start = pd.Timestamp(stay_start).normalize()
        stay_end = stay_start + pd.offsets.MonthEnd(0)

        df = parse_nface_file(
            raw_path,
            hotel_id=hotel_id,
            layout=layout,
            output_dir=output_dir,
            save=False,
            filename_asof_ymd=asof_date,
        )
        if df.empty:
            continue

        output_path = upsert_daily_snapshots_range_by_hotel(
            df,
            hotel_id,
            asof_min=asof_ts,
            asof_max=asof_ts,
            stay_min=stay_start,
            stay_max=stay_end,
            output_dir=base_dir,
        )
        updated_pairs.append(
            {
                "target_month": target_month,
                "asof_date": asof_date,
                "path": str(raw_path),
                "output_path": str(output_path),
            }
        )

    return {
        "processed_pairs": processed_pairs,
        "skipped_missing_raw_pairs": skipped_missing_raw_pairs,
        "skipped_parse_fail_files": skipped_parse_fail_files,
        "updated_pairs": updated_pairs,
    }


def build_daily_snapshots_fast(
    input_dir: str | Path,
    hotel_id: str,
    target_months: list[str],
    asof_min: pd.Timestamp | None,
    asof_max: pd.Timestamp | None,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
    recursive: bool = False,
) -> None:
    """Build snapshots quickly by filename filtering and single append.

    Supports optional recursive discovery of raw Excel files.
    """

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    asof_min_ts = _normalize_boundary_timestamp(asof_min, "asof_min") if asof_min is not None else None
    asof_max_ts = _normalize_boundary_timestamp(asof_max, "asof_max") if asof_max is not None else None

    files = _discover_excel_files(input_path, glob, recursive=recursive)
    _validate_no_duplicate_keys(files)

    filtered: list[tuple[Path, str]] = []
    for file in files:
        stay_ym, asof_ymd = parse_nface_filename(file)
        if stay_ym is None or asof_ymd is None:
            continue
        if stay_ym not in target_months:
            continue
        asof_ts = pd.to_datetime(asof_ymd, format="%Y%m%d", errors="coerce")
        if pd.isna(asof_ts):
            logger.warning("%s: ASOF を日付に変換できないためスキップします", file)
            continue
        asof_ts = pd.Timestamp(asof_ts).normalize()
        if asof_min_ts is not None and asof_ts < asof_min_ts:
            continue
        if asof_max_ts is not None and asof_ts > asof_max_ts:
            continue
        filtered.append((file, asof_ymd))

    if not filtered:
        logger.info("%s: 対象ファイルがありません (FAST)", input_path)
        return

    df_list: list[pd.DataFrame] = []
    for file, asof_ymd in filtered:
        try:
            df = parse_nface_file(
                file,
                hotel_id=hotel_id,
                layout=layout,
                output_dir=output_dir,
                save=False,
                filename_asof_ymd=asof_ymd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s の処理中にエラーが発生しました: %s", file, exc)
            continue
        if not df.empty:
            df_list.append(df)

    if not df_list:
        logger.info("%s: Excel解析結果が空のためスキップします (FAST)", input_path)
        return

    df_new = pd.concat(df_list, ignore_index=True)
    base_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    output_path = append_daily_snapshots_by_hotel(df_new, hotel_id, output_dir=base_dir)
    logger.info("%s: FASTモードで %s 件のファイルを処理しました -> %s", input_path, len(df_list), output_path)


def build_daily_snapshots_full_months(
    input_dir: str | Path,
    hotel_id: str,
    target_months: list[str],
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
    recursive: bool = False,
) -> None:
    """Append snapshots for specified months using single append.

    Supports optional recursive discovery of raw Excel files.
    """

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    files = _discover_excel_files(input_path, glob, recursive=recursive)
    _validate_no_duplicate_keys(files)

    filtered: list[tuple[Path, str]] = []
    for file in files:
        stay_ym, asof_ymd = parse_nface_filename(file)
        if stay_ym is None or asof_ymd is None:
            continue
        if stay_ym not in target_months:
            continue
        filtered.append((file, asof_ymd))

    if not filtered:
        logger.info("%s: 対象ファイルがありません (FULL_MONTHS)", input_path)
        return

    df_list: list[pd.DataFrame] = []
    for file, asof_ymd in filtered:
        try:
            df = parse_nface_file(
                file,
                hotel_id=hotel_id,
                layout=layout,
                output_dir=output_dir,
                save=False,
                filename_asof_ymd=asof_ymd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s の処理中にエラーが発生しました: %s", file, exc)
            continue
        if not df.empty:
            df_list.append(df)

    if not df_list:
        logger.info("%s: Excel解析結果が空のためスキップします (FULL_MONTHS)", input_path)
        return

    df_new = pd.concat(df_list, ignore_index=True)
    base_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    output_path = append_daily_snapshots_by_hotel(df_new, hotel_id, output_dir=base_dir)
    logger.info("%s: FULL_MONTHSモードで %s 件のファイルを処理しました -> %s", input_path, len(df_list), output_path)


def build_daily_snapshots_full_all(
    input_dir: str | Path,
    hotel_id: str,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
    recursive: bool = False,
) -> None:
    """Append snapshots for all Excel files with a single append.

    Supports optional recursive discovery of raw Excel files.
    """

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    files = _discover_excel_files(input_path, glob, recursive=recursive)
    _validate_no_duplicate_keys(files)

    if not files:
        logger.warning("%s 配下に対象ファイルが見つかりません", input_path)
        return

    df_list: list[pd.DataFrame] = []
    for file in files:
        stay_ym, asof_ymd = parse_nface_filename(file)
        if stay_ym is None or asof_ymd is None:
            continue
        try:
            df = parse_nface_file(
                file,
                hotel_id=hotel_id,
                layout=layout,
                output_dir=output_dir,
                save=False,
                filename_asof_ymd=asof_ymd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s の処理中にエラーが発生しました: %s", file, exc)
            continue
        if not df.empty:
            df_list.append(df)

    if not df_list:
        logger.info("%s: Excel解析結果が空のためスキップします (FULL_ALL)", input_path)
        return

    df_new = pd.concat(df_list, ignore_index=True)
    base_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    output_path = append_daily_snapshots_by_hotel(df_new, hotel_id, output_dir=base_dir)
    logger.info("%s: FULL_ALLモードで %s 件のファイルを処理しました -> %s", input_path, len(df_list), output_path)


def build_daily_snapshots_from_folder_partial(
    input_dir: str | Path,
    hotel_id: str,
    target_months: list[str] | None,
    asof_min: pd.Timestamp | str | None,
    asof_max: pd.Timestamp | str | None,
    stay_min: pd.Timestamp | str | None,
    stay_max: pd.Timestamp | str | None,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
    recursive: bool = False,
) -> None:
    """部分更新用にファイル名フィルタを優先するパーシャルビルド。"""

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    asof_min_ts = _normalize_boundary_timestamp(asof_min, "asof_min") if asof_min is not None else None
    asof_max_ts = _normalize_boundary_timestamp(asof_max, "asof_max") if asof_max is not None else None
    stay_min_ts = _normalize_boundary_timestamp(stay_min, "stay_min") if stay_min is not None else None
    stay_max_ts = _normalize_boundary_timestamp(stay_max, "stay_max") if stay_max is not None else None

    files = _discover_excel_files(input_path, glob, recursive=recursive)
    _validate_no_duplicate_keys(files)

    logger.info(
        "%s: partial build filters -> target_months=%s, asof_min=%s, asof_max=%s",
        input_path,
        target_months,
        asof_min,
        asof_max,
    )

    filtered_files: list[tuple[Path, str]] = []
    for file in files:
        target_month_ym, asof_ymd = parse_nface_filename(file)
        if target_month_ym is None or asof_ymd is None:
            continue

        if target_months is not None and target_month_ym not in target_months:
            continue

        asof_ts = pd.to_datetime(asof_ymd, format="%Y%m%d", errors="coerce")
        if pd.isna(asof_ts):
            logger.warning("%s: ASOF を日付に変換できないためスキップします", file)
            continue

        if asof_min_ts is not None and asof_ts < asof_min_ts:
            continue
        if asof_max_ts is not None and asof_ts > asof_max_ts:
            continue

        filtered_files.append((file, asof_ymd))

    logger.info("%s: partial build 対象ファイル数=%s", input_path, len(filtered_files))

    if not filtered_files:
        logger.info("%s: 対象ファイルがありません", input_path)
        return

    df_list: list[pd.DataFrame] = []
    for file, asof_ymd in filtered_files:
        try:
            df = parse_nface_file(
                file,
                hotel_id=hotel_id,
                layout=layout,
                output_dir=output_dir,
                save=False,
                filename_asof_ymd=asof_ymd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s の処理中にエラーが発生しました: %s", file, exc)
            continue

        if df.empty:
            continue

        if stay_min_ts is not None or stay_max_ts is not None:
            stay_mask = pd.Series(True, index=df.index)
            if stay_min_ts is not None:
                stay_mask &= df["stay_date"] >= stay_min_ts
            if stay_max_ts is not None:
                stay_mask &= df["stay_date"] <= stay_max_ts
            df = df.loc[stay_mask]

        if not df.empty:
            df_list.append(df)

    if not df_list:
        logger.info("%s: 対象ファイルがありません (Excel 解析結果が空)", input_path)
        return

    df_new = pd.concat(df_list, ignore_index=True)

    output_path = upsert_daily_snapshots_range_by_hotel(
        df_new,
        hotel_id,
        asof_min=asof_min_ts,
        asof_max=asof_max_ts,
        stay_min=stay_min_ts,
        stay_max=stay_max_ts,
        output_dir=Path(output_dir) if output_dir is not None else OUTPUT_DIR,
    )
    logger.info("%s: %s 件のファイルから部分更新を実施しました -> %s", input_path, len(df_list), output_path)


__all__ = [
    "parse_nface_file",
    "parse_nface_filename",
    "build_daily_snapshots_fast",
    "build_daily_snapshots_from_folder",
    "build_daily_snapshots_full_all",
    "build_daily_snapshots_full_months",
    "build_daily_snapshots_from_folder_partial",
    "build_daily_snapshots_for_pairs",
]
