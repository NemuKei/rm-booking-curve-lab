from __future__ import annotations

from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR


def _load_calendar(hotel_tag: str) -> pd.DataFrame:
    """
    calendar_features_{hotel_tag}.csv を読み込んで返す。
    date 列を DatetimeIndex にして返す。
    """
    path = Path(OUTPUT_DIR) / f"calendar_features_{hotel_tag}.csv"
    cal = pd.read_csv(path)
    cal["date"] = pd.to_datetime(cal["date"])
    cal = cal.set_index("date")
    return cal


def apply_segment_adjustment(forecast_df: pd.DataFrame, hotel_tag: str) -> pd.DataFrame:
    """
    forecast_df にセグメント別の係数補正を適用し、
    adjusted_projected_rooms 列を追加して返す。

    現状のルール:
    - 3連休以上 (holiday_block_len >= 3) かつ holiday_position == "middle"
      の日だけ projected_rooms * 0.98 にする。
    - それ以外は 1.0 倍（補正なし）。
    - 補正後は四捨五入して整数にする。
    """
    if "projected_rooms" not in forecast_df.columns:
        raise ValueError("forecast_df に 'projected_rooms' 列が必要です。")

    cal = _load_calendar(hotel_tag)

    df = forecast_df.copy()
    df.index = pd.to_datetime(df.index)

    df = df.join(cal, how="left")

    factor = pd.Series(1.0, index=df.index)

    mask_middle_long = (df["holiday_block_len"] >= 3) & (df["holiday_position"] == "middle")
    factor.loc[mask_middle_long] = 0.98

    adjusted = (df["projected_rooms"] * factor).round().astype(int)
    df["adjusted_projected_rooms"] = adjusted

    out_cols = list(forecast_df.columns)
    out_cols.append("adjusted_projected_rooms")
    df_out = df[out_cols]

    return df_out
