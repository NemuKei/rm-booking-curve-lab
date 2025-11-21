from pathlib import Path
import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.plot_booking_curve import filter_by_weekday
from booking_curve.forecast_simple import (
    moving_average_recent_90days_weighted,
    forecast_final_from_avg,
    forecast_month_from_recent90,
)

# ===== 設定値（必要に応じてユーザーが書き換える） =====
HOTEL_TAG = "daikokucho"
TARGET_MONTH = "202512"   # 予測対象の宿泊月 (例)
HISTORY_MONTHS = ["202501","202502", "202503", "202504", "202505", "202506", "202507", "202508", "202509", "202510", "202511", "202512", "202601", "202602"]
AS_OF_DATE = "2025-11-21"
CAPACITY = 168.0
# ================================================


def load_lt_csv(month: str) -> pd.DataFrame:
    file_name = f"lt_data_{month}_{HOTEL_TAG}.csv"
    file_path = Path(OUTPUT_DIR) / file_name
    return pd.read_csv(file_path, index_col=0)


def main() -> None:
    print("[recent90_weighted] Start forecast generation")
    df_target = load_lt_csv(TARGET_MONTH)
    history_raw = {m: load_lt_csv(m) for m in HISTORY_MONTHS}

    all_forecasts: dict[pd.Timestamp, float] = {}

    as_of_ts = pd.to_datetime(AS_OF_DATE)

    for weekday in range(7):
        print(f"[recent90_weighted] Processing weekday {weekday}")
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            print(f"[recent90_weighted] No history for weekday {weekday}")
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = moving_average_recent_90days_weighted(
            lt_df=history_all,
            as_of_date=as_of_ts,
            lt_min=-1,
            lt_max=90,
        )

        df_target_wd = filter_by_weekday(df_target, weekday=weekday)
        if df_target_wd.empty:
            print(f"[recent90_weighted] No target data for weekday {weekday}")
            continue

        fc_series = forecast_final_from_avg(
            lt_df=df_target_wd,
            avg_curve=avg_curve,
            as_of_date=as_of_ts,
            capacity=CAPACITY,
            lt_min=0,
            lt_max=90,
        )

        for stay_date, value in fc_series.items():
            all_forecasts[stay_date] = value

    if not all_forecasts:
        print("[recent90_weighted] No forecasts were generated. Check settings or data.")
        return

    out_df = forecast_month_from_recent90(
        df_target=df_target,
        forecasts=all_forecasts,
        as_of_ts=as_of_ts,
        hotel_tag=HOTEL_TAG,
    )

    asof_tag = AS_OF_DATE.replace("-", "")
    out_name = f"forecast_recent90w_{TARGET_MONTH}_{HOTEL_TAG}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[recent90_weighted][OK] Forecast exported to {out_path}")


if __name__ == "__main__":
    main()
