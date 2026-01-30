from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from booking_curve.config import HOTEL_CONFIG, get_hotel_output_dir
from booking_curve.daily_snapshots import (
    build_month_asof_index,
    get_daily_snapshots_path,
    load_month_asof_index,
    read_daily_snapshots_csv,
)
from booking_curve.raw_inventory import (
    RawInventory,
    RawInventoryIndex,
    build_raw_inventory,
    build_raw_inventory_index,
)

logger = logging.getLogger(__name__)


def _resolve_hotel_output_dir(hotel_id: str, output_dir: Path | str | None) -> Path:
    if output_dir is None:
        return get_hotel_output_dir(hotel_id)
    base_dir = Path(output_dir)
    if base_dir.name == hotel_id:
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir
    hotel_dir = base_dir / hotel_id
    hotel_dir.mkdir(parents=True, exist_ok=True)
    return hotel_dir


def _require_hotel_config(hotel_id: str) -> dict[str, object]:
    if not hotel_id or not isinstance(hotel_id, str):
        raise ValueError("missing_report: hotel_id must be a non-empty string")
    if hotel_id not in HOTEL_CONFIG:
        raise ValueError(
            f"missing_report: hotel_id '{hotel_id}' not found in HOTEL_CONFIG (check config/hotels.json)",
        )
    return HOTEL_CONFIG[hotel_id]


def _resolve_daily_snapshots_path(hotel_id: str, daily_snapshots_path: Path | str | None) -> Path:
    if daily_snapshots_path is None:
        return get_daily_snapshots_path(hotel_id)
    return Path(daily_snapshots_path)


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


def _format_asof(asof_str: str) -> str:
    asof_ts = pd.to_datetime(asof_str, format="%Y%m%d", errors="coerce")
    return asof_ts.strftime("%Y-%m-%d") if not pd.isna(asof_ts) else asof_str


