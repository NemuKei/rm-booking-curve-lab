import argparse
import sys
from pathlib import Path


def _setup_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))


def main() -> None:
    _setup_paths()

    import pandas as pd

    import booking_curve.forecast_simple as fs
    import run_full_evaluation as r

    parser = argparse.ArgumentParser(description="Diagnose weekshape factors.")
    parser.add_argument("--hotel", required=True, help="Hotel tag (e.g., hotel_001)")
    parser.add_argument("--asof", required=True, help="As-of date (YYYYMMDD or YYYY-MM-DD)")
    parser.add_argument("--target", required=True, help="Target month (YYYYMM)")
    args = parser.parse_args()

    hotel = str(args.hotel).strip()
    if not hotel:
        raise SystemExit("hotel_tag is required. Pass --hotel (e.g., hotel_001).")
    asof = str(args.asof).strip()
    target = str(args.target).strip()

    asof_ts = pd.to_datetime(asof)

    # target month lt_data
    lt_df = r.load_lt_csv(target, hotel_tag=hotel)

    # history months (same as build_monthly_forecast)
    history_months = r.get_history_months_around_asof(
        as_of_ts=asof_ts,
        months_back=4,
        months_forward=4,
    )

    history_raw: dict[str, pd.DataFrame] = {}
    for ym in history_months:
        try:
            df_m = r.load_lt_csv(ym, hotel_tag=hotel)
        except FileNotFoundError:
            continue
        if df_m.empty:
            continue
        history_raw[ym] = df_m

    if not history_raw:
        raise SystemExit("No history_raw loaded. Cannot diagnose weekshape.")

    cap = r.HOTEL_CONFIG.get(hotel, {}).get("capacity", r.CAPACITY)

    # build baseline_curves_by_weekday & history_by_weekday (same logic as build_monthly_forecast)
    baseline_curves_by_weekday: dict[int, pd.Series] = {}
    history_all_by_weekday: dict[int, pd.DataFrame] = {}

    for weekday in range(7):
        history_dfs = []
        for df_m in history_raw.values():
            df_m_wd = r.filter_by_weekday(df_m, weekday=weekday)
            if not df_m_wd.empty:
                history_dfs.append(df_m_wd)

        if not history_dfs:
            continue

        history_all = pd.concat(history_dfs, axis=0)
        history_all.index = pd.to_datetime(history_all.index)

        avg_curve = r.moving_average_recent_90days(
            lt_df=history_all,
            as_of_date=asof_ts,
            lt_min=r.LT_MIN,
            lt_max=r.LT_MAX,
            min_count=r.RECENT90_MIN_COUNT_WEEKDAY,
        )
        baseline_curves_by_weekday[weekday] = avg_curve
        history_all_by_weekday[weekday] = history_all

    def summarize_detail(tag: str, detail: pd.DataFrame) -> None:
        if detail is None or not isinstance(detail, pd.DataFrame) or detail.empty:
            print(tag, "detail: EMPTY")
            return
        cols = set(detail.columns)
        if "gated" in cols and "factor" in cols:
            gated_true = int(detail["gated"].sum())
            neq1 = int((detail["factor"] != 1.0).sum())
            print(
                tag,
                f"detail_rows={len(detail)} gated_true={gated_true} factor!=1={neq1}",
            )
            f = detail["factor"].astype(float)
            print(
                tag,
                "factor stats:",
                "min=",
                float(f.min()),
                "p50=",
                float(f.median()),
                "max=",
                float(f.max()),
            )
            return
        if "weekshape_factor" in cols:
            weekshape_n_events = detail.get("weekshape_n_events")
            if weekshape_n_events is None:
                weekshape_n_events = pd.Series([float("nan")] * len(detail), index=detail.index)
            weekshape_sum_base = detail.get("weekshape_sum_base")
            if weekshape_sum_base is None:
                weekshape_sum_base = pd.Series([float("nan")] * len(detail), index=detail.index)
            gated = (
                (weekshape_n_events < fs.WEEKSHAPE_MIN_EVENTS)
                | (weekshape_sum_base.abs() < fs.WEEKSHAPE_MIN_SUM_BASE)
                | weekshape_sum_base.isna()
            )
            gated_true = int(gated.sum())
            neq1 = int((detail["weekshape_factor"] != 1.0).sum())
            print(
                tag,
                f"detail_rows={len(detail)} gated_true={gated_true} factor!=1={neq1}",
            )
            f = detail["weekshape_factor"].astype(float)
            print(
                tag,
                "factor stats:",
                "min=",
                float(f.min()),
                "p50=",
                float(f.median()),
                "max=",
                float(f.max()),
            )

    def run(boundary: str):
        fs.WEEKSHAPE_WEEK_BOUNDARY = boundary

        # 1) factor map + detail from compute_weekshape_flow_factors (the core of weekshape)
        factor_map, detail_f = fs.compute_weekshape_flow_factors(
            lt_df=lt_df,
            as_of_ts=asof_ts,
            baseline_curves_by_weekday=baseline_curves_by_weekday,
            hotel_tag=hotel,
            lt_min=15,
            lt_max=45,
            w=7,
        )

        # 2) final forecast + detail from forecast_final_from_pace14_weekshape_flow (end-to-end)
        fc, detail_fc = fs.forecast_final_from_pace14_weekshape_flow(
            lt_df=lt_df,
            baseline_curves_by_weekday=baseline_curves_by_weekday,
            history_by_weekday=history_all_by_weekday,
            as_of_date=asof_ts,
            capacity=cap,
            hotel_tag=hotel,
            lt_min=0,
            lt_max=r.LT_MAX,
        )

        fc_n = pd.to_numeric(fc, errors="coerce")
        print("\n=== boundary =", boundary, "===")
        print(
            "forecast_sum=",
            float(fc_n.sum(skipna=True)),
            "len=",
            len(fc_n),
            "na=",
            int(fc_n.isna().sum()),
        )
        print("factor_map_size=", len(factor_map))
        summarize_detail("compute_weekshape_flow_factors", detail_f)
        summarize_detail("forecast_final_from_pace14_weekshape_flow", detail_fc)

        # sanity: how many stay_dates change week_id compared to iso
        return fc_n, detail_f, detail_fc, factor_map

    print("HOTEL=", hotel, "ASOF=", asof, "TARGET=", target)
    print(
        "LT_MIN/LT_MAX=",
        r.LT_MIN,
        r.LT_MAX,
        "RECENT90_MIN_COUNT_WEEKDAY=",
        r.RECENT90_MIN_COUNT_WEEKDAY,
    )
    print("history_months=", history_months)
    print("history_raw_months_loaded=", sorted(history_raw.keys()))
    print("baseline_weekdays=", sorted(baseline_curves_by_weekday.keys()))

    iso_fc, iso_df1, iso_df2, iso_map = run("iso")
    sun_fc, sun_df1, sun_df2, sun_map = run("sun")

    # compare forecasts
    diff_days = int((iso_fc.fillna(0).round().astype("Int64") != sun_fc.fillna(0).round().astype("Int64")).sum())
    print("\n=== iso vs sun compare ===")
    print("different_days=", diff_days, "of", len(iso_fc))
    print("delta_sum=", float((sun_fc - iso_fc).sum(skipna=True)))

    # compare factor maps (how many keys differ)
    common = set(iso_map.keys()) & set(sun_map.keys())
    diff_keys = sum(1 for k in common if float(iso_map[k]) != float(sun_map[k]))
    print(
        "factor_map common=",
        len(common),
        "diff_in_common=",
        int(diff_keys),
        "iso_only=",
        len(set(iso_map) - set(sun_map)),
        "sun_only=",
        len(set(sun_map) - set(iso_map)),
    )


if __name__ == "__main__":
    main()
