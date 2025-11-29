"""
直近数ヶ月分の LT_DATA CSV をまとめて出力するスクリプト。

使い方（今は手動で設定）：
- HOTEL_SUBDIR, TIME_SERIES_FILE を自分の環境に合わせる
- TARGET_MONTHS を ["YYYYMM", ...] 形式で指定する
- src フォルダで `python run_build_lt_csv.py` を実行
"""

from pathlib import Path

import pandas as pd

from booking_curve.data_loader import load_time_series_excel
from booking_curve.lt_builder import build_lt_data, extract_asof_dates_from_timeseries
from booking_curve.config import OUTPUT_DIR


# ===== 設定ここから =====

# data/ 以下のホテル用サブフォルダ
HOTEL_SUBDIR = "namba_daikokucho"

# PMSから整理した「時系列データ」Excel
TIME_SERIES_FILE = "大国町_時系列データ.xlsx"

# LT_DATA を出したい宿泊月（シート名）リスト
# 例：2025年7〜10月
TARGET_MONTHS = [
    "202511",
    "202512",
    "202601",
    "202602",
]

# 出力ファイル名に付けるホテル識別子（お好みで）
HOTEL_TAG = "daikokucho"

# 最大リードタイム
MAX_LT = 120

# ===== 設定ここまで =====


def build_lt_for_month(sheet_name: str) -> list[pd.Timestamp]:
    """指定月シートの LT_DATA を作成して CSV 出力し、その月の ASOF 日付一覧を返す。"""

    # data_loader は data/ 配下を前提にしているので、
    # ホテルフォルダ＋ファイル名で相対パス指定する
    relative_path = f"{HOTEL_SUBDIR}/{TIME_SERIES_FILE}"

    print(f"[INFO] sheet={sheet_name} から LT_DATA を作成中 ...")

    df_ts = load_time_series_excel(
        filename=relative_path,
        sheet_name=sheet_name,
    )

    # 取得日(ASOF)一覧を抽出
    asof_dates = extract_asof_dates_from_timeseries(df_ts)

    lt_df = build_lt_data(df_ts, max_lt=MAX_LT)

    out_name = f"lt_data_{sheet_name}_{HOTEL_TAG}.csv"
    out_path = OUTPUT_DIR / out_name

    lt_df.to_csv(out_path, index=True)
    print(f"[OK] 出力: {out_path}")

    # datetime → pandas.Timestamp に揃えて返す
    return [pd.Timestamp(d) for d in asof_dates]


def run_build_lt_for_gui(target_months: list[str]) -> None:
    """
    GUI から呼び出すための薄いラッパー。

    target_months に指定された宿泊月(YYYYMM)だけについて LT_DATA CSV を再生成し、
    それらの取得日一覧をまとめて asof_dates_＜HOTEL_TAG＞.csv として上書き出力する。
    """

    if not target_months:
        return

    all_asof_dates: set[pd.Timestamp] = set()

    for sheet in target_months:
        month_asofs = build_lt_for_month(sheet)
        for d in month_asofs:
            all_asof_dates.add(d.normalize())

    if all_asof_dates:
        asof_list = sorted(all_asof_dates)
        df_asof = pd.DataFrame({"as_of_date": asof_list})
        asof_path = OUTPUT_DIR / f"asof_dates_{HOTEL_TAG}.csv"
        df_asof.to_csv(asof_path, index=False)
        print(f"[OK] 取得日一覧: {asof_path}")
    else:
        print("[WARN] 取得日が1件も検出されませんでした (asof_dates CSV は出力されません)。")


def main():
    print("=== LT_DATA CSV 一括生成 ===")
    print(f"対象ホテル: {HOTEL_SUBDIR} / ファイル: {TIME_SERIES_FILE}")
    print(f"対象月シート: {', '.join(TARGET_MONTHS)}")
    print("")

    run_build_lt_for_gui(TARGET_MONTHS)

    print("\n=== 完了しました ===")


if __name__ == "__main__":
    main()
