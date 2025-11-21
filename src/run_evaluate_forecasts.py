from __future__ import annotations

from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"
TARGET_MONTHS = [
    "202311",
    "202312",
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
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
]  # 評価したい宿泊月 (YYYYMM)

# 評価対象モデルとファイル名プレフィックス
MODEL_DEFS = {
    "recent90": "forecast_recent90",
    "avg": "forecast",
    # 将来SARIMAなどを追加するならここに増やす
}
# ===== 設定ここまで =====


def find_forecast_files() -> list[tuple[str, str, str, Path]]:
    """
    OUTPUT_DIR から対象月の forecast CSV を探し、
    (target_month, model_name, as_of, path) のタプルのリストを返す。

    as_of は 'YYYYMMDD' 文字列とする。
    """
    out_dir = Path(OUTPUT_DIR)
    results: list[tuple[str, str, str, Path]] = []

    for model_name, prefix in MODEL_DEFS.items():
        for target_month in TARGET_MONTHS:
            pattern = f"{prefix}_{target_month}_{HOTEL_TAG}_asof_"
            for p in out_dir.glob(f"{pattern}*.csv"):
                # ファイル名から as_of 部分を抽出
                # 例: forecast_recent90_202506_daikokucho_asof_20250531.csv
                name = p.name
                # "asof_" 以降の数字部分を切り出す
                try:
                    after = name.split("asof_")[1]
                    asof_str = after.replace(".csv", "").strip()
                except Exception:
                    continue

                if len(asof_str) != 8 or not asof_str.isdigit():
                    continue

                results.append((target_month, model_name, asof_str, p))

    # target_month, as_of の順でソート
    results.sort(key=lambda x: (x[0], x[2]))
    return results


def main() -> None:
    records: list[dict] = []

    files = find_forecast_files()
    if not files:
        print("対象の forecast CSV が見つかりませんでした。設定を確認してください。")
        return

    for target_month, model_name, asof_str, path in files:
        df = pd.read_csv(path, index_col=0)
        if "actual_rooms" not in df.columns:
            raise ValueError(f"{path} に actual_rooms 列がありません。")

        actual_total = float(df["actual_rooms"].sum(skipna=True))

        def _calc_one(model_label: str, col_name: str) -> dict | None:
            if col_name not in df.columns:
                return None
            forecast_total = float(df[col_name].sum(skipna=True))
            error = forecast_total - actual_total
            if actual_total == 0:
                error_pct = float("nan")
            else:
                error_pct = error / actual_total * 100.0
            return {
                "target_month": target_month,
                "model": model_label,
                "as_of": asof_str,
                "file": path.name,
                "actual_total": actual_total,
                "forecast_total": forecast_total,
                "error": error,
                "error_pct": error_pct,
                "abs_error_pct": abs(error_pct) if error_pct == error_pct else float("nan"),
            }

        rec_base = _calc_one(model_name, "projected_rooms")
        if rec_base is not None:
            records.append(rec_base)

        if model_name == "recent90":
            rec_adj = _calc_one("recent90_adj", "adjusted_projected_rooms")
            if rec_adj is not None:
                records.append(rec_adj)

    # DataFrame にしてソート
    df_result = pd.DataFrame(records)
    df_result.sort_values(by=["target_month", "model", "as_of"], inplace=True)

    # 出力
    out_dir = Path(OUTPUT_DIR)
    out_name = f"evaluation_{HOTEL_TAG}_multi.csv"
    out_path = out_dir / out_name
    df_result.to_csv(out_path, index=False)

    print("[OK] 評価結果を出力しました:")
    print(out_path)
    print()
    print(df_result.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))


if __name__ == "__main__":
    main()
