from __future__ import annotations

import logging
import re
import warnings
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.daily_snapshots import (
    append_daily_snapshots_by_hotel,
    normalize_daily_snapshots_df,
    upsert_daily_snapshots_range_by_hotel,
)

# layout="auto" 時は A列の日付行の間隔から自動判定する
# "shifted": 宿泊日行(row_idx)の1行下(row_idx+1)に OH があるレイアウト (無加工/A/B)
# "inline" : 宿泊日行(row_idx)と同じ行に OH があるレイアウト (加工C)
# "auto"   : A列の日付行の間隔から自動判定
LayoutType = Literal["shifted", "inline", "auto"]

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


def _parse_asof_date(df: pd.DataFrame, file_path: Path, filename_asof_ymd: str | None) -> Optional[pd.Timestamp]:
    """Parse the as-of date prioritizing filename information."""

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

    if filename_ts is not None:
        if cell_ts is not None and filename_ts != cell_ts:
            logger.warning(
                "%s: ファイル名ASOF(%s)とセルASOF(%s)が一致しません",
                file_path,
                filename_ts.date(),
                cell_ts.date(),
            )
        return filename_ts

    if cell_ts is not None:
        return cell_ts

    for candidate in re.findall(r"\d{8}", file_path.name):
        ts = pd.to_datetime(candidate, format="%Y%m%d", errors="coerce")
        if not pd.isna(ts):
            return pd.Timestamp(ts).normalize()

    logger.error("%s: ASOF 日付を取得できませんでした", file_path)
    return None


def _parse_nface_filename(file_path: Path) -> tuple[str | None, str | None]:
    """Extract target month and as-of date from filename.

    The expected pattern is "YYYYMM_YYYYMMDD". If parsing fails, returns
    (None, None) with a warning log.
    """

    m = re.search(r"(?P<ym>\d{6})_(?P<asof>\d{8})", file_path.name)
    if not m:
        logger.warning("%s: ファイル名から宿泊月/ASOFを解釈できません", file_path)
        return None, None

    return m.group("ym"), m.group("asof")


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


def _extract_oh_values_for_row(
    df: pd.DataFrame,
    row_idx: int,
    layout: LayoutType,
    file_path: Path,
) -> tuple[object, object, object]:
    """宿泊日行から OH 値を抽出する。"""
    if layout == "shifted":
        oh_idx = row_idx + 1
        if oh_idx >= df.shape[0]:
            logger.warning("%s: OH行がシート末尾を超えています (row=%s)", file_path, row_idx)
            rooms_oh = pax_oh = revenue_oh = pd.NA
        else:
            rooms_oh = df.iloc[oh_idx, 4] if df.shape[1] > 4 else pd.NA
            pax_oh = df.iloc[oh_idx, 5] if df.shape[1] > 5 else pd.NA
            revenue_oh = df.iloc[oh_idx, 6] if df.shape[1] > 6 else pd.NA
    elif layout == "inline":
        rooms_oh = df.iloc[row_idx, 4] if df.shape[1] > 4 else pd.NA
        pax_oh = df.iloc[row_idx, 5] if df.shape[1] > 5 else pd.NA
        revenue_oh = df.iloc[row_idx, 6] if df.shape[1] > 6 else pd.NA
    else:
        raise ValueError(f"Unknown layout: {layout!r}")

    values = [rooms_oh, pax_oh, revenue_oh]
    if all(pd.isna(v) or v == 0 for v in values):
        logger.warning("%s: OH値が全て0/NaNです (row=%s)", file_path, row_idx)

    return rooms_oh, pax_oh, revenue_oh


