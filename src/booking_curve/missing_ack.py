from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from booking_curve.config import ACK_DIR

logger = logging.getLogger(__name__)

ACK_COLUMNS = ["kind", "target_month", "asof_date", "path", "acked_at", "severity"]


def get_missing_ack_path(hotel_id: str, output_dir: Path | str = ACK_DIR) -> Path:
    output_dir = Path(output_dir)
    return output_dir / f"missing_ack_{hotel_id}_ops.csv"


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value)


def build_ack_key(kind: object, target_month: object, asof_date: object, path: object) -> str:
    return "|".join(
        [
            _stringify(kind).strip(),
            _stringify(target_month).strip(),
            _stringify(asof_date).strip(),
            _stringify(path).strip(),
        ]
    )


def build_ack_key_from_row(row: pd.Series) -> str:
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


def load_missing_ack_df(hotel_id: str, output_dir: Path | str = ACK_DIR) -> pd.DataFrame:
    path = get_missing_ack_path(hotel_id, output_dir=output_dir)
    if not path.exists():
        return _normalize_ack_df(pd.DataFrame(columns=ACK_COLUMNS))
    try:
        df = pd.read_csv(path, dtype=str)
        return _normalize_ack_df(df)
    except Exception:
        logger.exception("Failed to read missing ack file: %s", path)
        return _normalize_ack_df(pd.DataFrame(columns=ACK_COLUMNS))


def load_missing_ack_set(hotel_id: str, output_dir: Path | str = ACK_DIR) -> set[str]:
    df = load_missing_ack_df(hotel_id, output_dir=output_dir)
    if df.empty:
        return set()
    keys = df.apply(build_ack_key_from_row, axis=1).tolist()
    return {k for k in keys if k}


def filter_missing_report_with_ack(
    report_df: pd.DataFrame,
    acked_keys: set[str],
    *,
    severities: tuple[str, ...] = ("ERROR", "WARN"),
) -> pd.DataFrame:
    if report_df.empty or not acked_keys:
        return report_df

    df = report_df.copy()
    if "severity" not in df.columns:
        return report_df

    target_mask = df["severity"].isin(severities)
    if not target_mask.any():
        return report_df

    subset = df.loc[target_mask].copy()
    for col in ["kind", "target_month", "asof_date", "path"]:
        if col not in subset.columns:
            subset[col] = ""
    subset["_ack_key"] = subset.apply(build_ack_key_from_row, axis=1)

    keep_mask = ~subset["_ack_key"].isin(acked_keys)
    kept_subset = subset.loc[keep_mask].drop(columns=["_ack_key"])
    non_target = df.loc[~target_mask]

    return pd.concat([non_target, kept_subset], ignore_index=True)


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

    report_keys = set(report_subset["_ack_key"].tolist())

    preserved_rows = base_df[~base_df.apply(build_ack_key_from_row, axis=1).isin(report_keys)]

    acked_rows = report_subset[report_subset["_ack_key"].isin(acked_keys)].copy()
    if acked_rows.empty:
        updated = preserved_rows.copy()
        return _normalize_ack_df(updated)

    existing_map = {build_ack_key(row["kind"], row["target_month"], row["asof_date"], row["path"]): row["acked_at"] for _, row in base_df.iterrows()}
    acked_rows["acked_at"] = [existing_map.get(key, acked_at_value) for key in acked_rows["_ack_key"].tolist()]

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


def _write_missing_ack_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df_out = _normalize_ack_df(df)
    df_out.to_csv(path, index=False, encoding="utf-8-sig")


def write_missing_ack_df(
    hotel_id: str,
    df: pd.DataFrame,
    output_dir: Path | str = ACK_DIR,
) -> Path:
    path = get_missing_ack_path(hotel_id, output_dir)
    _write_missing_ack_df(df, path)
    return path


def _coerce_iterable(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()
    return {str(v) for v in values if str(v).strip()}


def write_missing_ack_df_from_keys(
    hotel_id: str,
    acked_keys: Iterable[str],
    *,
    output_dir: Path | str = ACK_DIR,
    acked_at: str | None = None,
    severities: Iterable[str] | None = None,
) -> None:
    acked_keys_set = _coerce_iterable(acked_keys)
    if not acked_keys_set:
        write_missing_ack_df(hotel_id, pd.DataFrame(columns=ACK_COLUMNS), output_dir)
        return

    severity_set = _coerce_iterable(severities) or {"ERROR", "WARN"}
    acked_at_value = acked_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    for key in acked_keys_set:
        parts = key.split("|")
        if len(parts) != 4:
            continue
        kind, target_month, asof_date, path = parts
        rows.append(
            {
                "kind": kind,
                "target_month": target_month,
                "asof_date": asof_date,
                "path": path,
                "acked_at": acked_at_value,
                "severity": next(iter(severity_set)),
            }
        )
    df = pd.DataFrame(rows, columns=ACK_COLUMNS)
    write_missing_ack_df(hotel_id, df, output_dir)
