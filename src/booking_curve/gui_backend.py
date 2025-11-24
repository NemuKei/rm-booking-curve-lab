from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from booking_curve.forecast_simple import (
    moving_average_recent_90days,
    moving_average_recent_90days_weighted,
    moving_average_3months,
)

# プロジェクトルートから見た output ディレクトリ
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

# ホテル別設定 (将来は設定画面や外部ファイルに出してもよい)
HOTEL_CONFIG: Dict[str, Dict[str, float]] = {
    "daikokucho": {
        "capacity": 168.0,
    },
    # 他ホテルを追加する場合はここに辞書を増やす
}


def _get_capacity(hotel_tag: str, capacity: Optional[float]) -> float:
    """GUIから渡された capacity があればそれを優先し、
    なければ HOTEL_CONFIG のデフォルトを返す。
    """
    if capacity is not None:
        return float(capacity)
    return float(HOTEL_CONFIG.get(hotel_tag, {}).get("capacity", 1.0))


def _load_lt_data(hotel_tag: str, target_month: str) -> pd.DataFrame:
    """LT_DATA CSV を読み込み、stay_date を DatetimeIndex に揃える。"""

    csv_path = OUTPUT_DIR / f"lt_data_{target_month}_{hotel_tag}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"LT_DATA csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)
    df.index = pd.to_datetime(df.index)

    # 列を int 化できるものだけに限定する
    col_map: dict[str, int] = {}
    for col in df.columns:
        try:
            col_map[col] = int(col)
        except Exception:
            continue

    if not col_map:
        raise ValueError("LT 列が見つかりませんでした。")

    lt_df = df[list(col_map.keys())].copy()
    lt_df.columns = [col_map[c] for c in lt_df.columns]

    # 念のため対象月でフィルタ
    year = int(target_month[:4])
    month = int(target_month[4:])
    lt_df = lt_df[(lt_df.index.year == year) & (lt_df.index.month == month)]

    return lt_df


def _get_history_months_around_asof(
    as_of_ts: pd.Timestamp,
    months_back: int = 4,
    months_forward: int = 4,
) -> list[str]:
    """
    ASOF 日付を中心に、前後の月を YYYYMM 文字列リストで返す。
    例: as_of=2025-09-30 -> ["202505", ..., "202601"]
    """
    center = as_of_ts.to_period("M")
    months: list[str] = []
    for offset in range(-months_back, months_forward + 1):
        p = center + offset
        months.append(f"{p.year}{p.month:02d}")
    return months


