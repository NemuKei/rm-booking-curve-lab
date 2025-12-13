from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from booking_curve.daily_snapshots import get_latest_asof_date
from booking_curve.pms_adapter_nface import (
    build_daily_snapshots_from_folder,
    build_daily_snapshots_from_folder_partial,
)

# N@FACE 生データの配置とレイアウト指定
# layout は省略すれば "auto" になるが、必要なら "shifted"/"inline" を明示してもよい。
HOTELS = {
    # 無加工 / A / B がメインだが、C が混じっていても layout="auto" で自動判定可能
    "daikokucho": {
        "input_dir": Path("data/pms_nface_raw/daikokucho"),
        "layout": "auto",  # ここを "shifted" に固定してもOK
    },
    # 関西側も同様に混在を想定して "auto" にしておく
    "kansai": {
        "input_dir": Path("data/pms_nface_raw/kansai"),
        "layout": "auto",  # 必要なら "inline" 固定も可
    },
    "domemae": {
        "input_dir": Path("data/pms_nface_raw/domemae"),
        "layout": "auto",  # 必要なら "inline" 固定も可
    },
    # 他ホテルを追加する場合はここにエントリを増やす
    # "some_hotel": {
    #     "input_dir": Path("data/pms_nface_raw/some_hotel"),
    #     "layout": "auto",
    # },
}


def _parse_target_months(
    target_months_arg: str | None, from_ym: str | None, to_ym: str | None
) -> tuple[list[str] | None, pd.Timestamp | None, pd.Timestamp | None]:
    """Parse target months argument into list and stay date boundaries."""

    def _validate_month(month: str) -> pd.Timestamp:
        month = month.strip()
        if len(month) != 6 or not month.isdigit():
            raise ValueError("month must be in YYYYMM format")
        return pd.to_datetime(f"{month}01", format="%Y%m%d", errors="raise")

    if target_months_arg:
        months = [m.strip() for m in target_months_arg.split(",") if m.strip()]
        if not months:
            raise ValueError("target-months must contain at least one YYYYMM value")
        month_starts = [_validate_month(month) for month in months]
    elif from_ym or to_ym:
        if not (from_ym and to_ym):
            raise ValueError("both --from-ym and --to-ym are required when using ranges")
        start = _validate_month(from_ym)
        end = _validate_month(to_ym)
        if start > end:
            raise ValueError("from-ym must be earlier than or equal to to-ym")
        month_starts = [
            (start + pd.DateOffset(months=offset))
            for offset in range((end.year - start.year) * 12 + (end.month - start.month) + 1)
        ]
        months = [dt.strftime("%Y%m") for dt in month_starts]
    else:
        return None, None, None

    stay_min = min(month_starts)
    last_month_end = max(month_starts) + pd.offsets.MonthEnd(0)
    return months, stay_min, last_month_end


def _log_run_parameters(
    hotel_ids: Iterable[str],
    mode: str,
    target_months: list[str] | None,
    asof_min: pd.Timestamp | str | None,
    asof_max: pd.Timestamp | str | None,
    buffer_days: int,
) -> None:
    hotels_str = ",".join(hotel_ids)
    logging.info(
        "run params -> hotel=%s, mode=%s, target_months=%s, asof_min=%s, asof_max=%s, buffer_days=%s",
        hotels_str,
        mode,
        target_months,
        asof_min,
        asof_max,
        buffer_days,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily snapshots from N@FACE folders")
    parser.add_argument(
        "--hotel",
        choices=[*HOTELS.keys(), "all"],
        default="all",
        help="Hotel identifier to process (default: all)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "partial"],
        default="partial",
        help="Build mode: full or partial (default: partial)",
    )
    parser.add_argument("--from-ym", help="Stay month range start in YYYYMM", dest="from_ym")
    parser.add_argument("--to-ym", help="Stay month range end in YYYYMM", dest="to_ym")
    parser.add_argument(
        "--target-months",
        help="Comma separated stay months (YYYYMM). Takes precedence over from/to range",
    )
    parser.add_argument("--asof-min", help="Minimum as_of_date in YYYY-MM-DD")
    parser.add_argument("--asof-max", help="Maximum as_of_date in YYYY-MM-DD")
    parser.add_argument(
        "--buffer-days",
        type=int,
        default=14,
        help="Buffer days when computing asof_min automatically (default: 14)",
    )
    parser.add_argument(
        "--auto-asof-from-csv",
        action="store_true",
        help="Infer asof_min from existing daily_snapshots CSV when not specified",
    )
    return parser.parse_args()


def main() -> None:
    # ログ設定（必要に応じてレベルを INFO/WARNING に調整）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    args = _parse_args()
    target_months, stay_min, stay_max = _parse_target_months(
        args.target_months, args.from_ym, args.to_ym
    )

    hotels_to_process: Iterable[tuple[str, dict]]
    if args.hotel == "all":
        hotels_to_process = HOTELS.items()
    else:
        hotels_to_process = [(args.hotel, HOTELS[args.hotel])]

    for hotel_id, cfg in hotels_to_process:
        input_dir = cfg["input_dir"]
        layout = cfg.get("layout", "auto")

        asof_min = args.asof_min
        asof_max = args.asof_max
        if (
            args.mode == "partial"
            and args.auto_asof_from_csv
            and not args.asof_min
            and not args.asof_max
        ):
            last_asof = get_latest_asof_date(hotel_id)
            if last_asof is not None:
                asof_min = last_asof - pd.Timedelta(days=args.buffer_days)

        _log_run_parameters(
            [hotel_id],
            args.mode,
            target_months,
            asof_min,
            asof_max,
            args.buffer_days,
        )
        logging.info("ホテル %s の N@FACE 生データを処理します (layout=%s)", hotel_id, layout)

        if args.mode == "full":
            build_daily_snapshots_from_folder(
                input_dir=input_dir,
                hotel_id=hotel_id,
                layout=layout,  # "auto" / "shifted" / "inline"
                output_dir=None,  # None -> booking_curve.config.OUTPUT_DIR が使われる
                glob="*.xls*",  # .xls / .xlsx 両方を対象
            )
        else:
            build_daily_snapshots_from_folder_partial(
                input_dir=input_dir,
                hotel_id=hotel_id,
                target_months=target_months,
                asof_min=asof_min,
                asof_max=asof_max,
                stay_min=stay_min,
                stay_max=stay_max,
                layout=layout,
                output_dir=None,
                glob="*.xls*",
            )

    logging.info("すべてのホテルの処理が完了しました。")


if __name__ == "__main__":
    main()
