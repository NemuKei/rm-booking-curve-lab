from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.plot_booking_curve import filter_by_weekday
from booking_curve.forecast_simple import (
    moving_average_3months,
    moving_average_recent_90days,
    moving_average_recent_90days_weighted,
    forecast_final_from_avg,
    forecast_month_from_recent90,
)

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"

# 評価したい宿泊月 (YYYYMM)。必要に応じて増減可。
TARGET_MONTHS = [
    "202311",
    "202312",
    "202401",
    "202402",
    "202403",
    "202404",
    "202405",
    "202406",
    "202407",
    "202408",
    "202409",
    "202410",
    "202411",
    "202412",
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
]

# LTの範囲など、既存スクリプトと揃える
LT_MIN = -1
LT_MAX = 90
CAPACITY = 168.0
# ===== 設定ここまで =====

# HISTORY_MONTHS は既存スクリプトに合わせて個別に定義
AVG_HISTORY_MONTHS = [
    "202308",
    "202309",
    "202310",
    "202311",
    "202312",
    "202401",
    "202402",
    "202403",
    "202404",
    "202405",
    "202406",
    "202407",
    "202408",
    "202409",
    "202410",
    "202411",
    "202412",
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
    "202511",
]

RECENT90_HISTORY_MONTHS = [
    "202308",
    "202309",
    "202310",
    "202311",
    "202312",
    "202401",
    "202402",
    "202403",
    "202404",
    "202405",
    "202406",
    "202407",
    "202408",
    "202409",
    "202410",
    "202411",
    "202412",
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
    "202511",
    "202512",
    "202601",
    "202602",
]


def get_asof_dates_for_month(target_month: str) -> list[str]:
    """
    対象月 YYYYMM に対して、
    - 前月末
    - 当月10日
    - 当月20日
    の3つの as_of 日付(YYYYMMDD)を返す。
    """
    year = int(target_month[:4])
    month = int(target_month[4:])

    # 当月1日
    first = date(year, month, 1)

    # 前月末 = 当月1日から1日引く
    prev_month_end = first - timedelta(days=1)

    # 当月10日, 20日
    asof_10 = date(year, month, 10)
    asof_20 = date(year, month, 20)

    return [
        prev_month_end.strftime("%Y%m%d"),
        asof_10.strftime("%Y%m%d"),
        asof_20.strftime("%Y%m%d"),
    ]


def load_lt_csv(month: str) -> pd.DataFrame:
    file_name = f"lt_data_{month}_{HOTEL_TAG}.csv"
    file_path = Path(OUTPUT_DIR) / file_name
    return pd.read_csv(file_path, index_col=0)


def _prepare_output(df_target: pd.DataFrame, forecast: dict[pd.Timestamp, float], as_of_ts: pd.Timestamp) -> pd.DataFrame:
    result = pd.Series(forecast, dtype=float)
    result.sort_index(inplace=True)

    all_dates = pd.to_datetime(df_target.index)
    all_dates = all_dates.sort_values()

    out_df = pd.DataFrame(index=all_dates)
    out_df.index.name = "stay_date"

    act_col = None
    for col in df_target.columns:
        try:
            if int(col) == -1:
                act_col = col
                break
        except Exception:
            continue

    if act_col is not None:
        actual_series = df_target[act_col]
        actual_series.index = all_dates
        out_df["actual_rooms"] = actual_series
    else:
        out_df["actual_rooms"] = pd.NA

    out_df["forecast_rooms"] = result.reindex(all_dates)
    out_df["forecast_rooms_int"] = out_df["forecast_rooms"].round().astype("Int64")

    projected = []
    for dt in out_df.index:
        if dt < as_of_ts:
            projected.append(out_df.loc[dt, "actual_rooms"])
        else:
            projected.append(out_df.loc[dt, "forecast_rooms_int"])

    out_df["projected_rooms"] = projected
    return out_df


