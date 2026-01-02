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
    開発環境 (.py 実行) での「リポジトリルート」を返す。
    """
    return Path(__file__).resolve().parents[2]


def _get_resource_root() -> Path:
    """
    リソース参照用のルートを返す。

    - PyInstaller 実行時: sys._MEIPASS を優先
    - 通常実行時: リポジトリルート
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _get_project_root()


def _get_executable_root() -> Path:
    """
    実行ファイルの位置を基準としたルートを返す。

    - PyInstaller 実行時: sys.executable の親ディレクトリ
    - 通常実行時: リポジトリルート
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _get_project_root()


def get_app_base_dir() -> Path:
    """
    アプリが書き込むベースディレクトリを返す。

    - Windows: %LOCALAPPDATA%/BookingCurveLab
    - macOS: ~/Library/Application Support/BookingCurveLab
    - Linux: $XDG_DATA_HOME/BookingCurveLab or ~/.local/share/BookingCurveLab
    """
    if sys.platform.startswith("win"):
        local_app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if local_app_data:
            return Path(local_app_data) / "BookingCurveLab"
        return Path.home() / "AppData" / "Local" / "BookingCurveLab"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BookingCurveLab"

    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "BookingCurveLab"

    return Path.home() / ".local" / "share" / "BookingCurveLab"


RESOURCE_ROOT = _get_resource_root()
BASE_DIR = _get_executable_root()
APP_BASE_DIR = get_app_base_dir()

DATA_DIR = RESOURCE_ROOT / "data"
OUTPUT_DIR = APP_BASE_DIR / "output"
LOGS_DIR = OUTPUT_DIR / "logs"
ACK_DIR = APP_BASE_DIR / "acks"
CONFIG_DIR = APP_BASE_DIR / "config"
LOCAL_OVERRIDES_DIR = APP_BASE_DIR / "local_overrides"

HOTEL_CONFIG_PATH = CONFIG_DIR / "hotels.json"

for directory in (APP_BASE_DIR, OUTPUT_DIR, LOGS_DIR, ACK_DIR, CONFIG_DIR, LOCAL_OVERRIDES_DIR):
    directory.mkdir(parents=True, exist_ok=True)


REQUIRED_HOTEL_KEYS = (
    "hotel_id",
    "display_name",
    "capacity",
    "forecast_cap",
    "adapter_type",
    "raw_root_dir",
    "include_subfolders",
)

LOCAL_OVERRIDES_VERSION = 1

LOGGER = logging.getLogger(__name__)
RUNTIME_INIT_ERRORS: list[str] = []
STARTUP_INIT_LOG_PATH = LOGS_DIR / "startup_init.log"


def _record_runtime_init_error(message: str) -> None:
    RUNTIME_INIT_ERRORS.append(message)
    LOGGER.warning(message)
    try:
        STARTUP_INIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with STARTUP_INIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        # 起動時の初期化ログが書けなくてもクラッシュはさせない
        return


def _copy_if_missing(src: Path, dst: Path) -> None:
    """
    dst が存在しない場合にのみ、src から dst へファイルをコピーする。
    - src が存在しない場合は何もしない。
    - dst がすでに存在する場合も何もしない（上書き禁止）。
    - エラーが発生してもツール全体を落とさないように、ログに残して終了する。
    """
    try:
        if not src.exists():
            return
        if dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except Exception as exc:
        _record_runtime_init_error(
            f"Failed to copy template file: src={src} dst={dst} error={exc}"
        )


def _initialize_runtime_files() -> None:
    """
    リソースに含まれるテンプレートを、端末ローカルへ初期展開する。

    - config/ 配下のファイルを app_base_dir/config にコピー（不足分のみ）
    - 既存ファイルがある場合は上書きしない
    """
    template_config_root = RESOURCE_ROOT / "config"
    if template_config_root.exists():
        for src_path in template_config_root.rglob("*"):
            if not src_path.is_file():
                continue
            rel = src_path.relative_to(template_config_root)
            dst_path = CONFIG_DIR / rel
            _copy_if_missing(src_path, dst_path)


_initialize_runtime_files()


def _get_local_overrides_dir() -> Path:
    """端末ローカルの上書き設定ディレクトリを返す。"""
    return LOCAL_OVERRIDES_DIR


def get_local_overrides_path() -> Path:
    """端末ローカルの上書き設定ファイルパスを返す。"""
    return _get_local_overrides_dir() / "local_overrides.json"


def _load_local_overrides() -> dict[str, dict[str, Any]]:
    overrides_path = get_local_overrides_path()
    if not overrides_path.exists():
        return {}

    try:
        with overrides_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Failed to parse local overrides JSON at %s: %s", overrides_path, exc)
        return {}
    except OSError as exc:  # pragma: no cover - I/O error boundary
        LOGGER.warning("Failed to read local overrides at %s: %s", overrides_path, exc)
        return {}

    if not isinstance(raw, dict):
        LOGGER.warning("Local overrides JSON must be an object: %s", overrides_path)
        return {}

    version = raw.get("version")
    if version not in (None, LOCAL_OVERRIDES_VERSION):
        LOGGER.warning(
            "Unsupported local overrides version at %s: %s", overrides_path, version
        )

    hotels = raw.get("hotels", {})
    if hotels is None:
        return {}
    if not isinstance(hotels, dict):
        LOGGER.warning("Local overrides 'hotels' must be an object: %s", overrides_path)
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for hotel_id, overrides in hotels.items():
        if not isinstance(overrides, dict):
            LOGGER.warning(
                "Local overrides for hotel_id=%s must be an object: %s", hotel_id, overrides_path
            )
            continue
        normalized[hotel_id] = dict(overrides)
    return normalized


def _write_local_overrides(hotels: dict[str, dict[str, Any]]) -> None:
    overrides_path = get_local_overrides_path()
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": LOCAL_OVERRIDES_VERSION, "hotels": hotels}
    with overrides_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _resolve_raw_root_dir(hotel_id: str, raw_root_dir: str | Path) -> Path:
    """Resolve raw_root_dir to an absolute Path using APP_BASE_DIR as the base.

    raw_root_dir resolution is centralized here to keep HOTEL_CONFIG normalized.
    Relative paths are anchored to APP_BASE_DIR to keep per-device independence
    even when the executable directory moves.
    """
    try:
        raw_root_path = Path(raw_root_dir)
    except TypeError as exc:
        raise TypeError(
            f"{hotel_id}: raw_root_dir must be a string or Path (got {raw_root_dir!r})"
        ) from exc

    if not raw_root_path.is_absolute():
        raw_root_path = APP_BASE_DIR / raw_root_path

    try:
        return raw_root_path.resolve(strict=False)
    except OSError as exc:
        raise ValueError(
            f"{hotel_id}: failed to resolve raw_root_dir={raw_root_dir!r} (key=raw_root_dir)"
        ) from exc


def _normalize_display_name(hotel_id: str, display_name: Any) -> str:
    if display_name is None:
        return ""
    if not isinstance(display_name, str):
        raise TypeError(f"{hotel_id}: display_name must be a string (got {display_name!r})")
    return display_name


def _normalize_optional_number(hotel_id: str, key_name: str, value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{hotel_id}: {key_name} must be numeric or null (got {value!r})")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{hotel_id}: {key_name} must be numeric or null (got blank string)")
        try:
            return float(stripped)
        except ValueError as exc:
            raise ValueError(f"{hotel_id}: {key_name} must be numeric or null (got {value!r})") from exc
    raise TypeError(f"{hotel_id}: {key_name} must be numeric or null (got {value!r})")


def _validate_hotel_config(hotel_id: str, hotel_cfg: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(hotel_cfg, dict):
        raise TypeError(f"{hotel_id}: hotel config must be a JSON object")

    missing_keys = [key for key in REQUIRED_HOTEL_KEYS if key not in hotel_cfg]
    if missing_keys:
        raise ValueError(f"{hotel_id}: missing required key(s) in hotels.json: {', '.join(missing_keys)}")

    hotel_id_in_cfg = str(hotel_cfg["hotel_id"])
    if not hotel_id_in_cfg:
        raise ValueError(f"{hotel_id}: hotel_id cannot be blank")
    if hotel_id_in_cfg != hotel_id:
        raise ValueError(f"{hotel_id}: hotel_id must match the map key (got {hotel_id_in_cfg})")

    adapter_type_raw = hotel_cfg["adapter_type"]
    if adapter_type_raw is None:
        raise ValueError(f"{hotel_id}: adapter_type cannot be blank")
    adapter_type = str(adapter_type_raw).strip().lower()
    if not adapter_type:
        raise ValueError(f"{hotel_id}: adapter_type cannot be blank")
    if adapter_type != "nface":
        raise ValueError(f"{hotel_id}: unsupported adapter_type '{adapter_type_raw}' (nface only)")

    raw_root_dir_value = hotel_cfg["raw_root_dir"]
    raw_root_dir_str = str(raw_root_dir_value).strip() if raw_root_dir_value is not None else ""
    if not raw_root_dir_str:
        raise ValueError(f"{hotel_id}: raw_root_dir cannot be blank")
    raw_root_dir = _resolve_raw_root_dir(hotel_id, raw_root_dir_value)

    include_subfolders = hotel_cfg["include_subfolders"]
    if not isinstance(include_subfolders, bool):
        raise TypeError(f"{hotel_id}: include_subfolders must be a boolean")

    display_name = _normalize_display_name(hotel_id, hotel_cfg["display_name"])
    capacity = _normalize_optional_number(hotel_id, "capacity", hotel_cfg["capacity"])
    forecast_cap = _normalize_optional_number(hotel_id, "forecast_cap", hotel_cfg["forecast_cap"])

    normalized = dict(hotel_cfg)
    normalized["hotel_id"] = hotel_id_in_cfg
    normalized["display_name"] = display_name
    normalized["adapter_type"] = adapter_type
    normalized["raw_root_dir"] = raw_root_dir
    normalized["input_dir"] = raw_root_dir
    normalized["include_subfolders"] = include_subfolders
    normalized["capacity"] = capacity
    normalized["forecast_cap"] = forecast_cap

    return normalized


def _load_hotels_json() -> dict[str, Any]:
    if not HOTEL_CONFIG_PATH.exists():
        init_errors = pop_runtime_init_errors()
        if init_errors:
            details = "\n".join(init_errors)
            raise RuntimeError(
                f"Hotel config not found: {HOTEL_CONFIG_PATH}\n"
                f"Startup init errors:\n{details}"
            )
        raise RuntimeError(f"Hotel config not found: {HOTEL_CONFIG_PATH}")

    try:
        with HOTEL_CONFIG_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse hotel config JSON at {HOTEL_CONFIG_PATH}: {exc}") from exc
    except OSError as exc:  # pragma: no cover - I/O error boundary
        raise RuntimeError(f"Failed to read hotel config at {HOTEL_CONFIG_PATH}: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"hotels.json must contain a non-empty object: {HOTEL_CONFIG_PATH}")

    return raw


def _apply_local_raw_root_overrides(raw_hotels: dict[str, Any]) -> dict[str, Any]:
    overrides = _load_local_overrides()
    if not overrides:
        return raw_hotels

    merged: dict[str, Any] = {}
    for hotel_id, hotel_cfg in raw_hotels.items():
        merged_cfg = dict(hotel_cfg)
        override_cfg = overrides.get(hotel_id)
        if override_cfg:
            raw_override = override_cfg.get("raw_root_dir")
            if raw_override is not None:
                raw_override_str = str(raw_override).strip()
                if raw_override_str:
                    merged_cfg["raw_root_dir"] = raw_override
                else:
                    LOGGER.warning(
                        "Ignoring blank raw_root_dir override for hotel_id=%s", hotel_id
                    )
        merged[hotel_id] = merged_cfg

    for hotel_id in overrides:
        if hotel_id not in raw_hotels:
            LOGGER.warning(
                "Ignoring local override for unknown hotel_id=%s", hotel_id
            )

    return merged


def load_hotel_config() -> Dict[str, Dict[str, Any]]:
    """config/hotels.json からホテル設定を読み込み、必須項目を検証する。

    - hotels.json の欠落やパースエラーは RuntimeError として停止する。
    - 必須キーが不足している場合や不明な adapter_type が指定された場合は ValueError を送出する。
    - raw_root_dir はこのモジュールで絶対 Path に正規化し、input_dir にも反映する。
    """
    raw = _load_hotels_json()
    raw = _apply_local_raw_root_overrides(raw)

    validated: Dict[str, Dict[str, Any]] = {}
    for hotel_id, hotel_cfg in raw.items():
        validated[hotel_id] = _validate_hotel_config(hotel_id, hotel_cfg)

    return validated


def reload_hotel_config_inplace() -> Dict[str, Dict[str, Any]]:
    """Reload hotels.json and update HOTEL_CONFIG in place.

    This keeps existing imports intact by clearing and updating the shared dict
    instead of replacing it.
    """
    updated = load_hotel_config()
    HOTEL_CONFIG.clear()
    HOTEL_CONFIG.update(updated)
    return HOTEL_CONFIG


def pop_runtime_init_errors() -> list[str]:
    """初期展開エラーを取得し、内部のリストをクリアする。"""
    errors = list(RUNTIME_INIT_ERRORS)
    RUNTIME_INIT_ERRORS.clear()
    return errors


def set_local_override_raw_root_dir(hotel_id: str, raw_root_dir: str | Path) -> None:
    """端末ローカルの raw_root_dir 上書きを保存して、HOTEL_CONFIG に反映する。"""
    raw = _load_hotels_json()
    if hotel_id not in raw:
        raise ValueError(f"Unknown hotel_id: {hotel_id}")

    raw_root_dir_str = str(raw_root_dir).strip() if raw_root_dir is not None else ""
    if not raw_root_dir_str:
        raise ValueError("raw_root_dir cannot be blank")

    overrides = _load_local_overrides()
    overrides[hotel_id] = {"raw_root_dir": raw_root_dir_str}
    _write_local_overrides(overrides)

    raw_root_path = Path(raw_root_dir_str)
    if not raw_root_path.exists():
        LOGGER.warning("raw_root_dir does not exist: %s", raw_root_dir_str)

    updated_cfg = dict(raw[hotel_id])
    updated_cfg["raw_root_dir"] = raw_root_dir_str
    HOTEL_CONFIG[hotel_id] = _validate_hotel_config(hotel_id, updated_cfg)


def clear_local_override_raw_root_dir(hotel_id: str) -> None:
    """端末ローカルの raw_root_dir 上書きを削除して hotels.json の値に戻す。"""
    raw = _load_hotels_json()
    if hotel_id not in raw:
        raise ValueError(f"Unknown hotel_id: {hotel_id}")

    overrides = _load_local_overrides()
    overrides.pop(hotel_id, None)
    _write_local_overrides(overrides)

    HOTEL_CONFIG[hotel_id] = _validate_hotel_config(hotel_id, raw[hotel_id])


HOTEL_CONFIG: Dict[str, Dict[str, Any]] = load_hotel_config()
