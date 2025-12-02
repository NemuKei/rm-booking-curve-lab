from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import json

import pandas as pd
import build_calendar_features
import run_forecast_batch
import run_build_lt_csv
from run_full_evaluation import run_full_evaluation_for_gui

from booking_curve.forecast_simple import (
    moving_average_recent_90days,
    moving_average_recent_90days_weighted,
    moving_average_3months,
)

# プロジェクトルートから見た output ディレクトリ
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"
HOTEL_CONFIG_PATH = CONFIG_DIR / "hotels.json"


def _load_default_hotel_config() -> Dict[str, Dict[str, float]]:
    """設定ファイルが無い場合に使うデフォルト設定。現状は大国町のみ。"""
    return {
        "daikokucho": {
            "capacity": 168.0,
        }
    }


def load_hotel_config() -> Dict[str, Dict[str, float]]:
    """
    config/hotels.json からホテル設定を読み込む。
    - ファイルが存在しない場合や読み込みエラー時は、デフォルト設定を返す。
    - JSON のフォーマットは:
        {
          "daikokucho": {
            "display_name": "ソビアルなんば大国町",
            "capacity": 168
          },
          "kansai": {
            "display_name": "ホテル関西",
            "capacity": 400
          }
        }
      のような想定とする。
    - display_name は現時点では利用しない（あっても無視してよい）。
    """
    try:
        if not HOTEL_CONFIG_PATH.exists():
            return _load_default_hotel_config()
        with HOTEL_CONFIG_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return _load_default_hotel_config()

    config: Dict[str, Dict[str, float]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        cap = value.get("capacity")
        if cap is None:
            continue
        try:
            cap_f = float(cap)
        except Exception:
            continue
        config[key] = {"capacity": cap_f}

    if not config:
        return _load_default_hotel_config()
    return config


HOTEL_CONFIG: Dict[str, Dict[str, float]] = load_hotel_config()


def generate_month_range(start_yyyymm: str, end_yyyymm: str) -> list[str]:
    """
    開始月・終了月 (YYYYMM) から、両端を含む月リストを生成する。
    例: "202401", "202403" -> ["202401", "202402", "202403"]
    """

    def _parse_yyyymm(value: str) -> tuple[int, int]:
        if len(value) != 6:
            raise ValueError(f"Invalid YYYYMM format: {value}")
        try:
            year = int(value[:4])
            month = int(value[4:])
        except ValueError:
            raise ValueError(f"Invalid YYYYMM format: {value}") from None
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month in YYYYMM: {value}")
        return year, month

    start_year, start_month = _parse_yyyymm(start_yyyymm)
    end_year, end_month = _parse_yyyymm(end_yyyymm)

    if (start_year, start_month) > (end_year, end_month):
        raise ValueError("start_yyyymm must not be later than end_yyyymm")

    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year}{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

    return months


def build_calendar_for_gui(hotel_tag: str) -> str:
    """
    GUI からのカレンダー再生成ボタン用ラッパ。

    現状は build_calendar_features.main() が内部で HOTEL_TAG="daikokucho" 固定で
    calendar_features_daikokucho.csv を出力する前提になっている。

    将来的には hotel_tag ごとに別のカレンダーを生成するように build_calendar_features 側を
    拡張する想定だが、現時点では hotel_tag はインターフェース上の引数として受け取るだけにする。

    戻り値:
        生成されたカレンダーファイルの絶対パス文字列。
    """

    # まず既存の main() を呼んでファイル生成を行う。
    try:
        build_calendar_features.main()
    except Exception:
        # 例外はそのまま呼び出し元(GUI側)に送る
        raise

    # 現状は hotel_tag に関わらず daikokucho 固定ファイルが出力される想定。
    # OUTPUT_DIR は本モジュール内で定義されている output フォルダへのパスを使う。
    csv_path = OUTPUT_DIR / f"calendar_features_{hotel_tag}.csv"
    return str(csv_path)


def get_calendar_coverage(hotel_tag: str) -> Dict[str, Optional[str]]:
    """
    calendar_features_<hotel_tag>.csv の日付範囲を返すヘルパー。

    戻り値:
        {
            "min_date": "YYYY-MM-DD" または None,
            "max_date": "YYYY-MM-DD" または None,
        }

    ファイルが存在しない、もしくは内容が不正な場合は両方とも None を返す。
    """

    csv_path = OUTPUT_DIR / f"calendar_features_{hotel_tag}.csv"
    if not csv_path.exists():
        return {"min_date": None, "max_date": None}

    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
    except Exception:
        return {"min_date": None, "max_date": None}

    if df.empty or "date" not in df.columns:
        return {"min_date": None, "max_date": None}

    # date 列から最小・最大を取得
    min_dt = df["date"].min()
    max_dt = df["date"].max()

    if pd.isna(min_dt) or pd.isna(max_dt):
        return {"min_date": None, "max_date": None}

    min_str = pd.to_datetime(min_dt).normalize().strftime("%Y-%m-%d")
    max_str = pd.to_datetime(max_dt).normalize().strftime("%Y-%m-%d")

    return {"min_date": min_str, "max_date": max_str}


def _get_capacity(hotel_tag: str, capacity: Optional[float]) -> float:
    """GUIから渡された capacity があればそれを優先し、
    なければ HOTEL_CONFIG のデフォルトを返す。
    """
    if capacity is not None:
        return float(capacity)
    return float(HOTEL_CONFIG.get(hotel_tag, {}).get("capacity", 171.0))


def get_latest_asof_for_hotel(hotel_tag: str) -> Optional[str]:
    """ホテル別の最新 ASOF 日付を asof_dates_<hotel_tag>.csv から取得する。"""

    csv_path = OUTPUT_DIR / f"asof_dates_{hotel_tag}.csv"
    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path, parse_dates=["as_of_date"])
    except Exception:
        return None

    if "as_of_date" not in df.columns:
        return None

    asof_series = df["as_of_date"]
    if asof_series.empty:
        return None

    latest_asof = asof_series.max()
    if pd.isna(latest_asof):
        return None

    return pd.to_datetime(latest_asof).normalize().strftime("%Y-%m-%d")


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


