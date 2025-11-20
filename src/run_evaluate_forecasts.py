from __future__ import annotations

from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"
TARGET_MONTH = "202506"  # 評価したい宿泊月 (YYYYMM)

# 評価対象モデルとファイル名プレフィックス
MODEL_DEFS = {
    "recent90": "forecast_recent90",
    "avg": "forecast",
    # 将来SARIMAなどを追加するならここに増やす
}
# ===== 設定ここまで =====


def find_forecast_files() -> list[tuple[str, str, Path]]:
    """
    OUTPUT_DIR から対象月の forecast CSV を探し、
    (model_name, as_of, path) のタプルのリストを返す。

    as_of は 'YYYYMMDD' 文字列とする。
    """
    out_dir = Path(OUTPUT_DIR)
    results: list[tuple[str, str, Path]] = []

    for model_name, prefix in MODEL_DEFS.items():
        pattern = f"{prefix}_{TARGET_MONTH}_{HOTEL_TAG}_asof_"
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

            results.append((model_name, asof_str, p))

    # as_of 日付順にソート
    results.sort(key=lambda x: x[1])
    return results


def evaluate_forecast_file(path: Path) -> tuple[float, float, float, float]:
    """
    単一の forecast CSV について、
    (actual_total, forecast_total, error, error_pct) を計算して返す。

    - actual_total : actual_rooms の合計（NaN は無視）
    - forecast_total : projected_rooms の合計（NaN は無視）
    """
    df = pd.read_csv(path, index_col=0)

    if "actual_rooms" not in df.columns:
        raise ValueError(f"{path} に actual_rooms 列がありません。")
    if "projected_rooms" not in df.columns:
        raise ValueError(f"{path} に projected_rooms 列がありません。")

    actual_total = float(df["actual_rooms"].sum(skipna=True))
    forecast_total = float(df["projected_rooms"].sum(skipna=True))
    error = forecast_total - actual_total
    if actual_total == 0:
        error_pct = float("nan")
    else:
        error_pct = error / actual_total * 100.0

    return actual_total, forecast_total, error, error_pct


def main() -> None:
    records: list[dict] = []

    files = find_forecast_files()
    if not files:
        print("対象の forecast CSV が見つかりませんでした。設定を確認してください。")
        return

    for model_name, asof_str, path in files:
        actual_total, forecast_total, error, error_pct = evaluate_forecast_file(path)

        records.append(
            {
                "model": model_name,
                "as_of": asof_str,
                "file": path.name,
                "actual_total": actual_total,
                "forecast_total": forecast_total,
                "error": error,
                "error_pct": error_pct,
            }
        )

    # DataFrame にしてソート
    df_result = pd.DataFrame(records)
    df_result.sort_values(by=["model", "as_of"], inplace=True)

    # 出力
    out_dir = Path(OUTPUT_DIR)
    out_name = f"evaluation_{TARGET_MONTH}_{HOTEL_TAG}.csv"
    out_path = out_dir / out_name
    df_result.to_csv(out_path, index=False)

    print("[OK] 評価結果を出力しました:")
    print(out_path)
    print()
    print(df_result.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))


if __name__ == "__main__":
    main()
