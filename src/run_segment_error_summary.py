from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from booking_curve.config import OUTPUT_DIR

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"
DAILY_ERRORS_FILE = f"daily_errors_{HOTEL_TAG}.csv"
# ===== 設定ここまで =====


def load_daily_errors() -> pd.DataFrame:
    """
    日別誤差テーブル(daily_errors_{HOTEL_TAG}.csv)を読み込み、
    future部分（stay_date >= as_of）のみを返す。
    """
    path = Path(OUTPUT_DIR) / DAILY_ERRORS_FILE
    df = pd.read_csv(path, dtype={"as_of": str, "target_month": str})

    df["stay_date"] = pd.to_datetime(df["stay_date"])
    df["as_of"] = pd.to_datetime(df["as_of"], format="%Y%m%d")

    # 未来データのみに絞る
    df = df[df["stay_date"] >= df["as_of"]].copy()

    # error_pct が NaN の行は集計対象外にする
    df = df[df["error_pct"].notna()].copy()

    return df


def summarize_group(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """
    group_cols で groupby し、件数・平均誤差・絶対誤差平均を集計する。
    """
    g = (
        df.groupby(group_cols)
        .agg(
            n=("error_pct", "count"),
            mean_error_pct=("error_pct", "mean"),
            mae=("error_pct", lambda x: x.abs().mean()),
        )
        .reset_index()
    )
    return g


def summarize_by_weekday(df: pd.DataFrame) -> pd.DataFrame:
    """
    model × weekday 別に誤差サマリーを作成する。
    weekday: 0=Mon, ..., 6=Sun
    """
    cols = ["model", "weekday"]
    result = summarize_group(df, cols)

    # 見やすさのため weekday 昇順でソート
    result = result.sort_values(by=["model", "weekday"]).reset_index(drop=True)
    return result


def summarize_by_holiday_position(df: pd.DataFrame) -> pd.DataFrame:
    """
    holiday_block_len >= 3 (3連休以上) の行に絞り、
    model × holiday_position 別に誤差サマリーを作成する。

    holiday_position: "first", "middle", "last", "single", "none" など。
    ここでは 3連休以上に限定するため、
    holiday_block_len >= 3 かつ holiday_position != "none" の行のみ対象とする。
    """
    df_long = df[(df["holiday_block_len"] >= 3) & (df["holiday_position"] != "none")].copy()
    cols = ["model", "holiday_position"]
    result = summarize_group(df_long, cols)

    # 位置の順序をある程度並べ替える（存在するものだけ）
    pos_order = ["first", "middle", "last", "single", "none"]
    result["holiday_position"] = pd.Categorical(
        result["holiday_position"],
        categories=pos_order,
        ordered=True,
    )
    result = result.sort_values(by=["model", "holiday_position"]).reset_index(drop=True)
    return result


def categorize_before_holiday(df: pd.DataFrame) -> pd.DataFrame:
    """
    平日/祝前日/休日期間をざっくり3カテゴリに分類する:
    - weekday_before_holiday: is_holiday_or_weekend=False かつ is_before_holiday=True
    - normal_weekday:        is_holiday_or_weekend=False かつ is_before_holiday=False
    - holiday_or_weekend:    is_holiday_or_weekend=True
    """
    conds = [
        (~df["is_holiday_or_weekend"]) & (df["is_before_holiday"]),
        (~df["is_holiday_or_weekend"]) & (~df["is_before_holiday"]),
        (df["is_holiday_or_weekend"]),
    ]
    choices = ["weekday_before_holiday", "normal_weekday", "holiday_or_weekend"]

    df = df.copy()
    df["day_type"] = np.select(conds, choices, default="other")
    return df


def summarize_by_before_holiday(df: pd.DataFrame) -> pd.DataFrame:
    """
    model × day_type 別に誤差サマリーを作成する。
    """
    df_cat = categorize_before_holiday(df)
    cols = ["model", "day_type"]
    result = summarize_group(df_cat, cols)

    # day_type の並び順をある程度整える
    type_order = ["normal_weekday", "weekday_before_holiday", "holiday_or_weekend", "other"]
    result["day_type"] = pd.Categorical(result["day_type"], categories=type_order, ordered=True)
    result = result.sort_values(by=["model", "day_type"]).reset_index(drop=True)
    return result


def main() -> None:
    df = load_daily_errors()

    # 1) weekday
    summary_weekday = summarize_by_weekday(df)
    print("=== Summary by weekday ===")
    print(summary_weekday.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # 2) holiday_position (3連休以上)
    summary_hpos = summarize_by_holiday_position(df)
    print("\n=== Summary by holiday_position (block_len >= 3) ===")
    print(summary_hpos.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # 3) before_holidayカテゴリ
    summary_bh = summarize_by_before_holiday(df)
    print("\n=== Summary by before-holiday categories ===")
    print(summary_bh.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # CSV 保存
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_weekday.to_csv(out_dir / f"error_summary_weekday_{HOTEL_TAG}.csv", index=False)
    summary_hpos.to_csv(out_dir / f"error_summary_holiday_position_{HOTEL_TAG}.csv", index=False)
    summary_bh.to_csv(out_dir / f"error_summary_before_holiday_{HOTEL_TAG}.csv", index=False)

    print("\n[OK] セグメント別誤差サマリーを出力しました。")


if __name__ == "__main__":
    main()
