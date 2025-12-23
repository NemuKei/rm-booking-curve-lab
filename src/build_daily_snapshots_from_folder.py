from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from booking_curve.config import HOTEL_CONFIG
from booking_curve.daily_snapshots import (
    get_latest_asof_date,
    rebuild_asof_dates_from_daily_snapshots,
)
from booking_curve.raw_inventory import RawInventory, build_raw_inventory
from booking_curve.pms_adapter_nface import (
    build_daily_snapshots_fast,
    build_daily_snapshots_full_all,
    build_daily_snapshots_full_months,
)

EXCEL_GLOB = "*.xls*"
LOGS_DIR = Path("output/logs")
DEFAULT_FULL_ALL_RATE = 0.5


def _configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=handlers,
        force=True,
    )


def _parse_target_months_arg(target_months: str | None) -> list[str]:
    if not target_months:
        raise ValueError("target-months is required for FAST or FULL_MONTHS mode")

    months: list[str] = []
    for value in target_months.split(","):
        ym = value.strip()
        if not ym:
            continue
        if not re.fullmatch(r"\d{6}", ym):
            raise ValueError(f"Invalid target month format: {ym}")
        months.append(ym)

    if not months:
        raise ValueError("target-months must include at least one YYYYMM value")

    return months


def count_excel_files(input_dir: Path, glob: str = EXCEL_GLOB, recursive: bool = False) -> int:
    candidates = input_dir.rglob(glob) if recursive else input_dir.glob(glob)
    return sum(1 for p in candidates if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"})


def load_historical_full_all_rate(logs_dir: Path) -> float | None:
    if not logs_dir.exists():
        return None

    for log_path in sorted(logs_dir.glob("full_all_*.log"), reverse=True):
        lines = log_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            match = re.search(r"rate_files_per_sec=([0-9.]+)", line)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
    return None


def _resolve_hotel_ids(target: str) -> Iterable[str]:
    hotel_ids = list(HOTEL_CONFIG.keys())
    if target == "all":
        return hotel_ids
    if target not in HOTEL_CONFIG:
        raise ValueError(f"Unknown hotel: {target}")
    return [target]


def _build_raw_inventory_or_raise(hotel_id: str) -> RawInventory:
    raw_inventory = build_raw_inventory(hotel_id)
    if raw_inventory.health.severity == "WARN":
        logging.warning(raw_inventory.health.message)
    return raw_inventory


def _run_fast(
    hotel_id: str,
    raw_inventory: RawInventory,
    layout: str,
    target_months: list[str],
    buffer_days: int,
    recursive: bool,
) -> None:
    latest_asof = get_latest_asof_date(hotel_id)
    asof_min = latest_asof - pd.Timedelta(days=buffer_days) if latest_asof is not None else None

    logging.info(
        "Running FAST: hotel=%s target_months=%s buffer_days=%s asof_min=%s",
        hotel_id,
        target_months,
        buffer_days,
        asof_min,
    )

    build_daily_snapshots_fast(
        input_dir=raw_inventory.raw_root_dir,
        hotel_id=hotel_id,
        target_months=target_months,
        asof_min=asof_min,
        asof_max=None,
        layout=layout,
        output_dir=None,
        glob=EXCEL_GLOB,
        recursive=recursive,
    )


def _run_full_months(
    hotel_id: str,
    raw_inventory: RawInventory,
    layout: str,
    target_months: list[str],
    recursive: bool,
) -> None:
    logging.info("Running FULL_MONTHS: hotel=%s target_months=%s", hotel_id, target_months)

    build_daily_snapshots_full_months(
        input_dir=raw_inventory.raw_root_dir,
        hotel_id=hotel_id,
        target_months=target_months,
        layout=layout,
        output_dir=None,
        glob=EXCEL_GLOB,
        recursive=recursive,
    )


def _run_full_all(hotel_id: str, raw_inventory: RawInventory, layout: str, recursive: bool) -> None:
    input_dir = raw_inventory.raw_root_dir
    file_count = count_excel_files(input_dir, EXCEL_GLOB, recursive=recursive)
    historical_rate = load_historical_full_all_rate(LOGS_DIR)
    rate = historical_rate if historical_rate and historical_rate > 0 else DEFAULT_FULL_ALL_RATE
    estimated_seconds = file_count / rate if rate > 0 and file_count else None

    logging.info(
        "FULL_ALL precheck: hotel=%s files=%s input_dir=%s",
        hotel_id,
        file_count,
        input_dir,
    )
    if estimated_seconds is not None:
        logging.info("Estimated duration: ~%.1f seconds (rate %.2f files/sec)", estimated_seconds, rate)
    else:
        logging.info("Estimated duration unavailable; using rate %.2f files/sec", rate)

    start = time.monotonic()
    build_daily_snapshots_full_all(
        input_dir=input_dir,
        hotel_id=hotel_id,
        layout=layout,
        output_dir=None,
        glob=EXCEL_GLOB,
        recursive=recursive,
    )
    duration = time.monotonic() - start
    actual_rate = file_count / duration if duration > 0 and file_count else 0.0

    logging.info(
        "FULL_ALL completed: files=%s duration_sec=%.1f rate_files_per_sec=%.2f",
        file_count,
        duration,
        actual_rate,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily snapshots from N@FACE folders")
    parser.add_argument(
        "--hotel",
        choices=[*HOTEL_CONFIG.keys(), "all"],
        default="all",
        help="Hotel identifier to process",
    )
    parser.add_argument(
        "--mode",
        choices=["FAST", "FULL_MONTHS", "FULL_ALL"],
        default="FAST",
        type=str.upper,
        help="Execution mode",
    )
    parser.add_argument(
        "--target-months",
        help="Comma separated stay months (YYYYMM,YYYYMM,...). Required for FAST and FULL_MONTHS.",
    )
    parser.add_argument(
        "--buffer-days",
        type=int,
        default=14,
        help="Buffer days for FAST mode when inferring asof_min",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm FULL_ALL execution without interactive prompt",
    )
    parser.add_argument(
        "--confirm-full-all",
        help='Additional confirmation string required for FULL_ALL (expects "FULL_ALL")',
    )
    parser.add_argument(
        "--rebuild-asof-index",
        action="store_true",
        help="Rebuild asof_dates CSV after processing each hotel",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search Excel files recursively under input_dir (supports monthly subfolders).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    log_file: Path | None = None
    if args.mode == "FULL_ALL":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        log_file = LOGS_DIR / f"full_all_{timestamp}.log"

    _configure_logging(log_file)

    target_months: list[str] | None = None
    if args.mode in {"FAST", "FULL_MONTHS"}:
        target_months = _parse_target_months_arg(args.target_months)

    confirmed_full_all = bool(args.yes) or (args.confirm_full_all or "").strip().upper() == "FULL_ALL"
    if args.mode == "FULL_ALL" and not confirmed_full_all:
        logging.warning(
            "FULL_ALL mode requires confirmation. Specify --yes or --confirm-full-all FULL_ALL to proceed.",
        )
        return

    hotel_ids = _resolve_hotel_ids(args.hotel)

    for hotel_id in hotel_ids:
        raw_inventory = _build_raw_inventory_or_raise(hotel_id)
        adapter_type = raw_inventory.adapter_type

        if adapter_type != "nface":
            raise ValueError(f"{hotel_id}: adapter_type '{adapter_type}' is not supported (nface only)")

        recursive = raw_inventory.include_subfolders
        if args.recursive and not recursive:
            logging.info(
                "%s: include_subfolders is False in hotels.json; ignoring --recursive flag to keep hotels.json authoritative",
                hotel_id,
            )

        layout = HOTEL_CONFIG[hotel_id].get("layout", "auto")

        if args.mode == "FAST":
            _run_fast(hotel_id, raw_inventory, layout, target_months or [], args.buffer_days, recursive)
        elif args.mode == "FULL_MONTHS":
            _run_full_months(hotel_id, raw_inventory, layout, target_months or [], recursive)
        else:
            _run_full_all(hotel_id, raw_inventory, layout, recursive)

        if args.rebuild_asof_index:
            rebuild_asof_dates_from_daily_snapshots(hotel_id)


if __name__ == "__main__":
    main()
