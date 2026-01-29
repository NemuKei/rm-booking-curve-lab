"""
Diagnostic tool to inspect market pace impact on pace14_market forecasts.

Usage:
  python tools/diag_market_effect.py --hotel <hotel_tag> --asof <YYYY-MM-DD> --target <YYYYMM> --capacity <float>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "src"))

from booking_curve.forecast_simple import (  # noqa: E402
    MARKET_PACE_CLIP,
    MARKET_PACE_LT_MAX,
    MARKET_PACE_LT_MIN,
    compute_market_pace_7d,
    forecast_final_from_pace14_market,
    moving_average_recent_90days,
)
from run_forecast_batch import (  # noqa: E402
    LT_MAX,
    LT_MIN,
    filter_by_weekday,
    get_history_months_around_asof,
    load_lt_csv,
)


def _yyyymm(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y%m")


def _next_month_yyyymm(ts: pd.Timestamp) -> str:
    first = ts.replace(day=1)
    nextm = first + pd.offsets.MonthBegin(1)
    return nextm.strftime("%Y%m")


def _load_lt_df_for_market(hotel_tag: str, as_of_ts: pd.Timestamp) -> pd.DataFrame:
    """Load LT_DATA for as-of month + next month for market pace."""
    ym0 = _yyyymm(as_of_ts)
    ym1 = _next_month_yyyymm(as_of_ts)
    dfs = []
    for ym in (ym0, ym1):
        try:
            df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="rooms")
        except FileNotFoundError:
            continue
        if df is None or df.empty:
            continue
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    out = pd.concat(dfs, axis=0)
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")]
    return out


def _build_history_by_weekday(hotel_tag: str, as_of_ts: pd.Timestamp, months_back: int = 6) -> dict[int, pd.DataFrame]:
    months = get_history_months_around_asof(as_of_ts, months_back=months_back, months_forward=0)
    history_raw: dict[str, pd.DataFrame] = {}
    for ym in months:
        try:
            df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="rooms")
        except FileNotFoundError:
            continue
        if df is None or df.empty:
            continue
        df.index = pd.to_datetime(df.index)
        history_raw[ym] = df

    history_by_weekday: dict[int, pd.DataFrame] = {}
    for weekday in range(7):
        dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                dfs.append(df_m_wd)
        if dfs:
            history_all = pd.concat(dfs, axis=0)
            history_all.index = pd.to_datetime(history_all.index)
            history_by_weekday[weekday] = history_all
    return history_by_weekday


def _build_baseline_curves(
    history_by_weekday: dict[int, pd.DataFrame],
    as_of_ts: pd.Timestamp,
) -> dict[int, pd.Series]:
    baseline_curves: dict[int, pd.Series] = {}
    for weekday, history_df in history_by_weekday.items():
        baseline_curves[weekday] = moving_average_recent_90days(
            lt_df=history_df,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )
    return baseline_curves


def _safe_describe(series: pd.Series, label: str) -> None:
    if series is None or series.empty:
        print(f"{label}: no data")
        return
    desc = series.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print(desc.to_string())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose market pace impact on pace14_market forecasts.")
    parser.add_argument("--hotel", required=True, help="Hotel tag (e.g., hotel_001)")
    parser.add_argument("--asof", required=True, help="As-of date (YYYY-MM-DD)")
    parser.add_argument("--target", required=True, help="Target month (YYYYMM)")
    parser.add_argument("--capacity", required=True, type=float, help="Capacity for forecast (float)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    as_of_ts = pd.to_datetime(args.asof, errors="coerce")
    if pd.isna(as_of_ts):
        print("Invalid --asof date. Use YYYY-MM-DD.")
        raise SystemExit(1)
    as_of_ts = as_of_ts.normalize()

    try:
        df_target = load_lt_csv(args.target, hotel_tag=args.hotel, value_type="rooms")
    except FileNotFoundError as exc:
        print(f"Target LT_DATA not found: {exc}")
        raise SystemExit(1)
    if df_target is None or df_target.empty:
        print("Target LT_DATA is empty.")
        raise SystemExit(1)
    df_target.index = pd.to_datetime(df_target.index)

    history_by_weekday = _build_history_by_weekday(args.hotel, as_of_ts, months_back=6)
    if not history_by_weekday:
        print("No history LT_DATA found for baseline.")
        raise SystemExit(1)

    baseline_curves = _build_baseline_curves(history_by_weekday, as_of_ts)

    df_market = _load_lt_df_for_market(args.hotel, as_of_ts)
    if df_market.empty:
        print("Market LT_DATA is empty for as-of month + next month.")
        raise SystemExit(1)

    market_pace_7d, _ = compute_market_pace_7d(
        lt_df=df_market,
        as_of_ts=as_of_ts,
        history_by_weekday=history_by_weekday,
        lt_min=LT_MIN,
        lt_max=LT_MAX,
    )
    print(f"market_pace_7d = {market_pace_7d}")

    detail_frames: list[pd.DataFrame] = []
    for weekday in range(7):
        history_df = history_by_weekday.get(weekday)
        baseline_curve = baseline_curves.get(weekday)
        if history_df is None or baseline_curve is None:
            continue

        df_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_wd.empty:
            continue

        fc_mkt, det_mkt = forecast_final_from_pace14_market(
            lt_df=df_wd,
            baseline_curve=baseline_curve,
            history_df=history_df,
            as_of_date=as_of_ts,
            capacity=float(args.capacity),
            market_pace_7d=market_pace_7d,
            lt_min=0,
            lt_max=LT_MAX,
        )
        fc_nomkt, _ = forecast_final_from_pace14_market(
            lt_df=df_wd,
            baseline_curve=baseline_curve,
            history_df=history_df,
            as_of_date=as_of_ts,
            capacity=float(args.capacity),
            market_pace_7d=np.nan,
            lt_min=0,
            lt_max=LT_MAX,
        )

        if det_mkt is None or det_mkt.empty:
            continue
        det = det_mkt.copy()
        det["fc_market"] = fc_mkt
        det["fc_no_market"] = fc_nomkt
        det["delta_market"] = det["fc_market"] - det["fc_no_market"]
        detail_frames.append(det)

    if not detail_frames:
        print("No detail rows.")
        return

    detail_all = pd.concat(detail_frames, axis=0).sort_index()
    if "lt_now" not in detail_all.columns:
        print("Detail rows missing lt_now; cannot filter market band.")
        return

    band = detail_all[
        (detail_all["lt_now"] >= MARKET_PACE_LT_MIN) & (detail_all["lt_now"] <= MARKET_PACE_LT_MAX)
    ].copy()
    print(f"\n=== MARKET BAND rows === {len(band)}")

    if "delta_market" in band.columns:
        print("\ndelta_market.describe()")
        _safe_describe(band["delta_market"].dropna(), "delta_market")
    else:
        print("\ndelta_market column missing.")

    upper_cap = float(MARKET_PACE_CLIP[1])
    lower_cap = float(MARKET_PACE_CLIP[0])
    if "market_factor" in band.columns:
        upper = (band["market_factor"] >= upper_cap - 1e-9).mean()
        lower = (band["market_factor"] <= lower_cap + 1e-9).mean()
        print(f"\nclip_rate upper(={upper_cap}): {round(float(upper), 4)}")
        print(f"clip_rate lower(={lower_cap}): {round(float(lower), 4)}")
    else:
        print("\nmarket_factor column missing; skip clip_rate.")

    if "market_factor_raw" in band.columns:
        print("\nmarket_factor_raw stats")
        _safe_describe(band["market_factor_raw"].dropna(), "market_factor_raw")
    else:
        print("\nmarket_factor_raw column missing.")

    if "market_factor" in band.columns:
        print("\nmarket_factor stats")
        _safe_describe(band["market_factor"].dropna(), "market_factor")

    if "delta_market" not in band.columns:
        print("\nTop 10 abs(delta_market): delta_market column missing.")
        return

    tmp = band.copy()
    tmp["abs_delta"] = tmp["delta_market"].abs()
    base_cols = [
        "lt_now",
        "current_oh",
        "base_now",
        "base_delta",
        "market_factor_raw",
        "market_factor",
        "delta_market",
    ]
    optional_cols = ["base_final", "final_forecast"]
    columns = [col for col in base_cols if col in tmp.columns]
    columns.extend([col for col in optional_cols if col in tmp.columns])

    print("\nTop 10 abs(delta_market) in market band")
    print(tmp.sort_values("abs_delta", ascending=False)[columns].head(10).to_string())


if __name__ == "__main__":
    main()
