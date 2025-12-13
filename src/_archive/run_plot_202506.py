from pathlib import Path

import pandas as pd

# ブッキングカーブの描画関数をインポート
from booking_curve.plot_booking_curve import plot_booking_curves_for_weekday


def main():
    # プロジェクトルートを取得（src/ から1つ上）
    project_root = Path(__file__).resolve().parents[1]

    # LT_DATA の CSV パス（output フォルダ内）
    csv_path = project_root / "output" / "lt_data_202506_daikokucho_v2.csv"

    # CSV を読み込み（index_col=0 で宿泊日をインデックスにする）
    lt_df = pd.read_csv(csv_path, index_col=0)

    # 例：金曜のブッキングカーブを描画
    # weekday の定義：0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    weekday = 4  # 金曜

    title = "2025-06 金曜 Booking Curve（大国町）"

    plot_booking_curves_for_weekday(
        lt_df=lt_df,
        weekday=weekday,
        title=title,
        output_path=None,  # ファイル保存したいならパスを渡す
    )


if __name__ == "__main__":
    main()
