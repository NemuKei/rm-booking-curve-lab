from __future__ import annotations

import json
import logging
import os
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


LOGGER = logging.getLogger(__name__)

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


def get_local_overrides_path() -> Path:
    """端末ローカルの上書き設定ファイルパスを返す。"""
    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "BookingCurveLab" / "local_overrides.json"

    config_dir = Path.home() / ".config" / "BookingCurveLab"
    if config_dir.parent.exists() or config_dir.exists():
        return config_dir / "local_overrides.json"

    return Path.home() / ".booking_curve_lab" / "local_overrides.json"


def _default_local_overrides_payload() -> Dict[str, Any]:
    return {"version": 1, "hotels": {}}


def _load_local_overrides_payload() -> Dict[str, Any]:
    path = get_local_overrides_path()
    if not path.exists():
        return _default_local_overrides_payload()

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        LOGGER.warning("Failed to read local overrides: %s", exc)
        return _default_local_overrides_payload()

    if not isinstance(raw, dict):
        LOGGER.warning("Local overrides is not a JSON object. Ignoring.")
        return _default_local_overrides_payload()

    hotels = raw.get("hotels")
    if hotels is not None and not isinstance(hotels, dict):
        LOGGER.warning("Local overrides hotels section is invalid. Ignoring.")
        return _default_local_overrides_payload()

    version = raw.get("version")
    if not isinstance(version, int):
        raw["version"] = 1

    if hotels is None:
        raw["hotels"] = {}

    return raw


def _save_local_overrides_payload(payload: Dict[str, Any]) -> None:
    path = get_local_overrides_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        LOGGER.warning("Failed to save local overrides: %s", exc)


def _load_local_overrides() -> Dict[str, Dict[str, Any]]:
    payload = _load_local_overrides_payload()
    hotels = payload.get("hotels", {})
    if isinstance(hotels, dict):
        return hotels
    return {}


def _validate_hotel_config(
    raw_config: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for hotel_id, config in raw_config.items():
        if not isinstance(config, dict):
            continue
        normalized_config = dict(config)
        raw_root_dir = normalized_config.get("raw_root_dir")
        if raw_root_dir:
            normalized_config["raw_root_dir"] = (
                raw_root_dir if isinstance(raw_root_dir, Path) else Path(raw_root_dir)
            )
        normalized[hotel_id] = normalized_config
    return normalized


def _apply_local_overrides(
    hotel_config: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    overrides = _load_local_overrides()
    if not overrides:
        return hotel_config

    updated: Dict[str, Dict[str, Any]] = {}
    for hotel_id, config in hotel_config.items():
        updated_config = dict(config)
        override = overrides.get(hotel_id)
        if isinstance(override, dict) and "raw_root_dir" in override:
            updated_config["raw_root_dir"] = override["raw_root_dir"]
        updated[hotel_id] = updated_config
    return updated


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
                merged = _apply_local_overrides(raw)
                return _validate_hotel_config(merged)
    except Exception:
        pass
    fallback = _load_default_hotel_config()
    merged_fallback = _apply_local_overrides(fallback)
    return _validate_hotel_config(merged_fallback)


def set_local_override_raw_root_dir(hotel_id: str, raw_root_dir: str | Path) -> None:
    """端末ローカルの raw_root_dir 上書きを設定する。"""
    if hotel_id not in HOTEL_CONFIG:
        raise ValueError(f"Unknown hotel_id: {hotel_id}")

    raw_root_value = str(raw_root_dir).strip()
    if not raw_root_value:
        raise ValueError("raw_root_dir must not be empty.")

    path_value = Path(raw_root_value).expanduser()
    if not path_value.exists():
        LOGGER.warning("raw_root_dir does not exist: %s", path_value)

    payload = _load_local_overrides_payload()
    hotels = payload.setdefault("hotels", {})
    if not isinstance(hotels, dict):
        hotels = {}
        payload["hotels"] = hotels

    hotel_overrides = hotels.get(hotel_id)
    if not isinstance(hotel_overrides, dict):
        hotel_overrides = {}
        hotels[hotel_id] = hotel_overrides

    hotel_overrides["raw_root_dir"] = str(path_value)
    _save_local_overrides_payload(payload)

    global HOTEL_CONFIG
    HOTEL_CONFIG = load_hotel_config()


def clear_local_override_raw_root_dir(hotel_id: str) -> None:
    """端末ローカルの raw_root_dir 上書きを削除する。"""
    if hotel_id not in HOTEL_CONFIG:
        raise ValueError(f"Unknown hotel_id: {hotel_id}")

    payload = _load_local_overrides_payload()
    hotels = payload.get("hotels", {})
    if isinstance(hotels, dict) and hotel_id in hotels:
        hotel_overrides = hotels.get(hotel_id, {})
        if isinstance(hotel_overrides, dict):
            hotel_overrides.pop("raw_root_dir", None)
            if not hotel_overrides:
                hotels.pop(hotel_id, None)
        _save_local_overrides_payload(payload)

    global HOTEL_CONFIG
    HOTEL_CONFIG = load_hotel_config()


HOTEL_CONFIG: Dict[str, Dict[str, Any]] = load_hotel_config()
