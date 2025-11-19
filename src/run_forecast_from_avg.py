"""Generate forecast CSV using weekday averages and capped logic."""
from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR
from booking_curve.plot_booking_curve import filter_by_weekday
from booking_curve.forecast_simple import (
    moving_average_3months,
    forecast_final_from_avg,
)


# =========================
# User configuration block
# =========================
HOTEL_TAG = "daikokucho"
TARGET_MONTH = "202506"
HISTORY_MONTHS = ["202503", "202504", "202505"]
AS_OF_DATE = "2025-05-31"
CAPACITY = 168.0


# =========================
# Helper functions
# =========================
def load_lt_csv(month: str) -> pd.DataFrame:
    """Load LT data CSV for the specified month."""
    file_name = f"lt_data_{month}_{HOTEL_TAG}.csv"
    file_path = Path(OUTPUT_DIR) / file_name
    return pd.read_csv(file_path, index_col=0)


# =========================
# Main logic
# =========================
def main() -> None:
    df_target = load_lt_csv(TARGET_MONTH)
    history_raw = {month: load_lt_csv(month) for month in HISTORY_MONTHS}

    all_forecasts: dict[pd.Timestamp, float] = {}

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        avg_curve = moving_average_3months(history_dfs, lt_min=-1, lt_max=90)
        df_target_wd = filter_by_weekday(df_target, weekday=weekday)

        as_of_ts = pd.to_datetime(AS_OF_DATE)
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
        print("No forecasts were generated. Check settings or data.")
        return

    result = pd.Series(all_forecasts, dtype=float)
    result.sort_index(inplace=True)

    out_df = result.to_frame(name="forecast_rooms")
    out_df.index.name = "stay_date"

    asof_tag = AS_OF_DATE.replace("-", "")
    out_name = f"forecast_{TARGET_MONTH}_{HOTEL_TAG}_asof_{asof_tag}.csv"
    out_path = Path(OUTPUT_DIR) / out_name

    out_df.to_csv(out_path, index=True)
    print(f"[OK] Forecast exported to {out_path}")


if __name__ == "__main__":
    main()
