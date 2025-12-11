import argparse

from .config import OUTPUT_DIR
from .data_loader import load_time_series_excel
from .lt_builder import build_lt_data


def main():
    parser = argparse.ArgumentParser(description="Booking Curve LT_DATA generator")
    parser.add_argument("--file", required=True, help="時系列Excelファイル名（data/配下想定）")
    parser.add_argument("--sheet", required=True, help="シート名（例: 202506）")
    parser.add_argument("--out", default="lt_data.csv", help="出力CSVファイル名")
    args = parser.parse_args()

    df_raw = load_time_series_excel(args.file, args.sheet)
    lt_df = build_lt_data(df_raw, max_lt=90)

    out_path = OUTPUT_DIR / args.out
    lt_df.to_csv(out_path, index=True)
    print(f"LT_DATA を出力しました: {out_path}")


if __name__ == "__main__":
    main()
