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

HOTEL_TAG = "daikokucho"
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
ASOF_TYPES = ["M-2_END", "M-1_END", "M10", "M20"]

LT_MIN = -1
LT_MAX = 90
CAPACITY = 168.0


def resolve_asof_dates_for_month(target_month: str) -> list[tuple[str, str]]:
    year = int(target_month[:4])
    month = int(target_month[4:])

    first_day = date(year, month, 1)
    prev_month_end = first_day - timedelta(days=1)
    prev2_month_end = prev_month_end.replace(day=1) - timedelta(days=1)
    asof_10 = date(year, month, 10)
    asof_20 = date(year, month, 20)

    return [
        ("M-2_END", prev2_month_end.strftime("%Y%m%d")),
        ("M-1_END", prev_month_end.strftime("%Y%m%d")),
        ("M10", asof_10.strftime("%Y%m%d")),
        ("M20", asof_20.strftime("%Y%m%d")),
    ]


def get_history_months_around_asof(
    as_of_ts: pd.Timestamp, months_back: int = 4, months_forward: int = 4
) -> list[str]:
    center = as_of_ts.to_period("M")
    months: list[str] = []
    for offset in range(-months_back, months_forward + 1):
        p = center + offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_avg_history_months(target_month: str, months_back: int = 3) -> list[str]:
    period = pd.Period(target_month, freq="M")
    months: list[str] = []
    for offset in range(1, months_back + 1):
        p = period - offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def load_lt_csv(month: str) -> pd.DataFrame:
    file_name = f"lt_data_{month}_{HOTEL_TAG}.csv"
    file_path = Path(OUTPUT_DIR) / file_name
    return pd.read_csv(file_path, index_col=0)


def _get_actual_series(lt_df: pd.DataFrame, index: pd.Index) -> pd.Series:
    act_col = None
    for col in lt_df.columns:
        try:
            if int(col) == -1:
                act_col = col
                break
        except Exception:
            continue

    if act_col is None:
        return pd.Series(pd.NA, index=index)

    actual_series = lt_df[act_col].copy()
    actual_series.index = index
    return actual_series


def _build_projected_series(
    lt_df: pd.DataFrame, forecasts: dict[pd.Timestamp, float], as_of_ts: pd.Timestamp
) -> pd.Series:
    all_dates = pd.to_datetime(lt_df.index)
    all_dates = all_dates.sort_values()

    forecast_series = pd.Series(forecasts, dtype=float)
    forecast_series = forecast_series.reindex(all_dates)

    forecast_int = forecast_series.round().astype("Int64")
    actual_series = _get_actual_series(lt_df, all_dates)

    projected = []
    for dt in all_dates:
        if dt < as_of_ts:
            projected.append(actual_series.loc[dt])
        else:
            projected.append(forecast_int.loc[dt])

    return pd.Series(projected, index=all_dates)


def _infer_target_month(lt_df: pd.DataFrame) -> str:
    dates = pd.to_datetime(lt_df.index)
    first = dates.sort_values()[0]
    p = first.to_period("M")
    return f"{p.year}{p.month:02d}"


def build_monthly_forecast(
    lt_df: pd.DataFrame, model_name: str, as_of_date: str
) -> pd.Series:
    as_of_ts = pd.to_datetime(as_of_date)
    target_month = _infer_target_month(lt_df)

    if model_name == "avg":
        history_months = get_avg_history_months(target_month=target_month, months_back=3)
    else:
        history_months = get_history_months_around_asof(
            as_of_ts=as_of_ts, months_back=4, months_forward=4
        )

    history_raw: dict[str, pd.DataFrame] = {}
    for ym in history_months:
        try:
            df_m = load_lt_csv(ym)
        except FileNotFoundError:
            continue
        if df_m.empty:
            continue
        history_raw[ym] = df_m

    all_forecasts: dict[pd.Timestamp, float] = {}

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        if model_name == "avg":
            avg_curve = moving_average_3months(history_dfs, lt_min=LT_MIN, lt_max=LT_MAX)
        elif model_name in {"recent90", "recent90_adj"}:
            history_all = pd.concat(history_dfs, axis=0)
            history_all.index = pd.to_datetime(history_all.index)
            avg_curve = moving_average_recent_90days(
                lt_df=history_all, as_of_date=as_of_ts, lt_min=LT_MIN, lt_max=LT_MAX
            )
        elif model_name in {"recent90w", "recent90w_adj"}:
            history_all = pd.concat(history_dfs, axis=0)
            history_all.index = pd.to_datetime(history_all.index)
            avg_curve = moving_average_recent_90days_weighted(
                lt_df=history_all, as_of_date=as_of_ts, lt_min=LT_MIN, lt_max=LT_MAX
            )
        else:
            raise ValueError(f"Unknown model_name: {model_name}")

        df_target_wd = filter_by_weekday(lt_df, weekday=weekday)
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
        return pd.Series(dtype=float)

    if model_name == "avg":
        projected = _build_projected_series(lt_df=lt_df, forecasts=all_forecasts, as_of_ts=as_of_ts)
        return projected

    out_df = forecast_month_from_recent90(
        df_target=lt_df, forecasts=all_forecasts, as_of_ts=as_of_ts, hotel_tag=HOTEL_TAG
    )

    if model_name in {"recent90_adj", "recent90w_adj"}:
        col = "adjusted_projected_rooms"
    else:
        col = "projected_rooms"

    return out_df[col]