def _detect_layout(df: pd.DataFrame, file_path: Path) -> Literal["shifted", "inline"]:
    """A列の日付行インデックス間隔から 'shifted' / 'inline' を判定する。"""

    col = df.iloc[:, 0]
    dates = pd.to_datetime(col, errors="coerce")
    date_idxs = dates[dates.notna()].index.to_numpy()

    if len(date_idxs) < 3:
        logger.error("%s: 日付行が少なすぎるためレイアウトを自動判定できません", file_path)
        raise ValueError("日付行が少なすぎるためレイアウトを自動判定できません")

    diffs = date_idxs[1:] - date_idxs[:-1]
    inline_votes = (diffs == 1).sum()
    shifted_votes = (diffs >= 2).sum()
    total_votes = inline_votes + shifted_votes

    if total_votes == 0:
        logger.error("%s: 日付行の間隔からレイアウトを判定できません", file_path)
        raise ValueError("日付行の間隔からレイアウトを判定できません")

    inline_ratio = inline_votes / total_votes
    if inline_ratio >= 0.8:
        layout = "inline"
    elif inline_ratio <= 0.2:
        layout = "shifted"
    else:
        logger.error(
            "%s: レイアウトを自動判定できません (inline_ratio=%.2f)",
            file_path,
            inline_ratio,
        )
        raise ValueError(f"レイアウトを自動判定できません (inline_ratio={inline_ratio:.2f})")

    logger.info("%s: layout を自動判定しました -> %s", file_path, layout)
    return layout


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
            "auto" はA列の日付間隔から自動判定。
        output_dir: 標準CSVを保存する出力ディレクトリ。
        save: True の場合は標準CSVに追記する。

    Returns:
        Normalized dataframe of daily snapshots extracted from the file.
    """
    path = Path(file_path)
    filename_stay_ym, parsed_filename_asof = _parse_nface_filename(path)
    if filename_asof_ymd is None:
        filename_asof_ymd = parsed_filename_asof
    df_raw = pd.read_excel(path, header=None)

    if layout == "auto":
        resolved_layout = _detect_layout(df_raw, path)
    elif layout in ("shifted", "inline"):
        resolved_layout = layout
    else:
        raise ValueError(f"Unknown layout: {layout!r}")

    target_month = _parse_target_month(df_raw, path)
    if target_month is None:
        logger.error("%s: target_month が取得できないためスキップします", path)
        return normalize_daily_snapshots_df(pd.DataFrame(), hotel_id=hotel_id)

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

        rooms_oh, pax_oh, revenue_oh = _extract_oh_values_for_row(df_raw, row_idx, resolved_layout, path)
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
        logger.warning("%s: 宿泊日行が見つからないか、target_month に一致する行がありません", path)
        return normalize_daily_snapshots_df(pd.DataFrame(), hotel_id=hotel_id)

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


def build_daily_snapshots_fast(
    input_dir: str | Path,
    hotel_id: str,
    target_months: list[str],
    asof_min: pd.Timestamp | None,
    asof_max: pd.Timestamp | None,
    layout: LayoutType = "auto",
    output_dir: Optional[Path] = None,
    glob: str = "*.xls*",
) -> None:
    """Build snapshots quickly by filename filtering and single append."""

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    asof_min_ts = _normalize_boundary_timestamp(asof_min, "asof_min") if asof_min is not None else None
    asof_max_ts = _normalize_boundary_timestamp(asof_max, "asof_max") if asof_max is not None else None

    files = sorted(p for p in input_path.glob(glob) if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"})

    filtered: list[tuple[Path, str]] = []
    for file in files:
        stay_ym, asof_ymd = _parse_nface_filename(file)
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
) -> None:
    """Append snapshots for specified months using single append."""

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    files = sorted(p for p in input_path.glob(glob) if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"})

    filtered: list[tuple[Path, str]] = []
    for file in files:
        stay_ym, asof_ymd = _parse_nface_filename(file)
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
) -> None:
    """Append snapshots for all Excel files with a single append."""

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error("%s が存在しないかディレクトリではありません", input_path)
        return

    files = sorted(p for p in input_path.glob(glob) if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"})

    if not files:
        logger.warning("%s 配下に対象ファイルが見つかりません", input_path)
        return

    df_list: list[pd.DataFrame] = []
    for file in files:
        stay_ym, asof_ymd = _parse_nface_filename(file)
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

    candidates = list(input_path.glob(glob))
    files = sorted(p for p in candidates if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"})

    logger.info(
        "%s: partial build filters -> target_months=%s, asof_min=%s, asof_max=%s",
        input_path,
        target_months,
        asof_min,
        asof_max,
    )

    filtered_files: list[tuple[Path, str]] = []
    for file in files:
        target_month_ym, asof_ymd = _parse_nface_filename(file)
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
    "build_daily_snapshots_fast",
    "build_daily_snapshots_from_folder",
    "build_daily_snapshots_full_all",
    "build_daily_snapshots_full_months",
    "build_daily_snapshots_from_folder_partial",
]
