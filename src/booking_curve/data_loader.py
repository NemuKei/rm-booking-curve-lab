from pathlib import Path

import pandas as pd

from .config import DATA_DIR


def load_time_series_excel(
    filename: str,
    sheet_name: str,
) -> pd.DataFrame:
    """
    時系列データ（宿泊日 × 取得日）を読み込む。

    想定フォーマット：
      - 行0: 取得日（Excelシリアル）
      - 行1以降:
          col0: 宿泊日
          col1以降: 各取得日時点のオンハンド室数
    """
    file_path = Path(filename)
    if not file_path.is_absolute():
        file_path = DATA_DIR / file_path

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    return df
