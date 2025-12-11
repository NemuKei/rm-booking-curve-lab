"""LT（Lead Time）データ生成モジュール.

PMSから取得した宿泊日×取得日の時系列データを、宿泊日×LTの
ブッキングカーブ形式に整形する。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
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


def build_lt_table_from_daily_snapshots(df: pd.DataFrame, max_lt: int = 120) -> pd.DataFrame:
    """日別スナップショットから LT テーブルを構築する。

    この関数では観測値のみを利用し、補完は行わない。
    """

    if df is None or df.empty:
        return pd.DataFrame(columns=list(range(0, max_lt + 1)) + [-1], dtype="float")

    lt_df = df.copy()
    lt_df["stay_date"] = pd.to_datetime(lt_df.get("stay_date"), errors="coerce").dt.normalize()
    lt_df["as_of_date"] = pd.to_datetime(lt_df.get("as_of_date"), errors="coerce").dt.normalize()

    lt_df = lt_df.dropna(subset=["stay_date", "as_of_date", "rooms_oh"])
    if lt_df.empty:
        return pd.DataFrame(columns=list(range(0, max_lt + 1)) + [-1], dtype="float")

    lt_df["lt"] = (lt_df["stay_date"] - lt_df["as_of_date"]).dt.days
    lt_df_valid = lt_df[(lt_df["lt"] >= 0) & (lt_df["lt"] <= max_lt)]
    if lt_df_valid.empty:
        lt_table = pd.DataFrame(index=pd.Index([], name="stay_date"), columns=range(0, max_lt + 1))
    else:
        lt_df_valid = lt_df_valid.sort_values(["stay_date", "lt", "as_of_date"])
        latest_lt = lt_df_valid.groupby(["stay_date", "lt"], as_index=False).tail(1)
        lt_table = latest_lt.pivot(index="stay_date", columns="lt", values="rooms_oh")
        lt_table = lt_table.reindex(columns=range(0, max_lt + 1))

    lt_table.index = pd.to_datetime(lt_table.index)
    lt_table.index.name = "stay_date"

    df_act = lt_df[lt_df["as_of_date"] > lt_df["stay_date"]]
    if not df_act.empty:
        df_act = df_act.sort_values(["stay_date", "as_of_date"])
        s_act = df_act.groupby("stay_date")["rooms_oh"].tail(1)
        lt_table[-1] = s_act
    else:
        lt_table[-1] = float("nan")

    lt_table = lt_table.sort_index()
    lt_table.index.name = "stay_date"

    cols = list(range(0, max_lt + 1)) + [-1]
    lt_table = lt_table.reindex(columns=cols)

    return lt_table.astype(float)


def build_lt_data_from_daily_snapshots_for_month(
    hotel_id: str,
    target_month: str,
    max_lt: int = 120,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    """日別スナップショットCSVから、指定月の宿泊日×LTのテーブルを構築する。"""

    lt_desc_columns = list(range(0, max_lt + 1)) + [-1]

    df = read_daily_snapshots_for_month(
        hotel_id=hotel_id, target_month=target_month, output_dir=output_dir
    )

    if df is None or df.empty:
        return pd.DataFrame(columns=lt_desc_columns, dtype="float")

    if "hotel_id" in df.columns:
        df = df[df["hotel_id"] == hotel_id]

    lt_table = build_lt_table_from_daily_snapshots(df, max_lt=max_lt)

    if lt_table.empty:
        return lt_table

    if output_dir is None:
        from booking_curve.config import OUTPUT_DIR

        output_path = Path(OUTPUT_DIR)
    else:
        output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / f"lt_data_{target_month}_{hotel_id}.csv"
    lt_table.to_csv(csv_path, index_label="stay_date")

    print(f"[lt_builder] LT table saved to {csv_path}")

    return lt_table


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
    "build_lt_table_from_daily_snapshots",
    "build_lt_data_from_daily_snapshots_for_month",
    "build_monthly_curve_from_timeseries",
]
