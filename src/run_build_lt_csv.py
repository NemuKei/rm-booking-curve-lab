"""
直近数ヶ月分の LT_DATA CSV をまとめて出力するスクリプト。

GUI からは run_build_lt_for_gui(hotel_tag, target_months) を呼び出す。
CLI ???? --hotel ? hotel_tag ??????????
"""

import argparse
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from booking_curve.config import DATA_DIR, HOTEL_CONFIG, OUTPUT_DIR
from booking_curve.daily_snapshots import read_daily_snapshots_for_month
from booking_curve.data_loader import load_time_series_excel
from booking_curve.lt_builder import (
    build_lt_data,
    build_lt_data_from_daily_snapshots_for_month,
    extract_asof_dates_from_timeseries,
)

# LT_DATA を出したい宿泊月（シート名）リスト（CLI デフォルト）
TARGET_MONTHS = [
    "202511",
    "202512",
    "202601",
    "202602",
]

# 最大リードタイム
MAX_LT = 120


def build_monthly_curve_from_timeseries(df_ts: pd.DataFrame, max_lt: int) -> pd.DataFrame:
    """
    時系列Excelから月次ブッキングカーブ用の「LT別・月次Rooms合計」を生成する。
    """

    if df_ts is None or df_ts.empty:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    booking_serials = df_ts.iloc[0, 1:]
    excel_base = datetime(1899, 12, 30)
    as_of_dates: list[pd.Timestamp] = []

    for serial in booking_serials:
        if pd.isna(serial):
            as_of_dates.append(pd.NaT)
            continue
        as_of = excel_base + timedelta(days=float(serial))
        as_of_dates.append(pd.to_datetime(as_of))

    stay_dates_raw = df_ts.iloc[1:, 0]
    stay_dates = pd.to_datetime(stay_dates_raw, errors="coerce").dropna()
    if stay_dates.empty:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    month_end = stay_dates.max().normalize()

    monthly_by_lt: dict[int, float] = {}

    for col_idx in range(1, df_ts.shape[1]):
        as_of_date = as_of_dates[col_idx - 1]
        if pd.isna(as_of_date):
            continue

        rooms_col = df_ts.iloc[1:, col_idx]
        if rooms_col.isna().all():
            continue

        total = rooms_col.sum(skipna=True)

        lt_raw = (month_end.date() - as_of_date.date()).days
        if lt_raw < 0:
            lt = -1
        elif lt_raw > max_lt:
            continue
        else:
            lt = int(lt_raw)

        monthly_by_lt[lt] = float(total)

    if not monthly_by_lt:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    rows = sorted(monthly_by_lt.items(), key=lambda x: x[0])
    df_out = pd.DataFrame(rows, columns=["lt", "rooms_total"])
    df_out["lt"] = df_out["lt"].astype(int)
    return df_out


def build_monthly_curve_from_daily_snapshots(
    hotel_id: str, target_month: str, output_dir: Path, max_lt: int = MAX_LT
) -> pd.DataFrame:
    """
    daily snapshots 由来の月次カーブを ASOF ベースで集計し、LT 軸に変換する。
    """

    df_month = read_daily_snapshots_for_month(
        hotel_id=hotel_id, target_month=target_month, output_dir=output_dir
    )

    if df_month is None or df_month.empty:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    df_month = df_month.copy()
    df_month["stay_date"] = pd.to_datetime(df_month["stay_date"], errors="coerce").dt.normalize()
    df_month["as_of_date"] = pd.to_datetime(df_month["as_of_date"], errors="coerce").dt.normalize()

    df_month = df_month.dropna(subset=["stay_date", "as_of_date", "rooms_oh"])
    if df_month.empty:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    year = int(target_month[:4])
    month = int(target_month[4:])
    last_day = monthrange(year, month)[1]
    month_end = datetime(year, month, last_day)
    act_asof = month_end + timedelta(days=1)

    df_monthly = df_month.groupby("as_of_date")["rooms_oh"].sum().sort_index()
    df_monthly = df_monthly.reset_index().rename(columns={"rooms_oh": "rooms_total"})

    df_monthly["lt"] = (act_asof - df_monthly["as_of_date"]).dt.days - 1

    df_monthly = df_monthly[(df_monthly["lt"] >= -1) & (df_monthly["lt"] <= max_lt)]
    if df_monthly.empty:
        return pd.DataFrame(columns=["lt", "rooms_total"])

    df_monthly = (
        df_monthly.groupby("lt")["rooms_total"]
        .sum()
        .reset_index()
        .sort_values("lt")
        .reset_index(drop=True)
    )

    df_monthly["lt"] = df_monthly["lt"].astype(int)
    return df_monthly