def get_booking_curve_data(
    hotel_tag: str,
    target_month: str,
    weekday: int,
    model: str,
    as_of_date: str,
) -> dict:
    """曜日別ブッキングカーブ画面向けのデータセットを返す。"""

    lt_df = _load_lt_data(hotel_tag=hotel_tag, target_month=target_month)

    # 曜日でフィルタ（0=Mon..6=Sun）
    df_week = lt_df[lt_df.index.weekday == weekday].copy()
    df_week.sort_index(inplace=True)

    lt_ticks = sorted(df_week.columns) if not df_week.empty else sorted(lt_df.columns)
    lt_min, lt_max = (lt_ticks[0], lt_ticks[-1]) if lt_ticks else (-1, 90)

    df_week_plot = df_week.copy()

    asof_ts = pd.to_datetime(as_of_date)

    # ASOF を中心に前後4ヶ月の LT_DATA を読み込み、同曜日だけを連結
    history_months = _get_history_months_around_asof(
        as_of_ts=asof_ts,
        months_back=4,
        months_forward=4,
    )

    history_dfs: list[pd.DataFrame] = []
    for ym in history_months:
        try:
            df_m = _load_lt_data(hotel_tag=hotel_tag, target_month=ym)
        except FileNotFoundError:
            continue
        df_m_wd = df_m[df_m.index.weekday == weekday].copy()
        if not df_m_wd.empty:
            history_dfs.append(df_m_wd)

    if history_dfs:
        history_all = pd.concat(history_dfs, axis=0)
        history_all.sort_index(inplace=True)
    else:
        # 履歴が取れない場合はフォールバックとして target_month の曜日データを使う
        history_all = df_week.copy()

    for stay_date in df_week_plot.index:
        delta_days = (stay_date.normalize() - asof_ts).days
        if delta_days > 0:
            for lt in df_week_plot.columns:
                if lt < delta_days:
                    df_week_plot.at[stay_date, lt] = pd.NA

    # stay_date ごとのカーブ
    curves = {}
    for stay_date, row in df_week_plot.iterrows():
        curves[stay_date] = row.reindex(lt_ticks)

    # --- 3ヶ月平均カーブの計算 ---
    target_period = pd.Period(target_month, freq="M")
    history_dfs: list[pd.DataFrame] = []

    for offset in (1, 2, 3):
        past_period = target_period - offset
        past_month_str = f"{past_period.year}{past_period.month:02d}"
        try:
            past_lt = _load_lt_data(hotel_tag=hotel_tag, target_month=past_month_str)
        except FileNotFoundError:
            continue

        past_week = past_lt[past_lt.index.weekday == weekday].copy()
        if not past_week.empty:
            history_dfs.append(past_week)

    if history_dfs:
        avg_curve = moving_average_3months(
            lt_df_list=history_dfs,
            lt_min=lt_min,
            lt_max=lt_max,
        )
    else:
        if not df_week.empty:
            avg_curve = df_week.reindex(columns=lt_ticks).mean(axis=0, skipna=True)
        else:
            avg_curve = None

    forecast_curve = None

    if model == "recent90":
        if not history_all.empty:
            forecast_curve = moving_average_recent_90days(
                lt_df=history_all,
                as_of_date=asof_ts,
                lt_min=lt_min,
                lt_max=lt_max,
            )
    elif model == "recent90w":
        if not history_all.empty:
            forecast_curve = moving_average_recent_90days_weighted(
                lt_df=history_all,
                as_of_date=asof_ts,
                lt_min=lt_min,
                lt_max=lt_max,
            )
    elif model == "avg":
        forecast_curve = avg_curve

    dates: List[pd.Timestamp] = list(df_week.index)

    return {
        "curves": curves,
        "avg_curve": avg_curve,
        "forecast_curve": forecast_curve,
        "lt_ticks": lt_ticks,
        "dates": dates,
    }


def get_monthly_curve_data(hotel_tag: str, target_month: str) -> pd.DataFrame:
    """月次ブッキングカーブ画面向けに CSV から DataFrame を返す。"""

    csv_path = OUTPUT_DIR / f"monthly_curve_{target_month}_{hotel_tag}_all.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"monthly curve csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)

    try:
        df.index = pd.Index([int(i) for i in df.index], dtype=int)
    except Exception:
        pass

    return df


