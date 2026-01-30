import pandas as pd

# ブッキングカーブの描画関数をインポート
from booking_curve.config import get_hotel_output_dir
from booking_curve.plot_booking_curve import plot_booking_curves_for_weekday

HOTEL_TAG = "daikokucho"
TARGET_MONTH = "202506"


def main():
    # LT_DATA の CSV パス（output/<hotel_id>/ 内）
    csv_path = get_hotel_output_dir(HOTEL_TAG) / f"lt_data_{TARGET_MONTH}.csv"

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