def _get_latest_asof_from_lt(hotel_tag: str, target_month: str) -> Optional[str]:
    """
    asof_dates_xxx.csv が無い場合用のフォールバック。
    LT_DATA から「今日以前に存在する ASOF 日付」の最大値を推定して返す。
    """
    try:
        lt_df = _load_lt_data(hotel_tag=hotel_tag, target_month=target_month)
    except FileNotFoundError:
        return None

    if lt_df.empty:
        return None

    # LT >= 0 の列だけを対象にする
    lt_cols = [c for c in lt_df.columns if isinstance(c, (int, float)) and c >= 0]
    if not lt_cols:
        return None

    today = pd.Timestamp.today().normalize()
    latest_asof: Optional[pd.Timestamp] = None

    for stay_date, row in lt_df[lt_cols].iterrows():
        for lt, val in row.items():
            if pd.isna(val):
                continue
            try:
                lt_int = int(lt)
            except Exception:
                continue
            asof = stay_date.normalize() - pd.Timedelta(days=lt_int)
            # 未来日付は無視
            if asof > today:
                continue
            if (latest_asof is None) or (asof > latest_asof):
                latest_asof = asof

    if latest_asof is None:
        return None
    return latest_asof.normalize().strftime("%Y-%m-%d")


def get_latest_asof_for_month(hotel_tag: str, target_month: str) -> Optional[str]:
    """
    指定ホテル・指定宿泊月の「最新ASOF」を返す。

    優先順位:
    1. output/asof_dates_{hotel_tag}.csv の as_of_date 最大値
    2. asof_dates が無い場合は、LT_DATA からのフォールバック推定
    """
    latest_asof = get_latest_asof_for_hotel(hotel_tag)
    if latest_asof is not None:
        return latest_asof

    # asof_dates が無い場合は、LT_DATA から推定
    return _get_latest_asof_from_lt(hotel_tag, target_month)


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

    has_act_column = -1 in df_week_plot.columns
    asof_normalized = asof_ts.normalize()

    for stay_date in df_week_plot.index:
        delta_days = (stay_date.normalize() - asof_ts).days
        if delta_days > 0:
            for lt in df_week_plot.columns:
                if lt < delta_days:
                    df_week_plot.at[stay_date, lt] = pd.NA

        if has_act_column and stay_date.normalize() >= asof_normalized:
            df_week_plot.at[stay_date, -1] = pd.NA

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