def run_avg_forecast(target_month: str, as_of_date: str) -> None:
    """
    avgモデル(3ヶ月平均)で target_month を as_of_date 時点で予測し、
    run_forecast_from_avg.py と同じ形式の CSV を OUTPUT_DIR に出力する。
    """
    df_target = load_lt_csv(target_month)
    history_raw = {month: load_lt_csv(month) for month in AVG_HISTORY_MONTHS}

    all_forecasts: dict[pd.Timestamp, float] = {}
    as_of_ts = pd.to_datetime(as_of_date)

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        avg_curve = moving_average_3months(history_dfs, lt_min=LT_MIN, lt_max=LT_MAX)
        df_target_wd = filter_by_weekday(df_target, weekday=weekday)

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=CAPACITY,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")
        return

    out_df = _prepare_output(df_target, all_forecasts, as_of_ts)

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_{target_month}_{HOTEL_TAG}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def run_recent90_forecast(target_month: str, as_of_date: str) -> None:
    """
    recent90モデル(観測日から遡る90日平均)で target_month を as_of_date 時点で予測し、
    run_forecast_from_recent90.py と同じ形式の CSV を OUTPUT_DIR に出力する。
    """
    df_target = load_lt_csv(target_month)
    history_raw = {m: load_lt_csv(m) for m in RECENT90_HISTORY_MONTHS}

    all_forecasts: dict[pd.Timestamp, float] = {}

    as_of_ts = pd.to_datetime(as_of_date)

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=CAPACITY,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("No forecasts were generated. Check settings or data.")
        return

    out_df = forecast_month_from_recent90(
        df_target=df_target,
        forecasts=all_forecasts,
        as_of_ts=as_of_ts,
        hotel_tag=HOTEL_TAG,
    )

    asof_tag = as_of_date.replace("-", "")
    out_name = f"forecast_recent90_{target_month}_{HOTEL_TAG}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


def run_recent90_weighted_forecast(target_month: str, as_of: str) -> None:
    """
    recent90_weightedモデル(観測日から遡る90日平均・重み付き)で
    target_month の予測CSVを出力する。

    出力ファイル名:
      forecast_recent90w_{target_month}_{HOTEL_TAG}_asof_{as_of}.csv
    """
    df_target = load_lt_csv(target_month)
    history_raw = {m: load_lt_csv(m) for m in RECENT90_HISTORY_MONTHS}

    as_of_ts = pd.to_datetime(as_of, format="%Y%m%d")

    all_forecasts: dict[pd.Timestamp, float] = {}

    for weekday in range(7):
        # 履歴側: 該当曜日だけに絞る
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        # ★ここが simple recent90 との違い: weighted 版を使う
        avg_curve = moving_average_recent_90days_weighted(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=LT_MIN,
            lt_max=LT_MAX,
        )

        # 対象月側も同じ曜日だけに絞る
        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            continue

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=CAPACITY,
            lt_min=0,
            lt_max=LT_MAX,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print(f"[recent90_weighted] No forecasts for {target_month} as_of={as_of}")
        return

    out_df = _prepare_output(
        df_target=df_target,
        forecast=all_forecasts,
        as_of_ts=as_of_ts,
    )

    out_name = f"forecast_recent90w_{target_month}_{HOTEL_TAG}_asof_{as_of}.csv"
    out_path = Path(OUTPUT_DIR) / out_name
    out_df.to_csv(out_path, index=True)
    print(f"[recent90_weighted][OK] {out_path}")


def main() -> None:
    for target_month in TARGET_MONTHS:
        asof_list = get_asof_dates_for_month(target_month)
        for as_of in asof_list:
            print(f"[avg]       target={target_month} as_of={as_of}")
            run_avg_forecast(target_month, as_of)

            print(f"[recent90]  target={target_month} as_of={as_of}")
            run_recent90_forecast(target_month, as_of)

            print(f"[recent90w] target={target_month} as_of={as_of}")
            run_recent90_weighted_forecast(target_month, as_of)

    print("=== batch forecast finished ===")


if __name__ == "__main__":
    main()
