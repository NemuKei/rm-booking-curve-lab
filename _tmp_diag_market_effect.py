import numpy as np
import pandas as pd
import sys
sys.path.append(".")
sys.path.append("src")

from run_forecast_batch import (
    LT_MIN, LT_MAX,
    load_lt_csv, filter_by_weekday, get_history_months_around_asof,
)
from booking_curve.forecast_simple import (
    moving_average_recent_90days,
    compute_market_pace_7d,
    forecast_final_from_pace14_market,
    MARKET_PACE_LT_MIN, MARKET_PACE_LT_MAX,
)

def yyyymm(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y%m")

def next_yyyymm(ts: pd.Timestamp) -> str:
    first = ts.replace(day=1)
    nextm = first + pd.offsets.MonthBegin(1)
    return nextm.strftime("%Y%m")

def load_lt_df_for_market(hotel_tag: str, as_of_ts: pd.Timestamp) -> pd.DataFrame:
    ym0 = yyyymm(as_of_ts)
    ym1 = next_yyyymm(as_of_ts)
    dfs = []
    for ym in [ym0, ym1]:
        try:
            df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="rooms")
        except FileNotFoundError:
            continue
        if df is not None and not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    out = pd.concat(dfs, axis=0)
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")]
    return out

hotel_tag   = "daikokucho"
as_of       = "2026-01-20"
target_month= "202602"
capacity    = 168.0

as_of_ts = pd.Timestamp(as_of).normalize()

# --- target month (forecast対象) ---
df_target = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
df_target.index = pd.to_datetime(df_target.index)

# --- history for baseline ---
history_months = get_history_months_around_asof(as_of_ts, months_back=6, months_forward=0)
history_raw = {}
for ym in history_months:
    try:
        df = load_lt_csv(ym, hotel_tag=hotel_tag, value_type="rooms")
    except FileNotFoundError:
        continue
    if df is not None and not df.empty:
        df.index = pd.to_datetime(df.index)
        history_raw[ym] = df

history_by_weekday = {}
baseline_curves = {}
for wd in range(7):
    dfs = []
    for df_m in history_raw.values():
        d = filter_by_weekday(df_m, weekday=wd)
        if not d.empty:
            dfs.append(d)
    if not dfs:
        continue
    hist = pd.concat(dfs, axis=0)
    hist.index = pd.to_datetime(hist.index)
    history_by_weekday[wd] = hist
    baseline_curves[wd] = moving_average_recent_90days(
        lt_df=hist, as_of_date=as_of_ts, lt_min=LT_MIN, lt_max=LT_MAX
    )

# ★ market用LTは「ASOF月＋翌月」
df_market = load_lt_df_for_market(hotel_tag, as_of_ts)
market_pace_7d, mp_detail = compute_market_pace_7d(
    lt_df=df_market,
    as_of_ts=as_of_ts,
    history_by_weekday=history_by_weekday,
    lt_min=LT_MIN,
    lt_max=LT_MAX,
)
print("market_pace_7d =", market_pace_7d)

# --- forecast (marketあり/なし) ---
detail_frames = []
for wd in range(7):
    hist = history_by_weekday.get(wd)
    base = baseline_curves.get(wd)
    if hist is None or base is None:
        continue
    df_wd = filter_by_weekday(df_target, weekday=wd)
    if df_wd.empty:
        continue

    fc_mkt, det_mkt = forecast_final_from_pace14_market(
        lt_df=df_wd, baseline_curve=base, history_df=hist,
        as_of_date=as_of_ts, capacity=capacity,
        market_pace_7d=market_pace_7d, lt_min=0, lt_max=LT_MAX
    )
    fc_nomkt, det_nomkt = forecast_final_from_pace14_market(
        lt_df=df_wd, baseline_curve=base, history_df=hist,
        as_of_date=as_of_ts, capacity=capacity,
        market_pace_7d=np.nan, lt_min=0, lt_max=LT_MAX
    )

    if not det_mkt.empty:
        det = det_mkt.copy()
        det["fc_market"] = fc_mkt
        det["fc_no_market"] = fc_nomkt
        det["delta_market"] = det["fc_market"] - det["fc_no_market"]
        detail_frames.append(det)

if not detail_frames:
    print("No detail rows.")
    raise SystemExit(0)

detail_all = pd.concat(detail_frames, axis=0).sort_index()
band = detail_all[(detail_all["lt_now"] >= MARKET_PACE_LT_MIN) & (detail_all["lt_now"] <= MARKET_PACE_LT_MAX)].copy()

print("\n=== MARKET BAND rows ===", len(band))
print("delta_market.describe()")
print(band["delta_market"].describe(percentiles=[.1,.25,.5,.75,.9]).to_string())

upper_cap = 1.20
lower_cap = 0.85
upper = (band["market_factor"] >= upper_cap - 1e-9).mean()
lower = (band["market_factor"] <= lower_cap + 1e-9).mean()
print(f"\nclip_rate upper(={upper_cap}):", round(float(upper), 4))
print(f"clip_rate lower(={lower_cap}):", round(float(lower), 4))

print("\nmarket_factor_raw stats")
print(band["market_factor_raw"].describe(percentiles=[.1,.25,.5,.75,.9]).to_string())
print("\nmarket_factor stats")
print(band["market_factor"].describe(percentiles=[.1,.25,.5,.75,.9]).to_string())

print("\nTop 10 abs(delta_market) in market band")
tmp = band.copy()
tmp["abs_delta"] = tmp["delta_market"].abs()
print(tmp.sort_values("abs_delta", ascending=False)[["lt_now","market_factor_raw","market_factor","delta_market"]].head(10).to_string())
