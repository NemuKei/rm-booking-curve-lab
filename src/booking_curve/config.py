from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


def _get_project_root() -> Path:
    """
    開発環境 (.py 実行) と PyInstaller EXE 実行時の両方で、
    実行時の「ルートディレクトリ」を返すヘルパー。

    - 開発環境: src/booking_curve/config.py から 2階層上 (= リポジトリルート)
    - EXE: dist/BookingCurveLab/_internal/.../config.py から 2階層上 (= dist/BookingCurveLab)
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _get_project_root()
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = PROJECT_ROOT / "config"
HOTEL_CONFIG_PATH = CONFIG_DIR / "hotels.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _get_template_root() -> Path | None:
    """
    PyInstaller 実行時に、バンドルされたテンプレート群が置かれている
    ルートディレクトリを返すヘルパー。

    - EXE版: sys._MEIPASS が存在し、そのパス配下に config/, data/ がある前提。
    - .py版: sys._MEIPASS は存在しないので None を返す。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return None


def _copy_if_missing(src: Path, dst: Path) -> None:
    """
    dst が存在しない場合にのみ、src から dst へファイルをコピーする。
    - src が存在しない場合は何もしない。
    - dst がすでに存在する場合も何もしない（上書き禁止）。
    - エラーが発生してもツール全体を落とさないように、例外は握りつぶす。
    """
    try:
        if not src.exists():
            return
        if dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except Exception:
        # ログには出さずに黙って失敗する（起動は続行させる）
        return


def _initialize_runtime_files() -> None:
    """
    EXE版実行時に、_internal 配下にバンドルされているテンプレートから
    config/ や data/ に最低限のファイルをコピーする初期化処理。

    - .py 実行時 (開発環境) では何もしない。
    - すでに config/ や data/ に同名ファイルが存在する場合は一切上書きしない。
    - 現時点では、以下を対象とする:
      - config/hotels.json
      - data/ 以下の全てのファイル
    """
    template_root = _get_template_root()
    if template_root is None:
        # PyInstaller で固めていない通常実行時はテンプレ展開不要
        return

    # hotels.json
    template_hotels = template_root / "config" / "hotels.json"
    _copy_if_missing(template_hotels, HOTEL_CONFIG_PATH)

    # data/ 以下のテンプレを data/ 以下にコピー（不足分のみ）
    template_data_root = template_root / "data"
    if template_data_root.exists():
        for src_path in template_data_root.rglob("*"):
            if not src_path.is_file():
                continue
            rel = src_path.relative_to(template_data_root)
            dst_path = DATA_DIR / rel
            _copy_if_missing(src_path, dst_path)


_initialize_runtime_files()


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
