from __future__ import annotations

import logging
from pathlib import Path

from booking_curve.pms_adapter_nface import build_daily_snapshots_from_folder


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


def main() -> None:
    # ログ設定（必要に応じてレベルを INFO/WARNING に調整）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    for hotel_id, cfg in HOTELS.items():
        input_dir = cfg["input_dir"]
        layout = cfg.get("layout", "auto")

        logging.info("ホテル %s の N@FACE 生データを処理します (layout=%s)", hotel_id, layout)

        build_daily_snapshots_from_folder(
            input_dir=input_dir,
            hotel_id=hotel_id,
            layout=layout,      # "auto" / "shifted" / "inline"
            output_dir=None,    # None -> booking_curve.config.OUTPUT_DIR が使われる
            glob="*.xls*",      # .xls / .xlsx 両方を対象
        )

    logging.info("すべてのホテルの処理が完了しました。")


if __name__ == "__main__":
    main()
