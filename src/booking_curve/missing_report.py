from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.daily_snapshots import read_daily_snapshots_csv
from booking_curve.pms_adapter_nface import parse_nface_filename

logger = logging.getLogger(__name__)


def add_months_yyyymm(yyyymm: str, delta: int) -> str:
    """Add `delta` months to a YYYYMM string and return YYYYMM."""
    base_ts = pd.to_datetime(f"{yyyymm}01", format="%Y%m%d", errors="coerce")
    if pd.isna(base_ts):
        raise ValueError("yyyymm must be in YYYYMM format")
    shifted = base_ts + pd.DateOffset(months=delta)
    return shifted.strftime("%Y%m")


def iter_month_dates(yyyymm: str) -> list[pd.Timestamp]:
    """Return all dates for the given YYYYMM."""
    start = pd.to_datetime(f"{yyyymm}01", format="%Y%m%d", errors="coerce")
    if pd.isna(start):
        raise ValueError("yyyymm must be in YYYYMM format")
    end = start + pd.offsets.MonthEnd(0)
    return list(pd.date_range(start=start, end=end, freq="D"))


def discover_raw_nface_files(
    input_dir: Path,
    recursive: bool = True,
    glob_pattern: str = "*.xls*",
) -> dict[tuple[str, str], Path]:
    """
    Collect raw PMS files and map to (target_month, asof_date).

    - Files whose names cannot be parsed are skipped with a warning.
    - Duplicate (target_month, asof_date) combinations raise ValueError.
    """

    globber = input_dir.rglob if recursive else input_dir.glob
    result: dict[tuple[str, str], Path] = {}

    for path in globber(glob_pattern):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue

        if not path.suffix.lower().startswith(".xls"):
            continue

        target_month, asof_date = parse_nface_filename(path)
        if not target_month or not asof_date:
            logger.warning("%s: ファイル名からtarget_month/asof_dateを取得できないためスキップします", path)
            continue

        key = (target_month, asof_date)
        if key in result:
            existing_path = result[key]
            raise ValueError(
                f"Duplicate raw files for target_month={target_month}, asof_date={asof_date}: {existing_path} / {path}",
            )

        result[key] = path

    return result


def _format_asof(asof_str: str) -> str:
    asof_ts = pd.to_datetime(asof_str, format="%Y%m%d", errors="coerce")
    return asof_ts.strftime("%Y-%m-%d") if not pd.isna(asof_ts) else asof_str


