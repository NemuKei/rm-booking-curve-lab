from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from booking_curve.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

ACK_COLUMNS = ["kind", "target_month", "asof_date", "path", "acked_at", "severity"]


def get_missing_ack_path(hotel_id: str, output_dir: Path | str = OUTPUT_DIR) -> Path:
    return Path(output_dir) / f"missing_ack_{hotel_id}_ops.csv"


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp) and pd.isna(value):
        return ""
    return str(value)


def build_ack_key(kind: object, target_month: object, asof_date: object, path: object) -> str:
    return "||".join(
        [
            _stringify(kind).strip(),
            _stringify(target_month).strip(),
            _stringify(asof_date).strip(),
            _stringify(path).strip(),
        ],
    )


def build_ack_key_from_row(row: dict[str, object] | pd.Series) -> str:
    return build_ack_key(
        row.get("kind"),
        row.get("target_month"),
        row.get("asof_date"),
        row.get("path"),
    )


def _normalize_ack_df(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    for col in ACK_COLUMNS:
        if col not in df_out.columns:
            df_out[col] = ""
    return df_out[ACK_COLUMNS].fillna("")


def load_missing_ack_df(hotel_id: str, output_dir: Path | str = OUTPUT_DIR) -> pd.DataFrame:
    path = get_missing_ack_path(hotel_id, output_dir=output_dir)
    if not path.exists():
        return pd.DataFrame(columns=ACK_COLUMNS)
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as exc:
        logger.warning("missing_ack: failed to read %s: %s", path, exc)
        return pd.DataFrame(columns=ACK_COLUMNS)
    return _normalize_ack_df(df)


def load_missing_ack_set(hotel_id: str, output_dir: Path | str = OUTPUT_DIR) -> set[str]:
    df = load_missing_ack_df(hotel_id, output_dir=output_dir)
    if df.empty:
        return set()
    return {
        build_ack_key(row["kind"], row["target_month"], row["asof_date"], row["path"])
        for _, row in df.iterrows()
    }


def filter_missing_report_with_ack(
    report_df: pd.DataFrame,
    ack_set: Iterable[str],
    *,
    severities: tuple[str, ...] = ("ERROR", "WARN"),
) -> pd.DataFrame:
    if report_df.empty:
        return report_df

    ack_keys = set(ack_set)
    df = report_df.copy()
    df["severity"] = df.get("severity", "").fillna("")
    df["_ack_key"] = df.apply(build_ack_key_from_row, axis=1)
    severity_mask = df["severity"].isin(severities)
    acked_mask = df["_ack_key"].isin(ack_keys)
    filtered = df[~(severity_mask & acked_mask)].copy()
    return filtered.drop(columns=["_ack_key"])


def update_missing_ack_df(
    existing_df: pd.DataFrame,
    report_df: pd.DataFrame,
    acked_keys: set[str],
    *,
    acked_at: str | None = None,
) -> pd.DataFrame:
    base_df = _normalize_ack_df(existing_df)
    if report_df.empty:
        return base_df

    acked_at_value = acked_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    report_subset = report_df.copy()
    for col in ["kind", "target_month", "asof_date", "path", "severity"]:
        if col not in report_subset.columns:
            report_subset[col] = ""
    report_subset["_ack_key"] = report_subset.apply(build_ack_key_from_row, axis=1)

    existing_keys = {
        build_ack_key(row["kind"], row["target_month"], row["asof_date"], row["path"])
        for _, row in base_df.iterrows()
    }
    report_keys = set(report_subset["_ack_key"].tolist())

    preserved_rows = base_df[~base_df.apply(build_ack_key_from_row, axis=1).isin(report_keys)]

    acked_rows = report_subset[report_subset["_ack_key"].isin(acked_keys)].copy()
    if acked_rows.empty:
        updated = preserved_rows.copy()
        return _normalize_ack_df(updated)

    existing_map = {
        build_ack_key(row["kind"], row["target_month"], row["asof_date"], row["path"]): row["acked_at"]
        for _, row in base_df.iterrows()
    }
    acked_rows["acked_at"] = [
        existing_map.get(key, acked_at_value) for key in acked_rows["_ack_key"].tolist()
    ]

    updated = pd.concat(
        [
            preserved_rows[ACK_COLUMNS],
            acked_rows[ACK_COLUMNS],
        ],
        ignore_index=True,
    )
    updated["_ack_key"] = updated.apply(build_ack_key_from_row, axis=1)
    updated = updated.drop_duplicates(subset=["_ack_key"], keep="last").drop(columns=["_ack_key"])
    return _normalize_ack_df(updated)


def write_missing_ack_df(
    hotel_id: str,
    df: pd.DataFrame,
    output_dir: Path | str = OUTPUT_DIR,
) -> Path:
    path = get_missing_ack_path(hotel_id, output_dir=output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_to_save = _normalize_ack_df(df)
    df_to_save.to_csv(path, index=False, encoding="utf-8-sig")
    return path
