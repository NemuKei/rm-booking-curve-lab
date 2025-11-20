"""
直近数ヶ月分の LT_DATA CSV をまとめて出力するスクリプト。

使い方（今は手動で設定）：
- HOTEL_SUBDIR, TIME_SERIES_FILE を自分の環境に合わせる
- TARGET_MONTHS を ["YYYYMM", ...] 形式で指定する
- src フォルダで `python run_build_lt_csv.py` を実行
"""

from pathlib import Path

from booking_curve.data_loader import load_time_series_excel
from booking_curve.lt_builder import build_lt_data
from booking_curve.config import OUTPUT_DIR


# ===== 設定ここから =====

# data/ 以下のホテル用サブフォルダ
HOTEL_SUBDIR = "namba_daikokucho"

# PMSから整理した「時系列データ」Excel
TIME_SERIES_FILE = "大国町_時系列データ.xlsx"

# LT_DATA を出したい宿泊月（シート名）リスト
# 例：2025年7〜10月
TARGET_MONTHS = [
    "202401",
    "202402",
    "202403",
    "202404",
    "202405",
    "202406",
    "202407",
    "202408",
    "202409",
    "202410",
    "202411",
    "202412",
]

# 出力ファイル名に付けるホテル識別子（お好みで）
HOTEL_TAG = "daikokucho"

# 最大リードタイム
MAX_LT = 120

# ===== 設定ここまで =====


def build_lt_for_month(sheet_name: str) -> None:
    """指定月シートの LT_DATA を作成して CSV 出力する。"""
    # data_loader は data/ 配下を前提にしているので、
    # ホテルフォルダ＋ファイル名で相対パス指定する
    relative_path = f"{HOTEL_SUBDIR}/{TIME_SERIES_FILE}"

    print(f"[INFO] sheet={sheet_name} から LT_DATA を作成中 ...")

    df_ts = load_time_series_excel(
        filename=relative_path,
        sheet_name=sheet_name,
    )

    lt_df = build_lt_data(df_ts, max_lt=MAX_LT)

    out_name = f"lt_data_{sheet_name}_{HOTEL_TAG}.csv"
    out_path = OUTPUT_DIR / out_name

    lt_df.to_csv(out_path, index=True)
    print(f"[OK] 出力: {out_path}")


def main():
    print("=== LT_DATA CSV 一括生成 ===")
    print(f"対象ホテル: {HOTEL_SUBDIR} / ファイル: {TIME_SERIES_FILE}")
    print(f"対象月シート: {', '.join(TARGET_MONTHS)}")
    print("")

    for sheet in TARGET_MONTHS:
        build_lt_for_month(sheet)

    print("\n=== 完了しました ===")


if __name__ == "__main__":
    main()
