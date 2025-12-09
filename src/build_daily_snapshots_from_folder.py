from pathlib import Path
from booking_curve.pms_adapter_nface import build_daily_snapshots_from_folder

# 大国町：無加工 / 加工A / 加工B 系
# → 宿泊日行の「1行下」に OH が入っているレイアウトなので layout="shifted"
build_daily_snapshots_from_folder(
    input_dir=Path("data/pms_nface_raw/daikokucho"),
    hotel_id="daikokucho",
    layout="shifted",          # 無加工 / A / B はすべて shifted
    output_dir=None,           # Noneなら booking_curve.config.OUTPUT_DIR を使用
    glob="*.xls*",             # .xls / .xlsx 両方対応
)

# ホテル関西：加工C 系
# → 宿泊日行と「同じ行」に OH が入っているレイアウトなので layout="inline"
build_daily_snapshots_from_folder(
    input_dir=Path("data/pms_nface_raw/kansai"),
    hotel_id="kansai",
    layout="inline",           # 加工C は inline
    output_dir=None,           # Noneなら booking_curve.config.OUTPUT_DIR を使用
    glob="*.xls*",             # .xls / .xlsx 両方対応
)