def _get_hotel_io_config(hotel_tag: str) -> tuple[Path, str]:
    """
    指定された hotel_tag について、時系列データExcelのパスと表示名を返すヘルパー。

    Returns:
        excel_path: DATA_DIR / data_subdir / timeseries_file
        display_name: GUIなどで使う表示名
    """
    cfg = HOTEL_CONFIG.get(hotel_tag)
    if cfg is None:
        raise KeyError(f"Unknown hotel_tag: {hotel_tag!r}")

    data_subdir = cfg.get("data_subdir")
    timeseries_file = cfg.get("timeseries_file")
    if not data_subdir or not timeseries_file:
        raise ValueError(f"Hotel config missing data_subdir/timeseries_file for {hotel_tag!r}")

    excel_path = DATA_DIR / data_subdir / timeseries_file
    display_name = cfg.get("display_name", hotel_tag)
    return excel_path, display_name


def build_lt_for_month(sheet_name: str, hotel_tag: str, excel_path: Path) -> list[pd.Timestamp]:
    """指定した宿泊月シートの LT_DATA を作成し、ASOF 日付一覧を返す。"""

    print(f"[INFO] sheet={sheet_name} から LT_DATA を作成中 ...")

    df_ts = load_time_series_excel(
        filename=excel_path,
        sheet_name=sheet_name,
    )

    asof_dates = extract_asof_dates_from_timeseries(df_ts)
    lt_df = build_lt_data(df_ts, max_lt=MAX_LT)

    out_name = f"lt_data_{sheet_name}_{hotel_tag}.csv"
    out_path = OUTPUT_DIR / out_name

    lt_df.to_csv(out_path, index=True)
    print(f"[OK] 出力: {out_path}")

    try:
        monthly_df = build_monthly_curve_from_timeseries(df_ts, max_lt=MAX_LT)
    except Exception as exc:  # noqa: BLE001
        print(f"[run_build_lt_csv] Skip monthly_curve for {hotel_tag} {sheet_name}: {exc}")
    else:
        if monthly_df.empty:
            print(f"[WARN] 月次カーブ用データが取得できませんでした: {sheet_name}")
        else:
            monthly_out_name = f"monthly_curve_{sheet_name}_{hotel_tag}.csv"
            monthly_out_path = OUTPUT_DIR / monthly_out_name
            monthly_df.to_csv(monthly_out_path, index=False)
            print(f"[OK] 月次カーブ出力: {monthly_out_path}")

    return [pd.Timestamp(d) for d in asof_dates]


