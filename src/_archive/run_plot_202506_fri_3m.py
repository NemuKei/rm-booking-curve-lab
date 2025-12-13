import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.forecast_simple import moving_average_3months
from booking_curve.plot_booking_curve import (
    filter_by_weekday,
    plot_booking_curves_for_weekday,
)

# ===== 設定 =====

HOTEL_TAG = "daikokucho"  # LT CSV のファイル名に合わせる
TARGET_MONTH = "202506"  # 描画したい宿泊月（6月）
HISTORY_MONTHS = ["202503", "202504", "202505"]  # 3ヶ月平均に使う履歴月
WEEKDAY = 4  # 0=月, 1=火, ..., 4=金, 5=土, 6=日

# =================


def load_lt_csv(month: str) -> pd.DataFrame:
    """output/ 下の lt_data_{month}_{HOTEL_TAG}.csv を読む。"""
    csv_path = OUTPUT_DIR / f"lt_data_{month}_{HOTEL_TAG}.csv"
    return pd.read_csv(csv_path, index_col=0)


def main():
    # ターゲット月（6月）の LT_DATA
    df_target = load_lt_csv(TARGET_MONTH)

    # 履歴3ヶ月分の LT_DATA（3〜5月）のうち、指定曜日だけ取り出す
    history_dfs = []
    for m in HISTORY_MONTHS:
        df_m = load_lt_csv(m)
        df_m_wd = filter_by_weekday(df_m, weekday=WEEKDAY)
        history_dfs.append(df_m_wd)

    # 3ヶ月平均カーブ（Series: index=LT, values=平均室数）
    avg_3m = moving_average_3months(history_dfs, lt_min=-1, lt_max=90)

    # グラフタイトル
    title = "2025-06 金曜 Booking Curve（大国町：3ヶ月平均基準）"

    # 描画：ターゲット月のLT_DATA＋3ヶ月平均カーブ
    plot_booking_curves_for_weekday(
        lt_df=df_target,
        weekday=WEEKDAY,
        title=title,
        output_path=None,  # 画像保存したければパスを入れる
        external_avg=avg_3m,
        external_avg_label="3-month avg",
    )


if __name__ == "__main__":
    main()