def get_daily_forecast_table(
    hotel_tag: str,
    target_month: str,
    as_of_date: str,
    gui_model: str,
    capacity: Optional[float] = None,
) -> pd.DataFrame:
    """日別フォーキャスト一覧画面向けのテーブルを構築する。

    Parameters
    ----------
    hotel_tag : str
        ホテル識別子 (例: "daikokucho")
    target_month : str
        対象宿泊月 "YYYYMM"
    as_of_date : str
        予測基準日 "YYYY-MM-DD"
    gui_model : str
        GUI上で選択されたモデル名
        ("avg", "recent90", "recent90_adj", "recent90w", "recent90w_adj")
    capacity : float, optional
        None の場合は HOTEL_CONFIG の設定を使用

    Returns
    -------
    pd.DataFrame
        日別行 + 最終行に TOTAL 行 を含むテーブル
    """
    cap = _get_capacity(hotel_tag, capacity)

    # GUIモデル名から CSV prefix と列名を決定する
    model_map = {
        "avg": ("forecast", "projected_rooms"),
        "recent90": ("forecast_recent90", "projected_rooms"),
        "recent90w": ("forecast_recent90w", "projected_rooms"),
        "recent90_adj": ("forecast_recent90", "adjusted_projected_rooms"),
        "recent90w_adj": ("forecast_recent90w", "adjusted_projected_rooms"),
    }
    if gui_model not in model_map:
        raise ValueError(f"Unsupported gui_model: {gui_model}")

    prefix, col_name = model_map[gui_model]

    # as_of_date を "YYYYMMDD" に変換 (既存ファイル命名規則と揃える)
    asof_ts = pd.to_datetime(as_of_date)
    asof_tag = asof_ts.strftime("%Y%m%d")

    csv_name = f"{prefix}_{target_month}_{hotel_tag}_asof_{asof_tag}.csv"
    csv_path = OUTPUT_DIR / csv_name
    if not csv_path.exists():
        raise FileNotFoundError(f"forecast csv not found: {csv_path}")

    df = pd.read_csv(csv_path, index_col=0)
    # index は stay_date
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # 列存在チェック
    if "actual_rooms" not in df.columns:
        raise ValueError(f"{csv_path} に actual_rooms 列がありません。")
    if col_name not in df.columns:
        raise ValueError(f"{csv_path} に {col_name} 列がありません。")

    out = pd.DataFrame(index=df.index.copy())
    out["stay_date"] = out.index
    # 曜日 (0=Monday..6=Sunday)
    out["weekday"] = out["stay_date"].dt.weekday

    out["actual_rooms"] = df["actual_rooms"].astype(float)
    out["forecast_rooms"] = df[col_name].astype(float)

    # 差異 (actual が NaN の場合は NaN)
    out["diff_rooms"] = out["forecast_rooms"] - out["actual_rooms"]
    # 差異率
    denom = out["actual_rooms"].replace(0, pd.NA)
    out["diff_pct"] = (out["diff_rooms"] / denom * 100.0).astype(float)

    # 稼働率 (daily)
    out["occ_actual_pct"] = (out["actual_rooms"] / cap * 100.0).astype(float)
    out["occ_forecast_pct"] = (out["forecast_rooms"] / cap * 100.0).astype(float)

    # 月次合計行の追加
    # 有効日数 = stay_date のユニーク数
    num_days = out["stay_date"].nunique()

    actual_total = out["actual_rooms"].fillna(0).sum()
    forecast_total = out["forecast_rooms"].fillna(0).sum()
    diff_total = forecast_total - actual_total
    if actual_total > 0:
        diff_total_pct = diff_total / actual_total * 100.0
    else:
        diff_total_pct = float("nan")

    occ_actual_month = actual_total / (cap * num_days) * 100.0 if num_days > 0 else float("nan")
    occ_forecast_month = forecast_total / (cap * num_days) * 100.0 if num_days > 0 else float("nan")

    total_row = {
        "stay_date": pd.NaT,
        "weekday": "",
        "actual_rooms": actual_total,
        "forecast_rooms": forecast_total,
        "diff_rooms": diff_total,
        "diff_pct": diff_total_pct,
        "occ_actual_pct": occ_actual_month,
        "occ_forecast_pct": occ_forecast_month,
    }

    out = out.reset_index(drop=True)
    out = pd.concat([out, pd.DataFrame([total_row])], ignore_index=True)

    return out


def get_model_evaluation_table(hotel_tag: str) -> pd.DataFrame:
    """モデル評価画面向けに、月次 MAE/バイアス一覧を返す。"""
    csv_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_multi.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"evaluation csv not found: {csv_path}")

    df = pd.read_csv(csv_path)
    # 必要な列だけに整形 (target_month, model, mean_error_pct, mae_pct)
    cols = []
    for c in ["target_month", "model", "mean_error_pct", "mae_pct"]:
        if c not in df.columns:
            raise ValueError(f"{csv_path} に {c} 列がありません。")
        cols.append(c)
    df = df[cols].copy()
    return df

