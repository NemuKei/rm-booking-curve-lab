from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from booking_curve.config import HOTEL_CONFIG
from booking_curve.pms_adapter_nface import parse_nface_filename

logger = logging.getLogger(__name__)


@dataclass
class RawInventoryHealth:
    candidate_files: int
    parsed_files: int
    failed_files: int
    parse_success_rate: float | None
    latest_asof_ymd: str | None
    severity: str  # "OK" / "WARN" / "STOP"
    message: str


@dataclass
class RawInventory:
    hotel_id: str
    raw_root_dir: Path
    adapter_type: str
    include_subfolders: bool
    files: dict[tuple[str, str], Path]
    health: RawInventoryHealth


@dataclass(frozen=True)
class RawInventoryIndex:
    pairs: set[tuple[str, str]]
    asof_dates: set[str]
    target_months: set[str]
    asof_to_targets: dict[str, set[str]]


def _discover_candidates(raw_root_dir: Path, include_subfolders: bool) -> list[Path]:
    globber = raw_root_dir.rglob if include_subfolders else raw_root_dir.glob
    return sorted(
        path
        for path in globber("*.xls*")
        if path.is_file() and path.suffix.lower().startswith(".xls") and not path.name.startswith("~$")
    )


def _extract_keys(file_path: Path, adapter_type: str) -> tuple[str | None, str | None]:
    if adapter_type == "nface":
        return parse_nface_filename(file_path)
    raise ValueError(f"Unsupported adapter_type: {adapter_type}")


def _parse_asof_date(asof_ymd: str, file_path: Path) -> date | None:
    try:
        return datetime.strptime(asof_ymd, "%Y%m%d").date()
    except ValueError:
        logger.warning("%s: ASOF (%s) を日付に変換できません", file_path, asof_ymd)
        return None


def _validate_target_month(target_month: str, file_path: Path) -> str | None:
    try:
        datetime.strptime(f"{target_month}01", "%Y%m%d")
    except ValueError:
        logger.warning("%s: target_month (%s) を日付に変換できません", file_path, target_month)
        return None
    return target_month


def _build_health(
    *,
    hotel_id: str,
    raw_root_dir: Path,
    candidate_files: int,
    parsed_files: int,
    latest_asof_ymd: str | None,
) -> RawInventoryHealth:
    failed_files = candidate_files - parsed_files
    parse_success_rate = parsed_files / candidate_files if candidate_files else None

    severity = "OK"
    message: str

    if candidate_files == 0:
        severity = "STOP"
        message = f"{hotel_id}: raw files not found under {raw_root_dir}"
    elif parse_success_rate is not None and parse_success_rate < 0.30:
        severity = "STOP"
        message = f"{hotel_id}: parse success rate {parse_success_rate:.1%} below stop threshold"
    elif parse_success_rate is not None and parse_success_rate < 0.80:
        severity = "WARN"
        message = f"{hotel_id}: parse success rate {parse_success_rate:.1%} below warn threshold"
    else:
        message = f"{hotel_id}: raw inventory ready ({parsed_files}/{candidate_files} parsed)"

    if latest_asof_ymd:
        message = f"{message}; latest_asof={latest_asof_ymd}"

    return RawInventoryHealth(
        candidate_files=candidate_files,
        parsed_files=parsed_files,
        failed_files=failed_files,
        parse_success_rate=parse_success_rate,
        latest_asof_ymd=latest_asof_ymd,
        severity=severity,
        message=message,
    )


def build_raw_inventory(hotel_id: str, raw_root_dir: str | Path | None = None) -> RawInventory:
    """Build raw inventory using resolved paths from booking_curve.config.HOTEL_CONFIG.

    raw_root_dir must already be normalized in config.py; this module does not resolve paths.
    """
    if hotel_id not in HOTEL_CONFIG:
        raise KeyError(f"hotel_id '{hotel_id}' not found in HOTEL_CONFIG")

    hotel_cfg = HOTEL_CONFIG[hotel_id]
    adapter_type = hotel_cfg.get("adapter_type")
    raw_root_dir_cfg = raw_root_dir if raw_root_dir is not None else hotel_cfg.get("raw_root_dir")
    include_subfolders = bool(hotel_cfg.get("include_subfolders", False))

    if not adapter_type:
        raise ValueError(f"{hotel_id}: adapter_type is required in HOTEL_CONFIG")
    if not raw_root_dir_cfg:
        raise ValueError(f"{hotel_id}: raw_root_dir is required in HOTEL_CONFIG")

    resolved_raw_root_dir = Path(raw_root_dir_cfg)
    if not resolved_raw_root_dir.exists() or not resolved_raw_root_dir.is_dir():
        raise ValueError(
            f"{hotel_id}: raw_root_dir does not exist or is not a directory: "
            f"{resolved_raw_root_dir} (include_subfolders={include_subfolders})",
        )
    if not os.access(resolved_raw_root_dir, os.R_OK):
        raise ValueError(
            f"{hotel_id}: raw_root_dir is not readable: "
            f"{resolved_raw_root_dir} (include_subfolders={include_subfolders})",
        )

    candidate_paths = _discover_candidates(resolved_raw_root_dir, include_subfolders)

    files: dict[tuple[str, str], Path] = {}
    parsed_files = 0
    accepted_asof_dates: list[str] = []

    for file_path in candidate_paths:
        target_month_raw, asof_ymd_raw = _extract_keys(file_path, adapter_type)
        if not target_month_raw or not asof_ymd_raw:
            logger.warning("%s: ファイル名の解析に失敗したためスキップします", file_path)
            continue

        target_month = _validate_target_month(target_month_raw, file_path)
        asof_dt = _parse_asof_date(asof_ymd_raw, file_path)
        if target_month is None or asof_dt is None:
            continue

        parsed_files += 1

        if asof_dt > date.today():
            logger.info("%s: 未来ASOF(%s)のため台帳から除外します", file_path, asof_dt)
            continue

        key = (target_month, asof_dt.strftime("%Y%m%d"))
        if key in files:
            existing = files[key]
            raise ValueError(
                f"Duplicate key detected for {key}: {existing} and {file_path}",
            )

        files[key] = file_path
        accepted_asof_dates.append(key[1])

    latest_asof_ymd = max(accepted_asof_dates) if accepted_asof_dates else None
    health = _build_health(
        hotel_id=hotel_id,
        raw_root_dir=resolved_raw_root_dir,
        candidate_files=len(candidate_paths),
        parsed_files=parsed_files,
        latest_asof_ymd=latest_asof_ymd,
    )

    if health.severity == "STOP":
        raise ValueError(health.message)

    return RawInventory(
        hotel_id=hotel_id,
        raw_root_dir=resolved_raw_root_dir,
        adapter_type=adapter_type,
        include_subfolders=include_subfolders,
        files=files,
        health=health,
    )


def build_raw_inventory_index(raw_inventory: RawInventory) -> RawInventoryIndex:
    asof_dates: set[str] = set()
    target_months: set[str] = set()
    asof_to_targets: dict[str, set[str]] = defaultdict(set)

    for target_month, asof_date in raw_inventory.files:
        asof_dates.add(asof_date)
        target_months.add(target_month)
        asof_to_targets[asof_date].add(target_month)

    pairs = {(target_month, asof_date) for target_month, asof_date in raw_inventory.files}

    return RawInventoryIndex(
        pairs=pairs,
        asof_dates=asof_dates,
        target_months=target_months,
        asof_to_targets=dict(asof_to_targets),
    )
