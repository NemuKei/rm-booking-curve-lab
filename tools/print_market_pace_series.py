# usage:
#   python tools/print_market_pace_series.py 202602 daikokucho 2026-01-23 90
#
# 202602 = target_month(YYYYMM)
# daikokucho = hotel_tag
# 2026-01-23 = end_asof (この日まで遡って計算)
# 90 = lookback_days (何日前から見るか)

import sys

import pandas as pd

# repo root 前提
sys.path.append("src")

from booking_curve.forecast_simple import compute_market_pace_7d
from run_forecast_batch import LT_MAX, LT_MIN, filter_by_weekday, get_history_months_around_asof, load_lt_csv


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


def main(target_month, hotel_tag, end_asof, lookback_days):
    end_ts = pd.Timestamp(end_asof).normalize()
    start_ts = (end_ts - pd.Timedelta(days=int(lookback_days))).normalize()

    # target月のLT_DATA（これが無いと算出不可）
    lt_df = load_lt_csv(target_month, hotel_tag=hotel_tag, value_type="rooms")
    lt_df.index = pd.to_datetime(lt_df.index)

    rows = []
    for as_of_ts in pd.date_range(start_ts, end_ts, freq="D"):
        # 履歴から weekday別 recent90 を作り、market_pace_7d を算出
        history_by_weekday = build_history_by_weekday(hotel_tag, as_of_ts, months_back=6, months_forward=0)
        mp_7d, mp_detail = compute_market_pace_7d(
            lt_df=lt_df,
            as_of_ts=as_of_ts,
            history_by_weekday=history_by_weekday,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
            days=7,
        )
        rows.append(
            {
                "as_of": as_of_ts.date().isoformat(),
                "market_pace_7d": mp_7d,
                "mp_raw_min_7d": float(mp_detail["mp_raw"].min(skipna=True)) if not mp_detail.empty else float("nan"),
                "mp_raw_max_7d": float(mp_detail["mp_raw"].max(skipna=True)) if not mp_detail.empty else float("nan"),
                "mp_raw_count_7d": int(mp_detail["mp_raw"].count()) if not mp_detail.empty else 0,
            }
        )

    out = pd.DataFrame(rows)

    # ざっくりのレンジ感（クリップ設計の材料）
    desc = out["market_pace_7d"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print("\n=== market_pace_7d series (tail 14) ===")
    print(out.tail(14).to_string(index=False))
    print("\n=== market_pace_7d describe ===")
    print(desc.to_string())
    print("\nTIP: この describe の p10/p90 を見て、clip候補(例: 0.92-1.08 / 0.90-1.10)を決めると速いです。")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("usage: python tools/print_market_pace_series.py <YYYYMM> <hotel_tag> <YYYY-MM-DD> <lookback_days>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
