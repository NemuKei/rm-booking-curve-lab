"""LT（Lead Time）データ生成モジュール.

PMSから取得した宿泊日×取得日の時系列データを、宿泊日×LTの
ブッキングカーブ形式に整形する。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

import pandas as pd

EXCEL_BASE_DATE = datetime(1899, 12, 30)


def _excel_serial_to_datetime(serial: float) -> datetime:
    """Excelシリアル値をdatetimeに変換する。"""

    return EXCEL_BASE_DATE + timedelta(days=float(serial))


def build_lt_data(df: pd.DataFrame, max_lt: int = 90) -> pd.DataFrame:
    """宿泊日×取得日のデータから宿泊日×LT（-1〜max_lt）のテーブルを構築する。"""

    lt_desc_columns = list(range(max_lt, -2, -1))

    if df is None or df.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    booking_date_serials = df.iloc[0, 1:]
    booking_dates: List[datetime] = []
    for serial in booking_date_serials:
        if pd.isna(serial):
            booking_dates.append(pd.NaT)
            continue
        booking_dates.append(_excel_serial_to_datetime(serial))

    records = []
    for _, row in df.iloc[1:].iterrows():
        stay_raw = row.iloc[0]
        stay_date = pd.to_datetime(stay_raw, errors="coerce")
        if pd.isna(stay_date):
            continue
        stay_date = stay_date.normalize()

        for idx, rooms in enumerate(row.iloc[1:]):
            if pd.isna(rooms):
                continue
            if idx >= len(booking_dates):
                break

            booking_date = booking_dates[idx]
            if pd.isna(booking_date):
                continue

            lt = (stay_date - booking_date).days
            if -1 <= lt <= max_lt:
                records.append({"stay_date": stay_date, "lt": lt, "rooms": rooms})

    if not records:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    records_df = pd.DataFrame(records)
    lt_table = (
        records_df.pivot_table(
            index="stay_date", columns="lt", values="rooms", aggfunc="last"
        )
        .reindex(columns=range(-1, max_lt + 1))
        .sort_index()
    )

    if lt_table.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    full_nan_rows = lt_table.isna().all(axis=1)

    lt_interpolated = lt_table.interpolate(axis=1, limit_direction="both")
    if full_nan_rows.any():
        lt_interpolated.loc[full_nan_rows, :] = float("nan")

    lt_rounded = lt_interpolated.round().astype("Int64")

    for stay_date in lt_rounded.index[full_nan_rows]:
        print(f"[lt_builder] Warning: No data for stay_date {stay_date.date()}")

    lt_final = lt_rounded.reindex(columns=lt_desc_columns)

    return lt_final