def get_monthly_curve_data(
    hotel_tag: str,
    target_month: str,
    as_of_date: Optional[str] = None,
) -> pd.DataFrame:
    """月次ブッキングカーブ画面向けに LT_DATA から集計した DataFrame を返す。

    Parameters
    ----------
    hotel_tag : str
        ホテルのタグ。
    target_month : str
        対象となる宿泊月 (YYYYMM)。
    as_of_date : Optional[str]
        現在は無視される。呼び出し元互換性のために残しているだけ。
    """

    lt_path = OUTPUT_DIR / f"lt_data_{target_month}_{hotel_tag}.csv"
    if not lt_path.exists():
        raise FileNotFoundError(f"lt_data csv not found: {lt_path}")

    df_raw = pd.read_csv(lt_path, index_col=0)
    df_raw.index = pd.to_datetime(df_raw.index, errors="coerce")
    df_raw = df_raw.dropna()
    df_raw = df_raw[~df_raw.index.isna()]

    lt_cols: list[str] = []
    for col in df_raw.columns:
        try:
            int(col)
        except Exception:
            continue
        lt_cols.append(col)

    if not lt_cols:
        raise ValueError("LT 列が見つかりませんでした。")

    df_lt = df_raw[lt_cols].copy()
    df_lt.columns = [int(c) for c in lt_cols]

    year = int(target_month[:4])
    month = int(target_month[4:])
    df_lt = df_lt[(df_lt.index.year == year) & (df_lt.index.month == month)]

    if df_lt.empty:
        raise ValueError("指定月の宿泊日がありません。")

    df_lt = df_lt.reindex(sorted(df_lt.columns), axis=1)

    curve = df_lt.sum(axis=0, skipna=True)

    result = pd.DataFrame({"rooms_total": curve})
    result.index = result.index.astype(int)

    return result


