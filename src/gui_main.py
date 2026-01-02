from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

try:
    from tkcalendar import DateEntry
except ImportError:  # tkcalendar が無い環境向けフォールバック
    DateEntry = None

# プロジェクト内モジュール
from booking_curve.config import (
    clear_local_override_raw_root_dir,
    get_local_overrides_path,
    set_local_override_raw_root_dir,
)
from booking_curve.gui_backend import (
    HOTEL_CONFIG,
    OUTPUT_DIR,
    build_calendar_for_gui,
    build_range_rebuild_plan_for_gui,
    clear_evaluation_detail_cache,
    get_all_target_months_for_lt_from_daily_snapshots,
    get_best_model_for_month,
    get_booking_curve_data,
    get_calendar_coverage,
    get_daily_forecast_table,
    get_eval_monthly_by_asof,
    get_eval_overview_by_asof,
    get_latest_asof_for_hotel,
    get_latest_asof_for_month,
    get_model_evaluation_table,
    get_monthly_curve_data,
    get_monthly_forecast_scenarios,
    run_build_lt_data_all_for_gui,
    run_build_lt_data_for_gui,
    run_daily_snapshots_for_gui,
    run_forecast_for_gui,
    run_full_evaluation_for_gui_range,
    run_import_missing_only,
    run_missing_audit_for_gui,
    run_missing_check_for_gui,
)
from booking_curve.missing_ack import (
    build_ack_key_from_row,
    filter_missing_report_with_ack,
    load_missing_ack_df,
    load_missing_ack_set,
    update_missing_ack_df,
    write_missing_ack_df,
)
from booking_curve.plot_booking_curve import LEAD_TIME_PITCHES
from build_daily_snapshots_from_folder import (
    DEFAULT_FULL_ALL_RATE,
    LOGS_DIR,
    count_excel_files,
    load_historical_full_all_rate,
)

# デフォルトホテル (現状は大国町のみ想定)
DEFAULT_HOTEL = next(iter(HOTEL_CONFIG.keys()), "daikokucho")
SETTINGS_FILE = OUTPUT_DIR / "gui_settings.json"


def open_file(path: str | Path) -> None:
    path_obj = Path(path)
    path_str = str(path_obj)
    if sys.platform.startswith("win"):
        os.startfile(path_str)  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.run(["open", path_str], check=False)
    else:
        subprocess.run(["xdg-open", path_str], check=False)


class BookingCurveApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Booking Curve Lab GUI")
        self.geometry("1200x900")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # タブ作成
        self.tab_booking_curve = ttk.Frame(self.notebook)
        self.tab_monthly_curve = ttk.Frame(self.notebook)
        self.tab_daily_forecast = ttk.Frame(self.notebook)
        self.tab_model_eval = ttk.Frame(self.notebook)
        self.tab_asof_eval = ttk.Frame(self.notebook)
        self.tab_master_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_booking_curve, text="ブッキングカーブ")
        self.notebook.add(self.tab_monthly_curve, text="月次カーブ")
        self.notebook.add(self.tab_daily_forecast, text="日別フォーキャスト")
        self.notebook.add(self.tab_model_eval, text="モデル評価")
        self.notebook.add(self.tab_asof_eval, text="ASOF比較")
        self.notebook.add(self.tab_master_settings, text="マスタ設定")

        self._settings = self._load_settings()

        general = self._settings.get("general") or {}
        initial_hotel = general.get("last_hotel")
        if initial_hotel not in HOTEL_CONFIG:
            initial_hotel = DEFAULT_HOTEL
        self.hotel_var = tk.StringVar(value=initial_hotel)
        self.hotel_var.trace_add("write", self._on_hotel_var_changed)
        self.lt_source_var = tk.StringVar(value="daily_snapshots")
        self.update_daily_snapshots_var = tk.BooleanVar(value=True)

        # モデル評価タブ用の状態変数
        self.model_eval_df: Optional[pd.DataFrame] = None
        self.model_eval_view_df: Optional[pd.DataFrame] = None
        self.model_eval_best_idx: set[int] = set()
        self.me_from_var = tk.StringVar(value="")
        self.me_to_var = tk.StringVar(value="")
        self._asof_overview_view_df: Optional[pd.DataFrame] = None
        self._asof_detail_view_df: Optional[pd.DataFrame] = None
        self._latest_asof_label_defaults: dict[tk.Label, tuple[str, str]] = {}

        self._init_daily_forecast_tab()
        self._init_model_eval_tab()
        self._init_asof_eval_tab()
        self._init_booking_curve_tab()
        self._init_monthly_curve_tab()
        self._create_master_settings_tab()
        self.hotel_var.trace_add("write", self._on_global_hotel_changed)

    def _load_settings(self) -> dict:
        try:
            if SETTINGS_FILE.exists():
                with SETTINGS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _save_settings(self) -> None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with SETTINGS_FILE.open("w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_open_output_dir(self) -> None:
        open_file(OUTPUT_DIR)

    def _get_missing_warning_ack(self, hotel_tag: str) -> str | None:
        master = self._settings.get("master_settings") or {}
        ack_map = master.get("missing_warning_ack") or {}
        if isinstance(ack_map, dict):
            value = ack_map.get(hotel_tag)
            return value if isinstance(value, str) else None
        return None

    def _set_missing_warning_ack(self, hotel_tag: str, asof_value: str) -> None:
        master = self._settings.setdefault("master_settings", {})
        ack_map = master.setdefault("missing_warning_ack", {})
        if not isinstance(ack_map, dict):
            master["missing_warning_ack"] = {}
            ack_map = master["missing_warning_ack"]
        ack_map[hotel_tag] = asof_value
        self._save_settings()

    def _get_missing_warning_sig_ack(self, hotel_tag: str) -> str | None:
        master = self._settings.get("master_settings") or {}
        ack_map = master.get("missing_warning_sig_ack") or {}
        if isinstance(ack_map, dict):
            value = ack_map.get(hotel_tag)
            return value if isinstance(value, str) else None
        return None

    def _set_missing_warning_sig_ack(self, hotel_tag: str, sig_value: str) -> None:
        master = self._settings.setdefault("master_settings", {})
        ack_map = master.setdefault("missing_warning_sig_ack", {})
        if not isinstance(ack_map, dict):
            master["missing_warning_sig_ack"] = {}
            ack_map = master["missing_warning_sig_ack"]
        ack_map[hotel_tag] = sig_value
        self._save_settings()

    def _precheck_missing_report_for_range_rebuild(
        self,
        hotel_tag: str,
        asof_min: pd.Timestamp,
        asof_max: pd.Timestamp,
    ) -> bool:
        asof_max_str = asof_max.strftime("%Y-%m-%d")

        try:
            report_path = run_missing_check_for_gui(hotel_tag)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("欠損チェック失敗", f"欠損チェックの実行に失敗しました。\n{exc}")
            return False

        try:
            df_report = pd.read_csv(report_path, dtype=str)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("欠損チェック失敗", f"欠損レポートの読み込みに失敗しました。\n{exc}")
            return False

        if df_report.empty:
            return True

        kind_series = df_report.get("kind", pd.Series([], dtype=str))
        if kind_series.empty:
            return True

        asof_max_ts = pd.Timestamp(asof_max).normalize()
        asof_min_ts = pd.Timestamp(asof_min).normalize()

        raw_missing_mask = kind_series == "raw_missing"
        raw_missing_dates = pd.to_datetime(df_report.get("asof_date"), errors="coerce").dt.normalize()
        raw_missing_count = int((raw_missing_mask & (raw_missing_dates == asof_max_ts)).sum())
        raw_missing_targets = df_report.get("target_month")
        if raw_missing_targets is None:
            raw_missing_target_months: list[str] = []
        else:
            raw_missing_target_months = sorted(
                {str(value) for value in raw_missing_targets[raw_missing_mask & (raw_missing_dates == asof_max_ts)].dropna().unique()},
            )

        asof_missing_mask = kind_series == "asof_missing"
        asof_missing_col = "missing_asof_date" if "missing_asof_date" in df_report.columns else "asof_date"
        asof_missing_dates = pd.to_datetime(df_report.get(asof_missing_col), errors="coerce").dt.normalize()
        asof_missing_count = int(
            (asof_missing_mask & asof_missing_dates.between(asof_min_ts, asof_max_ts)).sum(),
        )

        if raw_missing_dates.isna().all() and asof_missing_dates.isna().all():
            return True

        if raw_missing_count == 0 and asof_missing_count == 0:
            return True

        asof_missing_list = sorted(
            {
                date_value.strftime("%Y-%m-%d")
                for date_value in asof_missing_dates[asof_missing_mask]
                if not pd.isna(date_value) and date_value >= asof_min_ts and date_value <= asof_max_ts
            },
        )
        signature_payload = json.dumps(
            {
                "raw_missing_count": raw_missing_count,
                "raw_missing_target_months": raw_missing_target_months,
                "asof_missing_dates": asof_missing_list,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        current_sig = hashlib.sha1(signature_payload.encode("utf-8")).hexdigest()
        saved_sig = self._get_missing_warning_sig_ack(hotel_tag)
        if saved_sig == current_sig:
            return True

        message = (
            "直近レンジ内の欠損が検出されました。\n"
            f"RAW欠損(最新ASOF): {raw_missing_count} 件\n"
            f"ASOF欠損(直近レンジ): {asof_missing_count} 件\n"
            f"レポート: {report_path}\n\n"
            "続行しますか？"
        )

        proceed = messagebox.askokcancel("欠損警告", message)
        if not proceed:
            return False

        self._set_missing_warning_ack(hotel_tag, asof_max_str)
        self._set_missing_warning_sig_ack(hotel_tag, current_sig)
        return True

    def _on_hotel_var_changed(self, *args) -> None:
        """
        hotel_var が変更されたときに呼ばれるトレースコールバック。
        選択中ホテルを設定ファイル(self._settings)に保存する。
        """
        try:
            hotel_tag = self.hotel_var.get().strip()
        except Exception:
            return

        if not hotel_tag or hotel_tag not in HOTEL_CONFIG:
            return

        general = self._settings.setdefault("general", {})
        if general.get("last_hotel") != hotel_tag:
            general["last_hotel"] = hotel_tag
            self._save_settings()

    def _get_daily_caps_for_hotel(self, hotel_tag: str) -> tuple[float, float]:
        """
        Returns (forecast_cap, occ_capacity).
        """

        base_cap = float(HOTEL_CONFIG.get(hotel_tag, {}).get("capacity", 168.0))
        daily = self._settings.get("daily_forecast", {})
        fc_map = daily.get("forecast_cap", {})
        occ_map = daily.get("occ_capacity", {})
        try:
            fc = float(fc_map.get(hotel_tag, base_cap))
        except Exception:
            fc = base_cap
        try:
            occ = float(occ_map.get(hotel_tag, base_cap))
        except Exception:
            occ = base_cap
        return fc, occ

    def _set_daily_caps_for_hotel(self, hotel_tag: str, forecast_cap: float, occ_capacity: float) -> None:
        daily = self._settings.setdefault("daily_forecast", {})
        fc_map = daily.setdefault("forecast_cap", {})
        occ_map = daily.setdefault("occ_capacity", {})
        try:
            fc_map[hotel_tag] = float(forecast_cap)
            occ_map[hotel_tag] = float(occ_capacity)
        except Exception:
            return
        self._save_settings()

    def _get_best_model_stats_for_month(self, hotel: str, target_month: str) -> dict | None:
        return get_best_model_for_month(hotel, target_month)

    def _get_best_model_stats_for_recent_months(self, hotel: str, ref_month: str, window_months: int) -> dict | None:
        try:
            df = get_model_evaluation_table(hotel)
        except Exception:
            return None

        if df is None or df.empty:
            return None

        df = df.copy()
        df = df[df["target_month"] != "TOTAL"]
        df = df[df["mae_pct"].notna()]
        df = df[df["rmse_pct"].notna()]
        df = df[df["n_samples"].notna()]

        df["target_month_int"] = pd.to_numeric(df["target_month"].astype(str), errors="coerce").astype("Int64")

        latest_eval_month_int: int | None
        try:
            latest_eval_month_int = int(df["target_month_int"].dropna().max())
        except Exception:
            latest_eval_month_int = None

        today = date.today()
        y, m = today.year, today.month
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
        expected_latest_month_int = int(f"{y}{m:02d}")

        ref_int = pd.to_numeric(str(ref_month), errors="coerce")
        if pd.isna(ref_int):
            return None

        df = df[df["target_month_int"] < int(ref_int)]
        if df.empty:
            return None

        try:
            period = pd.Period(str(ref_month), freq="M")
            recent_months = [f"{(period - offset).year}{(period - offset).month:02d}" for offset in range(1, window_months + 1)]
        except Exception:
            recent_months = []
        if not recent_months:
            return None

        df = df[df["target_month"].isin(recent_months)]
        if df.empty:
            return None

        selected_months = [int(v) for v in df["target_month_int"].dropna().astype(int).unique()]

        candidates = []
        for model, g in df.groupby("model"):
            w = g["n_samples"].fillna(0)
            w_total = float(w.sum())
            if w_total <= 0:
                continue

            mean_error = (g["mean_error_pct"] * w).sum() / w_total
            mae = (g["mae_pct"] * w).sum() / w_total
            rmse = (g["rmse_pct"] * w).sum() / w_total

            has_missing_latest = False
            try:
                if latest_eval_month_int and expected_latest_month_int:
                    has_missing_latest = int(latest_eval_month_int) < int(expected_latest_month_int)
            except Exception:
                has_missing_latest = False

            candidates.append(
                {
                    "model": str(model),
                    "mean_error_pct": float(mean_error),
                    "mae_pct": float(mae),
                    "rmse_pct": float(rmse),
                    "n_samples": int(w_total),
                    "ref_month": str(ref_month),
                    "window_months": len(set(selected_months)),
                    "latest_eval_month_int": latest_eval_month_int,
                    "expected_latest_month_int": expected_latest_month_int,
                    "has_missing_latest": has_missing_latest,
                }
            )

        if not candidates:
            return None

        candidates.sort(key=lambda x: (abs(x["mae_pct"]), abs(x["rmse_pct"])))
        return candidates[0]

    def _build_best_model_label_text(
        self,
        target_month: str,
        best_month: dict | None,
        best_12: dict | None,
        best_3: dict | None,
    ) -> str:
        def _fmt_pct(v: float | None) -> str:
            try:
                return f"{float(v):.1f}%"
            except Exception:
                return "n/a"

        def _fmt_int(v: int | None) -> str:
            try:
                return str(int(v))
            except Exception:
                return "0"

        def _fmt_ym_int(v: int | None) -> str:
            try:
                s = f"{int(v):06d}"
                return f"{s[:4]}-{s[4:]}"
            except Exception:
                return ""

        def _resolve_months(v: int | None, default: int) -> int:
            try:
                iv = int(v)
                return iv if iv > 0 else default
            except Exception:
                return default

        if not (best_month or best_12 or best_3):
            return "最適モデル: 評価データなし"

        lines: list[str] = ["最適モデル（評価ベース）"]

        if best_month:
            lines.append(
                "対象月 {}: {} MAE={} RMSE={} バイアス={} n={}".format(
                    target_month,
                    best_month.get("model", ""),
                    _fmt_pct(best_month.get("mae_pct")),
                    _fmt_pct(best_month.get("rmse_pct")),
                    _fmt_pct(best_month.get("mean_error_pct")),
                    _fmt_int(best_month.get("n_samples")),
                )
            )

        if best_12:
            months_12 = _resolve_months(best_12.get("window_months"), 12)
            lines.append(
                "最近{}ヶ月: {} MAE={} RMSE={} バイアス={} n={}".format(
                    months_12,
                    best_12.get("model", ""),
                    _fmt_pct(best_12.get("mae_pct")),
                    _fmt_pct(best_12.get("rmse_pct")),
                    _fmt_pct(best_12.get("mean_error_pct")),
                    _fmt_int(best_12.get("n_samples")),
                )
            )

        if best_3:
            months_3 = _resolve_months(best_3.get("window_months"), 3)
            lines.append(
                "最近{}ヶ月: {} MAE={} RMSE={} バイアス={} n={}".format(
                    months_3,
                    best_3.get("model", ""),
                    _fmt_pct(best_3.get("mae_pct")),
                    _fmt_pct(best_3.get("rmse_pct")),
                    _fmt_pct(best_3.get("mean_error_pct")),
                    _fmt_int(best_3.get("n_samples")),
                )
            )

        info = best_12 or best_3
        if info:
            latest_eval = info.get("latest_eval_month_int") if isinstance(info, dict) else None
            expected_latest = info.get("expected_latest_month_int") if isinstance(info, dict) else None
            has_missing = bool(info.get("has_missing_latest")) if isinstance(info, dict) else False
            if has_missing and latest_eval and expected_latest:
                lines.append(f"※評価データは {_fmt_ym_int(latest_eval)} まで（最新着地月 {_fmt_ym_int(expected_latest)} は未評価）")

        return "\n".join(lines)

    def _get_current_daily_forecast_total(self) -> float | None:
        df = getattr(self, "df_daily_forecast_df", None)
        if df is None:
            return None

        if "forecast_rooms" not in df.columns:
            return None

        if "stay_date" in df.columns:
            subset = df.loc[df["stay_date"].notna(), "forecast_rooms"]
        else:
            subset = df["forecast_rooms"]

        try:
            total = float(subset.fillna(0).sum())
        except Exception:
            return None

        return total

    def _update_daily_forecast_scenario_label(
        self,
        best_3m: dict | None,
        total_forecast_rooms: float | None,
        hotel: str | None,
        target_month: str | None,
        asof_date: str | None,
    ) -> None:
        label = getattr(self, "df_scenario_label", None)
        if label is None:
            return

        if total_forecast_rooms is None or not hotel or not target_month or len(str(target_month)) != 6:
            label.configure(text="")
            return

        try:
            forecast_total = int(round(float(total_forecast_rooms)))
        except Exception:
            label.configure(text="")
            return

        scenarios = get_monthly_forecast_scenarios(
            hotel_key=hotel,
            target_month=str(target_month),
            forecast_total_rooms=forecast_total,
            asof_date_str=asof_date or None,
            best_model_stats=best_3m,
        )

        avg = scenarios.get("avg_asof")
        nearest = scenarios.get("nearest_asof")

        lines: list[str] = []

        if avg is not None:
            lines.append(
                f"ASOF平均シナリオ（月次Rooms） "
                f"悲観={avg['pessimistic']:,} / 基準={avg['base']:,} / 楽観={avg['optimistic']:,} "
                f"(Forecast={avg['forecast']:,})"
            )

        if nearest is not None:
            lines.append(
                f"近似ASOFシナリオ（月次Rooms） "
                f"悲観={nearest['pessimistic']:,} / 基準={nearest['base']:,} / 楽観={nearest['optimistic']:,} "
                f"(Forecast={nearest['forecast']:,})"
            )
        else:
            lines.append("近似ASOFシナリオ（月次Rooms） 対象データなし")

        label.configure(text="\n".join(lines))

    def _shift_month_var(self, var: tk.StringVar, delta_months: int) -> None:
        """
        var で参照されている "YYYYMM" 形式の文字列を delta_months だけ
        前後にシフトする。パースに失敗した場合はエラーダイアログ表示。
        """
        ym = var.get().strip()
        try:
            if len(ym) != 6:
                raise ValueError
            year = int(ym[:4])
            month = int(ym[4:6])
        except Exception:
            messagebox.showerror("Error", f"対象月の形式が不正です: {ym}")
            return

        # pandas Period を使って月シフトする
        p = pd.Period(f"{year:04d}-{month:02d}", freq="M")
        p_new = p + delta_months
        var.set(p_new.strftime("%Y%m"))

    def _on_df_shift_month(self, delta_months: int) -> None:
        self._shift_month_var(self.df_month_var, delta_months)
        self._update_df_latest_asof_label(False)

    def _on_bc_shift_month(self, delta_months: int) -> None:
        self._shift_month_var(self.bc_month_var, delta_months)
        self._update_bc_latest_asof_label(False)

    def _on_bc_quick_weekday(self, weekday_value: str) -> None:
        """
        ブッキングカーブタブのクイック曜日ボタン用コールバック。
        weekday_value は "0:Mon" や "5:Sat" のような文字列。
        """

        self.bc_weekday_var.set(weekday_value)
        # 曜日変更後、即座にブッキングカーブを再描画する
        self._on_draw_booking_curve()

    def _create_master_settings_tab(self) -> None:
        frame = self.tab_master_settings

        # ------- カレンダー設定 -------
        calendar_frame = ttk.LabelFrame(frame, text="カレンダー")
        calendar_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(calendar_frame, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.hotel_combo = ttk.Combobox(calendar_frame, textvariable=self.hotel_var, state="readonly")
        self.hotel_combo["values"] = sorted(HOTEL_CONFIG.keys())
        self.hotel_combo.grid(row=0, column=1, padx=4, pady=2, sticky="w")
        self.hotel_combo.bind("<<ComboboxSelected>>", self._on_hotel_changed)

        self.calendar_coverage_var = tk.StringVar()
        self.calendar_coverage_label = ttk.Label(calendar_frame, textvariable=self.calendar_coverage_var)
        self.calendar_coverage_label.grid(row=1, column=0, columnspan=3, padx=4, pady=2, sticky="w")

        self.calendar_build_button = ttk.Button(
            calendar_frame,
            text="カレンダー再生成",
            command=self._on_build_calendar_clicked,
        )
        self.calendar_build_button.grid(row=1, column=3, padx=4, pady=2, sticky="e")

        # ------- 日別FC / ブッキング共通キャパ設定 -------
        caps_frame = ttk.LabelFrame(frame, text="日別フォーキャスト / ブッキングカーブ共通設定")
        caps_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(caps_frame, text="予測キャップ:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.master_fc_cap_var = tk.StringVar()
        ttk.Entry(caps_frame, textvariable=self.master_fc_cap_var, width=8).grid(row=0, column=1, padx=4, pady=2, sticky="w")

        ttk.Label(caps_frame, text="稼働率キャパ:").grid(row=0, column=2, sticky="w", padx=12, pady=2)
        self.master_occ_cap_var = tk.StringVar()
        ttk.Entry(caps_frame, textvariable=self.master_occ_cap_var, width=8).grid(row=0, column=3, padx=4, pady=2, sticky="w")

        ttk.Button(
            caps_frame,
            text="保存（このホテルのみ）",
            command=self._on_save_master_daily_caps,
        ).grid(row=0, column=4, padx=12, pady=2, sticky="e")

        # ------- RAW取込元（このPCのみ） -------
        raw_root_frame = ttk.LabelFrame(frame, text="RAW取込元（このPCのみ）")
        raw_root_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(
            raw_root_frame,
            text="この設定はこのPCのみ有効です（hotels.jsonは変更しません）。",
        ).grid(row=0, column=0, columnspan=3, padx=4, pady=(2, 6), sticky="w")

        ttk.Label(raw_root_frame, text="現在のRAW取込元:").grid(row=1, column=0, sticky="nw", padx=4, pady=2)
        self.master_raw_root_dir_var = tk.StringVar()
        self.master_raw_root_dir_label = ttk.Label(
            raw_root_frame,
            textvariable=self.master_raw_root_dir_var,
            wraplength=800,
            justify="left",
        )
        self.master_raw_root_dir_label.grid(row=1, column=1, columnspan=2, padx=4, pady=2, sticky="w")

        ttk.Button(
            raw_root_frame,
            text="変更...",
            command=self._on_change_master_raw_root_dir,
        ).grid(row=2, column=1, padx=4, pady=4, sticky="w")
        ttk.Button(
            raw_root_frame,
            text="初期値に戻す",
            command=self._on_clear_master_raw_root_dir,
        ).grid(row=2, column=2, padx=4, pady=4, sticky="w")

        local_overrides_path = get_local_overrides_path()
        ttk.Label(
            raw_root_frame,
            text=f"ローカル設定ファイル: {local_overrides_path}",
            foreground="#555555",
            wraplength=800,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, padx=4, pady=(2, 4), sticky="w")

        output_frame = ttk.LabelFrame(frame, text="出力フォルダ")
        output_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(
            output_frame,
            text=f"出力フォルダ: {OUTPUT_DIR}",
            foreground="#555555",
            wraplength=800,
            justify="left",
        ).grid(row=0, column=0, padx=4, pady=2, sticky="w")

        ttk.Button(
            output_frame,
            text="出力フォルダを開く",
            command=self._on_open_output_dir,
        ).grid(row=0, column=1, padx=8, pady=2, sticky="w")

        advanced_frame = ttk.LabelFrame(frame, text="Advanced / Daily snapshots")
        advanced_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(
            advanced_frame,
            text="FULL_ALL は大量処理です。事前確認のうえ実行してください。",
        ).grid(row=0, column=0, columnspan=2, padx=4, pady=2, sticky="w")
        self.full_all_button = ttk.Button(
            advanced_frame,
            text="Daily snapshots 全量再生成（危険）",
            command=self._on_run_full_all_snapshots,
        )
        self.full_all_button.grid(row=1, column=0, padx=4, pady=4, sticky="w")
        self.full_all_status_var = tk.StringVar(value="")
        ttk.Label(advanced_frame, textvariable=self.full_all_status_var).grid(row=1, column=1, padx=4, pady=4, sticky="w")

        self.lt_all_button = ttk.Button(
            advanced_frame,
            text="LT_DATA 全期間生成（危険）",
            command=self._on_run_lt_all,
        )
        self.lt_all_button.grid(row=2, column=0, padx=4, pady=4, sticky="w")
        self.lt_all_status_var = tk.StringVar(value="")
        ttk.Label(advanced_frame, textvariable=self.lt_all_status_var).grid(row=2, column=1, padx=4, pady=4, sticky="w")

        ttk.Button(
            advanced_frame,
            text="欠損チェック（運用）",
            command=self._on_run_missing_check,
        ).grid(row=3, column=0, padx=4, pady=4, sticky="w")
        ttk.Button(
            advanced_frame,
            text="欠損一覧（運用）",
            command=self._on_open_missing_ops_list,
        ).grid(row=3, column=1, padx=4, pady=4, sticky="w")
        ttk.Button(
            advanced_frame,
            text="欠損監査（全期間）",
            command=self._on_run_missing_audit,
        ).grid(row=4, column=0, padx=4, pady=4, sticky="w")
        ttk.Button(
            advanced_frame,
            text="欠損だけ取り込み",
            command=self._on_run_import_missing_only,
        ).grid(row=5, column=0, padx=4, pady=4, sticky="w")

        self.master_missing_check_status_var = tk.StringVar(value="欠損検査：未実施")
        self.master_missing_check_status_label = ttk.Label(
            advanced_frame,
            textvariable=self.master_missing_check_status_var,
            foreground="#555555",
        )
        self.master_missing_check_status_label.grid(row=6, column=0, columnspan=2, padx=4, pady=(8, 4), sticky="w")

        # 初期表示
        self._refresh_calendar_coverage()
        self._refresh_master_daily_caps()
        self._refresh_master_raw_root_dir()
        self._update_master_missing_check_status()

    def _on_hotel_changed(self, event=None) -> None:
        # マスタ設定タブのホテル変更時に、カレンダー範囲とキャパ設定を両方更新
        self._refresh_calendar_coverage()
        self._refresh_master_daily_caps()
        self._refresh_master_raw_root_dir()
        self._update_master_missing_check_status()

    def _on_global_hotel_changed(self, *args) -> None:
        """
        ホテル選択がどのタブから変更されても呼ばれるグローバルハンドラ。
        - マスタ設定のカレンダー範囲 & キャパ表示を更新
        - 日別フォーキャスト / ブッキングカーブ / 月次カーブ / 評価系の表示をクリア
        - 日別FC/ブッキングのキャパと最新ASOFラベルを更新
        """

        hotel_tag = self.hotel_var.get().strip()

        self._refresh_calendar_coverage()
        self._refresh_master_daily_caps()
        self._refresh_master_raw_root_dir()
        self._update_master_missing_check_status()

        if hasattr(self, "df_hotel_var"):
            fc_cap, occ_cap = self._get_daily_caps_for_hotel(hotel_tag)
            self.df_forecast_cap_var.set(str(fc_cap))
            self.df_occ_cap_var.set(str(occ_cap))
            self._update_df_latest_asof_label(update_asof_if_empty=False)
            self._update_df_best_model_label()

            if hasattr(self, "df_tree"):
                self._reset_df_selection_state()
                for item in self.df_tree.get_children():
                    self.df_tree.delete(item)
            self.df_daily_forecast_df = None
            self.df_table_df = None

        if hasattr(self, "bc_hotel_var"):
            fc_cap, _ = self._get_daily_caps_for_hotel(hotel_tag)
            self.bc_forecast_cap_var.set(str(fc_cap))
            self._update_bc_latest_asof_label(update_asof_if_empty=False)
            self._update_bc_best_model_label()

            if hasattr(self, "bc_ax"):
                self.bc_ax.clear()
                self.bc_ax.set_axis_off()
                if hasattr(self, "bc_canvas"):
                    self.bc_canvas.draw()
            if hasattr(self, "bc_tree"):
                for item in self.bc_tree.get_children():
                    self.bc_tree.delete(item)
                self.bc_tree["columns"] = ()

        if hasattr(self, "mc_ax"):
            self.mc_ax.clear()
            self.mc_ax.set_axis_off()
            if hasattr(self, "mc_canvas"):
                self.mc_canvas.draw()

        if hasattr(self, "me_tree"):
            for item in self.me_tree.get_children():
                self.me_tree.delete(item)
        self.model_eval_df = None
        self.model_eval_view_df = None
        self.model_eval_best_idx = set()

        if hasattr(self, "asof_overview_tree"):
            for item in self.asof_overview_tree.get_children():
                self.asof_overview_tree.delete(item)
        if hasattr(self, "asof_detail_tree"):
            for item in self.asof_detail_tree.get_children():
                self.asof_detail_tree.delete(item)
        self._asof_overview_df = None
        self._asof_detail_df = None
        self._asof_overview_view_df = None
        self._asof_detail_view_df = None

    def _on_build_calendar_clicked(self) -> None:
        hotel_tag = self.hotel_var.get()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        self.calendar_build_button["state"] = "disabled"
        try:
            csv_path = build_calendar_for_gui(hotel_tag)
        except Exception as e:
            messagebox.showerror("エラー", f"カレンダー再生成に失敗しました:\n{e}")
        else:
            messagebox.showinfo("完了", f"カレンダーを再生成しました。\n{csv_path}")
            self._refresh_calendar_coverage()
        finally:
            self.calendar_build_button["state"] = "normal"

    def _refresh_calendar_coverage(self) -> None:
        if not hasattr(self, "calendar_coverage_var"):
            return

        hotel_tag = self.hotel_var.get()
        if not hotel_tag:
            self.calendar_coverage_var.set("カレンダー: ホテル未選択")
            return

        coverage = get_calendar_coverage(hotel_tag)
        min_date = coverage.get("min_date")
        max_date = coverage.get("max_date")

        if min_date is None and max_date is None:
            self.calendar_coverage_var.set("カレンダー: 未作成")
        elif min_date is None or max_date is None:
            self.calendar_coverage_var.set("カレンダー: 範囲情報を取得できませんでした")
        else:
            self.calendar_coverage_var.set(f"カレンダー: {min_date} ～ {max_date}")

    def _refresh_master_daily_caps(self) -> None:
        """マスタ設定タブのキャパシティ表示を現在のホテルに合わせて更新する。"""
        if not hasattr(self, "master_fc_cap_var"):
            return

        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            self.master_fc_cap_var.set("")
            self.master_occ_cap_var.set("")
            return

        fc_cap, occ_cap = self._get_daily_caps_for_hotel(hotel_tag)
        # 整数っぽい値は整数表示、それ以外はそのまま
        try:
            self.master_fc_cap_var.set(str(int(fc_cap)))
        except Exception:
            self.master_fc_cap_var.set(str(fc_cap))
        try:
            self.master_occ_cap_var.set(str(int(occ_cap)))
        except Exception:
            self.master_occ_cap_var.set(str(occ_cap))

    def _refresh_master_raw_root_dir(self) -> None:
        if not hasattr(self, "master_raw_root_dir_var"):
            return

        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            self.master_raw_root_dir_var.set("ホテル未選択")
            return

        cfg = HOTEL_CONFIG.get(hotel_tag, {})
        raw_root_dir = cfg.get("raw_root_dir") or cfg.get("input_dir")
        if not raw_root_dir:
            self.master_raw_root_dir_var.set("未設定")
            return

        self.master_raw_root_dir_var.set(str(raw_root_dir))

    def _on_change_master_raw_root_dir(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        selected_dir = filedialog.askdirectory(title="RAW取込元フォルダを選択")
        if not selected_dir:
            return

        try:
            set_local_override_raw_root_dir(hotel_tag, selected_dir)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"RAW取込元フォルダの変更に失敗しました。\n{exc}")
            return

        self._refresh_master_raw_root_dir()
        messagebox.showinfo("完了", "RAW取込元フォルダを更新しました（このPCのみ）。")

    def _on_clear_master_raw_root_dir(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        try:
            clear_local_override_raw_root_dir(hotel_tag)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"RAW取込元フォルダの復帰に失敗しました。\n{exc}")
            return

        self._refresh_master_raw_root_dir()
        messagebox.showinfo("完了", "RAW取込元フォルダを初期値に戻しました。")

    def _set_master_missing_check_status(self, text: str, color: str) -> None:
        self.master_missing_check_status_var.set(text)
        try:
            self.master_missing_check_status_label.configure(foreground=color)
        except Exception:
            logging.debug("欠損検査ステータスラベルの色設定に失敗しました", exc_info=True)

    def _update_master_missing_check_status(self, csv_path: str | Path | None = None) -> None:
        default_text = "欠損検査：未実施"
        default_color = "#C62828"

        if not hasattr(self, "master_missing_check_status_var"):
            return

        target_path: Path | None
        if csv_path is not None:
            target_path = Path(csv_path)
        else:
            hotel_tag = self.hotel_var.get().strip()
            target_path = OUTPUT_DIR / f"missing_report_{hotel_tag}_ops.csv" if hotel_tag else None

        if target_path is None or not target_path.exists():
            self._set_master_missing_check_status(default_text, default_color)
            return

        try:
            df = pd.read_csv(target_path, dtype=str)
        except Exception:
            self._set_master_missing_check_status("欠損検査：状態不明（CSV読込失敗）", "#EF6C00")
            return

        hotel_tag = self.hotel_var.get().strip()
        ack_set = load_missing_ack_set(hotel_tag) if hotel_tag else set()
        filtered_df = filter_missing_report_with_ack(df, ack_set)

        severity_series = filtered_df.get("severity", pd.Series([], dtype=str)).fillna("")
        error_count = int((severity_series == "ERROR").sum())
        warn_count = int((severity_series == "WARN").sum())

        try:
            last_run = datetime.fromtimestamp(target_path.stat().st_mtime)
            last_run_text = last_run.strftime("%Y-%m-%d %H:%M")
        except Exception:
            last_run_text = "不明"

        text = f"欠損検査：最終実施 {last_run_text}（ERROR:{error_count} / WARN:{warn_count}）"

        snapshots_path = OUTPUT_DIR / f"daily_snapshots_{hotel_tag}.csv" if hotel_tag else None
        needs_rerun = False
        if snapshots_path is not None and snapshots_path.exists():
            try:
                needs_rerun = snapshots_path.stat().st_mtime > target_path.stat().st_mtime
            except Exception:
                needs_rerun = False

        if needs_rerun:
            text = f"{text} 要再実施"

        if error_count > 0 or needs_rerun:
            color = "#C62828"
        elif warn_count > 0:
            color = "#EF6C00"
        else:
            color = "#2E7D32"

        self._set_master_missing_check_status(text, color)

    def _on_save_master_daily_caps(self) -> None:
        """マスタ設定タブからキャパシティを保存し、関連タブにも反映する。"""
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        fc_str = self.master_fc_cap_var.get().strip()
        occ_str = self.master_occ_cap_var.get().strip()
        try:
            fc_val = float(fc_str)
            occ_val = float(occ_str)
        except Exception:
            messagebox.showerror("エラー", "キャパシティには数値を入力してください。")
            return

        # 永続化
        self._set_daily_caps_for_hotel(hotel_tag, fc_val, occ_val)

        # 日別フォーキャストタブに反映（同じホテルを見ている場合のみ）
        if hasattr(self, "df_hotel_var") and self.df_hotel_var.get().strip() == hotel_tag:
            self.df_forecast_cap_var.set(str(fc_val))
            self.df_occ_cap_var.set(str(occ_val))

        # ブッキングカーブタブに反映（同じホテルを見ている場合のみ）
        if hasattr(self, "bc_hotel_var") and self.bc_hotel_var.get().strip() == hotel_tag:
            self.bc_forecast_cap_var.set(str(fc_val))

        messagebox.showinfo("保存完了", "キャパシティ設定を保存しました。")

    def _on_run_missing_check(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        try:
            csv_path = run_missing_check_for_gui(hotel_tag)
            self._show_stale_asof_warning(csv_path)
            open_file(csv_path)
            self._update_master_missing_check_status(csv_path)
        except Exception as e:
            logging.exception("欠損チェックに失敗しました")
            messagebox.showerror("エラー", f"欠損チェックに失敗しました:\n{e}")

    def _on_run_missing_audit(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        try:
            csv_path = run_missing_audit_for_gui(hotel_tag)
            open_file(csv_path)
            self._update_master_missing_check_status()
        except Exception as e:
            logging.exception("欠損監査に失敗しました")
            messagebox.showerror("エラー", f"欠損監査に失敗しました:\n{e}")

    def _on_run_import_missing_only(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        try:
            result = run_import_missing_only(hotel_tag)
        except ValueError as e:
            logging.exception("欠損だけ取り込みに失敗しました")
            messagebox.showerror("エラー", f"欠損だけ取り込みに失敗しました:\n{e}")
            return
        except Exception as e:  # noqa: BLE001
            logging.exception("欠損だけ取り込みに失敗しました")
            messagebox.showerror("エラー", f"欠損だけ取り込みに失敗しました:\n{e}")
            return

        processed_pairs = result.get("processed_pairs", 0)
        skipped_raw = result.get("skipped_missing_raw_pairs", 0)
        skipped_asof_missing = result.get("skipped_asof_missing_rows", 0)
        updated = len(result.get("updated_pairs", []))
        coverage_warning = result.get("coverage_warning")
        msg_lines = [
            f"処理対象ペア数: {processed_pairs}",
            f"raw欠損でスキップ: {skipped_raw}",
            f"ASOF丸抜けでスキップ: {skipped_asof_missing}",
            f"更新したペア数: {updated}",
        ]
        if isinstance(coverage_warning, (int, float)):
            msg_lines.append(f"daily snapshot coverage (WARN): {coverage_warning:.1%}")
        messagebox.showinfo("完了", "\n".join(msg_lines))

        report_path = result.get("missing_report_path")
        if report_path:
            try:
                open_file(report_path)
            except Exception:
                pass
            self._update_master_missing_check_status(report_path)
        else:
            self._update_master_missing_check_status()

    def _show_stale_asof_warning(self, csv_path: str | Path) -> None:
        try:
            df = pd.read_csv(csv_path, dtype=str)
        except Exception:
            return

        if df.empty or "kind" not in df.columns:
            return

        hotel_tag = self.hotel_var.get().strip()
        ack_set = load_missing_ack_set(hotel_tag) if hotel_tag else set()
        filtered_df = filter_missing_report_with_ack(df, ack_set)
        severity_series = filtered_df.get("severity", pd.Series([], dtype=str)).fillna("")
        error_count = int((severity_series == "ERROR").sum())
        warn_count = int((severity_series == "WARN").sum())

        if error_count == 0 and warn_count == 0:
            return

        msg_lines = ["欠損検査結果に警告があります。"]
        msg_lines.append(f"ERROR: {error_count} 件 / WARN: {warn_count} 件")
        msg_lines.append("詳細は欠損レポートをご確認ください。")
        messagebox.showwarning("警告", "\n".join(msg_lines))

    def _on_open_missing_ops_list(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        report_path = OUTPUT_DIR / f"missing_report_{hotel_tag}_ops.csv"
        if not report_path.exists():
            messagebox.showerror("エラー", "欠損レポートが見つかりません。先に欠損チェックを実行してください。")
            return

        try:
            df_report = pd.read_csv(report_path, dtype=str)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"欠損レポートの読み込みに失敗しました。\n{exc}")
            return

        if df_report.empty:
            messagebox.showinfo("欠損一覧（運用）", "欠損レポートに表示対象の行がありません。")
            return

        df_report["severity"] = df_report.get("severity", "").fillna("")
        df_report = df_report[df_report["severity"].isin(["ERROR", "WARN"])].copy()

        if df_report.empty:
            messagebox.showinfo("欠損一覧（運用）", "ERROR/WARN の欠損がありません。")
            return

        ack_df = load_missing_ack_df(hotel_tag)
        acked_keys_state = {build_ack_key_from_row(row) for _, row in ack_df.iterrows()}

        window = tk.Toplevel(self)
        window.title(f"欠損一覧（運用） - {hotel_tag}")
        window.geometry("1200x600")
        window.minsize(900, 400)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        header_frame = ttk.Frame(window)
        header_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        header_frame.columnconfigure(1, weight=1)

        header = ttk.Label(header_frame, text="ACK列をクリックして確認済みをトグルできます。")
        header.grid(row=0, column=0, sticky="w")

        hide_acked_var = tk.BooleanVar(value=True)
        hide_acked_check = ttk.Checkbutton(
            header_frame,
            text="ACK済を非表示",
            variable=hide_acked_var,
        )
        hide_acked_check.grid(row=0, column=1, sticky="e")

        columns = ["ack", "kind", "target_month", "asof_date", "severity", "path", "message"]
        headings = {
            "ack": "ACK",
            "kind": "kind",
            "target_month": "target_month",
            "asof_date": "asof_date",
            "severity": "severity",
            "path": "path",
            "message": "message",
        }

        tree_frame = ttk.Frame(window)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        tree.configure(yscrollcommand=scrollbar.set)

        for col in columns:
            tree.heading(col, text=headings.get(col, col))
            width = 60 if col == "ack" else 120
            if col in {"path", "message"}:
                width = 280 if col == "path" else 320
            tree.column(col, width=width, anchor="w")

        def safe_cell(value: object) -> str:
            if value is None or pd.isna(value):
                return ""
            return str(value)

        item_to_key: dict[str, str] = {}

        def refresh_tree() -> None:
            nonlocal item_to_key
            children = tree.get_children()
            if children:
                tree.delete(*children)
            item_to_key = {}
            for _, row in df_report.iterrows():
                ack_key = build_ack_key_from_row(row)
                if hide_acked_var.get() and ack_key in acked_keys_state:
                    continue
                ack_mark = "✓" if ack_key in acked_keys_state else ""
                values = [
                    ack_mark,
                    safe_cell(row.get("kind", "")),
                    safe_cell(row.get("target_month", "")),
                    safe_cell(row.get("asof_date", "")),
                    safe_cell(row.get("severity", "")),
                    safe_cell(row.get("path", "")),
                    safe_cell(row.get("message", "")),
                ]
                item_id = tree.insert("", "end", values=values)
                item_to_key[item_id] = ack_key

        def on_toggle_hide_acked() -> None:
            refresh_tree()

        hide_acked_check.configure(command=on_toggle_hide_acked)
        refresh_tree()

        def on_toggle_ack(event: tk.Event) -> None:
            region = tree.identify("region", event.x, event.y)
            if region != "cell":
                return
            col = tree.identify_column(event.x)
            if col != "#1":
                return
            item_id = tree.identify_row(event.y)
            if not item_id:
                return
            ack_key = item_to_key.get(item_id)
            if not ack_key:
                return
            if ack_key in acked_keys_state:
                acked_keys_state.remove(ack_key)
            else:
                acked_keys_state.add(ack_key)
            refresh_tree()

        tree.bind("<Button-1>", on_toggle_ack)

        button_frame = ttk.Frame(window)
        button_frame.grid(row=2, column=0, sticky="e", padx=8, pady=(0, 8))

        def on_save_ack() -> None:
            existing_df = load_missing_ack_df(hotel_tag)
            updated_df = update_missing_ack_df(existing_df, df_report, acked_keys_state)
            try:
                write_missing_ack_df(hotel_tag, updated_df)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("保存失敗", f"ACKの保存に失敗しました。\n{exc}")
                return

            self._update_master_missing_check_status(report_path)
            refresh_tree()
            messagebox.showinfo("保存完了", "ACKを保存しました。")

        ttk.Button(button_frame, text="保存", command=on_save_ack).pack(side=tk.RIGHT, padx=4)
        ttk.Button(button_frame, text="閉じる", command=window.destroy).pack(side=tk.RIGHT, padx=4)

    def _load_historical_lt_all_rate(self) -> float | None:
        if not LOGS_DIR.exists():
            return None

        for log_path in sorted(LOGS_DIR.glob("lt_all_*.log"), reverse=True):
            try:
                lines = log_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in reversed(lines):
                match = re.search(r"rate_months_per_sec=([0-9.]+)", line)
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue
        return None

    def _on_run_full_all_snapshots(self) -> None:
        hotel_tag = self.hotel_var.get().strip()
        if not hotel_tag:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        cfg = HOTEL_CONFIG.get(hotel_tag)
        if cfg is None:
            messagebox.showerror("エラー", f"ホテル設定が見つかりません: {hotel_tag}")
            return

        input_dir_raw = cfg.get("raw_root_dir") or cfg.get("input_dir")
        if not input_dir_raw:
            messagebox.showerror("エラー", f"入力ディレクトリが設定されていません: {hotel_tag}")
            return

        recursive = bool(cfg.get("include_subfolders", False))
        input_dir = Path(input_dir_raw)
        file_count = count_excel_files(input_dir, recursive=recursive)
        rate = load_historical_full_all_rate(LOGS_DIR) or DEFAULT_FULL_ALL_RATE
        estimate_sec = file_count / rate if rate > 0 and file_count else None
        log_file = LOGS_DIR / f"full_all_{datetime.now().strftime('%Y%m%d_%H%M')}.log"

        estimate_text = (
            f"概算時間: ~{estimate_sec:.1f} 秒 (rate {rate:.2f} files/sec)"
            if estimate_sec is not None
            else f"概算時間: 不明 (rate {rate:.2f} files/sec)"
        )

        subfolder_label = "含む" if recursive else "含まない"
        message = (
            "Daily snapshots を全量再生成します。\n"
            f"ホテル: {hotel_tag}\n"
            f"対象ファイル数: {file_count} (サブフォルダ{subfolder_label})\n"
            f"{estimate_text}\n"
            f"ログ: {log_file}"
        )

        messagebox.showinfo("FULL_ALL 事前確認", message)

        confirm = simpledialog.askstring("最終確認", '続行するには "FULL_ALL" と入力してください。')
        if confirm is None or confirm.strip().upper() != "FULL_ALL":
            messagebox.showinfo("中断", "FULL_ALL を入力しなかったため処理を中止しました。")
            return

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"ログファイルを開けませんでした。\n{exc}")
            return
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
        self.full_all_button.state(["disabled"])
        self.full_all_status_var.set("実行中...")

        threading.Thread(
            target=self._run_full_all_snapshots_async,
            args=(hotel_tag, log_file, file_handler),
            daemon=True,
        ).start()

    def _run_full_all_snapshots_async(self, hotel_tag: str, log_file: Path, file_handler: logging.Handler) -> None:
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        success = True
        error: Exception | None = None
        try:
            run_daily_snapshots_for_gui(hotel_tag=hotel_tag, mode="FULL_ALL")
        except Exception as exc:  # noqa: BLE001
            success = False
            error = exc
            logging.exception("FULL_ALL 実行中にエラーが発生しました")
        finally:
            root_logger.removeHandler(file_handler)
            try:
                file_handler.close()
            except Exception:
                logging.warning("FULL_ALL ログファイルのクローズに失敗しました", exc_info=True)

        self.after(0, lambda: self._on_full_all_complete(success, hotel_tag, log_file, error))

    def _on_full_all_complete(self, success: bool, hotel_tag: str, log_file: Path, error: Exception | None) -> None:
        self.full_all_button.state(["!disabled"])
        self.full_all_status_var.set("")
        try:
            self._update_bc_latest_asof_label(update_asof_if_empty=False)
            self._update_df_latest_asof_label(update_asof_if_empty=False)
            self._update_master_missing_check_status()
        except Exception:
            logging.warning("最新ASOF表示の更新に失敗しました", exc_info=True)

        if success:
            messagebox.showinfo("完了", f"Daily snapshots FULL_ALL が完了しました。\nログ: {log_file}")
            proceed = messagebox.askyesno("確認", "続けて全期間LT_DATA生成を実行しますか？")
            if proceed:
                self._on_run_lt_all(hotel_tag)
        else:
            messagebox.showerror(
                "エラー",
                f"FULL_ALL 実行に失敗しました。\n{error}\nログ: {log_file}",
            )

    def _on_run_lt_all(self, hotel_tag: str | None = None) -> None:
        target_hotel = hotel_tag or self.hotel_var.get().strip()
        if not target_hotel:
            messagebox.showerror("エラー", "ホテルが選択されていません。")
            return

        try:
            months = get_all_target_months_for_lt_from_daily_snapshots(target_hotel)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"全期間LT_DATA生成の対象月取得に失敗しました:\n{exc}")
            return

        if not months:
            messagebox.showerror("エラー", "対象月を取得できませんでした。daily snapshots を確認してください。")
            return

        rate = self._load_historical_lt_all_rate()
        estimate_sec = len(months) / rate if rate and rate > 0 else None
        log_file = LOGS_DIR / f"lt_all_{datetime.now().strftime('%Y%m%d_%H%M')}.log"
        estimate_text = f"概算時間: ~{estimate_sec:.1f} 秒 (rate {rate:.3f} months/sec)" if estimate_sec is not None else "概算時間: 不明"

        precheck_message = (
            "LT_DATA を全期間生成します。\n"
            f"ホテル: {target_hotel}\n"
            f"対象月数: {len(months)}\n"
            f"範囲: {months[0]}〜{months[-1]}\n"
            f"{estimate_text}\n"
            f"ログ: {log_file}"
        )
        messagebox.showinfo("LT_ALL 事前確認", precheck_message)

        confirm = simpledialog.askstring("最終確認", '続行するには "LT_ALL" と入力してください。')
        if confirm is None or confirm.strip().upper() != "LT_ALL":
            messagebox.showinfo("中断", "LT_ALL を入力しなかったため処理を中止しました。")
            return

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("エラー", f"ログファイルを開けませんでした。\n{exc}")
            return
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))

        if hasattr(self, "lt_all_button"):
            self.lt_all_button.state(["disabled"])
        if hasattr(self, "lt_all_status_var"):
            self.lt_all_status_var.set("実行中...")

        threading.Thread(
            target=self._run_lt_all_async,
            args=(target_hotel, log_file, file_handler),
            daemon=True,
        ).start()

    def _run_lt_all_async(self, hotel_tag: str, log_file: Path, file_handler: logging.Handler) -> None:
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        success = True
        error: Exception | None = None
        months: list[str] = []
        duration_sec: float | None = None
        rate: float | None = None

        start = time.monotonic()
        try:
            months = run_build_lt_data_all_for_gui(hotel_tag, source="daily_snapshots")
            duration_sec = time.monotonic() - start
            rate = (len(months) / duration_sec) if duration_sec and duration_sec > 0 else 0.0
            logging.info(
                "LT_ALL completed: months=%s duration_sec=%.3f rate_months_per_sec=%.3f",
                len(months),
                duration_sec,
                rate,
            )
        except Exception as exc:  # noqa: BLE001
            success = False
            error = exc
            logging.exception("LT_ALL 実行中にエラーが発生しました")
        finally:
            root_logger.removeHandler(file_handler)
            try:
                file_handler.close()
            except Exception:
                logging.warning("LT_ALL ログファイルのクローズに失敗しました", exc_info=True)

        self.after(
            0,
            lambda: self._on_lt_all_complete(
                success,
                hotel_tag,
                months,
                log_file,
                error,
                duration_sec,
                rate,
            ),
        )

    def _on_lt_all_complete(
        self,
        success: bool,
        hotel_tag: str,
        months: list[str],
        log_file: Path,
        error: Exception | None,
        duration_sec: float | None,
        rate: float | None,
    ) -> None:
        if hasattr(self, "lt_all_button"):
            self.lt_all_button.state(["!disabled"])
        if hasattr(self, "lt_all_status_var"):
            self.lt_all_status_var.set("")

        try:
            self._update_bc_latest_asof_label(update_asof_if_empty=False)
            self._update_df_latest_asof_label(update_asof_if_empty=False)
        except Exception:
            logging.warning("最新ASOF表示の更新に失敗しました", exc_info=True)

        if success:
            range_text = f"{months[0]}〜{months[-1]}" if months else "N/A"
            extra = ""
            if duration_sec is not None and rate is not None:
                extra = f"\n所要時間: {duration_sec:.1f} 秒 (rate {rate:.3f} months/sec)"
            messagebox.showinfo(
                "完了",
                f"LT_DATA 全期間生成が完了しました。\nホテル: {hotel_tag}\n対象月: {range_text} ({len(months)}ヶ月)\nログ: {log_file}{extra}",
            )
        else:
            messagebox.showerror(
                "エラー",
                f"LT_DATA 全期間生成に失敗しました。\n{error}\nログ: {log_file}",
            )

    # =========================
    # 3) 日別フォーキャスト一覧タブ
    # =========================
    def _init_daily_forecast_tab(self) -> None:
        frame = self.tab_daily_forecast

        # 上部入力フォーム
        form = ttk.Frame(frame)
        form.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        # ホテル
        ttk.Label(form, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.df_hotel_var = self.hotel_var
        hotel_combo = ttk.Combobox(form, textvariable=self.df_hotel_var, state="readonly")
        hotel_combo["values"] = sorted(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)
        hotel_combo.bind("<<ComboboxSelected>>", self._on_df_hotel_changed)

        # 対象月
        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.df_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.df_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        # as_of
        ttk.Label(form, text="AS OF (YYYY-MM-DD):").grid(row=0, column=4, sticky="w")
        self.df_asof_var = tk.StringVar(value="")
        if DateEntry is not None:
            self.df_asof_entry = DateEntry(
                form,
                textvariable=self.df_asof_var,
                date_pattern="yyyy-mm-dd",
                width=12,
            )
        else:
            self.df_asof_entry = ttk.Entry(
                form,
                textvariable=self.df_asof_var,
                width=12,
            )
        self.df_asof_entry.grid(row=0, column=5, padx=4, pady=2)

        self.df_latest_asof_var = tk.StringVar(value="")
        ttk.Label(form, text="最新ASOF:").grid(row=0, column=6, sticky="w")
        self.df_latest_asof_label = tk.Label(form, textvariable=self.df_latest_asof_var, width=12, anchor="w")
        self._latest_asof_label_defaults[self.df_latest_asof_label] = (
            self.df_latest_asof_label.cget("background"),
            self.df_latest_asof_label.cget("foreground"),
        )
        self.df_latest_asof_label.grid(row=0, column=7, padx=4, pady=2, sticky="w")
        ttk.Button(form, text="最新に反映", command=self._on_df_set_asof_to_latest).grid(row=0, column=8, padx=4, pady=2, sticky="w")

        # モデル
        ttk.Label(form, text="モデル:").grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.df_model_var = tk.StringVar(value="recent90w")
        model_combo = ttk.Combobox(
            form,
            textvariable=self.df_model_var,
            state="readonly",
            width=14,
        )
        model_combo["values"] = [
            "avg",
            "recent90",
            "recent90_adj",
            "recent90w",
            "recent90w_adj",
        ]
        model_combo.grid(row=1, column=1, padx=4, pady=(4, 2))

        # 予測キャップ / 稼働率キャパ
        # 現在選択されているホテルのキャパを取得
        current_hotel = self.hotel_var.get().strip() or DEFAULT_HOTEL
        fc_cap, occ_cap = self._get_daily_caps_for_hotel(current_hotel)

        ttk.Label(form, text="予測キャップ:").grid(row=1, column=2, sticky="w")
        self.df_forecast_cap_var = tk.StringVar(value=str(fc_cap))
        ttk.Entry(form, textvariable=self.df_forecast_cap_var, width=6).grid(row=1, column=3, padx=4, pady=2)

        nav_frame = ttk.Frame(form)
        nav_frame.grid(row=2, column=2, columnspan=6, sticky="w", pady=(4, 0))

        ttk.Label(nav_frame, text="月移動:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            nav_frame,
            text="-1Y",
            command=lambda: self._on_df_shift_month(-12),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="-1M",
            command=lambda: self._on_df_shift_month(-1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1M",
            command=lambda: self._on_df_shift_month(+1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1Y",
            command=lambda: self._on_df_shift_month(+12),
        ).pack(side=tk.LEFT, padx=2)

        # 実行ボタン
        forecast_btn = ttk.Button(
            form,
            text="Forecast実行",
            command=self._on_run_daily_forecast,
        )
        forecast_btn.grid(row=1, column=4, padx=4, pady=2, sticky="e")
        export_btn = ttk.Button(form, text="CSV出力", command=self._on_export_daily_forecast_csv)
        export_btn.grid(row=1, column=5, padx=4, pady=2, sticky="e")
        ttk.Label(form, text="稼働率キャパ:").grid(row=1, column=6, sticky="w")
        self.df_occ_cap_var = tk.StringVar(value=str(occ_cap))
        ttk.Entry(form, textvariable=self.df_occ_cap_var, width=6).grid(row=1, column=7, padx=4, pady=2)

        # テーブル用コンテナ
        table_container = ttk.Frame(frame)
        table_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        columns = [
            "stay_date",
            "weekday",
            "actual_rooms",
            "asof_oh_rooms",
            "forecast_rooms",
            "diff_rooms_vs_actual",
            "diff_pct_vs_actual",
            "pickup_expected_from_asof",
            "diff_rooms",
            "diff_pct",
            "occ_actual_pct",
            "occ_asof_pct",
            "occ_forecast_pct",
        ]

        self.df_tree = ttk.Treeview(table_container, columns=columns, show="headings", height=25)
        for col in columns:
            header = col
            if col == "stay_date":
                width = 100
                anchor = "center"
            elif col == "weekday":
                width = 70
                anchor = "center"
            elif col in (
                "actual_rooms",
                "asof_oh_rooms",
                "forecast_rooms",
                "diff_rooms_vs_actual",
                "pickup_expected_from_asof",
                "diff_rooms",
            ):
                width = 90
                anchor = "e"
            elif col in (
                "diff_pct_vs_actual",
                "diff_pct",
                "occ_actual_pct",
                "occ_asof_pct",
                "occ_forecast_pct",
            ):
                width = 90
                anchor = "e"
            else:
                width = 90
                anchor = "e"

            self.df_tree.heading(col, text=header)
            self.df_tree.column(col, width=width, anchor=anchor)

        self.df_tree.tag_configure("oddrow", background="#F7F7F7")

        # スクロールバー
        yscroll = ttk.Scrollbar(table_container, orient="vertical", command=self.df_tree.yview)
        self.df_tree.configure(yscrollcommand=yscroll.set)

        self.df_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        table_container.rowconfigure(0, weight=1)
        table_container.columnconfigure(0, weight=1)

        df_label_frame = ttk.Frame(frame)
        df_label_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))
        df_label_frame.grid_columnconfigure(0, weight=1)
        df_label_frame.grid_columnconfigure(1, weight=1)

        self.df_best_model_label = ttk.Label(
            df_label_frame,
            text="最適モデル: 評価データなし",
            anchor="w",
            justify="left",
        )
        self.df_best_model_label.grid(row=0, column=0, sticky="w")

        self.df_scenario_label = ttk.Label(
            df_label_frame,
            text="",
            anchor="e",
            justify="right",
        )
        self.df_scenario_label.grid(row=0, column=1, sticky="e")

        # セル選択状態
        self._df_cell_anchor = None
        self._df_cell_end = None

        # クリック / Shift+クリック / コピー
        self.df_tree.bind("<Button-1>", self._on_df_tree_click, add="+")
        self.df_tree.bind("<Shift-Button-1>", self._on_df_tree_shift_click, add="+")
        self.df_tree.bind("<Control-c>", self._on_df_tree_copy, add="+")

        self._update_df_latest_asof_label(update_asof_if_empty=True)

    def _apply_latest_asof_freshness(self, label: tk.Label, latest_asof_str: str) -> None:
        default_bg, default_fg = self._latest_asof_label_defaults.get(
            label,
            (label.cget("background"), label.cget("foreground")),
        )
        try:
            latest_date = datetime.strptime(latest_asof_str, "%Y-%m-%d").date()
        except Exception:
            label.configure(background=default_bg, foreground=default_fg)
            return

        age_days = (date.today() - latest_date).days
        if age_days <= 0:
            bg, fg = default_bg, default_fg
        elif age_days == 1:
            bg, fg = "yellow", "black"
        else:
            bg, fg = "red", "white"

        label.configure(background=bg, foreground=fg)

    def _update_df_latest_asof_label(self, update_asof_if_empty: bool = False) -> None:
        hotel = self.df_hotel_var.get().strip()
        try:
            latest = get_latest_asof_for_hotel(hotel)
        except Exception:
            self.df_latest_asof_var.set("(未取得)")
            self._apply_latest_asof_freshness(self.df_latest_asof_label, self.df_latest_asof_var.get())
            return

        if latest is None:
            self.df_latest_asof_var.set("なし")
        else:
            self.df_latest_asof_var.set(latest)

            if update_asof_if_empty:
                today_str = date.today().strftime("%Y-%m-%d")
                current = self.df_asof_var.get().strip()
                # 起動直後は DateEntry が今日を入れてしまうので、
                # 「空 or 今日」の場合だけ最新ASOFで上書きする
                if (not current) or (current == today_str):
                    self.df_asof_var.set(latest)

        self._apply_latest_asof_freshness(self.df_latest_asof_label, self.df_latest_asof_var.get())
        self._update_df_best_model_label()

    def _update_df_best_model_label(self) -> None:
        hotel = (self.df_hotel_var.get() or "").strip() or DEFAULT_HOTEL
        month = (self.df_month_var.get() or "").strip()

        if len(month) != 6 or not month.isdigit():
            self.df_best_model_label.config(text="最適モデル: 対象月が未設定です")
            self._update_daily_forecast_scenario_label(None, None, hotel, month, self.df_asof_var.get().strip())
            return

        best_month = self._get_best_model_stats_for_month(hotel, month)
        best_12 = self._get_best_model_stats_for_recent_months(hotel, month, 12)
        best_3 = self._get_best_model_stats_for_recent_months(hotel, month, 3)

        text = self._build_best_model_label_text(month, best_month, best_12, best_3)
        self.df_best_model_label.config(text=text)

        total_forecast_rooms = self._get_current_daily_forecast_total()
        self._update_daily_forecast_scenario_label(best_3, total_forecast_rooms, hotel, month, self.df_asof_var.get().strip())

    def _on_df_set_asof_to_latest(self) -> None:
        latest = self.df_latest_asof_var.get().strip()
        if latest and latest not in ("なし", "(未取得)"):
            self.df_asof_var.set(latest)

    def _update_bc_latest_asof_label(self, update_asof_if_empty: bool = False) -> None:
        hotel = self.bc_hotel_var.get().strip()
        try:
            latest = get_latest_asof_for_hotel(hotel)
        except Exception:
            self.bc_latest_asof_var.set("(未取得)")
            self._apply_latest_asof_freshness(self.bc_latest_asof_label, self.bc_latest_asof_var.get())
            return

        if latest is None:
            self.bc_latest_asof_var.set("なし")
        else:
            self.bc_latest_asof_var.set(latest)

            if update_asof_if_empty:
                today_str = date.today().strftime("%Y-%m-%d")
                current = self.bc_asof_var.get().strip()
                # 起動直後は DateEntry が今日を入れてしまうので、
                # 「空 or 今日」の場合だけ最新ASOFで上書きする
                if (not current) or (current == today_str):
                    self.bc_asof_var.set(latest)

        self._apply_latest_asof_freshness(self.bc_latest_asof_label, self.bc_latest_asof_var.get())
        self._update_bc_best_model_label()

    def _update_bc_best_model_label(self) -> None:
        hotel = (self.bc_hotel_var.get() or "").strip() or DEFAULT_HOTEL
        month = (self.bc_month_var.get() or "").strip()

        if len(month) != 6 or not month.isdigit():
            self.bc_best_model_label.config(text="最適モデル: 対象月が未設定です")
            return

        best_month = self._get_best_model_stats_for_month(hotel, month)
        best_12 = self._get_best_model_stats_for_recent_months(hotel, month, 12)
        best_3 = self._get_best_model_stats_for_recent_months(hotel, month, 3)

        text = self._build_best_model_label_text(month, best_month, best_12, best_3)
        self.bc_best_model_label.config(text=text)

    def _on_bc_hotel_changed(self, event=None) -> None:
        hotel = self.bc_hotel_var.get().strip()
        fc_cap, _ = self._get_daily_caps_for_hotel(hotel)
        self.bc_forecast_cap_var.set(str(fc_cap))
        self._update_bc_latest_asof_label(False)

    def _on_bc_set_asof_to_latest(self) -> None:
        latest = self.bc_latest_asof_var.get().strip()
        if latest and latest not in ("なし", "(未取得)"):
            self.bc_asof_var.set(latest)

    def _on_run_daily_forecast(self) -> None:
        """現在の設定で Forecast を実行し、テーブルを再読み込みする。"""

        hotel = self.df_hotel_var.get()
        month = self.df_month_var.get()
        asof = self.df_asof_var.get()
        model = self.df_model_var.get()
        fc_cap_str = self.df_forecast_cap_var.get().strip()
        occ_cap_str = self.df_occ_cap_var.get().strip()

        if not month:
            messagebox.showerror("エラー", "対象月(YYYYMM)を入力してください。")
            return

        if not fc_cap_str or not occ_cap_str:
            messagebox.showerror("エラー", "予測キャップと稼働率キャパを入力してください。")
            return

        try:
            forecast_cap = float(fc_cap_str)
            occ_capacity = float(occ_cap_str)
        except Exception:
            messagebox.showerror("エラー", "キャパシティには数値を入力してください。")
            return

        # ASOF 日付の簡易検証
        try:
            asof_ts = pd.to_datetime(asof)
        except Exception:
            messagebox.showerror("エラー", f"AS OF 日付の形式が不正です: {asof}")
            return

        latest = self.df_latest_asof_var.get().strip()
        if latest and latest not in ("なし", "(未取得)"):
            try:
                latest_ts = pd.to_datetime(latest)
            except Exception:
                latest_ts = None

            if latest_ts is not None and asof_ts > latest_ts:
                messagebox.showerror(
                    "エラー",
                    f"AS OF が最新データ ({latest}) を超えています。\n{latest} 以前の日付を指定してください。",
                )
                return

        # 現時点では「1ヶ月のみ」実行。将来的に複数月対応する場合は
        # ここで month 周辺のリストを組み立てて渡す。
        target_months = [month]

        try:
            run_forecast_for_gui(
                hotel_tag=hotel,
                target_months=target_months,
                as_of_date=asof,
                gui_model=model,
                capacity=forecast_cap,
            )
        except FileNotFoundError as e:
            messagebox.showerror("エラー", f"Forecast実行に必要な LT_DATA が見つかりません:\n{e}")
            return
        except Exception as e:
            messagebox.showerror("エラー", f"Forecast実行に失敗しました:\n{e}")
            return

        try:
            df = get_daily_forecast_table(
                hotel_tag=hotel,
                target_month=month,
                as_of_date=asof,
                gui_model=model,
                capacity=occ_capacity,
            )

            self._set_daily_caps_for_hotel(hotel, forecast_cap, occ_capacity)
        except Exception as e:
            self.df_daily_forecast_df = None
            messagebox.showerror("エラー", f"日別フォーキャスト読み込みに失敗しました:\n{e}")
            return

        self._reset_df_selection_state()

        # 既存行クリア
        for row_id in self.df_tree.get_children():
            self.df_tree.delete(row_id)

        # DataFrame を Treeview に流し込む
        for idx, (_, row) in enumerate(df.iterrows()):
            # TOTAL 行は stay_date が NaT なので、表示用に "TOTAL" とする
            stay_date = row["stay_date"]
            if pd.isna(stay_date):
                stay_str = "TOTAL"
            else:
                stay_str = pd.to_datetime(stay_date).strftime("%Y-%m-%d")

            weekday = row["weekday"]
            if isinstance(weekday, (int, float)) and not pd.isna(weekday) and 0 <= int(weekday) <= 6:
                weekday_idx = int(weekday)
                weekday_str = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][weekday_idx]
            else:
                weekday_str = str(weekday)

            values = [
                stay_str,
                weekday_str,
                _fmt_num(row.get("actual_rooms")),
                _fmt_num(row.get("asof_oh_rooms")),
                _fmt_num(row.get("forecast_rooms")),
                _fmt_num(row.get("diff_rooms_vs_actual")),
                _fmt_pct(row.get("diff_pct_vs_actual")),
                _fmt_num(row.get("pickup_expected_from_asof")),
                _fmt_num(row.get("diff_rooms")),
                _fmt_pct(row.get("diff_pct")),
                _fmt_pct(row.get("occ_actual_pct")),
                _fmt_pct(row.get("occ_asof_pct")),
                _fmt_pct(row.get("occ_forecast_pct")),
            ]
            tags: tuple[str, ...] = ()
            if idx % 2 == 1:
                tags = ("oddrow",)

            self.df_tree.insert("", tk.END, values=values, tags=tags)

        self.df_daily_forecast_df = df
        self.df_table_df = df

        self._update_df_best_model_label()

    def _df_get_row_col_index(self, row_id: str, col_id: str) -> tuple[int, int]:
        """row_id と '#n' 形式の col_id から (row_index, col_index) を返す。"""
        rows = self.df_tree.get_children("")
        try:
            r_idx = rows.index(row_id)
        except ValueError:
            r_idx = -1
        try:
            c_idx = int(col_id.replace("#", "")) - 1
        except Exception:
            c_idx = -1
        return r_idx, c_idx

    def _on_df_tree_click(self, event) -> None:
        if not hasattr(self, "df_tree"):
            return

        region = self.df_tree.identify("region", event.x, event.y)
        if region != "cell":
            self._df_cell_anchor = None
            self._df_cell_end = None
            self._clear_df_selection_rect()
            return

        row_id = self.df_tree.identify_row(event.y)
        col_id = self.df_tree.identify_column(event.x)  # "#1", "#2", ...
        if not row_id or not col_id:
            self._df_cell_anchor = None
            self._df_cell_end = None
            self._clear_df_selection_rect()
            return

        self.df_tree.focus(row_id)
        self.df_tree.selection_set(row_id)

        self._df_cell_anchor = (row_id, col_id)
        self._df_cell_end = (row_id, col_id)
        self._draw_df_selection_rect()

    def _on_df_tree_shift_click(self, event) -> None:
        if not hasattr(self, "df_tree"):
            return

        region = self.df_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.df_tree.identify_row(event.y)
        col_id = self.df_tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        if self._df_cell_anchor is None:
            self._df_cell_anchor = (row_id, col_id)
        self._df_cell_end = (row_id, col_id)

        rows = list(self.df_tree.get_children(""))
        a_r, _ = self._df_get_row_col_index(*self._df_cell_anchor)
        e_r, _ = self._df_get_row_col_index(row_id, col_id)
        if a_r >= 0 and e_r >= 0:
            lo = min(a_r, e_r)
            hi = max(a_r, e_r)
            sel_rows = rows[lo : hi + 1]
            self.df_tree.selection_set(sel_rows)
            if sel_rows:
                self.df_tree.focus(sel_rows[-1])

        self._draw_df_selection_rect()

    def _clear_df_selection_rect(self) -> None:
        """セル選択の描画をクリアする（Canvasなし版: 何もしない）。"""
        return

    def _draw_df_selection_rect(self) -> None:
        """セル選択の描画を行う（Canvasなし版: 何もしない）。"""
        return

    def _redraw_df_selection(self, event=None) -> None:
        """リサイズ時の再描画フック（Canvasなし版: 何もしない）。"""
        return

    def _reset_df_selection_state(self) -> None:
        self._df_cell_anchor = None
        self._df_cell_end = None
        self._clear_df_selection_rect()
        if hasattr(self, "df_tree"):
            self.df_tree.focus("")
            selection = self.df_tree.selection()
            if selection:
                self.df_tree.selection_remove(selection)

    def _on_df_tree_copy(self, event=None) -> None:
        """選択セル範囲をTSV形式でクリップボードにコピーする。"""
        if self._df_cell_anchor is None or self._df_cell_end is None:
            return
        if not hasattr(self, "df_tree"):
            return

        anchor_row, anchor_col = self._df_cell_anchor
        end_row, end_col = self._df_cell_end
        if not anchor_row or not anchor_col or not end_row or not end_col:
            return
        if not self.df_tree.exists(anchor_row) or not self.df_tree.exists(end_row):
            return

        rows = list(self.df_tree.get_children(""))
        if not rows:
            return

        a_r, a_c = self._df_get_row_col_index(anchor_row, anchor_col)
        e_r, e_c = self._df_get_row_col_index(end_row, end_col)
        if a_r < 0 or e_r < 0 or a_c < 0 or e_c < 0:
            return

        r_lo, r_hi = sorted((a_r, e_r))
        c_lo, c_hi = sorted((a_c, e_c))
        columns = list(self.df_tree["columns"])
        if not columns:
            return

        lines: list[str] = []
        for r_idx in range(r_lo, r_hi + 1):
            row_id = rows[r_idx]
            if not self.df_tree.exists(row_id):
                continue
            row_values = []
            for c_idx in range(c_lo, c_hi + 1):
                if not (0 <= c_idx < len(columns)):
                    continue
                col_name = columns[c_idx]
                v = self.df_tree.set(row_id, col_name)
                row_values.append("" if v is None else str(v))
            lines.append("\t".join(row_values))

        text = "\n".join(lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def _on_df_hotel_changed(self, event=None) -> None:
        hotel = self.df_hotel_var.get().strip()
        fc_cap, occ_cap = self._get_daily_caps_for_hotel(hotel)
        self.df_forecast_cap_var.set(str(fc_cap))
        self.df_occ_cap_var.set(str(occ_cap))

        self._update_df_latest_asof_label(False)

    def _on_export_daily_forecast_csv(self) -> None:
        df = getattr(self, "df_daily_forecast_df", None)
        if df is None or df.empty:
            messagebox.showerror("エラー", "先にForecast実行をしてください。")
            return

        columns = list(self.df_tree["columns"])
        tree_rows = [self.df_tree.item(row_id, "values") for row_id in self.df_tree.get_children("")]
        df_export = pd.DataFrame(tree_rows, columns=columns)

        hotel = self.df_hotel_var.get().strip()
        month = self.df_month_var.get().strip()
        asof = self.df_asof_var.get().strip()
        model = self.df_model_var.get().strip()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"daily_forecast_{hotel}_{month}_{model}_asof_{asof.replace('-', '')}.csv"

        try:
            df_export.to_csv(out_path, index=False)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"CSV を保存しました:\n{out_path}")

    def _get_last_month_int(self) -> int:
        today = date.today()
        y, m = today.year, today.month
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
        return int(f"{y}{m:02d}")

    def _shift_yyyymm_int(self, ym_int: int, delta_months: int) -> int:
        s = f"{ym_int:06d}"
        y = int(s[:4])
        m = int(s[4:])
        total = y * 12 + (m - 1) + delta_months
        y2 = total // 12
        m2 = total % 12 + 1
        return int(f"{y2}{m2:02d}")

    def _on_me_prev_month_clicked(self) -> None:
        last = self._get_last_month_int()
        self.me_from_var.set(f"{last:06d}")
        self.me_to_var.set(f"{last:06d}")
        self._refresh_model_eval_table()

    def _on_me_last3_clicked(self) -> None:
        last = self._get_last_month_int()
        start = self._shift_yyyymm_int(last, -2)
        self.me_from_var.set(f"{start:06d}")
        self.me_to_var.set(f"{last:06d}")
        self._refresh_model_eval_table()

    # =========================
    # 4) モデル評価タブ
    # =========================
    def _init_model_eval_tab(self) -> None:
        frame = self.tab_model_eval

        top = ttk.Frame(frame)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(top, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.me_hotel_var = self.hotel_var
        hotel_combo = ttk.Combobox(top, textvariable=self.me_hotel_var, state="readonly")
        hotel_combo["values"] = sorted(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)

        run_btn = ttk.Button(top, text="評価読み込み", command=self._on_load_model_eval)
        run_btn.grid(row=0, column=2, padx=4, pady=2)

        ttk.Label(top, text="開始月(YYYYMM):").grid(row=0, column=3, sticky="w", padx=(8, 4))
        ttk.Entry(top, textvariable=self.me_from_var, width=8).grid(row=0, column=4, padx=4, pady=2)

        ttk.Label(top, text="終了月(YYYYMM):").grid(row=0, column=5, sticky="w", padx=(8, 4))
        ttk.Entry(top, textvariable=self.me_to_var, width=8).grid(row=0, column=6, padx=4, pady=2)

        ttk.Button(top, text="前月", command=self._on_me_prev_month_clicked).grid(row=0, column=7, padx=4, pady=2)
        ttk.Button(top, text="直近3ヶ月", command=self._on_me_last3_clicked).grid(row=0, column=8, padx=4, pady=2)
        ttk.Button(top, text="直近12ヶ月", command=self._on_me_last12_clicked).grid(row=0, column=9, padx=4, pady=2)
        ttk.Button(top, text="CSV出力", command=self._on_export_model_eval_csv).grid(row=0, column=10, padx=4, pady=2)
        ttk.Button(top, text="評価再計算", command=self._on_rebuild_evaluation_csv).grid(row=0, column=11, padx=4, pady=2)

        columns = [
            "target_month",
            "model",
            "mean_error_pct",
            "mae_pct",
            "rmse_pct",
            "n_samples",
        ]
        self.me_tree = ttk.Treeview(frame, columns=columns, show="headings", height=25)
        for col in columns:
            self.me_tree.heading(col, text=col)
        self.me_tree.column("target_month", width=100, anchor="center")
        self.me_tree.column("model", width=120, anchor="center")
        self.me_tree.column("mean_error_pct", width=90, anchor="e")
        self.me_tree.column("mae_pct", width=90, anchor="e")
        self.me_tree.column("rmse_pct", width=90, anchor="e")
        self.me_tree.column("n_samples", width=80, anchor="e")
        self.me_tree.tag_configure("me_even", background="#ffffff")
        self.me_tree.tag_configure("me_odd", background="#f5f5f5")
        self.me_tree.tag_configure("me_total", background="#fff4d8")
        self.me_tree.tag_configure("me_best", background="#e0f2ff")
        self.me_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.me_tree.yview)
        self.me_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_rebuild_evaluation_csv(self) -> None:
        """
        選択中ホテルと期間From/To(YYYYMM)に基づいて評価CSVを再作成する。
        """

        hotel = (self.me_hotel_var.get() or "").strip()
        if not hotel:
            hotel = DEFAULT_HOTEL

        start = (self.me_from_var.get() or "").strip()
        end = (self.me_to_var.get() or "").strip()

        if not start or not end:
            messagebox.showerror(
                "エラー",
                "評価CSVを再計算するには、開始月と終了月(YYYYMM)を指定するか、\n"
                "前月／直近3ヶ月／直近12ヶ月ボタンのいずれかで期間を設定してください。",
            )
            return

        try:
            detail_path, summary_path = run_full_evaluation_for_gui_range(
                hotel_tag=hotel,
                start_yyyymm=start,
                end_yyyymm=end,
            )
        except ValueError as e:
            messagebox.showerror("エラー", f"期間指定が不正です:\n{e}")
            return
        except Exception as e:
            messagebox.showerror("エラー", f"評価CSVの再計算に失敗しました:\n{e}")
            return

        clear_evaluation_detail_cache(hotel)

        try:
            self._on_load_model_eval()
        except Exception:
            pass

        try:
            if getattr(self, "asof_hotel_var", None) is not None:
                asof_hotel = (self.asof_hotel_var.get() or "").strip() or DEFAULT_HOTEL
                if asof_hotel == hotel:
                    self._on_load_asof_eval()
        except Exception:
            pass

        # 日別フォーキャストタブの最適モデル・シナリオを最新化
        try:
            self._update_df_best_model_label()
        except Exception:
            pass

        # ブッキングカーブタブの最適モデルラベルを最新化
        try:
            self._update_bc_best_model_label()
        except Exception:
            pass

        messagebox.showinfo(
            "完了",
            f"評価CSVを再計算しました。\nDetail:  {detail_path}\nSummary: {summary_path}",
        )

    def _on_load_model_eval(self) -> None:
        hotel = (self.me_hotel_var.get() or "").strip() or DEFAULT_HOTEL
        try:
            df = get_model_evaluation_table(hotel)
        except FileNotFoundError:
            self.model_eval_df = None
            self.model_eval_best_idx = set()
            self._refresh_model_eval_table()
            messagebox.showinfo(
                "情報",
                "このホテルのモデル評価CSVが見つかりません。\n必要に応じて「評価再計算」を実行してください。",
            )
            return
        except Exception as e:
            messagebox.showerror("エラー", f"モデル評価読み込みに失敗しました:\n{e}")
            return

        best_idx = set()
        tmp = df[df["target_month"] != "TOTAL"].dropna(subset=["mae_pct"])
        for _, grp in tmp.groupby("target_month", sort=False):
            row = grp.loc[grp["mae_pct"].idxmin()]
            best_idx.add(row.name)
        self.model_eval_df = df
        self.model_eval_best_idx = best_idx

        self._refresh_model_eval_table()

    def _refresh_model_eval_table(self) -> None:
        if self.model_eval_df is None or self.model_eval_df.empty:
            self.model_eval_view_df = None
            for row_id in self.me_tree.get_children():
                self.me_tree.delete(row_id)
            return

        df = self.model_eval_df.copy()
        from_str = self.me_from_var.get().strip()
        to_str = self.me_to_var.get().strip()

        df_total = df[df["target_month"] == "TOTAL"]
        df_body = df[df["target_month"] != "TOTAL"].copy()

        def _to_int_ym(val):
            try:
                return int(val)
            except Exception:
                return None

        df_body["target_month_int"] = df_body["target_month"].map(_to_int_ym)
        df_body = df_body[~df_body["target_month_int"].isna()]

        try:
            if from_str:
                from_int = int(from_str)
                df_body = df_body[df_body["target_month_int"] >= from_int]
            if to_str:
                to_int = int(to_str)
                df_body = df_body[df_body["target_month_int"] <= to_int]
        except Exception:
            messagebox.showerror("エラー", "開始月/終了月はYYYYMMの整数で指定してください。")
            return

        df_body = df_body.drop(columns=["target_month_int"], errors="ignore")
        df_view = pd.concat([df_body, df_total], ignore_index=False)

        best_idx = set()
        tmp = df_body.dropna(subset=["mae_pct"])
        for _, grp in tmp.groupby("target_month", sort=False):
            row = grp.loc[grp["mae_pct"].idxmin()]
            best_idx.add(row.name)

        self.model_eval_view_df = df_view.copy()

        for row_id in self.me_tree.get_children():
            self.me_tree.delete(row_id)

        for i, (idx, row) in enumerate(df_view.iterrows()):
            n_raw = row.get("n_samples")
            try:
                if pd.isna(n_raw):
                    n_str = ""
                else:
                    n_str = str(int(n_raw))
            except Exception:
                n_str = ""

            values = [
                str(row.get("target_month")),
                str(row.get("model")),
                _fmt_pct(row.get("mean_error_pct")),
                _fmt_pct(row.get("mae_pct")),
                _fmt_pct(row.get("rmse_pct")),
                n_str,
            ]
            tags = ["me_even" if i % 2 == 0 else "me_odd"]
            if str(row.get("target_month")) == "TOTAL":
                tags.append("me_total")
            if idx in best_idx:
                tags.append("me_best")
            self.me_tree.insert("", tk.END, values=values, tags=tags)

    def _on_export_model_eval_csv(self) -> None:
        """
        モデル評価タブで現在表示中の内容を CSV 出力する。
        """

        df = getattr(self, "model_eval_view_df", None)
        if df is None or df.empty:
            messagebox.showerror("エラー", "先に評価を読み込んでください。")
            return

        hotel = self.me_hotel_var.get().strip() if hasattr(self, "me_hotel_var") else ""
        from_ym = self.me_from_var.get().strip() if hasattr(self, "me_from_var") else ""
        to_ym = self.me_to_var.get().strip() if hasattr(self, "me_to_var") else ""

        if not hotel:
            hotel = "unknown"
        if not from_ym:
            from_ym = "ALL"
        if not to_ym:
            to_ym = "ALL"

        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"model_eval_{hotel}_{from_ym}_{to_ym}.csv"
            out_path = OUTPUT_DIR / filename
            df.to_csv(out_path, index=False)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"CSV を保存しました。\n{out_path}")

    def _on_me_last12_clicked(self) -> None:
        last = self._get_last_month_int()
        start = self._shift_yyyymm_int(last, -11)
        self.me_from_var.set(f"{start:06d}")
        self.me_to_var.set(f"{last:06d}")

        self._refresh_model_eval_table()

    # =========================
    # 5) ASOF比較タブ
    # =========================
    def _init_asof_eval_tab(self) -> None:
        frame = self.tab_asof_eval

        self._asof_overview_df: Optional[pd.DataFrame] = None
        self._asof_detail_df: Optional[pd.DataFrame] = None
        self._asof_best_only_var = tk.BooleanVar(value=False)
        self._asof_filter_var = tk.StringVar(value="(すべて)")

        # 上部フィルタフォーム
        top = ttk.Frame(frame)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        self.asof_hotel_var = self.hotel_var
        ttk.Label(top, text="ホテル:").grid(row=0, column=0, sticky="w")
        hotel_combo = ttk.Combobox(top, textvariable=self.asof_hotel_var, state="readonly")
        hotel_combo["values"] = sorted(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)

        self.asof_from_ym_var = tk.StringVar()
        self.asof_to_ym_var = tk.StringVar()
        ttk.Label(top, text="期間From (YYYYMM):").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.asof_from_ym_var, width=8).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(top, text="期間To (YYYYMM):").grid(row=0, column=4, sticky="w")
        ttk.Entry(top, textvariable=self.asof_to_ym_var, width=8).grid(row=0, column=5, padx=4, pady=2)

        run_btn = ttk.Button(top, text="評価読み込み", command=self._on_load_asof_eval)
        run_btn.grid(row=0, column=6, padx=4, pady=2)

        ttk.Checkbutton(
            top,
            text="最適モデルのみ表示",
            variable=self._asof_best_only_var,
            command=self._refresh_asof_eval_tables,
        ).grid(row=0, column=7, padx=4, pady=2, sticky="w")

        ttk.Label(top, text="ASOFフィルタ:").grid(row=0, column=8, padx=(12, 0), pady=2, sticky="w")
        asof_filter_combo = ttk.Combobox(
            top,
            textvariable=self._asof_filter_var,
            state="readonly",
            values=["(すべて)", "M-2_END", "M-1_END", "M10", "M20"],
            width=10,
        )
        asof_filter_combo.grid(row=0, column=9, padx=4, pady=2, sticky="w")
        asof_filter_combo.bind("<<ComboboxSelected>>", lambda *_: self._refresh_asof_eval_tables())

        ttk.Button(top, text="CSV出力(サマリ)", command=self._on_export_asof_overview_csv).grid(row=0, column=10, padx=4, pady=2)
        ttk.Button(top, text="CSV出力(月別ログ)", command=self._on_export_asof_detail_csv).grid(row=0, column=11, padx=4, pady=2)

        # ASOF別サマリテーブル
        overview_frame = ttk.LabelFrame(frame, text="ASOF別サマリ")
        overview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        columns = ["model", "asof_type", "mean_error_pct", "mae_pct", "rmse_pct", "n_samples"]
        self.asof_overview_tree = ttk.Treeview(overview_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.asof_overview_tree.heading(col, text=col)
        # 列幅・整列設定
        self.asof_overview_tree.column("model", width=120, anchor="w")
        self.asof_overview_tree.column("asof_type", width=120, anchor="w")
        for col in ["mean_error_pct", "mae_pct", "rmse_pct"]:
            self.asof_overview_tree.column(col, width=120, anchor="e")
        self.asof_overview_tree.column("n_samples", width=100, anchor="e")
        self.asof_overview_tree.tag_configure("asof_even", background="#ffffff")
        self.asof_overview_tree.tag_configure("asof_odd", background="#f5f5f5")
        self.asof_overview_tree.tag_configure("asof_best", background="#e0f2ff")

        self.asof_overview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4), pady=4)
        vsb1 = ttk.Scrollbar(overview_frame, orient="vertical", command=self.asof_overview_tree.yview)
        self.asof_overview_tree.configure(yscrollcommand=vsb1.set)
        vsb1.pack(side=tk.RIGHT, fill=tk.Y)

        # 月別ログテーブル
        detail_frame = ttk.LabelFrame(frame, text="月別ログ")
        detail_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        detail_columns = ["target_month", "asof_type", "model", "error_pct", "abs_error_pct"]
        self.asof_detail_tree = ttk.Treeview(detail_frame, columns=detail_columns, show="headings", height=12)
        for col in detail_columns:
            self.asof_detail_tree.heading(col, text=col)

        self.asof_detail_tree.column("target_month", width=100, anchor="w")
        self.asof_detail_tree.column("asof_type", width=100, anchor="w")
        self.asof_detail_tree.column("model", width=120, anchor="w")
        self.asof_detail_tree.column("error_pct", width=120, anchor="e")
        self.asof_detail_tree.column("abs_error_pct", width=120, anchor="e")
        self.asof_detail_tree.tag_configure("asofd_even", background="#ffffff")
        self.asof_detail_tree.tag_configure("asofd_odd", background="#f5f5f5")
        self.asof_detail_tree.tag_configure("asofd_best", background="#e0f2ff")

        self.asof_detail_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4), pady=4)
        vsb2 = ttk.Scrollbar(detail_frame, orient="vertical", command=self.asof_detail_tree.yview)
        self.asof_detail_tree.configure(yscrollcommand=vsb2.set)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_load_asof_eval(self) -> None:
        """
        ASOF比較タブの「評価読み込み」ボタン押下時の処理。
        - get_eval_overview_by_asof / get_eval_monthly_by_asof を呼び、
          サマリテーブルと月別ログテーブルを更新する。
        """

        try:
            hotel = self.asof_hotel_var.get().strip() or DEFAULT_HOTEL
            from_ym = self.asof_from_ym_var.get().strip() or None
            to_ym = self.asof_to_ym_var.get().strip() or None

            overview_df = get_eval_overview_by_asof(hotel, from_ym=from_ym, to_ym=to_ym, force_reload=True)
            detail_df = get_eval_monthly_by_asof(hotel, from_ym=from_ym, to_ym=to_ym, force_reload=True)
        except Exception as exc:
            self._asof_overview_df = None
            self._asof_detail_df = None
            messagebox.showerror("エラー", f"モデル評価読み込みに失敗しました:\n{exc}")
            return

        self._asof_overview_df = overview_df
        self._asof_detail_df = detail_df
        self._refresh_asof_eval_tables()

    def _refresh_asof_eval_tables(self) -> None:
        if self._asof_overview_df is None or self._asof_detail_df is None:
            self._asof_overview_view_df = None
            self._asof_detail_view_df = None
            return

        asof_value = self._asof_filter_var.get()

        overview_df = self._asof_overview_df.copy()
        best_overview_idx: set[int] = set()
        if self._asof_best_only_var.get():
            sort_cols = ["mae_pct"]
            if "rmse_pct" in overview_df.columns:
                sort_cols.append("rmse_pct")
            selected_idx = []
            for _, grp in overview_df.groupby("asof_type", sort=False):
                candidates = grp.dropna(subset=["mae_pct"])
                if candidates.empty:
                    continue
                best_row = candidates.sort_values(sort_cols, ascending=True).iloc[0]
                selected_idx.append(best_row.name)
            overview_df = overview_df.loc[selected_idx]

        if asof_value and asof_value != "(すべて)":
            overview_df = overview_df[overview_df["asof_type"] == asof_value]

        if not self._asof_best_only_var.get():
            tmp = overview_df.dropna(subset=["mae_pct"])
            if not tmp.empty:
                for _, grp in tmp.groupby("asof_type", sort=False):
                    sort_cols = ["mae_pct"]
                    if "rmse_pct" in grp.columns:
                        sort_cols.append("rmse_pct")
                    best_row = grp.sort_values(sort_cols, ascending=True).iloc[0]
                    best_overview_idx.add(best_row.name)

        overview_df = overview_df.sort_values(["asof_type", "model"])

        self._asof_overview_view_df = overview_df.copy()

        for row_id in self.asof_overview_tree.get_children():
            self.asof_overview_tree.delete(row_id)
        for i, (idx, row) in enumerate(overview_df.iterrows()):
            values = [
                str(row["model"]),
                str(row["asof_type"]),
                _fmt_pct(row.get("mean_error_pct")),
                _fmt_pct(row.get("mae_pct")),
                _fmt_pct(row.get("rmse_pct")),
                str(row["n_samples"]),
            ]
            tags = ["asof_even" if i % 2 == 0 else "asof_odd"]
            if idx in best_overview_idx:
                tags.append("asof_best")
            self.asof_overview_tree.insert("", tk.END, values=values, tags=tags)

        base_df = self._asof_detail_df.copy()
        if asof_value and asof_value != "(すべて)":
            base_df = base_df[base_df["asof_type"] == asof_value]

        best_detail_idx: set[int] = set()
        if self._asof_best_only_var.get():
            sort_cols = ["abs_error_pct"]
            if "rmse_pct" in base_df.columns:
                sort_cols.append("rmse_pct")
            selected_idx = []
            for _, grp in base_df.groupby(["target_month", "asof_type"], sort=False):
                candidates = grp.dropna(subset=["abs_error_pct"])
                if candidates.empty:
                    continue
                best_row = candidates.sort_values(sort_cols, ascending=True).iloc[0]
                selected_idx.append(best_row.name)
            base_df = base_df.loc[selected_idx]

        if not self._asof_best_only_var.get():
            tmp = base_df.dropna(subset=["abs_error_pct"])
            if not tmp.empty:
                for _, grp in tmp.groupby(["target_month", "asof_type"], sort=False):
                    sort_cols = ["abs_error_pct"]
                    if "rmse_pct" in grp.columns:
                        sort_cols.append("rmse_pct")
                    best_row = grp.sort_values(sort_cols, ascending=True).iloc[0]
                    best_detail_idx.add(best_row.name)

        base_df = base_df.sort_values(["target_month", "asof_type", "model"])

        self._asof_detail_view_df = base_df.copy()

        for row_id in self.asof_detail_tree.get_children():
            self.asof_detail_tree.delete(row_id)
        for i, (idx, row) in enumerate(base_df.iterrows()):
            values = [
                str(row["target_month"]),
                str(row["asof_type"]),
                str(row["model"]),
                _fmt_pct(row.get("error_pct")),
                _fmt_pct(row.get("abs_error_pct")),
            ]
            tags = ["asofd_even" if i % 2 == 0 else "asofd_odd"]
            if idx in best_detail_idx:
                tags.append("asofd_best")
            self.asof_detail_tree.insert("", tk.END, values=values, tags=tags)

    def _on_export_asof_overview_csv(self) -> None:
        """
        ASOF比較タブの上段サマリを CSV 出力する。
        """

        df = getattr(self, "_asof_overview_view_df", None)
        if df is None or df.empty:
            messagebox.showerror("エラー", "先に評価を読み込んでください。")
            return

        hotel = self.asof_hotel_var.get().strip() if hasattr(self, "asof_hotel_var") else ""
        from_ym = self.asof_from_ym_var.get().strip() if hasattr(self, "asof_from_ym_var") else ""
        to_ym = self.asof_to_ym_var.get().strip() if hasattr(self, "asof_to_ym_var") else ""
        asof_filter = self._asof_filter_var.get().strip() if hasattr(self, "_asof_filter_var") else ""
        best_only = "best" if getattr(self, "_asof_best_only_var", tk.BooleanVar(value=False)).get() else "all"

        if not hotel:
            hotel = "unknown"
        if not from_ym:
            from_ym = "ALL"
        if not to_ym:
            to_ym = "ALL"

        if not asof_filter or "(すべて" in asof_filter:
            asof_key = "ALL"
        else:
            asof_key = asof_filter
            asof_key = asof_key.replace("(", "_").replace(")", "_").replace(" ", "_")

        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"asof_overview_{hotel}_{from_ym}_{to_ym}_{asof_key}_{best_only}.csv"
            out_path = OUTPUT_DIR / filename
            df.to_csv(out_path, index=False)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"CSV を保存しました。\n{out_path}")

    def _on_export_asof_detail_csv(self) -> None:
        """
        ASOF比較タブの下段(月別ログ)を CSV 出力する。
        """

        df = getattr(self, "_asof_detail_view_df", None)
        if df is None or df.empty:
            messagebox.showerror("エラー", "先に評価を読み込んでください。")
            return

        hotel = self.asof_hotel_var.get().strip() if hasattr(self, "asof_hotel_var") else ""
        from_ym = self.asof_from_ym_var.get().strip() if hasattr(self, "asof_from_ym_var") else ""
        to_ym = self.asof_to_ym_var.get().strip() if hasattr(self, "asof_to_ym_var") else ""
        asof_filter = self._asof_filter_var.get().strip() if hasattr(self, "_asof_filter_var") else ""
        best_only = "best" if getattr(self, "_asof_best_only_var", tk.BooleanVar(value=False)).get() else "all"

        if not hotel:
            hotel = "unknown"
        if not from_ym:
            from_ym = "ALL"
        if not to_ym:
            to_ym = "ALL"

        if not asof_filter or "(すべて" in asof_filter:
            asof_key = "ALL"
        else:
            asof_key = asof_filter
            asof_key = asof_key.replace("(", "_").replace(")", "_").replace(" ", "_")

        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"asof_detail_{hotel}_{from_ym}_{to_ym}_{asof_key}_{best_only}.csv"
            out_path = OUTPUT_DIR / filename
            df.to_csv(out_path, index=False)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"CSV を保存しました。\n{out_path}")

    # =========================
    # 1) ブッキングカーブタブ
    # =========================
    def _init_booking_curve_tab(self) -> None:
        frame = self.tab_booking_curve

        form = ttk.Frame(frame)
        form.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(form, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.bc_hotel_var = self.hotel_var
        hotel_combo = ttk.Combobox(form, textvariable=self.bc_hotel_var, state="readonly")
        hotel_combo["values"] = sorted(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)
        hotel_combo.bind("<<ComboboxSelected>>", self._on_bc_hotel_changed)

        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.bc_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.bc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(form, text="曜日:").grid(row=0, column=4, sticky="w")
        self.bc_weekday_var = tk.StringVar(value="5:Sat")
        weekday_combo = ttk.Combobox(form, textvariable=self.bc_weekday_var, state="readonly", width=7)
        weekday_combo["values"] = [
            "0:Mon",
            "1:Tue",
            "2:Wed",
            "3:Thu",
            "4:Fri",
            "5:Sat",
            "6:Sun",
        ]
        weekday_combo.grid(row=0, column=5, padx=4, pady=2)

        wd_btn_frame = ttk.Frame(form)
        wd_btn_frame.grid(row=0, column=6, columnspan=7, padx=4, pady=2, sticky="w")

        for text, value in [
            ("Sun", "6:Sun"),
            ("Mon", "0:Mon"),
            ("Tue", "1:Tue"),
            ("Wed", "2:Wed"),
            ("Thu", "3:Thu"),
            ("Fri", "4:Fri"),
            ("Sat", "5:Sat"),
        ]:
            ttk.Button(
                wd_btn_frame,
                text=text,
                width=4,
                command=lambda v=value: self._on_bc_quick_weekday(v),
            ).pack(side=tk.LEFT, padx=1)

        ttk.Label(form, text="AS OF (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.bc_asof_var = tk.StringVar(value="")  # 今日ではなく空で初期化
        if DateEntry is not None:
            self.bc_asof_entry = DateEntry(
                form,
                textvariable=self.bc_asof_var,
                date_pattern="yyyy-mm-dd",
                width=12,
            )
        else:
            self.bc_asof_entry = ttk.Entry(
                form,
                textvariable=self.bc_asof_var,
                width=12,
            )
        self.bc_asof_entry.grid(row=1, column=1, padx=4, pady=(4, 2))

        self.bc_latest_asof_var = tk.StringVar(value="")
        ttk.Label(form, text="最新ASOF:").grid(row=1, column=2, sticky="w", pady=(4, 2))
        self.bc_latest_asof_label = tk.Label(form, textvariable=self.bc_latest_asof_var, width=12, anchor="w")
        self._latest_asof_label_defaults[self.bc_latest_asof_label] = (
            self.bc_latest_asof_label.cget("background"),
            self.bc_latest_asof_label.cget("foreground"),
        )
        self.bc_latest_asof_label.grid(row=1, column=3, padx=4, pady=(4, 2), sticky="w")
        ttk.Button(form, text="最新に反映", command=self._on_bc_set_asof_to_latest).grid(row=1, column=4, padx=4, pady=(4, 2), sticky="w")

        ttk.Label(form, text="モデル:").grid(row=1, column=5, sticky="w", pady=(4, 2))
        self.bc_model_var = tk.StringVar(value="recent90w")
        model_combo = ttk.Combobox(form, textvariable=self.bc_model_var, state="readonly", width=12)
        model_combo["values"] = ["avg", "recent90", "recent90w"]
        model_combo.grid(row=1, column=6, padx=4, pady=(4, 2))

        # 現在選択されているホテルのキャパを取得
        current_hotel = self.hotel_var.get().strip() or DEFAULT_HOTEL
        fc_cap, _ = self._get_daily_caps_for_hotel(current_hotel)
        self.bc_forecast_cap_var = tk.StringVar(value=str(fc_cap))

        ttk.Label(form, text="予測キャップ:").grid(row=1, column=11, sticky="w", pady=(4, 2))
        ttk.Entry(form, textvariable=self.bc_forecast_cap_var, width=6).grid(row=1, column=12, padx=2, pady=(4, 2), sticky="w")

        save_btn = ttk.Button(form, text="PNG保存", command=self._on_save_booking_curve_png)
        save_btn.grid(row=1, column=7, padx=4, pady=(4, 2))

        nav_frame = ttk.Frame(form)
        nav_frame.grid(row=2, column=2, columnspan=8, sticky="w", pady=(4, 0))

        nav_left = ttk.Frame(nav_frame)
        nav_left.pack(side=tk.LEFT)
        nav_right = ttk.Frame(nav_frame)
        nav_right.pack(side=tk.LEFT, padx=16, fill=tk.X, expand=True)

        row1_frame = ttk.Frame(nav_right)
        row1_frame.pack(side=tk.TOP, fill=tk.X, anchor="w")
        row2_frame = ttk.Frame(nav_right)
        row2_frame.pack(side=tk.TOP, fill=tk.X, anchor="e", pady=(4, 0))

        ttk.Label(nav_left, text="月移動:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            nav_left,
            text="-1Y",
            command=lambda: self._on_bc_shift_month(-12),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_left,
            text="-1M",
            command=lambda: self._on_bc_shift_month(-1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_left,
            text="+1M",
            command=lambda: self._on_bc_shift_month(+1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_left,
            text="+1Y",
            command=lambda: self._on_bc_shift_month(+12),
        ).pack(side=tk.LEFT, padx=2)

        ttk.Label(row1_frame, text="LTソース:").pack(side=tk.LEFT, padx=(4, 2))
        self.lt_source_combo = ttk.Combobox(
            row1_frame,
            textvariable=self.lt_source_var,
            state="readonly",
            width=14,
        )
        self.lt_source_combo["values"] = ("daily_snapshots", "timeseries")
        self.lt_source_combo.pack(side=tk.LEFT, padx=2)

        self.chk_update_snapshots = ttk.Checkbutton(
            row1_frame,
            text="LT生成時にdaily snapshots更新",
            variable=self.update_daily_snapshots_var,
        )
        self.chk_update_snapshots.pack(side=tk.LEFT, padx=4)

        self.btn_build_lt = ttk.Button(row2_frame, text="LT_DATA(4ヶ月)", command=self._on_build_lt_data)
        self.btn_build_lt.pack(side=tk.LEFT, padx=4)

        self.btn_build_lt_range = ttk.Button(row2_frame, text="LT_DATA(期間指定)", command=self._on_build_lt_data_range)
        self.btn_build_lt_range.pack(side=tk.LEFT, padx=4)

        draw_btn = ttk.Button(row2_frame, text="描画", command=self._on_draw_booking_curve)
        draw_btn.pack(side=tk.LEFT, padx=8)

        self.lt_source_var.trace_add("write", self._on_lt_source_changed)
        self.lt_source_combo.bind("<<ComboboxSelected>>", self._on_lt_source_changed)
        self._sync_daily_snapshots_checkbox_state()

        self.bc_best_model_label = ttk.Label(
            frame,
            text="最適モデル: 評価データなし",
            anchor="w",
            justify="left",
        )
        self.bc_best_model_label.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))

        plot_frame = ttk.Frame(frame)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.bc_fig = Figure(figsize=(10, 5))
        # 左余白は詰めたまま、凡例用に右側に少しスペースを残す
        self.bc_fig.subplots_adjust(left=0.08, right=0.86)
        self.bc_ax = self.bc_fig.add_subplot(111)
        self.bc_ax.text(0.5, 0.5, "No data", ha="center", va="center")
        self.bc_ax.set_axis_off()
        self.bc_canvas = FigureCanvasTkAgg(self.bc_fig, master=plot_frame)
        self.bc_canvas.draw()
        self.bc_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # --- ブッキングカーブ用テーブル (stay_date × LT) ---
        table_frame = ttk.Frame(frame)
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))

        # 初期状態では列は空。データ取得時に動的に columns を設定する。
        self.bc_tree = ttk.Treeview(table_frame, columns=(), show="headings", height=8)
        self.bc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # forecast行の背景色（破線部分の値を示す行）
        self.bc_tree.tag_configure("forecast", background="#EEF7FF")

        # 縦スクロールバー
        bc_vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.bc_tree.yview)
        bc_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.bc_tree.configure(yscrollcommand=bc_vsb.set)

        # 横スクロールバー
        bc_hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.bc_tree.xview)
        bc_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.bc_tree.configure(xscrollcommand=bc_hsb.set)

        self._update_bc_latest_asof_label(update_asof_if_empty=True)

    def _on_save_booking_curve_png(self) -> None:
        hotel_tag = self.bc_hotel_var.get().strip()
        target_month = self.bc_month_var.get().strip()
        weekday_label = self.bc_weekday_var.get().strip()
        as_of_date = self.bc_asof_var.get().strip()
        model = self.bc_model_var.get().strip()

        try:
            weekday_int = int(weekday_label.split(":")[0])
        except Exception:
            messagebox.showerror("Error", f"曜日の値が不正です: {weekday_label}")
            return

        if not target_month or len(target_month) != 6:
            messagebox.showerror("Error", f"対象月の形式が不正です: {target_month}")
            return

        asof_tag = as_of_date.replace("-", "")
        if len(asof_tag) != 8 or not asof_tag.isdigit():
            messagebox.showerror("Error", f"AS OF の形式が不正です: {as_of_date}")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"booking_curve_{hotel_tag}_{target_month}_wd{weekday_int}_{model}_asof_{asof_tag}.png"
        out_path = OUTPUT_DIR / filename

        try:
            self.bc_fig.savefig(out_path, dpi=150, bbox_inches="tight")
        except Exception as e:
            messagebox.showerror("Error", f"PNG保存に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"PNG を保存しました:\n{out_path}")

    def _sync_daily_snapshots_checkbox_state(self) -> None:
        lt_source = self.lt_source_var.get()

        if lt_source == "timeseries":
            self.update_daily_snapshots_var.set(False)
            self.chk_update_snapshots.configure(state="disabled")
        else:
            self.chk_update_snapshots.configure(state="normal")

    def _on_lt_source_changed(self, *_: object) -> None:
        self._sync_daily_snapshots_checkbox_state()

    def _on_build_lt_data(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        base_ym = self.bc_month_var.get().strip()

        if len(base_ym) != 6 or not base_ym.isdigit():
            messagebox.showerror("LT_DATA生成エラー", "対象月は 6桁の数字 (YYYYMM) で入力してください。")
            return

        try:
            base_period = pd.Period(f"{base_ym[:4]}-{base_ym[4:]}", freq="M")
        except Exception:
            messagebox.showerror("LT_DATA生成エラー", "対象月は 6桁の数字 (YYYYMM) で入力してください。")
            return

        target_months = [(base_period + i).strftime("%Y%m") for i in range(4)]

        confirm = messagebox.askokcancel(
            "LT_DATA生成確認",
            f"{hotel_tag} の LT_DATA を {target_months[0]}〜{target_months[-1]} で再生成します。よろしいですか？",
        )
        if not confirm:
            return

        try:
            snapshots_updated = False
            lt_source = self.lt_source_var.get() or "daily_snapshots"
            # 必要に応じて daily snapshots を先に更新
            if self.update_daily_snapshots_var.get() and lt_source == "daily_snapshots":
                if not target_months:
                    messagebox.showwarning(
                        "LT_DATA生成エラー",
                        "対象月が未指定のため、daily snapshots の更新をスキップします。",
                    )
                    return

                plan = build_range_rebuild_plan_for_gui(
                    hotel_tag,
                    buffer_days=30,
                    lookahead_days=120,
                )
                if not self._precheck_missing_report_for_range_rebuild(
                    hotel_tag,
                    plan["asof_min"],
                    plan["asof_max"],
                ):
                    return

                run_daily_snapshots_for_gui(
                    hotel_tag=hotel_tag,
                    mode="RANGE_REBUILD",
                    target_months=target_months,
                    buffer_days=30,
                )
                snapshots_updated = True
            elif self.update_daily_snapshots_var.get():
                logging.info("LT生成: source=timeseries のため daily snapshots 更新はスキップ")

            run_build_lt_data_for_gui(hotel_tag, target_months, source=lt_source)
        except Exception as e:
            messagebox.showerror(
                "LT_DATA生成エラー",
                f"LT_DATA生成でエラーが発生しました。\n{e}",
            )
            return

        try:
            # ブッキングカーブタブ用の最新ASOFラベルを更新
            self._update_bc_latest_asof_label(update_asof_if_empty=False)
        except Exception:
            pass

        try:
            # 日別フォーキャストタブ用の最新ASOFラベルを更新
            self._update_df_latest_asof_label(update_asof_if_empty=False)
        except Exception:
            pass

        if snapshots_updated:
            try:
                self._update_master_missing_check_status()
            except Exception:
                logging.warning("欠損検査ステータスの更新に失敗しました", exc_info=True)

        messagebox.showinfo(
            "LT_DATA生成",
            f"LT_DATA CSV の生成が完了しました。\n対象月: {', '.join(target_months)}\n必要に応じて「最新に反映」ボタンで ASOF を更新してください。",
        )

    def _ask_month_range(self, initial_start: str, initial_end: str | None = None) -> tuple[str, str] | None:
        dialog = tk.Toplevel(self)
        dialog.title("LT_DATA生成")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        start_var = tk.StringVar(value=initial_start)
        end_var = tk.StringVar(value=initial_end if initial_end is not None else initial_start)
        result: tuple[str, str] | None = None

        def on_ok(*_: object) -> None:
            nonlocal result
            result = (start_var.get().strip(), end_var.get().strip())
            dialog.destroy()

        def on_cancel(*_: object) -> None:
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.bind("<Escape>", on_cancel)

        content = ttk.Frame(dialog, padding=12)
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content, text="開始月 (YYYYMM):").grid(row=0, column=0, sticky="w", pady=4)
        start_entry = ttk.Entry(content, textvariable=start_var, width=12)
        start_entry.grid(row=0, column=1, padx=(4, 0), pady=4)
        start_entry.bind("<Return>", on_ok)

        ttk.Label(content, text="終了月 (YYYYMM):").grid(row=1, column=0, sticky="w", pady=4)
        end_entry = ttk.Entry(content, textvariable=end_var, width=12)
        end_entry.grid(row=1, column=1, padx=(4, 0), pady=4)
        end_entry.bind("<Return>", on_ok)

        btn_frame = ttk.Frame(content)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(8, 0), sticky="e")
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="キャンセル", command=on_cancel).pack(side=tk.LEFT, padx=4)

        dialog.update_idletasks()  # サイズ確定
        w = dialog.winfo_width()
        h = dialog.winfo_height()

        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()

        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        start_entry.focus_set()
        dialog.wait_window(dialog)
        return result

    def _on_build_lt_data_range(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        default_ym = self.bc_month_var.get().strip()

        result = self._ask_month_range(default_ym)
        if result is None:
            return

        start_ym, end_ym = result
        if not start_ym or not end_ym:
            return

        for label, value in (("開始月", start_ym), ("終了月", end_ym)):
            if len(value) != 6 or not value.isdigit():
                messagebox.showerror(
                    "LT_DATA生成エラー",
                    f"{label} は 6桁の数字 (YYYYMM) で入力してください。\n入力値: {value}",
                )
                return

        try:
            start_p = pd.Period(f"{start_ym[:4]}-{start_ym[4:]}", freq="M")
            end_p = pd.Period(f"{end_ym[:4]}-{end_ym[4:]}", freq="M")
        except Exception:
            messagebox.showerror("LT_DATA生成エラー", "開始月と終了月は YYYYMM 形式で入力してください。")
            return

        if end_p < start_p:
            messagebox.showerror("LT_DATA生成エラー", "終了月は開始月以降を指定してください。")
            return

        diff_months = (end_p.year - start_p.year) * 12 + (end_p.month - start_p.month)
        target_months = [(start_p + i).strftime("%Y%m") for i in range(diff_months + 1)]

        if len(target_months) > 24:
            heavy_confirm = messagebox.askyesno(
                "LT_DATA生成確認",
                f"{len(target_months)}ヶ月分 ({target_months[0]}〜{target_months[-1]}) を生成します。\n"
                "時間がかかる可能性がありますが、よろしいですか？",
            )
            if not heavy_confirm:
                return

        confirm = messagebox.askokcancel(
            "LT_DATA生成確認",
            f"{hotel_tag} の LT_DATA を\n{target_months[0]}〜{target_months[-1]} の {len(target_months)}ヶ月分で再生成します。\nよろしいですか？",
        )
        if not confirm:
            return

        try:
            snapshots_updated = False
            lt_source = self.lt_source_var.get() or "daily_snapshots"
            if self.update_daily_snapshots_var.get() and lt_source == "daily_snapshots":
                if not target_months:
                    messagebox.showwarning(
                        "LT_DATA生成エラー",
                        "対象月が未指定のため、daily snapshots の更新をスキップします。",
                    )
                    return
                run_daily_snapshots_for_gui(
                    hotel_tag=hotel_tag,
                    mode="FULL_MONTHS",
                    target_months=target_months,
                )
                snapshots_updated = True
            elif self.update_daily_snapshots_var.get():
                logging.info("LT生成: source=timeseries のため daily snapshots 更新はスキップ")

            run_build_lt_data_for_gui(hotel_tag, target_months, source=lt_source)
        except Exception as e:
            messagebox.showerror(
                "LT_DATA生成エラー",
                f"LT_DATA生成でエラーが発生しました。\n{e}",
            )
            return

        try:
            # ブッキングカーブタブ用の最新ASOFラベルを更新
            self._update_bc_latest_asof_label(update_asof_if_empty=False)
        except Exception:
            pass

        try:
            # 日別フォーキャストタブ用の最新ASOFラベルを更新
            self._update_df_latest_asof_label(update_asof_if_empty=False)
        except Exception:
            pass

        if snapshots_updated:
            try:
                self._update_master_missing_check_status()
            except Exception:
                logging.warning("欠損検査ステータスの更新に失敗しました", exc_info=True)

        messagebox.showinfo(
            "LT_DATA生成",
            f"LT_DATA CSV の生成が完了しました。\n対象月: {', '.join(target_months)}",
        )

    def _on_draw_booking_curve(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        target_month = self.bc_month_var.get().strip()
        weekday_label = self.bc_weekday_var.get().strip()
        weekday_parts = weekday_label.split(":", 1)
        weekday_text = weekday_parts[1].strip() if len(weekday_parts) == 2 else weekday_label
        as_of_date = self.bc_asof_var.get().strip()
        model = self.bc_model_var.get().strip()

        fc_cap_str = self.bc_forecast_cap_var.get().strip()
        if not fc_cap_str:
            messagebox.showerror("Error", "予測キャップを入力してください。")
            return
        try:
            forecast_cap = float(fc_cap_str)
        except Exception:
            messagebox.showerror("Error", "予測キャップには数値を入力してください。")
            return

        _, occ_cap = self._get_daily_caps_for_hotel(hotel_tag)
        self._set_daily_caps_for_hotel(hotel_tag, forecast_cap, occ_cap)

        # ASOF と最新ASOFの比較
        latest_str = self.bc_latest_asof_var.get().strip()
        if latest_str and latest_str not in ("なし", "(未取得)"):
            try:
                asof_dt = pd.to_datetime(as_of_date)
                latest_dt = pd.to_datetime(latest_str)
            except Exception:
                messagebox.showerror("Error", f"AS OF 日付の形式が不正です: {as_of_date}")
                return

            # 最新ASOFより未来の場合だけ確認ダイアログを出す
            if asof_dt > latest_dt:
                use_latest = messagebox.askyesno(
                    "確認",
                    (f"最新ASOF は {latest_str} です。\n選択中の ASOF ({as_of_date}) は最新より未来の日付です。\n\n最新ASOFに変更して描画しますか？"),
                )
                if use_latest:
                    asof_dt = latest_dt
                    as_of_date = latest_dt.strftime("%Y-%m-%d")
                    self.bc_asof_var.set(as_of_date)
                else:
                    return

        try:
            weekday_int = int(weekday_parts[0])
        except Exception:
            messagebox.showerror("Error", "曜日の値が不正です")
            return

        try:
            data = get_booking_curve_data(
                hotel_tag=hotel_tag,
                target_month=target_month,
                weekday=weekday_int,
                model=model,
                as_of_date=as_of_date,
            )
        except Exception as e:
            messagebox.showerror("Error", f"ブッキングカーブ取得に失敗しました: {e}")
            return

        curves = data.get("curves", {})
        avg_curve = data.get("avg_curve")
        forecast_curve = data.get("forecast_curve")

        if not curves and avg_curve is None:
            messagebox.showerror("Error", "データが不足しています")
            return

        df_week = pd.DataFrame(curves).T if curves else pd.DataFrame()
        if not df_week.empty:
            df_week.columns = [int(c) for c in df_week.columns]
            df_week = df_week.reindex(columns=LEAD_TIME_PITCHES)

        if avg_curve is not None:
            avg_series = pd.Series(avg_curve)
        else:
            avg_series = df_week.mean(axis=0, skipna=True) if not df_week.empty else pd.Series(dtype=float)

        if forecast_curve is not None:
            forecast_series = pd.Series(forecast_curve)
        else:
            forecast_series = avg_series.copy()

        if not avg_series.empty:
            avg_series.index = [int(i) for i in avg_series.index]
            avg_series = avg_series.reindex(LEAD_TIME_PITCHES)

        if not forecast_series.empty:
            forecast_series.index = [int(i) for i in forecast_series.index]
            forecast_series = forecast_series.reindex(LEAD_TIME_PITCHES)

        x_positions = np.arange(len(LEAD_TIME_PITCHES))
        x_labels = ["ACT" if lt == -1 else str(lt) for lt in LEAD_TIME_PITCHES]

        self.bc_ax.clear()

        line_colors = [
            "#4C72B0",
            "#DD8452",
            "#55A868",
            "#C44E52",
            "#8172B2",
        ]

        for i, (stay_date, series) in enumerate(sorted(curves.items())):
            color = line_colors[i % len(line_colors)]

            series = series.reindex(LEAD_TIME_PITCHES)
            y_values = [series.get(lt, np.nan) for lt in LEAD_TIME_PITCHES]
            self.bc_ax.plot(
                x_positions,
                y_values,
                color=color,
                linewidth=1.8,
                alpha=0.9,
                label=stay_date.strftime("%m/%d"),
            )

            # ------- ここから破線 (モデルベースの延長) -------
            if forecast_series is None or forecast_series.empty:
                continue

            y_array = np.array(y_values, dtype=float)

            # 右端から見て「最後に実績がある LT」のインデックスを探す
            last_idx = None
            for idx in range(len(LEAD_TIME_PITCHES) - 1, -1, -1):
                if not np.isnan(y_array[idx]):
                    last_idx = idx
                    break

            # 実績が1つも無い場合 or すでに ACT まで埋まっている場合は延長不要
            if last_idx is None or last_idx == len(LEAD_TIME_PITCHES) - 1:
                continue

            base_lt = LEAD_TIME_PITCHES[last_idx]
            base_actual = y_array[last_idx]
            base_model = forecast_series.get(base_lt, np.nan)

            if np.isnan(base_actual) or np.isnan(base_model):
                continue

            y_dash = [np.nan] * len(LEAD_TIME_PITCHES)
            last_model_val = base_model

            # 基準LTを含めて ACT まで破線を描く
            for j in range(last_idx, len(LEAD_TIME_PITCHES)):
                lt = LEAD_TIME_PITCHES[j]
                if j == last_idx:
                    # 基準LTでは実績点と同じ位置から破線をスタートさせる
                    y_dash[j] = float(base_actual)
                else:
                    model_val = forecast_series.get(lt, np.nan)
                    if np.isnan(model_val):
                        # モデル値が欠損している場合は直前のモデル値を使ってフラットに延長
                        model_val = last_model_val
                    last_model_val = model_val
                    y_dash[j] = float(base_actual) + float(model_val - base_model)

            y_dash_capped = []
            for v in y_dash:
                try:
                    fv = float(v)
                except Exception:
                    y_dash_capped.append(np.nan)
                    continue
                if np.isnan(fv):
                    y_dash_capped.append(np.nan)
                else:
                    y_dash_capped.append(min(fv, forecast_cap))

            self.bc_ax.plot(
                x_positions,
                y_dash_capped,
                color=color,
                linestyle="--",
                linewidth=1.4,
                alpha=0.8,
            )

        y_avg = []
        for lt in LEAD_TIME_PITCHES:
            v = avg_series.get(lt, np.nan)
            if np.isnan(v):
                y_avg.append(np.nan)
            else:
                y_avg.append(min(float(v), forecast_cap))
        self.bc_ax.plot(
            x_positions,
            y_avg,
            color="#1F3F75",
            linewidth=4.5,
            alpha=0.2,
            label="model avg",
        )

        self.bc_ax.set_xticks(x_positions)
        self.bc_ax.set_xticklabels(x_labels)
        self.bc_ax.set_xlabel("Lead Time (days)")

        def _choose_axis_params(raw_max: float) -> tuple[int, int]:
            steps = [10, 20, 25, 50, 100, 200, 500]
            for step in steps:
                if raw_max / step <= 10:
                    ymax = int(np.ceil(raw_max / step) * step)
                    return ymax, int(step)
            ymax = int(np.ceil(raw_max / 500) * 500)
            return ymax, 500

        hotel_tag = self.bc_hotel_var.get()
        capacity = HOTEL_CONFIG.get(hotel_tag, {}).get("capacity", 180.0)
        capacity_for_axis = max(float(capacity), float(forecast_cap))
        raw_max = capacity_for_axis * 1.10
        ymax, major_step = _choose_axis_params(raw_max)
        minor_step = max(int(major_step / 2), 1)

        self.bc_ax.set_ylabel("Rooms")
        self.bc_ax.set_ylim(0, ymax)
        self.bc_ax.set_yticks(np.arange(0, ymax + 1, major_step))
        self.bc_ax.set_yticks(np.arange(0, ymax + 1, minor_step), minor=True)

        if len(target_month) == 6 and target_month.isdigit():
            title_month = f"{target_month[:4]}-{target_month[4:]}"
        else:
            title_month = target_month
        self.bc_ax.set_title(f"{title_month} Booking Curve ({weekday_text})")

        self.bc_ax.grid(axis="y", which="major", linestyle="--", alpha=0.3)
        self.bc_ax.grid(axis="y", which="minor", linestyle=":", alpha=0.15)
        self.bc_ax.grid(axis="x", which="major", linestyle=":", alpha=0.15)

        self.bc_ax.legend(bbox_to_anchor=(1.02, 1.0), loc="upper left")

        self.bc_canvas.draw()

        # データテーブルを更新
        try:
            self._update_booking_curve_table(data)
        except Exception as e:
            # テーブル更新でエラーが出てもグラフ描画は維持したいので、ここではダイアログだけ表示
            messagebox.showerror("Error", f"テーブル更新に失敗しました: {e}")

    def _update_booking_curve_table(self, data: dict) -> None:
        """
        ブッキングカーブタブのテーブルを更新する。
        data は get_booking_curve_data(...) の戻り値。
        """

        fc_cap_str = self.bc_forecast_cap_var.get().strip() if hasattr(self, "bc_forecast_cap_var") else ""
        forecast_cap = None
        try:
            if fc_cap_str:
                forecast_cap = float(fc_cap_str)
        except Exception:
            forecast_cap = None

        curves = data.get("curves", {})
        forecast_curve = data.get("forecast_curve")

        if not hasattr(self, "bc_tree"):
            return

        # 既存行クリア
        for row_id in self.bc_tree.get_children():
            self.bc_tree.delete(row_id)

        if not curves:
            self.bc_tree["columns"] = ()
            return

        # ---- 実績 DataFrame 作成 ----
        df = pd.DataFrame(curves).T
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        # 列は常に LEAD_TIME_PITCHES に揃える
        lt_list = list(LEAD_TIME_PITCHES)
        # データ側の列は int にそろえておく
        df.columns = [int(c) for c in df.columns]
        df = df.reindex(columns=lt_list)

        # ---- forecast 用 Series 作成 ----
        if forecast_curve is not None:
            forecast_series = pd.Series(forecast_curve)
            # index を int (LT) にそろえて reindex
            forecast_series.index = [int(i) for i in forecast_series.index]
            forecast_series = forecast_series.reindex(lt_list)
        else:
            forecast_series = None

        # ---- Treeview のカラム定義 ----
        columns = ["stay_date"] + [str(lt) for lt in lt_list]
        self.bc_tree["columns"] = columns

        for col in columns:
            if col == "stay_date":
                self.bc_tree.heading(col, text="stay_date")
                self.bc_tree.column(col, width=110, anchor="center")
            else:
                try:
                    lt_val = int(col)
                    header = "ACT" if lt_val == -1 else str(lt_val)
                except Exception:
                    header = col
                self.bc_tree.heading(col, text=header)
                self.bc_tree.column(col, width=45, anchor="e")

        # ---- 実績行＋forecast行を投入 ----
        for stay_date, row in df.iterrows():
            # stay_date 文字列
            if pd.isna(stay_date):
                stay_str = ""
            else:
                stay_str = pd.to_datetime(stay_date).strftime("%Y-%m-%d")

            # 実績行
            actual_values = [stay_str]
            for lt in lt_list:
                v = row.get(lt)
                if pd.isna(v):
                    actual_values.append("")
                else:
                    actual_values.append(_fmt_num(v))

            self.bc_tree.insert("", tk.END, values=actual_values)

            # forecast_curve が無い場合はここで終了
            if forecast_series is None or forecast_series.isna().all():
                continue

            # ---- 破線延長部分の値を計算 ----
            y_values = np.array([row.get(lt) for lt in lt_list], dtype=float)

            # 右端から見て最後に実績がある LT のインデックス
            last_idx = None
            for idx in range(len(lt_list) - 1, -1, -1):
                if not np.isnan(y_values[idx]):
                    last_idx = idx
                    break

            # 実績が1つも無い or すでに ACT まで埋まっている場合は破線なし
            if last_idx is None or last_idx == len(lt_list) - 1:
                continue

            base_lt = lt_list[last_idx]
            base_actual = y_values[last_idx]
            base_model = forecast_series.get(base_lt, np.nan)

            if np.isnan(base_actual) or np.isnan(base_model):
                continue

            forecast_row = [f"{stay_str} (forecast)"]

            last_model_val = base_model
            for j, lt in enumerate(lt_list):
                # last_idx まではOHのみ表示。forecast行は空欄にしておく。
                if j <= last_idx:
                    forecast_row.append("")
                    continue

                # last_idx+1 以降だけ forecast 値を表示する
                model_val = forecast_series.get(lt, np.nan)
                if np.isnan(model_val):
                    # モデル値が欠損している場合は直前の値でフラット延長
                    model_val = last_model_val
                last_model_val = model_val

                y_dash = float(base_actual) + float(model_val - base_model)
                if forecast_cap is not None:
                    y_dash = min(y_dash, forecast_cap)
                forecast_row.append(_fmt_num(y_dash))

            # forecast行をタグ付きで挿入（背景色変更）
            self.bc_tree.insert("", tk.END, values=forecast_row, tags=("forecast",))

    # =========================
    # 2) 月次カーブタブ
    # =========================
    def _init_monthly_curve_tab(self) -> None:
        frame = self.tab_monthly_curve

        form = ttk.Frame(frame)
        form.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(form, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.mc_hotel_var = self.hotel_var
        mc_combo = ttk.Combobox(form, textvariable=self.mc_hotel_var, state="readonly")
        mc_combo["values"] = sorted(HOTEL_CONFIG.keys())
        mc_combo.grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.mc_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.mc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        self.mc_show_prev_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="前年同月を重ねる", variable=self.mc_show_prev_var).grid(row=0, column=4, padx=8, pady=2, sticky="w")

        save_btn = ttk.Button(form, text="PNG保存", command=self._on_save_monthly_curve_png)
        save_btn.grid(row=0, column=5, padx=4, pady=2)

        draw_btn = ttk.Button(form, text="描画", command=self._on_draw_monthly_curve)
        draw_btn.grid(row=0, column=6, padx=4, pady=2)

        nav_frame = ttk.Frame(form)
        nav_frame.grid(row=1, column=2, columnspan=5, sticky="w", pady=(4, 0))

        ttk.Label(nav_frame, text="月移動:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            nav_frame,
            text="-1Y",
            command=lambda: self._shift_month_var(self.mc_month_var, -12),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="-1M",
            command=lambda: self._shift_month_var(self.mc_month_var, -1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1M",
            command=lambda: self._shift_month_var(self.mc_month_var, +1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1Y",
            command=lambda: self._shift_month_var(self.mc_month_var, +12),
        ).pack(side=tk.LEFT, padx=2)

        plot_frame = ttk.Frame(frame)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.mc_fig = Figure(figsize=(10, 5))
        self.mc_ax = self.mc_fig.add_subplot(111)
        self.mc_ax.text(0.5, 0.5, "No data", ha="center", va="center")
        self.mc_ax.set_axis_off()
        self.mc_canvas = FigureCanvasTkAgg(self.mc_fig, master=plot_frame)
        self.mc_canvas.draw()
        self.mc_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _on_save_monthly_curve_png(self) -> None:
        hotel_tag = self.mc_hotel_var.get().strip()
        target_month = self.mc_month_var.get().strip()

        if len(target_month) != 6 or not target_month.isdigit():
            messagebox.showerror("Error", f"対象月の形式が不正です: {target_month}")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"monthly_curve_{hotel_tag}_{target_month}_all.png"
        out_path = OUTPUT_DIR / filename

        try:
            self.mc_fig.savefig(out_path, dpi=150, bbox_inches="tight")
        except Exception as e:
            messagebox.showerror("Error", f"PNG保存に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"PNG を保存しました:\n{out_path}")

    def _on_draw_monthly_curve(self) -> None:
        """月次ブッキングカーブタブの描画処理。

        ・対象月を含めた直近4ヶ月分（対象月, -1M, -2M, -3M）を一括で描画
        ・「前年同月を重ねる」チェックONの場合は、各月の前年同月を
          同色の破線で追加描画
        ・リードタイム軸は「最大LT → … → 0 → ACT」の順で右に向かって小さくなる
          （ピッチは 1 日単位）
        """

        hotel_tag = self.mc_hotel_var.get()
        ym = self.mc_month_var.get().strip()
        show_prev_year = bool(self.mc_show_prev_var.get())

        # 対象月の形式チェック（YYYYMM）
        try:
            if len(ym) != 6 or not ym.isdigit():
                raise ValueError
            base_period = pd.Period(f"{ym[:4]}-{ym[4:]}", freq="M")
        except Exception:
            messagebox.showerror("Error", f"対象月の形式が不正です: {ym}")
            return

        # 対象月を含めた直近4ヶ月（対象月, -1M, -2M, -3M）
        main_periods = [base_period - i for i in range(4)]
        main_months = [p.strftime("%Y%m") for p in main_periods]

        latest_asof = get_latest_asof_for_month(hotel_tag, ym)
        try:
            asof_ts = pd.to_datetime(latest_asof) if latest_asof is not None else None
        except Exception:
            asof_ts = None

        # 日次ブッキングカーブと同系統のカラーパレット
        line_colors = [
            "#4C72B0",  # 対象月
            "#DD8452",  # -1M
            "#55A868",  # -2M
            "#C44E52",  # -3M
            "#8172B2",  # 予備
        ]

        curves: list[tuple[str, pd.DataFrame, str, str, float]] = []
        max_lt = -1
        has_act = False
        skipped_months: list[str] = []
        skipped_prev_months: list[str] = []

        def load_month_df(month_str: str) -> pd.DataFrame:
            """月次カーブ用DFを読み込み、LT・ACT情報を更新する。"""
            nonlocal max_lt, has_act

            df = get_monthly_curve_data(
                hotel_tag=hotel_tag,
                target_month=month_str,
                as_of_date=latest_asof,  # バックエンド側でASOFトリミングを実施
            )

            # インデックスを int LT に統一して昇順ソート
            if not pd.api.types.is_integer_dtype(df.index):
                df.index = df.index.astype(int)
            df = df.sort_index()

            if len(df.index) > 0:
                nonneg = [int(v) for v in df.index if int(v) >= 0]
                if nonneg:
                    max_lt = max(max_lt, max(nonneg))
                if -1 in df.index:
                    has_act = True
            return df

        # 対象月＋直近3ヶ月
        for idx, month_str in enumerate(main_months):
            try:
                df_m = load_month_df(month_str)
            except Exception as exc:
                logging.warning(
                    "Monthly curve not available for %s (%s): %s",
                    month_str,
                    hotel_tag,
                    exc,
                )
                skipped_months.append(f"{month_str}: {exc}")
                continue

            if df_m is None or df_m.empty:
                skipped_months.append(f"{month_str}: no data")
                continue

            color = line_colors[min(idx, len(line_colors) - 1)]
            linewidth = 2.0 if month_str == ym else 1.6
            curves.append((month_str, df_m, color, "-", linewidth))

        # 前年同月（各月と同色の破線）
        if show_prev_year:
            for idx, period in enumerate(main_periods):
                prev_period = period - 12
                prev_month_str = prev_period.strftime("%Y%m")

                try:
                    df_prev = load_month_df(prev_month_str)
                except Exception as exc:
                    logging.warning(
                        "Previous-year monthly curve not available for %s (%s): %s",
                        prev_month_str,
                        hotel_tag,
                        exc,
                    )
                    skipped_prev_months.append(f"{prev_month_str}: {exc}")
                    continue

                if df_prev is None or df_prev.empty:
                    skipped_prev_months.append(f"{prev_month_str}: no data")
                    continue

                color = line_colors[min(idx, len(line_colors) - 1)]
                curves.append((f"{prev_month_str} (prev)", df_prev, color, "--", 1.6))

        if skipped_months:
            logging.warning("Monthly curves were skipped for months: %s", ", ".join(sorted(skipped_months)))
        if skipped_prev_months:
            logging.warning(
                "Previous-year monthly curves were skipped for months: %s",
                ", ".join(sorted(skipped_prev_months)),
            )

        if not curves:
            self.mc_ax.clear()
            self.mc_ax.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=self.mc_ax.transAxes,
            )
            self.mc_canvas.draw()
            skipped_msg = "\n".join(skipped_months + skipped_prev_months)
            detail = f"\n{skipped_msg}" if skipped_msg else ""
            messagebox.showerror("Error", f"月次カーブの描画対象データがありません。{detail}")
            return

        if skipped_months or skipped_prev_months:
            warn_parts: list[str] = []
            if skipped_months:
                warn_parts.append("取得できなかった月次カーブ: " + ", ".join(sorted(skipped_months)))
            if skipped_prev_months:
                warn_parts.append("取得できなかった前年同月: " + ", ".join(sorted(skipped_prev_months)))
            warn_parts.append("必要なら daily snapshots を更新してください。")
            messagebox.showwarning("Warning", "\n".join(warn_parts))

        # ---- ここから描画ロジック ----
        self.mc_ax.clear()
        global_max_y = 0.0

        # X 軸上の LT 並びを定義：
        #   max_lt, max_lt-1, ..., 0, ACT(-1) の順に右へ進む
        if max_lt < 0:
            lt_order = [-1] if has_act else []
        else:
            lt_order = list(range(max_lt, -1, -1))  # max_lt → ... → 0
            if has_act and -1 not in lt_order:
                lt_order.append(-1)  # 最後に ACT

        x_positions = np.arange(len(lt_order))

        for label, df_m, color, linestyle, linewidth in curves:
            # rooms_total 列があればそれを、無ければ先頭列を使う
            if "rooms_total" in df_m.columns:
                y = df_m["rooms_total"]
            else:
                y = df_m.iloc[:, 0]

            # 定義した lt_order に合わせて並び替え
            y_ordered = y.reindex(lt_order)

            self.mc_ax.plot(
                x_positions,
                y_ordered.values,
                color=color,
                linestyle=linestyle,
                linewidth=linewidth,
                label=label,
            )

            if len(y_ordered) > 0:
                y_max = float(np.nanmax(y_ordered.values))
                if y_max > global_max_y:
                    global_max_y = y_max

        # X 軸の目盛り（1日ピッチ、左が最大LT・右端がACT）
        # ラベルは ACT を除く LT について 2 つに 1 つだけ数値表示する
        lt_numeric = [lt for lt in lt_order if lt != -1]
        show_map = {lt: idx % 2 == 0 for idx, lt in enumerate(lt_numeric)}

        xlabels = []
        for lt in lt_order:
            if lt == -1:
                xlabels.append("ACT")
            elif show_map.get(lt, False):
                xlabels.append(str(lt))
            else:
                xlabels.append("")
        self.mc_ax.set_xticks(x_positions)
        self.mc_ax.set_xticklabels(xlabels, rotation=90)

        # Y 軸は 0 スタート + 500単位の目盛りに統一
        if global_max_y > 0:
            # 5%の余白を持たせた値を 500 の倍数に切り上げ
            raw_max = float(global_max_y) * 1.05
            ymax = int(np.ceil(raw_max / 500.0) * 500)
            if ymax <= 0:
                ymax = 500
            self.mc_ax.set_ylim(0, ymax)
            self.mc_ax.set_yticks(np.arange(0, ymax + 1, 500))

        self.mc_ax.set_xlabel("Lead Time (days)")
        self.mc_ax.set_ylabel("Rooms (monthly cumulative)")
        if asof_ts is not None:
            title = f"Monthly booking curve {ym[:4]}-{ym[4:]} (all, ASOF {latest_asof})"
        else:
            title = f"Monthly booking curve {ym[:4]}-{ym[4:]} (all)"
        self.mc_ax.set_title(title)

        self.mc_ax.grid(True, linestyle=":", linewidth=0.5)
        self.mc_ax.legend()

        self.mc_canvas.draw()

    def _add_placeholder_plot(self, frame: tk.Widget, title: str) -> None:
        fig = Figure(figsize=(8, 4))
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, title, ha="center", va="center", fontsize=12)
        ax.set_axis_off()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=8)


def _fmt_num(v) -> str:
    if pd.isna(v):
        return ""
    try:
        return f"{float(v):.0f}"
    except Exception:
        return str(v)


def _fmt_pct(v) -> str:
    if pd.isna(v):
        return ""
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return str(v)


def main() -> None:
    app = BookingCurveApp()
    app.mainloop()


if __name__ == "__main__":
    main()
