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
BASE_DIR = PROJECT_ROOT
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = PROJECT_ROOT / "config"
HOTEL_CONFIG_PATH = CONFIG_DIR / "hotels.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


REQUIRED_HOTEL_KEYS = (
    "hotel_id",
    "display_name",
    "capacity",
    "forecast_cap",
    "adapter_type",
    "raw_root_dir",
    "include_subfolders",
)


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


def _resolve_raw_root_dir(hotel_id: str, raw_root_dir: str | Path) -> Path:
    """Resolve raw_root_dir to an absolute Path using BASE_DIR as the base.

    raw_root_dir resolution is centralized here to keep HOTEL_CONFIG normalized.
    """
    try:
        raw_root_path = Path(raw_root_dir)
    except TypeError as exc:
        raise TypeError(
            f"{hotel_id}: raw_root_dir must be a string or Path (got {raw_root_dir!r})"
        ) from exc

    if not raw_root_path.is_absolute():
        raw_root_path = BASE_DIR / raw_root_path

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


def load_hotel_config() -> Dict[str, Dict[str, Any]]:
    """config/hotels.json からホテル設定を読み込み、必須項目を検証する。

    - hotels.json の欠落やパースエラーは RuntimeError として停止する。
    - 必須キーが不足している場合や不明な adapter_type が指定された場合は ValueError を送出する。
    - raw_root_dir はこのモジュールで絶対 Path に正規化し、input_dir にも反映する。
    """
    raw = _load_hotels_json()

    validated: Dict[str, Dict[str, Any]] = {}
    for hotel_id, hotel_cfg in raw.items():
        validated[hotel_id] = _validate_hotel_config(hotel_id, hotel_cfg)

    return validated


HOTEL_CONFIG: Dict[str, Dict[str, Any]] = load_hotel_config()
