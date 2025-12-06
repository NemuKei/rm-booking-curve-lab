"""
直近数ヶ月分の LT_DATA CSV をまとめて出力するスクリプト。

GUI からは run_build_lt_for_gui(hotel_tag, target_months) を呼び出す。
CLI 実行時は HOTELS_CONFIG の先頭に定義された hotel_tag（現在は daikokucho）を処理する。
"""

from pathlib import Path

import pandas as pd

from booking_curve.data_loader import load_time_series_excel
from booking_curve.lt_builder import (
    build_lt_data,
    build_monthly_curve_from_timeseries,
    extract_asof_dates_from_timeseries,
)
from booking_curve.config import DATA_DIR, OUTPUT_DIR, HOTEL_CONFIG


DEFAULT_HOTEL_TAG = next(iter(HOTEL_CONFIG.keys()))

# LT_DATA を出したい宿泊月（シート名）リスト（CLI デフォルト）
TARGET_MONTHS = [
    "202511",
    "202512",
    "202601",
    "202602",
]

# 最大リードタイム
MAX_LT = 120


def _get_hotel_io_config(hotel_tag: str) -> tuple[Path, str]:
    """
    指定された hotel_tag について、時系列データExcelのパスと表示名を返すヘルパー。

    Returns:
        excel_path: DATA_DIR / data_subdir / timeseries_file
        display_name: GUIなどで使う表示名
    """
    cfg = HOTEL_CONFIG.get(hotel_tag)
    if cfg is None:
        raise KeyError(f"Unknown hotel_tag: {hotel_tag!r}")

    data_subdir = cfg.get("data_subdir")
    timeseries_file = cfg.get("timeseries_file")
    if not data_subdir or not timeseries_file:
        raise ValueError(
            f"Hotel config missing data_subdir/timeseries_file for {hotel_tag!r}"
        )

    excel_path = DATA_DIR / data_subdir / timeseries_file
    display_name = cfg.get("display_name", hotel_tag)
    return excel_path, display_name


def build_lt_for_month(
    sheet_name: str, hotel_tag: str, excel_path: Path
) -> list[pd.Timestamp]:
    """指定した宿泊月シートの LT_DATA を作成し、ASOF 日付一覧を返す。"""

    print(f"[INFO] sheet={sheet_name} から LT_DATA を作成中 ...")

    df_ts = load_time_series_excel(
        filename=excel_path,
        sheet_name=sheet_name,
    )

    asof_dates = extract_asof_dates_from_timeseries(df_ts)
    lt_df = build_lt_data(df_ts, max_lt=MAX_LT)

    out_name = f"lt_data_{sheet_name}_{hotel_tag}.csv"
    out_path = OUTPUT_DIR / out_name

    lt_df.to_csv(out_path, index=True)
    print(f"[OK] 出力: {out_path}")

    monthly_df = build_monthly_curve_from_timeseries(df_ts, max_lt=MAX_LT)
    if monthly_df.empty:
        print(
            f"[run_build_lt_csv] Skip monthly_curve for {hotel_tag} {sheet_name}: no data"
        )
    else:
        monthly_out_name = f"monthly_curve_{sheet_name}_{hotel_tag}.csv"
        monthly_out_path = OUTPUT_DIR / monthly_out_name
        monthly_df.to_csv(monthly_out_path)
        print(f"[run_build_lt_csv] Saved monthly_curve csv: {monthly_out_path}")

    return [pd.Timestamp(d) for d in asof_dates]


def run_build_lt_for_gui(
    hotel_tag: str,
    target_months: list[str],
) -> None:
    """
    GUI から呼び出すための薄いラッパー。

    target_months に指定された宿泊月(YYYYMM)だけについて LT_DATA CSV を再生成し、
    それらの取得日一覧をまとめて asof_dates_＜hotel_tag＞.csv として上書き出力する。
    """

    if not target_months:
        print("[INFO] 対象月が指定されていないため処理をスキップします。")
        return

    excel_path, display_name = _get_hotel_io_config(hotel_tag)
    print(
        f"対象ホテル: {display_name} ({hotel_tag}) / ファイル: {excel_path.name}"
    )

    all_asof_dates: list[pd.Timestamp] = []

    for ym in target_months:
        month_asofs = build_lt_for_month(
            ym,
            hotel_tag=hotel_tag,
            excel_path=excel_path,
        )
        all_asof_dates.extend(pd.Timestamp(d).normalize() for d in month_asofs)

    if not all_asof_dates:
        print("[WARN] 取得日が1件も検出されませんでした (asof_dates CSV は出力されません)。")
        return

    asof_list = sorted({d.normalize() for d in all_asof_dates})
    df_asof = pd.DataFrame({"as_of_date": asof_list})
    asof_path = OUTPUT_DIR / f"asof_dates_{hotel_tag}.csv"
    df_asof.to_csv(asof_path, index=False)
    print(f"[OK] 取得日一覧: {asof_path}")


def main():
    hotel_tag = DEFAULT_HOTEL_TAG
    excel_path, display_name = _get_hotel_io_config(hotel_tag)

    print("=== LT_DATA CSV 一括生成 ===")
    print(f"対象ホテル: {display_name} ({hotel_tag}) / ファイル: {excel_path.name}")
    print(f"対象月シート: {', '.join(TARGET_MONTHS)}")
    print("")

    run_build_lt_for_gui(hotel_tag=hotel_tag, target_months=TARGET_MONTHS)

    print("\n=== 完了しました ===")


if __name__ == "__main__":
    main()