def run_forecast_for_gui(
    hotel_tag: str,
    target_months: list[str],
    as_of_date: str,
    gui_model: str,
    capacity: float | None = None,
) -> None:
    """
    日別フォーキャストタブから Forecast を実行するための薄いラッパー。

    - target_months: 対象宿泊月の YYYYMM リスト。
      （現時点では GUI からは 1要素リストを渡す想定だが、
       将来的に「当月＋先3ヶ月」などの複数月対応も見越す）
    - as_of_date: "YYYY-MM-DD" 形式。run_forecast_batch 側では
      pd.to_datetime で解釈される前提。
    - gui_model: GUI のコンボボックス値
      ("avg", "recent90", "recent90_adj", "recent90w", "recent90w_adj")
    - capacity: 予測キャップ (None の場合は run_forecast_batch 側のデフォルトを使用)
    """
    # GUI からは "YYYY-MM-DD" が渡されるので、
    # run_forecast_batch 側の想定に合わせて "YYYYMMDD" に変換する。
    asof_ts = pd.to_datetime(as_of_date)
    asof_tag = asof_ts.strftime("%Y%m%d")

    # _adj 付きは、元 CSV の adjusted_projected_rooms 列を使うだけなので
    # 計算としては base モデルと同じでよい。
    base_model = gui_model.replace("_adj", "")

    for ym in target_months:
        if base_model == "avg":
            run_forecast_batch.run_avg_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
            )
        elif base_model == "recent90":
            run_forecast_batch.run_recent90_forecast(
                target_month=ym,
                as_of_date=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
            )
        elif base_model == "recent90w":
            run_forecast_batch.run_recent90_weighted_forecast(
                target_month=ym,
                as_of=asof_tag,
                capacity=capacity,
                hotel_tag=hotel_tag,
            )
        else:
            raise ValueError(f"Unsupported gui_model: {gui_model}")


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
    """
    評価CSVを読み込み、月別×モデル + モデルTOTAL の評価指標を返す。

    - mean_error_pct : 誤差率の平均（バイアス）
    - mae_pct        : 誤差率絶対値の平均
    - rmse_pct       : 誤差率の二乗平均平方根
    - n_samples      : 集計に使ったサンプル数（ASOF数）

    備考:
    - run_evaluate_forecasts.py が出力する
        evaluation_{hotel_tag}_multi.csv   : 月次サマリ
        evaluation_{hotel_tag}_detail.csv  : ASOF明細
      を利用する。
    """

    summary_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_multi.csv"
    detail_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"evaluation summary csv not found: {summary_path}")

    # --- 月次サマリ (mean_error_pct / mae_pct) 読み込み ---
    df_summary = pd.read_csv(summary_path)

    required_summary_cols = ["target_month", "model", "mean_error_pct", "mae_pct"]
    missing_sum = [c for c in required_summary_cols if c not in df_summary.columns]
    if missing_sum:
        raise ValueError(f"{summary_path} に {', '.join(missing_sum)} 列がありません。")

    df_summary = df_summary.copy()
    df_summary["target_month"] = df_summary["target_month"].astype(str)
    df_summary["model"] = df_summary["model"].astype(str)
    df_summary["mean_error_pct"] = pd.to_numeric(
        df_summary["mean_error_pct"], errors="coerce"
    )
    df_summary["mae_pct"] = pd.to_numeric(df_summary["mae_pct"], errors="coerce")

    # --- 明細から rmse_pct / n_samples を計算 ---
    if detail_path.exists():
        df_detail = pd.read_csv(detail_path)

        required_detail_cols = ["target_month", "model", "error_pct", "abs_error_pct"]
        missing_det = [c for c in required_detail_cols if c not in df_detail.columns]
        if missing_det:
            raise ValueError(f"{detail_path} に {', '.join(missing_det)} 列がありません。")

        df_detail = df_detail.copy()
        df_detail["target_month"] = df_detail["target_month"].astype(str)
        df_detail["model"] = df_detail["model"].astype(str)
        df_detail["error_pct"] = pd.to_numeric(
            df_detail["error_pct"], errors="coerce"
        )
        df_detail["abs_error_pct"] = pd.to_numeric(
            df_detail["abs_error_pct"], errors="coerce"
        )

        def _agg_group(g: pd.DataFrame) -> dict:
            err = g["error_pct"].dropna()
            err_abs = g["abs_error_pct"].dropna()
            n = int(err.count())
            rmse = err.pow(2).mean() ** 0.5 if not err.empty else float("nan")
            return {
                "rmse_pct": rmse,
                "n_samples": n,
            }

        # 月別×モデルの rmse_pct / n_samples
        records = []
        for (tm, model), g in df_detail.groupby(["target_month", "model"]):
            agg = _agg_group(g)
            records.append(
                {"target_month": tm, "model": model, **agg}
            )

        df_rmse = pd.DataFrame(
            records,
            columns=["target_month", "model", "rmse_pct", "n_samples"],
        )

        # サマリと結合
        df_merged = pd.merge(
            df_summary,
            df_rmse,
            on=["target_month", "model"],
            how="left",
        )

        # モデル別 TOTAL 行（全期間まとめ）
        total_records = []
        for model, g in df_detail.groupby("model"):
            agg = _agg_group(g)
            # TOTAL については mean_error_pct / mae_pct も detail から再計算
            err = g["error_pct"].dropna()
            err_abs = g["abs_error_pct"].dropna()
            mean_error = err.mean() if not err.empty else float("nan")
            mae = err_abs.mean() if not err_abs.empty else float("nan")

            total_records.append(
                {
                    "target_month": "TOTAL",
                    "model": model,
                    "mean_error_pct": mean_error,
                    "mae_pct": mae,
                    "rmse_pct": agg["rmse_pct"],
                    "n_samples": agg["n_samples"],
                }
            )

        df_total = pd.DataFrame(
            total_records,
            columns=[
                "target_month",
                "model",
                "mean_error_pct",
                "mae_pct",
                "rmse_pct",
                "n_samples",
            ],
        )

        out = pd.concat([df_merged, df_total], ignore_index=True)

    else:
        # 明細が無い場合は rmse/n_samples は NaN のまま
        df_summary["rmse_pct"] = float("nan")
        df_summary["n_samples"] = float("nan")
        out = df_summary

    # 並び替え
    def _sort_target_month(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            # "TOTAL" などは最後に回す
            return 999999

    out["target_month"] = out["target_month"].astype(str)
    out["__sort_month"] = out["target_month"].map(_sort_target_month)
    out.sort_values(by=["model", "__sort_month"], inplace=True)
    out.drop(columns=["__sort_month"], inplace=True)

    # 列順を固定
    out = out[
        [
            "target_month",
            "model",
            "mean_error_pct",
            "mae_pct",
            "rmse_pct",
            "n_samples",
        ]
    ]

    return out


def _target_month_to_int(value: object) -> int:
    """target_month を int に正規化する。"""

    try:
        return int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid target_month value: {value}")


def _filter_by_target_month(
    df: pd.DataFrame, from_ym: Optional[str], to_ym: Optional[str]
) -> pd.DataFrame:
    df = df.copy()
    df["target_month_int"] = df["target_month"].map(_target_month_to_int)

    mask = pd.Series([True] * len(df))
    if from_ym is not None:
        mask &= df["target_month_int"] >= _target_month_to_int(from_ym)
    if to_ym is not None:
        mask &= df["target_month_int"] <= _target_month_to_int(to_ym)

    return df.loc[mask].copy()


def get_eval_overview_by_asof(
    hotel_tag: str,
    from_ym: str | None = None,
    to_ym: str | None = None,
) -> pd.DataFrame:
    """
    モデル×ASOFタイプ別の期間トータル評価指標を返す。

    - 入力: evaluation_{hotel_tag}_detail.csv
    - 期間フィルタ:
        * from_ym, to_ym は "YYYYMM" 形式の文字列または None。
        * target_month を int 化して between でフィルタする。
        * None の場合は制限なし。
    - 出力列:
        ["model", "asof_type",
         "mean_error_pct",  # error_pct の平均
         "mae_pct",         # abs_error_pct の平均
         "rmse_pct",        # sqrt(mean(error_pct^2))
         "n_samples"]       # サンプル数
    - 並び順:
        model 昇順, asof_type 昇順。
    """

    csv_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"evaluation detail csv not found: {csv_path}")

    df_detail = pd.read_csv(csv_path)
    df_detail = _filter_by_target_month(df_detail, from_ym=from_ym, to_ym=to_ym)

    df_detail["error_pct"] = pd.to_numeric(df_detail["error_pct"], errors="coerce")
    df_detail["abs_error_pct"] = pd.to_numeric(
        df_detail["abs_error_pct"], errors="coerce"
    )

    records = []
    for (model, asof_type), g in df_detail.groupby(["model", "asof_type"]):
        err = g["error_pct"].dropna()
        err_abs = g["abs_error_pct"].dropna()
        mean_error = err.mean() if not err.empty else float("nan")
        mae = err_abs.mean() if not err_abs.empty else float("nan")
        rmse = err.pow(2).mean() ** 0.5 if not err.empty else float("nan")
        n = int(err.count())

        records.append(
            {
                "model": model,
                "asof_type": asof_type,
                "mean_error_pct": mean_error,
                "mae_pct": mae,
                "rmse_pct": rmse,
                "n_samples": n,
            }
        )

    out = pd.DataFrame(
        records,
        columns=[
            "model",
            "asof_type",
            "mean_error_pct",
            "mae_pct",
            "rmse_pct",
            "n_samples",
        ],
    )

    out.sort_values(by=["model", "asof_type"], inplace=True)

    return out