def _build_raw_missing_records(
    raw_files: dict[tuple[str, str], Path],
    input_dir: Path,
    hotel_id: str,
    months_ahead: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    asof_to_targets: defaultdict[str, set[str]] = defaultdict(set)
    for target_month, asof_date in raw_files:
        asof_to_targets[asof_date].add(target_month)

    for asof_date, target_months in asof_to_targets.items():
        asof_yyyymm = asof_date[:6]
        expected = {add_months_yyyymm(asof_yyyymm, i) for i in range(months_ahead + 1)}
        missing_targets = sorted(expected - target_months)
        for missing_target in missing_targets:
            records.append(
                {
                    "kind": "raw_missing",
                    "hotel_id": hotel_id,
                    "asof_date": _format_asof(asof_date),
                    "target_month": missing_target,
                    "missing_count": 1,
                    "missing_sample": missing_target,
                    "message": "",
                    "path": str(input_dir),
                },
            )

    return records


def _build_onhand_missing_records(df: pd.DataFrame, hotel_id: str, daily_snapshots_path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    df_filtered = df.copy()
    df_filtered["stay_date"] = pd.to_datetime(df_filtered["stay_date"], errors="coerce")
    df_filtered["as_of_date"] = pd.to_datetime(df_filtered["as_of_date"], errors="coerce")
    df_filtered = df_filtered.dropna(subset=["stay_date", "as_of_date"])
    df_filtered = df_filtered[df_filtered["hotel_id"] == hotel_id]

    if df_filtered.empty:
        return records

    df_filtered["target_month"] = df_filtered["stay_date"].dt.strftime("%Y%m")

    for (asof_ts, target_month), group in df_filtered.groupby(["as_of_date", "target_month"]):
        asof_norm = pd.Timestamp(asof_ts).normalize()
        expected_dates = [dt for dt in iter_month_dates(target_month) if dt.normalize() >= asof_norm]
        present_dates = {pd.Timestamp(dt).normalize() for dt in group["stay_date"]}
        missing_dates = [dt for dt in expected_dates if dt.normalize() not in present_dates]
        if not missing_dates:
            continue

        missing_dates_sorted = sorted(missing_dates)
        sample = ",".join(dt.strftime("%Y-%m-%d") for dt in missing_dates_sorted[:10])
        records.append(
            {
                "kind": "onhand_missing",
                "hotel_id": hotel_id,
                "asof_date": asof_norm.strftime("%Y-%m-%d"),
                "target_month": target_month,
                "missing_count": len(missing_dates_sorted),
                "missing_sample": sample,
                "message": "",
                "path": str(daily_snapshots_path),
            },
        )

    return records


def _find_closing_asof(raw_files: dict[tuple[str, str], Path]) -> dict[str, str]:
    closing_map: dict[str, str] = {}
    for target_month, asof_str in raw_files:
        try:
            target_ts = pd.to_datetime(f"{target_month}01", format="%Y%m%d", errors="coerce")
            asof_ts = pd.to_datetime(asof_str, format="%Y%m%d", errors="coerce")
        except Exception:
            continue
        if pd.isna(target_ts) or pd.isna(asof_ts):
            continue
        month_end = pd.Timestamp(target_ts) + pd.offsets.MonthEnd(0)
        if asof_ts.normalize() >= (month_end + pd.Timedelta(days=1)).normalize():
            current = closing_map.get(target_month)
            if current is None or asof_ts < pd.to_datetime(current, format="%Y%m%d"):
                closing_map[target_month] = asof_str
    return closing_map


def _build_act_missing_records(
    df: pd.DataFrame,
    hotel_id: str,
    daily_snapshots_path: Path,
    raw_files: dict[tuple[str, str], Path],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    closing_map = _find_closing_asof(raw_files)
    if not closing_map:
        return records

    df_filtered = df.copy()
    df_filtered["stay_date"] = pd.to_datetime(df_filtered["stay_date"], errors="coerce")
    df_filtered["as_of_date"] = pd.to_datetime(df_filtered["as_of_date"], errors="coerce")
    df_filtered = df_filtered.dropna(subset=["stay_date", "as_of_date"])
    df_filtered = df_filtered[df_filtered["hotel_id"] == hotel_id]

    if df_filtered.empty:
        return records

    df_filtered["target_month"] = df_filtered["stay_date"].dt.strftime("%Y%m")

    for target_month, closing_asof_str in closing_map.items():
        closing_ts = pd.to_datetime(closing_asof_str, format="%Y%m%d", errors="coerce")
        if pd.isna(closing_ts):
            continue
        closing_ts = pd.Timestamp(closing_ts).normalize()
        month_dates = iter_month_dates(target_month)
        group = df_filtered[
            (df_filtered["target_month"] == target_month) & (df_filtered["as_of_date"].dt.normalize() == closing_ts)
        ]

        if group.empty:
            records.append(
                {
                    "kind": "act_missing",
                    "hotel_id": hotel_id,
                    "asof_date": closing_ts.strftime("%Y-%m-%d"),
                    "target_month": target_month,
                    "missing_count": len(month_dates),
                    "missing_sample": "(no snapshot for closing_asof)",
                    "message": "",
                    "path": str(daily_snapshots_path),
                },
            )
            continue

        present_dates = {pd.Timestamp(dt).normalize() for dt in group["stay_date"]}
        missing_dates = {dt.normalize() for dt in month_dates if dt.normalize() not in present_dates}

        if "rooms_oh" in group.columns:
            na_mask = group["rooms_oh"].isna()
            missing_dates.update({pd.Timestamp(dt).normalize() for dt in group.loc[na_mask, "stay_date"]})

        if not missing_dates:
            continue

        missing_sorted = sorted(missing_dates)
        month_end = (pd.to_datetime(f"{target_month}01", format="%Y%m%d") + pd.offsets.MonthEnd(0)).normalize()
        kind = "act_missing_month_end_critical" if month_end in missing_dates else "act_missing"
        sample = ",".join(dt.strftime("%Y-%m-%d") for dt in missing_sorted[:10])
        records.append(
            {
                "kind": kind,
                "hotel_id": hotel_id,
                "asof_date": closing_ts.strftime("%Y-%m-%d"),
                "target_month": target_month,
                "missing_count": len(missing_sorted),
                "missing_sample": sample,
                "message": "",
                "path": str(daily_snapshots_path),
            },
        )

    return records


def build_missing_report(
    hotel_id: str,
    input_dir: Path,
    daily_snapshots_path: Path,
    *,
    recursive: bool = True,
    glob_pattern: str = "*.xls*",
    months_ahead: int = 3,
) -> Path:
    """Generate missing report for raw PMS files and daily snapshots."""
    raw_files = discover_raw_nface_files(input_dir, recursive=recursive, glob_pattern=glob_pattern)

    records: list[dict[str, object]] = []
    records.extend(_build_raw_missing_records(raw_files, input_dir, hotel_id, months_ahead))

    if not daily_snapshots_path.exists():
        records.append(
            {
                "kind": "daily_snapshots_missing_file",
                "hotel_id": hotel_id,
                "asof_date": "",
                "target_month": "",
                "missing_count": 0,
                "missing_sample": "",
                "message": "daily_snapshots file is missing",
                "path": str(daily_snapshots_path),
            },
        )
    else:
        df_snapshots = read_daily_snapshots_csv(daily_snapshots_path)
        records.extend(_build_onhand_missing_records(df_snapshots, hotel_id, daily_snapshots_path))
        records.extend(_build_act_missing_records(df_snapshots, hotel_id, daily_snapshots_path, raw_files))

    output_path = OUTPUT_DIR / f"missing_report_{hotel_id}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df_output = pd.DataFrame(
        records,
        columns=[
            "kind",
            "hotel_id",
            "asof_date",
            "target_month",
            "missing_count",
            "missing_sample",
            "message",
            "path",
        ],
    )
    df_output.to_csv(output_path, index=False)
    return output_path
