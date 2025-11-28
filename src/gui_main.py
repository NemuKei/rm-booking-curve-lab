from __future__ import annotations

from datetime import date
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
    get_model_evaluation_table,
    get_monthly_curve_data,
    OUTPUT_DIR,
    HOTEL_CONFIG,
    run_forecast_for_gui,
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

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        # タブ作成
        self.tab_booking_curve = ttk.Frame(notebook)
        self.tab_monthly_curve = ttk.Frame(notebook)
        self.tab_daily_forecast = ttk.Frame(notebook)
        self.tab_model_eval = ttk.Frame(notebook)

        notebook.add(self.tab_booking_curve, text="ブッキングカーブ")
        notebook.add(self.tab_monthly_curve, text="月次カーブ")
        notebook.add(self.tab_daily_forecast, text="日別フォーキャスト")
        notebook.add(self.tab_model_eval, text="モデル評価")

        self._settings = self._load_settings()

        self._init_daily_forecast_tab()
        self._init_model_eval_tab()
        self._init_booking_curve_tab()
        self._init_monthly_curve_tab()

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

        columns = ["target_month", "model", "mean_error_pct", "mae_pct"]
        self.me_tree = ttk.Treeview(frame, columns=columns, show="headings", height=25)
        for col in columns:
            self.me_tree.heading(col, text=col)
            self.me_tree.column(col, width=150, anchor="e")
        self.me_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.me_tree.yview)
        self.me_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_load_model_eval(self) -> None:
        try:
            hotel = self.me_hotel_var.get()
            df = get_model_evaluation_table(hotel)
        except Exception as e:
            messagebox.showerror("エラー", f"モデル評価読み込みに失敗しました:\n{e}")
            return

        for row_id in self.me_tree.get_children():
            self.me_tree.delete(row_id)

        for _, row in df.iterrows():
            values = [
                str(row.get("target_month")),
                str(row.get("model")),
                _fmt_pct(row.get("mean_error_pct")),
                _fmt_pct(row.get("mae_pct")),
            ]
            self.me_tree.insert("", tk.END, values=values)

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
        hotel_combo.bind("<<ComboboxSelected>>", lambda e: self._update_bc_latest_asof_label(False))

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

        save_btn = ttk.Button(form, text="PNG保存", command=self._on_save_booking_curve_png)
        save_btn.grid(row=1, column=7, padx=4, pady=(4, 2))

        draw_btn = ttk.Button(form, text="描画", command=self._on_draw_booking_curve)
        draw_btn.grid(row=1, column=8, padx=4, pady=(4, 2))

        nav_frame = ttk.Frame(form)
        nav_frame.grid(row=2, column=2, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Label(nav_frame, text="月移動:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            nav_frame,
            text="-1Y",
            command=lambda: self._on_bc_shift_month(-12),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="-1M",
            command=lambda: self._on_bc_shift_month(-1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1M",
            command=lambda: self._on_bc_shift_month(+1),
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            nav_frame,
            text="+1Y",
            command=lambda: self._on_bc_shift_month(+12),
        ).pack(side=tk.LEFT, padx=2)

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

    def _on_draw_booking_curve(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        target_month = self.bc_month_var.get().strip()
        weekday_label = self.bc_weekday_var.get().strip()
        weekday_parts = weekday_label.split(":", 1)
        weekday_text = weekday_parts[1].strip() if len(weekday_parts) == 2 else weekday_label
        as_of_date = self.bc_asof_var.get().strip()
        model = self.bc_model_var.get().strip()

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

            self.bc_ax.plot(
                x_positions,
                y_dash,
                color=color,
                linestyle="--",
                linewidth=1.4,
                alpha=0.8,
            )

        y_avg = [avg_series.get(lt, np.nan) for lt in LEAD_TIME_PITCHES]
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
        raw_max = capacity * 1.10
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

            df = get_monthly_curve_data(hotel_tag, month_str)

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