def get_eval_monthly_by_asof(
    hotel_tag: str,
    from_ym: str | None = None,
    to_ym: str | None = None,
    asof_types: list[str] | None = None,
    models: list[str] | None = None,
) -> pd.DataFrame:
    """
    月別×ASOF×モデルの評価ログを返す（1行=1 target_month×asof_type×model）。

    - 入力: evaluation_{hotel_tag}_detail.csv
    - 期間フィルタ:
        from_ym/to_ym は get_eval_overview_by_asof と同じ。
    - asof_types フィルタ:
        None の場合は全て、リスト指定時はその asof_type のみ残す。
    - models フィルタ:
        None の場合は全て、リスト指定時はその model のみ残す。
    - 出力列:
        ["target_month", "asof_type", "model",
         "error_pct", "abs_error_pct"]
      必要に応じて GUI 側で mean_error_pct / mae_pct として解釈する。
    - 並び順:
        target_month 昇順, asof_type 昇順, model 昇順。
    """

    csv_path = OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"evaluation detail csv not found: {csv_path}")

    df_detail = pd.read_csv(csv_path)
    df_detail = _filter_by_target_month(df_detail, from_ym=from_ym, to_ym=to_ym)

    if asof_types is not None:
        df_detail = df_detail[df_detail["asof_type"].isin(asof_types)]
    if models is not None:
        df_detail = df_detail[df_detail["model"].isin(models)]

    df_detail["error_pct"] = pd.to_numeric(df_detail["error_pct"], errors="coerce")
    df_detail["abs_error_pct"] = pd.to_numeric(
        df_detail["abs_error_pct"], errors="coerce"
    )

    df_detail.sort_values(
        by=["target_month_int", "asof_type", "model"], inplace=True
    )

    return df_detail[
        ["target_month", "asof_type", "model", "error_pct", "abs_error_pct"]
    ].reset_index(drop=True)


def run_build_lt_data_for_gui(
    hotel_tag: str,
    target_months: list[str],
) -> None:
    """
    Tkinter GUI から LT_DATA 生成バッチを実行するための薄いラッパー。

    現状は単一ホテル前提のため hotel_tag は将来拡張用のダミー引数だが、
    インターフェースとして受け取っておく。
    target_months には "YYYYMM" 形式の宿泊月を渡す。
    """

    if not target_months:
        return

    try:
        run_build_lt_csv.run_build_lt_for_gui(target_months)
    except Exception:
        raise


def run_full_evaluation_for_gui_range(
    hotel_tag: str,
    start_yyyymm: str,
    end_yyyymm: str,
) -> tuple[Path, Path]:
    months = generate_month_range(start_yyyymm, end_yyyymm)
    detail_path, summary_path = run_full_evaluation_for_gui(
        hotel_tag=hotel_tag,
        target_months=months,
    )
    return detail_path, summary_path

