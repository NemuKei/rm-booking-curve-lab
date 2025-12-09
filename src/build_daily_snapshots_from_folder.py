from pathlib import Path
from booking_curve.pms_adapter_nface import build_daily_snapshots_from_folder

build_daily_snapshots_from_folder(
    input_dir=Path("data/pms_nface_raw/daikokucho"),
    hotel_id="daikokucho",
    pattern="raw",   # A/B/C に合わせて変える
    output_dir=None, # Noneなら booking_curve.config.OUTPUT_DIR を使用
    glob="*.xls*",
)

build_daily_snapshots_from_folder(
    input_dir=Path("data/pms_nface_raw/kansai"),
    hotel_id="kansai",
    pattern="C",   # A/B/C に合わせて変える
    output_dir=None, # Noneなら booking_curve.config.OUTPUT_DIR を使用
    glob="*.xls*",
)