def build_evaluation_detail(hotel_tag: str, target_months: list[str]) -> pd.DataFrame:
    records: list[dict] = []

    for target_month in target_months:
        lt_csv_path = Path(OUTPUT_DIR) / f"lt_data_{target_month}_{hotel_tag}.csv"
        lt_df = pd.read_csv(lt_csv_path, index_col=0)

        all_dates = pd.to_datetime(lt_df.index)
        actual_series = _get_actual_series(lt_df, all_dates)
        actual_total_rooms = float(pd.to_numeric(actual_series, errors="coerce").sum(skipna=True))

        for asof_type, asof_date_str in resolve_asof_dates_for_month(target_month):
            asof_ts = pd.to_datetime(asof_date_str)

            for model_name in [
                "avg",
                "recent90",
                "recent90_adj",
                "recent90w",
                "recent90w_adj",
            ]:
                forecast_series = build_monthly_forecast(
                    lt_df=lt_df, model_name=model_name, as_of_date=asof_ts
                )
                forecast_total_rooms = float(
                    pd.to_numeric(forecast_series, errors="coerce").sum(skipna=True)
                )

                error = forecast_total_rooms - actual_total_rooms
                if actual_total_rooms > 0:
                    error_pct = (error / actual_total_rooms) * 100.0
                else:
                    error_pct = 0.0
                abs_error_pct = abs(error_pct)

                records.append(
                    {
                        "target_month": target_month,
                        "asof_date": asof_ts.date().isoformat(),
                        "asof_type": asof_type,
                        "model": model_name,
                        "actual_total_rooms": actual_total_rooms,
                        "forecast_total_rooms": forecast_total_rooms,
                        "error": error,
                        "error_pct": error_pct,
                        "abs_error_pct": abs_error_pct,
                    }
                )

    return pd.DataFrame(records)


def build_evaluation_summary(df_detail: pd.DataFrame) -> pd.DataFrame:
    df_summary = (
        df_detail.groupby(["target_month", "model"], dropna=False)
        .agg(
            mean_error_pct=("error_pct", "mean"),
            mae_pct=("abs_error_pct", "mean"),
        )
        .reset_index()
    )

    return df_summary.sort_values(by=["target_month", "model"]).reset_index(drop=True)


def run_full_evaluation_for_range(
    hotel_tag: str, target_months: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame, Path, Path]:
    """
    指定ホテル・指定宿泊月リストについて評価を実行し、
    詳細・サマリの DataFrame と、それぞれの出力パスを返す。
    """

    df_detail = build_evaluation_detail(hotel_tag=hotel_tag, target_months=target_months)
    detail_path = Path(OUTPUT_DIR) / f"evaluation_{hotel_tag}_detail.csv"
    df_detail.to_csv(detail_path, index=False)

    df_multi = build_evaluation_summary(df_detail)
    summary_path = Path(OUTPUT_DIR) / f"evaluation_{hotel_tag}_multi.csv"
    df_multi.to_csv(summary_path, index=False)

    return df_detail, df_multi, detail_path, summary_path


def run_full_evaluation_for_gui(hotel_tag: str, target_months: list[str]) -> tuple[Path, Path]:
    """
    GUI 用の簡易ラッパ。
    詳細・サマリCSVを書き出し、そのパスだけを返す。
    """

    _, _, detail_path, summary_path = run_full_evaluation_for_range(
        hotel_tag=hotel_tag,
        target_months=target_months,
    )
    return detail_path, summary_path


def main() -> None:
    hotel_tag = HOTEL_TAG
    target_months = list(TARGET_MONTHS)

    df_detail, df_multi, detail_path, summary_path = run_full_evaluation_for_range(
        hotel_tag=hotel_tag,
        target_months=target_months,
    )

    print("[OK] Evaluation tables generated.")
    print("Detail:", detail_path)
    print("Summary:", summary_path)
    print()
    print(df_multi.head().to_string(index=False))


if __name__ == "__main__":
    main()
