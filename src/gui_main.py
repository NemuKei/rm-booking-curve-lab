from __future__ import annotations

from datetime import date
from typing import Optional
import json

import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from tkcalendar import DateEntry
except ImportError:  # tkcalendar が無い環境向けフォールバック
    DateEntry = None

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# プロジェクト内モジュール
from booking_curve.gui_backend import (
    get_booking_curve_data,
    get_daily_forecast_table,
    get_latest_asof_for_hotel,
    get_latest_asof_for_month,
    get_model_evaluation_table,
    get_eval_monthly_by_asof,
    get_eval_overview_by_asof,
    get_monthly_curve_data,
    OUTPUT_DIR,
    HOTEL_CONFIG,
    run_build_lt_data_for_gui,
    run_forecast_for_gui,
    build_calendar_for_gui,
    get_calendar_coverage,
)
from booking_curve.plot_booking_curve import LEAD_TIME_PITCHES

# デフォルトホテル (現状は大国町のみ想定)
DEFAULT_HOTEL = next(iter(HOTEL_CONFIG.keys()), "daikokucho")
SETTINGS_FILE = OUTPUT_DIR / "gui_settings.json"


class BookingCurveApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Booking Curve Lab GUI")
        self.geometry("1200x800")

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

        self.hotel_var = tk.StringVar(value=DEFAULT_HOTEL)

        # モデル評価タブ用の状態変数
        self.model_eval_df: Optional[pd.DataFrame] = None
        self.model_eval_view_df: Optional[pd.DataFrame] = None
        self.model_eval_best_idx: set[int] = set()
        self.me_from_var = tk.StringVar(value="")
        self.me_to_var = tk.StringVar(value="")
        self._asof_overview_view_df: Optional[pd.DataFrame] = None
        self._asof_detail_view_df: Optional[pd.DataFrame] = None

        self._init_daily_forecast_tab()
        self._init_model_eval_tab()
        self._init_asof_eval_tab()
        self._init_booking_curve_tab()
        self._init_monthly_curve_tab()
        self._create_master_settings_tab()

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

        calendar_frame = ttk.LabelFrame(frame, text="カレンダー")
        calendar_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(calendar_frame, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.hotel_combo = ttk.Combobox(
            calendar_frame, textvariable=self.hotel_var, state="readonly"
        )
        self.hotel_combo["values"] = list(HOTEL_CONFIG.keys())
        self.hotel_combo.grid(row=0, column=1, padx=4, pady=2, sticky="w")
        self.hotel_combo.bind("<<ComboboxSelected>>", self._on_hotel_changed)

        self.calendar_coverage_var = tk.StringVar()
        self.calendar_coverage_label = ttk.Label(
            calendar_frame, textvariable=self.calendar_coverage_var
        )
        self.calendar_coverage_label.grid(
            row=1, column=0, columnspan=3, padx=4, pady=2, sticky="w"
        )

        self.calendar_build_button = ttk.Button(
            calendar_frame,
            text="カレンダー再生成",
            command=self._on_build_calendar_clicked,
        )
        self.calendar_build_button.grid(row=1, column=3, padx=4, pady=2, sticky="e")

        self._refresh_calendar_coverage()

    def _on_hotel_changed(self, event=None) -> None:
        self._refresh_calendar_coverage()

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
        self.df_hotel_var = tk.StringVar(value=DEFAULT_HOTEL)
        hotel_combo = ttk.Combobox(form, textvariable=self.df_hotel_var, state="readonly")
        hotel_combo["values"] = list(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)
        hotel_combo.bind("<<ComboboxSelected>>", self._on_df_hotel_changed)

        # 対象月
        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.df_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.df_month_var, width=8).grid(
            row=0, column=3, padx=4, pady=2
        )

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
        ttk.Label(form, textvariable=self.df_latest_asof_var, width=12).grid(
            row=0, column=7, padx=4, pady=2, sticky="w"
        )
        ttk.Button(form, text="最新に反映", command=self._on_df_set_asof_to_latest).grid(
            row=0, column=8, padx=4, pady=2, sticky="w"
        )

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
        fc_cap, occ_cap = self._get_daily_caps_for_hotel(DEFAULT_HOTEL)

        ttk.Label(form, text="予測キャップ:").grid(row=1, column=2, sticky="w")
        self.df_forecast_cap_var = tk.StringVar(value=str(fc_cap))
        ttk.Entry(form, textvariable=self.df_forecast_cap_var, width=6).grid(
            row=1, column=3, padx=4, pady=2
        )

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
        ttk.Entry(form, textvariable=self.df_occ_cap_var, width=6).grid(
            row=1, column=7, padx=4, pady=2
        )

        # テーブル用コンテナ
        table_container = ttk.Frame(frame)
        table_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        columns = [
            "stay_date",
            "weekday",
            "actual_rooms",
            "forecast_rooms",
            "diff_rooms",
            "diff_pct",
            "occ_actual_pct",
            "occ_forecast_pct",
        ]

        self.df_tree = ttk.Treeview(
            table_container, columns=columns, show="headings", height=25
        )
        for col in columns:
            header = col
            if col == "stay_date":
                width = 100
                anchor = "center"
            elif col == "weekday":
                width = 70
                anchor = "center"
            elif col in ("actual_rooms", "forecast_rooms", "diff_rooms"):
                width = 90
                anchor = "e"
            elif col in ("diff_pct", "occ_actual_pct", "occ_forecast_pct"):
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

        # セル選択状態
        self._df_cell_anchor = None
        self._df_cell_end = None

        # クリック / Shift+クリック / コピー
        self.df_tree.bind("<Button-1>", self._on_df_tree_click, add="+")
        self.df_tree.bind("<Shift-Button-1>", self._on_df_tree_shift_click, add="+")
        self.df_tree.bind("<Control-c>", self._on_df_tree_copy, add="+")

        self._update_df_latest_asof_label(update_asof_if_empty=True)

    def _update_df_latest_asof_label(self, update_asof_if_empty: bool = False) -> None:
        hotel = self.df_hotel_var.get().strip()
        try:
            latest = get_latest_asof_for_hotel(hotel)
        except Exception:
            self.df_latest_asof_var.set("(未取得)")
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
        if latest:
            try:
                latest_ts = pd.to_datetime(latest)
            except Exception:
                latest_ts = None

            if latest_ts is not None:
                if asof_ts > latest_ts:
                    messagebox.showerror(
                        "エラー",
                        f"AS OF が最新データ ({latest}) を超えています。\n"
                        f"{latest} 以前の日付を指定してください。",
                    )
                    return
                elif asof_ts < latest_ts:
                    use_latest = messagebox.askyesno(
                        "確認",
                        f"最新ASOF は {latest} です。\n"
                        f"選択中の ASOF ({asof}) で Forecast を実行しますか？\n\n"
                        f"最新ASOFで実行する場合は『はい』を選択してください。",
                    )
                    if use_latest:
                        asof_ts = latest_ts
                        asof = latest_ts.strftime("%Y-%m-%d")
                        self.df_asof_var.set(asof)

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

        self._df_cell_anchor = None
        self._df_cell_end = None
        self._clear_df_selection_rect()

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
            # 数値のままだと分かりにくいので、0-6 は "Mon".."Sun" にしてもよい
            if isinstance(weekday, (int, float)) and not pd.isna(weekday):
                weekday_str = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(weekday)]
            else:
                weekday_str = str(weekday)

            values = [
                stay_str,
                weekday_str,
                _fmt_num(row.get("actual_rooms")),
                _fmt_num(row.get("forecast_rooms")),
                _fmt_num(row.get("diff_rooms")),
                _fmt_pct(row.get("diff_pct")),
                _fmt_pct(row.get("occ_actual_pct")),
                _fmt_pct(row.get("occ_forecast_pct")),
            ]
            tags: tuple[str, ...] = ()
            if idx % 2 == 1:
                tags = ("oddrow",)

            self.df_tree.insert("", tk.END, values=values, tags=tags)

        self.df_daily_forecast_df = df
        self.df_table_df = df

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

    def _on_df_tree_copy(self, event=None) -> None:
        """選択セル範囲をTSV形式でクリップボードにコピーする。"""
        if self._df_cell_anchor is None or self._df_cell_end is None:
            return

        rows = list(self.df_tree.get_children(""))
        if not rows:
            return

        a_r, a_c = self._df_get_row_col_index(*self._df_cell_anchor)
        e_r, e_c = self._df_get_row_col_index(*self._df_cell_end)
        if a_r < 0 or e_r < 0 or a_c < 0 or e_c < 0:
            return

        r_lo, r_hi = sorted((a_r, e_r))
        c_lo, c_hi = sorted((a_c, e_c))
        columns = list(self.df_tree["columns"])

        lines: list[str] = []
        for r_idx in range(r_lo, r_hi + 1):
            row_id = rows[r_idx]
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

    # =========================
    # 4) モデル評価タブ
    # =========================
    def _init_model_eval_tab(self) -> None:
        frame = self.tab_model_eval

        top = ttk.Frame(frame)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(top, text="ホテル:").grid(row=0, column=0, sticky="w")
        self.me_hotel_var = tk.StringVar(value=DEFAULT_HOTEL)
        hotel_combo = ttk.Combobox(top, textvariable=self.me_hotel_var, state="readonly")
        hotel_combo["values"] = list(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)

        run_btn = ttk.Button(top, text="評価読み込み", command=self._on_load_model_eval)
        run_btn.grid(row=0, column=2, padx=4, pady=2)

        ttk.Label(top, text="開始月(YYYYMM):").grid(row=0, column=3, sticky="w", padx=(8, 4))
        ttk.Entry(top, textvariable=self.me_from_var, width=8).grid(row=0, column=4, padx=4, pady=2)

        ttk.Label(top, text="終了月(YYYYMM):").grid(row=0, column=5, sticky="w", padx=(8, 4))
        ttk.Entry(top, textvariable=self.me_to_var, width=8).grid(row=0, column=6, padx=4, pady=2)

        ttk.Button(top, text="直近12ヶ月", command=self._on_me_last12_clicked).grid(
            row=0, column=7, padx=4, pady=2
        )
        ttk.Button(top, text="CSV出力", command=self._on_export_model_eval_csv).grid(
            row=0, column=8, padx=4, pady=2
        )

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

    def _on_load_model_eval(self) -> None:
        try:
            hotel = self.me_hotel_var.get()
            df = get_model_evaluation_table(hotel)
            best_idx = set()
            tmp = df[df["target_month"] != "TOTAL"].dropna(subset=["mae_pct"])
            for _, grp in tmp.groupby("target_month", sort=False):
                row = grp.loc[grp["mae_pct"].idxmin()]
                best_idx.add(row.name)
            self.model_eval_df = df
            self.model_eval_best_idx = best_idx
        except Exception as e:
            messagebox.showerror("エラー", f"モデル評価読み込みに失敗しました:\n{e}")
            return

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
        if self.model_eval_df is None:
            self._on_load_model_eval()

        if self.model_eval_df is None or self.model_eval_df.empty:
            return

        df_body = self.model_eval_df[self.model_eval_df["target_month"] != "TOTAL"].copy()

        def _to_int_ym(val):
            try:
                return int(val)
            except Exception:
                return None

        df_body["target_month_int"] = df_body["target_month"].map(_to_int_ym)
        df_body = df_body[~df_body["target_month_int"].isna()]
        if df_body.empty:
            return

        latest_int = int(df_body["target_month_int"].max())

        def _add_months(ym_int: int, offset: int) -> int:
            s = f"{ym_int:06d}"
            y = int(s[:4])
            m = int(s[4:])
            total = y * 12 + (m - 1) + offset
            y2 = total // 12
            m2 = total % 12 + 1
            return int(f"{y2}{m2:02d}")

        start_int = _add_months(latest_int, -11)
        self.me_from_var.set(f"{start_int:06d}")
        self.me_to_var.set(f"{latest_int:06d}")

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

        self.asof_hotel_var = tk.StringVar(value=DEFAULT_HOTEL)
        ttk.Label(top, text="ホテル:").grid(row=0, column=0, sticky="w")
        hotel_combo = ttk.Combobox(top, textvariable=self.asof_hotel_var, state="readonly")
        hotel_combo["values"] = list(HOTEL_CONFIG.keys())
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
            values=["(すべて)", "M-1_END", "M10", "M20"],
            width=10,
        )
        asof_filter_combo.grid(row=0, column=9, padx=4, pady=2, sticky="w")
        asof_filter_combo.bind("<<ComboboxSelected>>", lambda *_: self._refresh_asof_eval_tables())

        ttk.Button(top, text="CSV出力(サマリ)", command=self._on_export_asof_overview_csv).grid(
            row=0, column=10, padx=4, pady=2
        )
        ttk.Button(top, text="CSV出力(月別ログ)", command=self._on_export_asof_detail_csv).grid(
            row=0, column=11, padx=4, pady=2
        )

        # ASOF別サマリテーブル
        overview_frame = ttk.LabelFrame(frame, text="ASOF別サマリ")
        overview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        columns = ["model", "asof_type", "mean_error_pct", "mae_pct", "rmse_pct", "n_samples"]
        self.asof_overview_tree = ttk.Treeview(
            overview_frame, columns=columns, show="headings", height=8
        )
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
        self.asof_detail_tree = ttk.Treeview(
            detail_frame, columns=detail_columns, show="headings", height=12
        )
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

            overview_df = get_eval_overview_by_asof(hotel, from_ym=from_ym, to_ym=to_ym)
            detail_df = get_eval_monthly_by_asof(hotel, from_ym=from_ym, to_ym=to_ym)
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
        self.bc_hotel_var = tk.StringVar(value=DEFAULT_HOTEL)
        hotel_combo = ttk.Combobox(form, textvariable=self.bc_hotel_var, state="readonly")
        hotel_combo["values"] = list(HOTEL_CONFIG.keys())
        hotel_combo.grid(row=0, column=1, padx=4, pady=2)
        hotel_combo.bind("<<ComboboxSelected>>", self._on_bc_hotel_changed)

        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.bc_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.bc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(form, text="曜日:").grid(row=0, column=4, sticky="w")
        self.bc_weekday_var = tk.StringVar(value="5:Sat")
        weekday_combo = ttk.Combobox(
            form, textvariable=self.bc_weekday_var, state="readonly", width=7
        )
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
        ttk.Label(form, textvariable=self.bc_latest_asof_var, width=12).grid(
            row=1, column=3, padx=4, pady=(4, 2), sticky="w"
        )
        ttk.Button(form, text="最新に反映", command=self._on_bc_set_asof_to_latest).grid(
            row=1, column=4, padx=4, pady=(4, 2), sticky="w"
        )

        ttk.Label(form, text="モデル:").grid(row=1, column=5, sticky="w", pady=(4, 2))
        self.bc_model_var = tk.StringVar(value="recent90w")
        model_combo = ttk.Combobox(form, textvariable=self.bc_model_var, state="readonly", width=12)
        model_combo["values"] = ["avg", "recent90", "recent90w"]
        model_combo.grid(row=1, column=6, padx=4, pady=(4, 2))

        fc_cap, _ = self._get_daily_caps_for_hotel(DEFAULT_HOTEL)
        self.bc_forecast_cap_var = tk.StringVar(value=str(fc_cap))
        ttk.Label(form, text="予測キャップ:").grid(row=1, column=11, sticky="w", pady=(4, 2))
        ttk.Entry(form, textvariable=self.bc_forecast_cap_var, width=6).grid(
            row=1, column=12, padx=2, pady=(4, 2), sticky="w"
        )

        save_btn = ttk.Button(form, text="PNG保存", command=self._on_save_booking_curve_png)
        save_btn.grid(row=1, column=7, padx=4, pady=(4, 2))

        nav_frame = ttk.Frame(form)
        nav_frame.grid(row=2, column=2, columnspan=8, sticky="w", pady=(4, 0))

        nav_left = ttk.Frame(nav_frame)
        nav_left.pack(side=tk.LEFT)
        nav_right = ttk.Frame(nav_frame)
        nav_right.pack(side=tk.LEFT, padx=16)

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

        self.btn_build_lt = ttk.Button(
            nav_right, text="LT_DATA(4ヶ月)", command=self._on_build_lt_data
        )
        self.btn_build_lt.pack(side=tk.LEFT, padx=4)

        self.btn_build_lt_range = ttk.Button(
            nav_right, text="LT_DATA(期間指定)", command=self._on_build_lt_data_range
        )
        self.btn_build_lt_range.pack(side=tk.LEFT, padx=4)

        draw_btn = ttk.Button(nav_right, text="描画", command=self._on_draw_booking_curve)
        draw_btn.pack(side=tk.LEFT, padx=8)

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
        filename = (
            f"booking_curve_{hotel_tag}_{target_month}_"
            f"wd{weekday_int}_{model}_asof_{asof_tag}.png"
        )
        out_path = OUTPUT_DIR / filename

        try:
            self.bc_fig.savefig(out_path, dpi=150, bbox_inches="tight")
        except Exception as e:
            messagebox.showerror("Error", f"PNG保存に失敗しました:\n{e}")
            return

        messagebox.showinfo("保存完了", f"PNG を保存しました:\n{out_path}")

    def _on_build_lt_data(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        base_ym = self.bc_month_var.get().strip()

        if len(base_ym) != 6 or not base_ym.isdigit():
            messagebox.showerror(
                "LT_DATA生成エラー", "対象月は 6桁の数字 (YYYYMM) で入力してください。"
            )
            return

        try:
            base_period = pd.Period(f"{base_ym[:4]}-{base_ym[4:]}", freq="M")
        except Exception:
            messagebox.showerror(
                "LT_DATA生成エラー", "対象月は 6桁の数字 (YYYYMM) で入力してください。"
            )
            return

        target_months = [(base_period + i).strftime("%Y%m") for i in range(4)]

        confirm = messagebox.askokcancel(
            "LT_DATA生成確認",
            f"{hotel_tag} の LT_DATA を {target_months[0]}〜{target_months[-1]} で再生成します。よろしいですか？",
        )
        if not confirm:
            return

        try:
            run_build_lt_data_for_gui(hotel_tag, target_months)
        except Exception as e:
            messagebox.showerror(
                "LT_DATA生成エラー",
                f"LT_DATA生成でエラーが発生しました。\n{e}",
            )
            return

        messagebox.showinfo(
            "LT_DATA生成",
            "LT_DATA CSV の生成が完了しました。\n"
            f"対象月: {', '.join(target_months)}\n"
            "必要に応じて「最新に反映」ボタンで ASOF を更新してください。",
        )

    def _ask_month_range(
        self, initial_start: str, initial_end: str | None = None
    ) -> tuple[str, str] | None:
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
            messagebox.showerror(
                "LT_DATA生成エラー", "開始月と終了月は YYYYMM 形式で入力してください。"
            )
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
            f"{hotel_tag} の LT_DATA を\n"
            f"{target_months[0]}〜{target_months[-1]} の {len(target_months)}ヶ月分で再生成します。\n"
            "よろしいですか？",
        )
        if not confirm:
            return

        try:
            run_build_lt_data_for_gui(hotel_tag, target_months)
        except Exception as e:
            messagebox.showerror(
                "LT_DATA生成エラー",
                f"LT_DATA生成でエラーが発生しました。\n{e}",
            )
            return

        messagebox.showinfo(
            "LT_DATA生成",
            "LT_DATA CSV の生成が完了しました。\n"
            f"対象月: {', '.join(target_months)}",
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
                    (
                        f"最新ASOF は {latest_str} です。\n"
                        f"選択中の ASOF ({as_of_date}) は最新より未来の日付です。\n\n"
                        "最新ASOFに変更して描画しますか？"
                    ),
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
            avg_series = (
                df_week.mean(axis=0, skipna=True) if not df_week.empty else pd.Series(dtype=float)
            )

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
        self.mc_hotel_var = tk.StringVar(value=DEFAULT_HOTEL)
        mc_combo = ttk.Combobox(form, textvariable=self.mc_hotel_var, state="readonly")
        mc_combo["values"] = list(HOTEL_CONFIG.keys())
        mc_combo.grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        current_month = date.today().strftime("%Y%m")
        self.mc_month_var = tk.StringVar(value=current_month)
        ttk.Entry(form, textvariable=self.mc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        self.mc_show_prev_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="前年同月を重ねる", variable=self.mc_show_prev_var).grid(
            row=0, column=4, padx=8, pady=2, sticky="w"
        )

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

        def load_month_df(month_str: str) -> pd.DataFrame:
            """月次カーブ用DFを読み込み、LT・ACT情報を更新する。"""
            nonlocal max_lt, has_act

            df = get_monthly_curve_data(
                hotel_tag=hotel_tag,
                target_month=month_str,
                as_of_date=None,  # ASOF trimming is now done at plotting time
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
            except FileNotFoundError:
                # その月のCSVが無ければスキップ
                continue
            except Exception as e:
                messagebox.showerror(
                    "Error",
                    f"月次カーブ取得に失敗しました: {month_str}\n{e}",
                )
                return

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
                except FileNotFoundError:
                    continue
                except Exception as e:
                    messagebox.showerror(
                        "Error",
                        f"前年同月の取得に失敗しました: {prev_month_str}\n{e}",
                    )
                    return

                if df_prev is not None and not df_prev.empty:
                    color = line_colors[min(idx, len(line_colors) - 1)]
                    curves.append((f"{prev_month_str} (prev)", df_prev, color, "--", 1.6))

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
            return

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

            # --- ASOF-based line cut for not-yet-landed months ---
            # Use the first 6 characters of the label as YYYYMM (e.g. "202512").
            if asof_ts is not None:
                month_tag = label[:6]
                try:
                    p = pd.Period(month_tag, freq="M")
                except Exception:
                    p = None

                if p is not None:
                    month_end = p.to_timestamp(how="end").normalize()
                    delta_days = (month_end - asof_ts).days

                    # If delta_days > 0, ASOF is before the end of this month,
                    # so we should hide LT < delta_days and ACT(-1).
                    if delta_days > 0:
                        mask_index = []
                        for lt in lt_order:
                            if lt == -1:
                                # Always hide ACT for not-yet-landed months
                                mask_index.append(True)
                            else:
                                # Hide LT positions that correspond to dates
                                # after the ASOF for the month-end side.
                                mask_index.append(lt < delta_days)

                        # Apply the mask: positions with True become NaN.
                        y_ordered = y_ordered.copy()
                        y_ordered = y_ordered.mask(mask_index)

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
        self.mc_ax.set_title(f"Monthly booking curve {ym[:4]}-{ym[4:]} (all)")

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