def run_build_lt_for_gui(
    hotel_tag: str,
    target_months: list[str],
    source: str = "timeseries",
) -> None:
    """
    GUI から呼び出すための薄いラッパー。

    target_months に指定された宿泊月(YYYYMM)だけについて LT_DATA CSV を再生成し、
    それらの取得日一覧をまとめて asof_dates_＜hotel_tag＞.csv として上書き出力する。
    """

    if not target_months:
        print("[INFO] 対象月が指定されていないため処理をスキップします。")
        return

    cfg = HOTEL_CONFIG.get(hotel_tag)
    if cfg is None:
        raise KeyError(f"Unknown hotel_tag: {hotel_tag!r}")

    if source == "timeseries":
        excel_path, display_name = _get_hotel_io_config(hotel_tag)
        print(f"対象ホテル: {display_name} ({hotel_tag}) / ファイル: {excel_path.name}")
    else:
        excel_path = None
        display_name = cfg.get("display_name", hotel_tag)
        print(f"対象ホテル: {display_name} ({hotel_tag}) / source: {source}")

    all_asof_dates: list[pd.Timestamp] = []

    for ym in target_months:
        if source == "timeseries":
            month_asofs = build_lt_for_month(
                ym,
                hotel_tag=hotel_tag,
                excel_path=excel_path,
            )
            all_asof_dates.extend(pd.Timestamp(d).normalize() for d in month_asofs)
        elif source == "daily_snapshots":
            print(f"[daily_snapshots] building LT_DATA for {hotel_tag} {ym}")
            lt_rooms = build_lt_data_from_daily_snapshots_for_month(
                hotel_id=hotel_tag,
                target_month=ym,
                value_col="rooms_oh",
                max_lt=MAX_LT,
                output_dir=OUTPUT_DIR,
                output_name=f"lt_data_rooms_{ym}_{hotel_tag}.csv",
            )
            legacy_out_path = OUTPUT_DIR / f"lt_data_{ym}_{hotel_tag}.csv"
            lt_rooms.to_csv(legacy_out_path, index_label="stay_date", encoding="utf-8-sig")
            print(f"[OK] 出力: {legacy_out_path}")

            build_lt_data_from_daily_snapshots_for_month(
                hotel_id=hotel_tag,
                target_month=ym,
                value_col="pax_oh",
                max_lt=MAX_LT,
                output_dir=OUTPUT_DIR,
                output_name=f"lt_data_pax_{ym}_{hotel_tag}.csv",
            )
            build_lt_data_from_daily_snapshots_for_month(
                hotel_id=hotel_tag,
                target_month=ym,
                value_col="revenue_oh",
                max_lt=MAX_LT,
                output_dir=OUTPUT_DIR,
                output_name=f"lt_data_revenue_{ym}_{hotel_tag}.csv",
            )

            monthly_df = build_monthly_curve_from_daily_snapshots(
                hotel_id=hotel_tag,
                target_month=ym,
                output_dir=OUTPUT_DIR,
                max_lt=MAX_LT,
            )

            if monthly_df.empty:
                print(f"[WARN] 月次カーブ用データが取得できませんでした: {ym}")
            else:
                mc_path = OUTPUT_DIR / f"monthly_curve_{ym}_{hotel_tag}.csv"
                monthly_df.to_csv(mc_path, index=False, encoding="utf-8-sig")
                print(f"[OK] 月次カーブ出力: {mc_path}")
        else:
            raise ValueError(f"Unknown source: {source}")

    if source != "timeseries":
        return

    if not all_asof_dates:
        print("[WARN] 取得日が1件も検出されませんでした (asof_dates CSV は出力されません)。")
        return

    asof_list = sorted({d.normalize() for d in all_asof_dates})
    df_asof = pd.DataFrame({"as_of_date": asof_list})
    asof_path = OUTPUT_DIR / f"asof_dates_{hotel_tag}.csv"
    df_asof.to_csv(asof_path, index=False)
    print(f"[OK] 取得日一覧: {asof_path}")


def main():
    parser = argparse.ArgumentParser(description="LT_DATA CSV batch generator")
    parser.add_argument(
        "--hotel",
        required=True,
        help="Hotel tag (e.g., hotel_001)",
    )
    parser.add_argument(
        "--source",
        choices=["timeseries", "daily_snapshots"],
        default="daily_snapshots",
        help="LT_DATA build source (default: daily_snapshots)",
    )
    args = parser.parse_args()

    hotel_tag = str(args.hotel).strip()
    if not hotel_tag:
        raise ValueError("hotel_tag is required. Pass --hotel (e.g., hotel_001).")
    source = args.source
    cfg = HOTEL_CONFIG.get(hotel_tag)
    if cfg is None:
        raise ValueError(f"Unknown hotel_tag: {hotel_tag!r}. Update hotels.json and retry.")
    display_name = cfg.get("display_name", hotel_tag)

    excel_path = None
    if source == "timeseries":
        excel_path, display_name = _get_hotel_io_config(hotel_tag)

    print("=== LT_DATA CSV 一括生成 ===")
    if excel_path is None:
        print(f"対象ホテル: {display_name} ({hotel_tag}) / source: {source}")
    else:
        print(f"対象ホテル: {display_name} ({hotel_tag}) / ファイル: {excel_path.name}")
    print(f"対象月シート: {', '.join(TARGET_MONTHS)}")
    print("")

    run_build_lt_for_gui(
        hotel_tag=hotel_tag,
        target_months=TARGET_MONTHS,
        source=source,
    )

    print("\n=== 完了しました ===")


if __name__ == "__main__":
    main()
