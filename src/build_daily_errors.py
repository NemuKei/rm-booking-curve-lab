from __future__ import annotations

from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"

# 評価対象モデルとファイル名プレフィックス
# model 列の値は "avg" / "recent90" / "recent90w"
# 対応するファイル名プレフィックスは
#   forecast_{month}_... / forecast_recent90_{month}_... / forecast_recent90w_{month}_...
MODEL_DEFS = {
    "avg": "forecast",
    "recent90": "forecast_recent90",
    "recent90w": "forecast_recent90w",
}

# 対象とする宿泊月 (YYYYMM)。既存の run_evaluate_forecasts.py と揃えて良い。
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
]
# ===== 設定ここまで =====


def load_calendar() -> pd.DataFrame:
    """
    calendar_features_{HOTEL_TAG}.csv を読み込んで返す。
    date列を Datetime に変換し、インデックスを date にする。
    """
    path = Path(OUTPUT_DIR) / f"calendar_features_{HOTEL_TAG}.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    return df


def find_forecast_files() -> list[tuple[str, str, str, Path]]:
    """
    OUTPUT_DIR から forecast CSV を探し、
    (target_month, model_name, as_of, path) のタプルリストを返す。
    """
    out_dir = Path(OUTPUT_DIR)
    results: list[tuple[str, str, str, Path]] = []

    for model_name, prefix in MODEL_DEFS.items():
        for target_month in TARGET_MONTHS:
            pattern = f"{prefix}_{target_month}_{HOTEL_TAG}_asof_"
            for p in out_dir.glob(f"{pattern}*.csv"):
                name = p.name
                try:
                    after = name.split("asof_")[1]
                    asof_str = after.replace(".csv", "").strip()
                except Exception:
                    continue

                if len(asof_str) != 8 or not asof_str.isdigit():
                    continue

                results.append((target_month, model_name, asof_str, p))

    # target_month, model, as_of の順でソート
    results.sort(key=lambda x: (x[0], x[1], x[2]))
    return results


def _append_errors_for_model(
    df_forecast: pd.DataFrame,
    target_month: str,
    model_name: str,
    as_of_str: str,
    records: list[pd.DataFrame],
) -> None:
    if "actual_rooms" not in df_forecast.columns:
        raise ValueError("actual_rooms 列がありません。")
    if "projected_rooms" not in df_forecast.columns:
        raise ValueError("projected_rooms 列がありません。")

    df = df_forecast.copy()

    # インデックスが泊日 (YYYY-MM-DD) 前提
    df.index = pd.to_datetime(df.index)

    out = pd.DataFrame(index=df.index.copy())
    out["stay_date"] = out.index
    out["target_month"] = target_month
    out["model"] = model_name
    out["as_of"] = as_of_str

    out["actual_rooms"] = df["actual_rooms"].astype(float)
    out["projected_rooms"] = df["projected_rooms"].astype(float)

    out["error"] = out["projected_rooms"] - out["actual_rooms"]
    # actual_total=0 の日があった場合にゼロ除算を避ける
    out["error_pct"] = out["error"] / out["actual_rooms"].replace(0, pd.NA) * 100.0

    records.append(out)


def build_daily_from_file(
    target_month: str, model_name: str, as_of_str: str, path: Path
) -> pd.DataFrame:
    """
    単一の forecast CSV を読み込み、日別誤差テーブルに変換して返す。
    """
    df = pd.read_csv(path, index_col=0)

    if "actual_rooms" not in df.columns:
        raise ValueError(f"{path} に actual_rooms 列がありません。")
    if "projected_rooms" not in df.columns:
        raise ValueError(f"{path} に projected_rooms 列がありません。")

    records: list[pd.DataFrame] = []

    _append_errors_for_model(
        df_forecast=df,
        target_month=target_month,
        model_name=model_name,
        as_of_str=as_of_str,
        records=records,
    )

    if "adjusted_projected_rooms" in df.columns and model_name in {"recent90", "recent90w"}:
        df_adj = df.copy()
        # 調整版では projected_rooms を adjusted_projected_rooms で置き換える
        df_adj["projected_rooms"] = df_adj["adjusted_projected_rooms"]
        # （adjusted_projected_rooms 列はあっても邪魔ではないが、
        #    気になる場合は drop してもよい）
        adj_model_name = {
            "recent90": "recent90_adj",
            "recent90w": "recent90w_adj",
        }[model_name]

        _append_errors_for_model(
            df_forecast=df_adj,
            target_month=target_month,
            model_name=adj_model_name,
            as_of_str=as_of_str,
            records=records,
        )

    return pd.concat(records, axis=0)


def main() -> None:
    cal = load_calendar()

    records: list[pd.DataFrame] = []
    files = find_forecast_files()
    if not files:
        print("forecast CSV が見つかりませんでした。")
        return

    for target_month, model_name, as_of_str, path in files:
        print(f"[READ] {path.name}")
        daily = build_daily_from_file(target_month, model_name, as_of_str, path)
        records.append(daily)

    df_all = pd.concat(records, axis=0).reset_index(drop=True)

    # カレンダーと結合 (stay_date をキーにする)
    df_all["stay_date"] = pd.to_datetime(df_all["stay_date"])
    df_all.set_index("stay_date", inplace=True)

    # カレンダーデータは date をindexにしてある前提
    df_merged = df_all.join(cal, how="left")

    # index を列に戻す
    df_merged.reset_index(inplace=True)
    df_merged.rename(columns={"index": "stay_date"}, inplace=True)

    # カラム順をある程度整理（必須ではないが読みやすく）
    cols_order = [
        "stay_date",
        "target_month",
        "model",
        "as_of",
        "actual_rooms",
        "projected_rooms",
        "error",
        "error_pct",
        "year",
        "month",
        "day",
        "weekday",
        "is_weekend",
        "is_jp_holiday",
        "is_holiday_or_weekend",
        "is_before_holiday",
        "is_after_holiday",
        "holiday_block_id",
        "holiday_block_len",
        "holiday_position",
        "is_long_holiday_middle",
    ]
    # 存在するカラムだけを選択
    cols_order = [c for c in cols_order if c in df_merged.columns]
    df_merged = df_merged[cols_order]

    out_path = Path(OUTPUT_DIR) / f"daily_errors_{HOTEL_TAG}.csv"
    df_merged.to_csv(out_path, index=False)

    print(f"[OK] 日別誤差テーブルを出力しました: {out_path}")


if __name__ == "__main__":
    main()
