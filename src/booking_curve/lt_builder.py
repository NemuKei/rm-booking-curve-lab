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


def build_monthly_curve_from_lt(lt_df: pd.DataFrame, target_month: str) -> pd.DataFrame:
    """
    LT形式の DataFrame から「月次ブッキングカーブ」用の集計を行うヘルパー。

    パラメータ
    ----------
    lt_df : pd.DataFrame
        build_lt_data() で生成された LT_DATA 相当の DataFrame
        index: DatetimeIndex(stay_date), columns: int or str の LT 列（-1, 0, 1, ..., maxLT）
    target_month : str
        対象となる宿泊月 (YYYYMM)。主にログメッセージ用で、集計ロジック自体には必須ではない。

    戻り値
    ------
    pd.DataFrame
        index: int 型の LT（昇順ソート、例: 0, 1, ..., maxLT, -1）
        columns: 1列のみ "rooms_total"
        各 LT 位置で、その月内の全宿泊日の Rooms 合計値を表す。
    """

    if lt_df is None or lt_df.empty:
        raise ValueError(f"LT_DATA is empty for target_month={target_month}")

    lt_columns = []
    for col in lt_df.columns:
        try:
            lt_columns.append(int(col))
        except Exception:
            continue

    if not lt_columns:
        raise ValueError("No valid LT columns in LT_DATA")

    lt_df = lt_df[sorted(lt_columns)]

    ym = int(target_month)
    year = ym // 100
    month = ym % 100
    mask = (lt_df.index.year == year) & (lt_df.index.month == month)
    lt_month = lt_df.loc[mask]

    if lt_month.empty:
        raise ValueError(f"No stay dates for target_month={target_month}")

    agg = lt_month.sum(axis=0, skipna=True)

    result = pd.DataFrame({"rooms_total": agg})
    result.index = result.index.astype(int)
    result = result.sort_index()

    return result
