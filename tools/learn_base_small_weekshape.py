import argparse
import json
import sys
from pathlib import Path


def _setup_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Learn base-small weekshape quantiles and persist to hotels.json.")
    parser.add_argument("--hotel", required=True, help="Hotel tag (e.g., daikokucho)")
    parser.add_argument("--window-months", type=int, default=3, help="Lookback window in months (default: 3)")
    parser.add_argument("--stride-days", type=int, default=7, help="Sampling stride in days (default: 7)")
    args = parser.parse_args()

    _setup_paths()

    from booking_curve.gui_backend import train_base_small_weekshape_for_gui

    result = train_base_small_weekshape_for_gui(
        args.hotel,
        window_months=args.window_months,
        sample_stride_days=args.stride_days,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
