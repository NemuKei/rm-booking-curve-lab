from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = PROJECT_ROOT / "config"
HOTEL_CONFIG_PATH = CONFIG_DIR / "hotels.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_default_hotel_config() -> Dict[str, Dict[str, Any]]:
    """hotels.json が無い場合や読み込みエラー時に使うデフォルト設定。

    現状は大国町のみを最低限の情報で定義しておく。
    ユーザー環境では基本的に hotels.json が存在するため、
    ここはフォールバック用途と考えてよい。
    """
    return {
        "daikokucho": {
            "display_name": "ソビアルなんば大国町",
            "capacity": 171,
            "data_subdir": "namba_daikokucho",
            "timeseries_file": "ソビアルなんば大国町_時系列データ.xlsx",
        }
    }


def load_hotel_config() -> Dict[str, Dict[str, Any]]:
    """config/hotels.json からホテル設定を読み込む。

    - ファイルが存在しない場合やパースエラー時は _load_default_hotel_config() を返す。
    - hotels.json が dict でない場合や空 dict の場合もフォールバックする。
    - それ以外の場合は JSON の内容をそのまま返す。
    """
    try:
        if HOTEL_CONFIG_PATH.exists():
            with HOTEL_CONFIG_PATH.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and raw:
                return raw
    except Exception:
        pass
    return _load_default_hotel_config()


HOTEL_CONFIG: Dict[str, Dict[str, Any]] = load_hotel_config()
