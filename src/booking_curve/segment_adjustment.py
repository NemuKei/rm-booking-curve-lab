from __future__ import annotations

from pathlib import Path
import logging

import numpy as np
import pandas as pd

from booking_curve.config import OUTPUT_DIR

logger = logging.getLogger(__name__)
_CALENDAR_WARNED = False


def _warn_calendar_missing(reason: str, hotel_tag: str, path: Path) -> None:
    global _CALENDAR_WARNED
    if _CALENDAR_WARNED:
        return
    logger.warning(
        "calendar_features missing or unreadable (%s). Using neutral adjustment. hotel_tag=%s path=%s",
        reason,
        hotel_tag,
        path,
    )
    _CALENDAR_WARNED = True


def _load_calendar(hotel_tag: str) -> pd.DataFrame:
    """
    calendar_features_{hotel_tag}.csv を読み込んで返す。
    date 列を DatetimeIndex にして返す。
    """
    path = Path(OUTPUT_DIR) / f"calendar_features_{hotel_tag}.csv"
    try:
        cal = pd.read_csv(path)
    except FileNotFoundError:
        _warn_calendar_missing("file_not_found", hotel_tag, path)
        return pd.DataFrame(index=pd.DatetimeIndex([]))
    except pd.errors.EmptyDataError:
        _warn_calendar_missing("empty_file", hotel_tag, path)
        return pd.DataFrame(index=pd.DatetimeIndex([]))
    cal["date"] = pd.to_datetime(cal["date"])
    cal = cal.set_index("date")
    return cal


def _round_int_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mask = values.isna()
    rounded = np.rint(values.fillna(0).to_numpy(dtype=float)).astype(np.int64, copy=False)
    result = pd.array(rounded, dtype="Int64")
    result[mask.to_numpy()] = pd.NA
    return pd.Series(result, index=series.index, name=series.name)


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

    if "holiday_block_len" in df.columns and "holiday_position" in df.columns:
        holiday_block_len = pd.to_numeric(df["holiday_block_len"], errors="coerce").fillna(0)
        holiday_position = df["holiday_position"].fillna("")
        mask_middle_long = (holiday_block_len >= 3) & (holiday_position == "middle")
        factor.loc[mask_middle_long] = 0.98

    projected = pd.to_numeric(df["projected_rooms"], errors="coerce")
    adjusted = _round_int_series(projected * factor)
    df["adjusted_projected_rooms"] = adjusted

    out_cols = list(forecast_df.columns)
    out_cols.append("adjusted_projected_rooms")
    df_out = df[out_cols]

    return df_out