def _build_ops_missing_records(
    raw_index: RawInventoryIndex,
    raw_root_dir: Path,
    hotel_id: str,
    asof_window_days: int,
    forward_months: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    asof_dates = raw_index.asof_dates
    asof_to_targets = raw_index.asof_to_targets

    if asof_window_days <= 0:
        return records

    end_date = date.today()
    start_date = end_date - timedelta(days=asof_window_days - 1)
    expected_asof_dates = {(start_date + timedelta(days=i)).strftime("%Y%m%d") for i in range(asof_window_days)}

    observed_asof_dates = {asof for asof in asof_dates if pd.notna(pd.to_datetime(asof, format="%Y%m%d", errors="coerce"))}
    missing_asof_dates = sorted(expected_asof_dates - observed_asof_dates)

    for asof in missing_asof_dates:
        records.append(
            {
                "kind": "asof_missing",
                "hotel_id": hotel_id,
                "asof_date": _format_asof(asof),
                "target_month": "",
                "missing_count": 1,
                "missing_sample": "",
                "message": "",
                "path": str(raw_root_dir),
                "severity": "WARN",
            },
        )

    for asof in sorted(observed_asof_dates):
        asof_ts = pd.to_datetime(asof, format="%Y%m%d", errors="coerce")
        if pd.isna(asof_ts):
            continue

        asof_dt = asof_ts.date()
        if asof_dt < start_date or asof_dt > end_date:
            continue

        asof_yyyymm = asof[:6]
        expected_targets = {add_months_yyyymm(asof_yyyymm, i) for i in range(forward_months + 1)}
        observed_targets = asof_to_targets.get(asof, set())
        missing_targets = sorted(expected_targets - observed_targets)
        for missing_target in missing_targets:
            records.append(
                {
                    "kind": "raw_missing",
                    "hotel_id": hotel_id,
                    "asof_date": _format_asof(asof),
                    "target_month": missing_target,
                    "missing_count": 1,
                    "missing_sample": missing_target,
                    "message": "",
                    "path": str(raw_root_dir),
                    "severity": "ERROR",
                },
            )

    if observed_asof_dates:
        valid_asof_ts = [pd.to_datetime(asof, format="%Y%m%d", errors="coerce") for asof in observed_asof_dates]
        valid_asof_ts = [ts for ts in valid_asof_ts if not pd.isna(ts)]
        if valid_asof_ts:
            latest_ts = max(valid_asof_ts).date()
            if latest_ts < end_date:
                delta_days = (end_date - latest_ts).days
                records.append(
                    {
                        "kind": "stale_latest_asof",
                        "hotel_id": hotel_id,
                        "asof_date": latest_ts.strftime("%Y-%m-%d"),
                        "target_month": "",
                        "missing_count": 0,
                        "missing_sample": "",
                        "message": f"最新ASOFが {delta_days} 日前です",
                        "path": str(raw_root_dir),
                        "severity": "WARN",
                    },
                )

    return records


def _iter_months_range(min_month: str, max_month: str) -> list[str]:
    try:
        start = pd.Period(min_month, freq="M")
        end = pd.Period(max_month, freq="M")
    except Exception:
        return []

    months: list[str] = []
    for p in pd.period_range(start=start, end=end, freq="M"):
        months.append(f"{p.year}{p.month:02d}")
    return months


def _build_audit_raw_missing_records(
    raw_index: RawInventoryIndex,
    raw_root_dir: Path,
    hotel_id: str,
    lt_days: int,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    target_months = raw_index.target_months

    if not target_months or lt_days <= 0:
        return records

    min_month = min(target_months)
    max_month = max(target_months)
    months = _iter_months_range(min_month, max_month)

    for target_month in months:
        month_start = pd.to_datetime(f"{target_month}01", format="%Y%m%d", errors="coerce")
        if pd.isna(month_start):
            continue

        month_end = pd.Timestamp(month_start) + pd.offsets.MonthEnd(0)
        start_asof = (month_end - pd.Timedelta(days=lt_days)).normalize()
        end_asof = min(month_end.normalize(), pd.Timestamp(date.today()))
        if end_asof < start_asof:
            continue

        expected_asof_dates = pd.date_range(start=start_asof, end=end_asof, freq="D")
        observed_asof_dates = {
            asof for tm, asof in raw_index.pairs if tm == target_month and pd.notna(pd.to_datetime(asof, format="%Y%m%d", errors="coerce"))
        }

        for asof_ts in expected_asof_dates:
            asof_key = asof_ts.strftime("%Y%m%d")
            if asof_key in observed_asof_dates:
                continue
            records.append(
                {
                    "kind": "raw_missing",
                    "hotel_id": hotel_id,
                    "asof_date": asof_ts.strftime("%Y-%m-%d"),
                    "target_month": target_month,
                    "missing_count": 1,
                    "missing_sample": target_month,
                    "message": "",
                    "path": str(raw_root_dir),
                    "severity": "ERROR",
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
                "severity": "ERROR",
            },
        )

    return records


def _find_closing_asof(raw_pairs: set[tuple[str, str]]) -> dict[str, str]:
    closing_map: dict[str, str] = {}
    for target_month, asof_str in raw_pairs:
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
    raw_pairs: set[tuple[str, str]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    closing_map = _find_closing_asof(raw_pairs)
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
        group = df_filtered[(df_filtered["target_month"] == target_month) & (df_filtered["as_of_date"].dt.normalize() == closing_ts)]

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
                    "severity": "ERROR",
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
                "severity": "ERROR",
            },
        )

    return records


def _build_snapshot_pair_missing_records(
    raw_index: RawInventoryIndex,
    snapshot_pairs: set[tuple[str, str]],
    hotel_id: str,
    daily_snapshots_path: Path,
) -> list[dict[str, object]]:
    missing_pairs = sorted(raw_index.pairs - snapshot_pairs)
    records: list[dict[str, object]] = []

    for target_month, asof in missing_pairs:
        records.append(
            {
                "kind": "snapshot_pair_missing",
                "hotel_id": hotel_id,
                "asof_date": _format_asof(asof),
                "target_month": target_month,
                "missing_count": 1,
                "missing_sample": target_month,
                "message": "raw exists but daily snapshot is missing",
                "path": str(daily_snapshots_path),
                "severity": "ERROR",
            },
        )

    return records


def _load_raw_parse_failures(output_dir: Path, hotel_id: str) -> list[dict[str, object]]:
    expected_columns = [
        "kind",
        "hotel_id",
        "asof_date",
        "target_month",
        "missing_count",
        "missing_sample",
        "message",
        "path",
        "severity",
    ]
    path = output_dir / "raw_parse_failures.csv"
    if not path.exists():
        return []

    try:
        df_failures = pd.read_csv(path)
    except Exception as exc:
        logger.warning("missing_report: failed to read raw_parse_failures: %s", exc)
        return []

    df_output = df_failures.copy()
    for col in expected_columns:
        if col not in df_output.columns:
            df_output[col] = 0 if col == "missing_count" else ""

    return df_output[expected_columns].to_dict(orient="records")


def find_unconverted_raw_pairs(
    hotel_id: str,
    daily_snapshots_path: Path | str | None = None,
) -> tuple[list[tuple[str, str]], RawInventoryIndex, RawInventory, set[tuple[str, str]]]:
    _require_hotel_config(hotel_id)
    try:
        raw_inventory = build_raw_inventory(hotel_id)
    except Exception as exc:
        msg = (
            f"missing_report: failed to build raw inventory for hotel_id '{hotel_id}'\n"
            f"CAUSE: {exc}"
        )
        raise ValueError(msg) from exc
    raw_index = build_raw_inventory_index(raw_inventory)
    resolved_daily_path = _resolve_daily_snapshots_path(hotel_id, daily_snapshots_path)
    snapshot_pairs = load_month_asof_index(hotel_id, resolved_daily_path) if resolved_daily_path.exists() else set()
    missing_pairs = sorted(raw_index.pairs - snapshot_pairs)
    return missing_pairs, raw_index, raw_inventory, snapshot_pairs


def build_missing_report(
    hotel_id: str,
    daily_snapshots_path: Path | str | None = None,
    *,
    mode: str = "ops",
    asof_window_days: int = 180,
    lt_days: int = 120,
    forward_months: int = 3,
    output_dir: Path | str | None = None,
) -> Path:
    """Generate missing report for raw PMS files and daily snapshots.

    mode:
        - \"ops\": 運用モード。ASOF窓で最新の取りこぼしを検知。
        - \"audit\": 監査モード。歴史的なギャップをSTAY MONTH全域で検知。
    """
    _require_hotel_config(hotel_id)
    try:
        raw_inventory = build_raw_inventory(hotel_id)
    except Exception as exc:
        msg = (
            f"missing_report: failed to build raw inventory for hotel_id '{hotel_id}'\n"
            f"CAUSE: {exc}"
        )
        raise ValueError(msg) from exc
    raw_index = build_raw_inventory_index(raw_inventory)
    raw_root_dir = raw_inventory.raw_root_dir

    records: list[dict[str, object]] = []
    mode_normalized = (mode or "ops").strip().lower()
    resolved_daily_path = _resolve_daily_snapshots_path(hotel_id, daily_snapshots_path)

    if raw_inventory.health.severity == "WARN":
        records.append(
            {
                "kind": "raw_inventory_health",
                "hotel_id": hotel_id,
                "asof_date": "",
                "target_month": "",
                "missing_count": raw_inventory.health.failed_files,
                "missing_sample": "",
                "message": raw_inventory.health.message,
                "path": str(raw_root_dir),
                "severity": raw_inventory.health.severity,
            },
        )

    if mode_normalized == "audit":
        records.extend(_build_audit_raw_missing_records(raw_index, raw_root_dir, hotel_id, lt_days))
    else:
        records.extend(
            _build_ops_missing_records(raw_index, raw_root_dir, hotel_id, asof_window_days, forward_months),
        )

    output_dir_path = _resolve_hotel_output_dir(hotel_id, output_dir)
    records.extend(_load_raw_parse_failures(output_dir_path, hotel_id))

    if not resolved_daily_path.exists():
        records.append(
            {
                "kind": "daily_snapshots_missing_file",
                "hotel_id": hotel_id,
                "asof_date": "",
                "target_month": "",
                "missing_count": 0,
                "missing_sample": "",
                "message": "daily_snapshots file is missing",
                "path": str(resolved_daily_path),
                "severity": "ERROR",
            },
        )
    else:
        df_snapshots = read_daily_snapshots_csv(resolved_daily_path)
        snapshot_pairs = build_month_asof_index(df_snapshots, hotel_id)
        records.extend(_build_snapshot_pair_missing_records(raw_index, snapshot_pairs, hotel_id, resolved_daily_path))
        records.extend(_build_onhand_missing_records(df_snapshots, hotel_id, resolved_daily_path))
        records.extend(_build_act_missing_records(df_snapshots, hotel_id, resolved_daily_path, raw_index.pairs))

    mode_suffix = "audit" if mode_normalized == "audit" else "ops"
    output_path = output_dir_path / f"missing_report_{mode_suffix}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for rec in records:
        rec.setdefault("severity", "INFO")

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
            "severity",
        ],
    )
    df_output.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


# Self-test notes:
# - ops/audit を連続実行してもCSVファイル名が衝突しないこと
# - Excelで開いた際に日本語messageが文字化けしないこと（UTF-8 BOM）
# - auditモードで today より未来の asof_date 欠損行が出力されないこと
