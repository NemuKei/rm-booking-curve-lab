import numpy as np
import pandas as pd
from datetime import datetime, timedelta

EXCEL_BASE_DATE = datetime(1899, 12, 30)  # Excel シリアルの日付原点

def _excel_serial_to_datetime(serial: float) -> datetime:
    return EXCEL_BASE_DATE + timedelta(days=float(serial))

def build_lt_data(df: pd.DataFrame, max_lt: int = 90) -> pd.DataFrame:
    """
    時系列データ（宿泊日 × 取得日）から LT_DATA を構築する。

    - df: data_loader.load_time_series_excel() で読み込んだ DataFrame
    - max_lt: 最大リードタイム（日）

    戻り値:
      index: 宿泊日（datetime）
      columns: LT（0〜max_ltの整数）
      values: 室数（整数／欠損はNaN）
    """

    # TODO:
    # 1. 行0から「取得日シリアル」を取り出し、datetime に変換する
    # 2. 行1以降を宿泊日ごとにループし、
    #    各セルの (宿泊日, 取得日) から LT = (宿泊日 - 取得日).days を計算
    # 3. 0 <= LT <= max_lt の範囲だけ使って、(stay_date, LT) → 室数 を集計
    # 4. pivot して宿泊日 × LT の DataFrame に変換
    # 5. LT 軸方向に線形補完し、四捨五入して整数化する（ただし全NaN行はそのまま）

    raise NotImplementedError("build_lt_data の実装はこれから作成します。")
