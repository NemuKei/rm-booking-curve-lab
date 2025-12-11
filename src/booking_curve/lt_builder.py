"""LT（Lead Time）データ生成モジュール.

PMSから取得した宿泊日×取得日の時系列データを、宿泊日×LTの
ブッキングカーブ形式に整形する。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

import pandas as pd

from booking_curve.daily_snapshots import read_daily_snapshots_for_month

EXCEL_BASE_DATE = datetime(1899, 12, 30)


def _excel_serial_to_datetime(serial: float) -> datetime:
    """Excelシリアル値をdatetimeに変換する。"""

    return EXCEL_BASE_DATE + timedelta(days=float(serial))


def extract_asof_dates_from_timeseries(df: pd.DataFrame) -> List[datetime]:
    """
    PMSの「宿泊日×取得日」時系列データから、実際に使われている取得日(ASOF)一覧を抽出する。

    - df.iloc[0, 1:] に Excel シリアル形式の取得日が格納されている前提。
    - 2行目以降で、完全に NaN の列は「未使用の取得日」とみなして除外する。

    Returns
    -------
    List[datetime]
        正規化(00:00)された datetime オブジェクトのリスト（重複なし、昇順）。
    """

    if df is None or df.empty:
        return []

    booking_date_serials = df.iloc[0, 1:]
    used_dates: List[datetime] = []

    for idx, serial in enumerate(booking_date_serials):
        # Excelシリアルが欠損ならスキップ
        if pd.isna(serial):
            continue

        col_idx = idx + 1
        # 2行目以降で1つも値が入っていない列は「未使用」とみなして除外
        col_values = df.iloc[1:, col_idx]
        if col_values.isna().all():
            continue

        dt = _excel_serial_to_datetime(serial)
        normalized = pd.to_datetime(dt).normalize().to_pydatetime()
        used_dates.append(normalized)

    if not used_dates:
        return []

    # 重複を除き、昇順にソートして返す
    unique_sorted = sorted(set(used_dates))
    return unique_sorted


def build_lt_data(df: pd.DataFrame, max_lt: int = 120) -> pd.DataFrame:
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
        records_df.pivot_table(index="stay_date", columns="lt", values="rooms", aggfunc="last")
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


def build_lt_data_from_daily_snapshots_for_month(
    hotel_id: str,
    target_month: str,
    max_lt: int = 120,
) -> pd.DataFrame:
    """日別スナップショットCSVから、指定月の宿泊日×LTのテーブルを構築する。"""

    lt_desc_columns = list(range(max_lt, -2, -1))

    df = read_daily_snapshots_for_month(
        hotel_id=hotel_id, target_month=target_month, output_dir=None
    )

    if df is None or df.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    df = df.copy()
    df["stay_date"] = pd.to_datetime(df.get("stay_date"), errors="coerce").dt.normalize()
    df["as_of_date"] = pd.to_datetime(df.get("as_of_date"), errors="coerce").dt.normalize()

    df = df.dropna(subset=["stay_date", "as_of_date"])
    if df.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    df["lt"] = (df["stay_date"] - df["as_of_date"]).dt.days
    df = df[df["lt"] <= max_lt]
    df.loc[df["lt"] < 0, "lt"] = -1

    grouped = df.groupby(["stay_date", "lt"], as_index=False)["rooms_oh"].sum()
    if grouped.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="Int64")

    pivot_df = grouped.pivot(index="stay_date", columns="lt", values="rooms_oh")
    pivot_df = pivot_df.sort_index().sort_index(axis=1)

    expected_lts = list(range(-1, max_lt + 1))
    pivot_df = pivot_df.reindex(columns=expected_lts, fill_value=0.0)

    pivot_df.index = pd.to_datetime(pivot_df.index).normalize()
    pivot_df.index.name = "stay_date"
    pivot_df.columns = pivot_df.columns.astype(int)
    pivot_df.columns.name = "lt"

    return pivot_df.astype(float)


def build_monthly_curve_from_timeseries(
    df: pd.DataFrame,
    max_lt: int = 120,
) -> pd.DataFrame:
    """
    PMSの時系列データ（宿泊日×取得日）から、月次ブッキングカーブ用の
    「LT別・月次累計Rooms」を集計する。

    パラメータ
    ----------
    df : pd.DataFrame
        load_time_series_excel() で読み込んだ1シート分の時系列データ。
        先頭行に取得日のExcelシリアル、先頭列に宿泊日のExcelシリアル or 日付が入っている前提。
    max_lt : int
        集計対象とする最大LT（日数）。例: 120。

    戻り値
    ------
    pd.DataFrame
        index: int 型の LT（例: max_lt, ..., 0, -1）
        columns: 1列 "rooms_total"
        各 LT 位置で、「そのLTに属する全セルのRooms合計」を表す。
        補間は行わず、生データのセルだけを合計する。
    """

    if df is None or df.empty:
        return pd.DataFrame(columns=["rooms_total"], dtype="float")

    booking_date_serials = df.iloc[0, 1:]
    booking_dates: List[datetime] = []
    for serial in booking_date_serials:
        if pd.isna(serial):
            booking_dates.append(pd.NaT)
        elif isinstance(serial, (int, float)):
            booking_dates.append(_excel_serial_to_datetime(serial))
        else:
            booking_dates.append(pd.to_datetime(serial))

    stay_date_serials = df.iloc[1:, 0]
    stay_dates: List[datetime] = []
    for serial in stay_date_serials:
        if pd.isna(serial):
            stay_dates.append(pd.NaT)
        elif isinstance(serial, (int, float)):
            stay_dates.append(_excel_serial_to_datetime(serial))
        else:
            stay_dates.append(pd.to_datetime(serial))

    value_block = df.iloc[1:, 1:]
    value_block = value_block.apply(pd.to_numeric, errors="coerce")
    value_block.index = pd.to_datetime(stay_dates)

    monthly_totals: dict[int, float] = {}

    for row_idx, stay_dt in enumerate(value_block.index):
        if pd.isna(stay_dt):
            continue
        row = value_block.iloc[row_idx, :]
        for col_idx, val in enumerate(row):
            if pd.isna(val):
                continue
            booking_dt = booking_dates[col_idx]
            if pd.isna(booking_dt):
                continue
            lt = (stay_dt.date() - booking_dt.date()).days

            if lt > max_lt:
                continue
            if lt < 0:
                lt = -1

            monthly_totals[lt] = monthly_totals.get(lt, 0.0) + float(val)

    if not monthly_totals:
        return pd.DataFrame(columns=["rooms_total"], dtype="float")

    lts = sorted(monthly_totals.keys(), reverse=True)
    result = pd.DataFrame(
        {"rooms_total": [monthly_totals[lt] for lt in lts]},
        index=pd.Index(lts, name="lt"),
    )
    return result


__all__ = [
    "extract_asof_dates_from_timeseries",
    "build_lt_data",
    "build_lt_data_from_daily_snapshots_for_month",
    "build_monthly_curve_from_timeseries",
]
