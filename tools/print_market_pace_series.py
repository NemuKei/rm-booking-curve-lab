# usage:
#   python tools/print_market_pace_series.py daikokucho 2026-01-23 90
#
# hotel_tag = daikokucho / kansai etc.
# end_asof  = YYYY-MM-DD
# lookback_days = 90 など

import sys

import numpy as np
import pandas as pd

sys.path.append("src")

from booking_curve.forecast_simple import PACE14_UPPER_LT, moving_average_recent_90days
from run_forecast_batch import (
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


def build_history_by_weekday(hotel_tag: str, as_of_ts: pd.Timestamp, months_back=6, months_forward=0):
    months = get_history_months_around_asof(as_of_ts, months_back=months_back, months_forward=months_forward)
    history_raw = {}
    for ym in months:
        try:
            df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="rooms")
        except FileNotFoundError:
            continue
        if df.empty:
            continue
        history_raw[ym] = df

    history_by_weekday = {}
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


def load_lt_df_for_market(hotel_tag: str, as_of_ts: pd.Timestamp) -> pd.DataFrame:
    """as_ofの当月+翌月を結合して、LT0-14に必要なstay_dateを跨げるようにする。"""
    ym0 = _yyyymm(as_of_ts)
    ym1 = _next_month_yyyymm(as_of_ts)

    dfs = []
    for ym in [ym0, ym1]:
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
    # 重複stay_dateがあれば後勝ち（通常は無い想定）
    out = out[~out.index.duplicated(keep="last")]
    return out


def market_pace_raw_with_diag(lt_df: pd.DataFrame, baseline_curves: dict[int, pd.Series], as_of_ts: pd.Timestamp):
    total_actual = 0.0
    total_base = 0.0
    n_events = 0

    df = lt_df.copy()
    df.index = pd.to_datetime(df.index)
    df.columns = pd.Index([int(c) for c in df.columns], dtype=int)

    for stay_date, row in df.iterrows():
        lt_now = (stay_date - as_of_ts).days
        if lt_now < 0 or lt_now > PACE14_UPPER_LT:
            continue
        if lt_now not in df.columns or (lt_now + 1) not in df.columns:
            continue

        current_oh = pd.to_numeric(row.get(lt_now, np.nan), errors="coerce")
        next_oh = pd.to_numeric(row.get(lt_now + 1, np.nan), errors="coerce")
        if pd.isna(current_oh) or pd.isna(next_oh):
            continue
        pickup = float(current_oh - next_oh)

        baseline_curve = baseline_curves.get(stay_date.weekday())
        if baseline_curve is None:
            continue
        base_now = pd.to_numeric(baseline_curve.get(lt_now, np.nan), errors="coerce")
        base_next = pd.to_numeric(baseline_curve.get(lt_now + 1, np.nan), errors="coerce")
        if pd.isna(base_now) or pd.isna(base_next):
            continue
        base_pickup = float(base_now - base_next)

        total_actual += pickup
        total_base += base_pickup
        n_events += 1

    mp_raw = np.nan if abs(total_base) < 1e-9 else (total_actual / total_base)
    return mp_raw, total_actual, total_base, n_events


def compute_market_pace_7d_agg(
    lt_df: pd.DataFrame,
    as_of_ts: pd.Timestamp,
    history_by_weekday: dict[int, pd.DataFrame],
    *,
    days: int = 7,
    min_count: int = 10,  # baseline作りのmin_count（現行より上げる推奨）
    min_events_7d: int = 20,  # 7日合算のpickupイベント数
    min_abs_base_7d: float = 1.0,  # 7日合算のbase_pickup絶対値
):
    records = []
    sum_a = 0.0
    sum_b = 0.0
    sum_n = 0

    for offset in range(days):
        target_date = (as_of_ts - pd.Timedelta(days=offset)).normalize()

        baseline_curves_for_date = {}
        for weekday, history_df in history_by_weekday.items():
            if history_df.empty:
                continue
            baseline_curves_for_date[weekday] = moving_average_recent_90days(
                lt_df=history_df,
                as_of_date=target_date,
                lt_min=LT_MIN,
                lt_max=LT_MAX,
                min_count=min_count,
            )

        mp_raw, a, b, n = market_pace_raw_with_diag(lt_df, baseline_curves_for_date, target_date)
        records.append(
            {
                "as_of_date": target_date,
                "mp_raw": mp_raw,
                "sum_actual": a,
                "sum_base": b,
                "n_events": n,
            }
        )

        if not np.isnan(mp_raw):
            sum_a += a
            sum_b += b
            sum_n += n

    detail = pd.DataFrame(records).sort_values("as_of_date")

    # 7日“合算比”で market_pace_7d を決める（小分母に強い）
    if abs(sum_b) < min_abs_base_7d or sum_n < min_events_7d:
        mp_7d = np.nan
    else:
        mp_7d = sum_a / sum_b

    return float(mp_7d) if not np.isnan(mp_7d) else np.nan, detail


def main(hotel_tag, end_asof, lookback_days):
    end_ts = pd.Timestamp(end_asof).normalize()
    start_ts = (end_ts - pd.Timedelta(days=int(lookback_days))).normalize()

    rows = []
    for as_of_ts in pd.date_range(start_ts, end_ts, freq="D"):
        lt_df = load_lt_df_for_market(hotel_tag, as_of_ts)
        if lt_df.empty:
            rows.append({"as_of": as_of_ts.date().isoformat(), "market_pace_7d": np.nan, "n_events_7d": 0, "sum_base_7d": np.nan})
            continue

        history_by_weekday = build_history_by_weekday(hotel_tag, as_of_ts, months_back=6, months_forward=0)
        mp_7d, mp_detail = compute_market_pace_7d_agg(
            lt_df=lt_df,
            as_of_ts=as_of_ts,
            history_by_weekday=history_by_weekday,
            days=7,
            min_count=10,  # まずは上げる（1だと暴れやすい）
            min_events_7d=20,
            min_abs_base_7d=1.0,
        )

        n_events_7d = int(mp_detail["n_events"].sum())
        sum_base_7d = float(mp_detail["sum_base"].sum())

        rows.append(
            {
                "as_of": as_of_ts.date().isoformat(),
                "market_pace_7d": mp_7d,
                "n_events_7d": n_events_7d,
                "sum_base_7d": sum_base_7d,
            }
        )

    out = pd.DataFrame(rows)
    desc = out["market_pace_7d"].dropna().describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])

    print("\n=== market_pace_7d series (tail 14) ===")
    print(out.tail(14).to_string(index=False))
    print("\n=== market_pace_7d describe (non-NaN) ===")
    print(desc.to_string())
    print("\nNOTE:")
    print("- market_pace_7d は 7日“合算比”(Σactual/Σbase) で算出")
    print("- n_events_7d / sum_base_7d が小さい日は NaN（計測不能）にしています")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: python tools/print_market_pace_series.py <hotel_tag> <YYYY-MM-DD> <lookback_days>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
