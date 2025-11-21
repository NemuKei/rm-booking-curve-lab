from __future__ import annotations

import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# プロジェクト内モジュール
from booking_curve.gui_backend import (
    get_daily_forecast_table,
    get_model_evaluation_table,
    HOTEL_CONFIG,
)

# デフォルトホテル (現状は大国町のみ想定)
DEFAULT_HOTEL = "daikokucho"


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

        self._init_daily_forecast_tab()
        self._init_model_eval_tab()
        self._init_booking_curve_tab()
        self._init_monthly_curve_tab()

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

        # 対象月
        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        self.df_month_var = tk.StringVar(value="202506")
        ttk.Entry(form, textvariable=self.df_month_var, width=8).grid(
            row=0, column=3, padx=4, pady=2
        )

        # as_of
        ttk.Label(form, text="AS OF (YYYY-MM-DD):").grid(row=0, column=4, sticky="w")
        self.df_asof_var = tk.StringVar(value="2025-06-20")
        ttk.Entry(form, textvariable=self.df_asof_var, width=12).grid(
            row=0, column=5, padx=4, pady=2
        )

        # モデル
        ttk.Label(form, text="モデル:").grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.df_model_var = tk.StringVar(value="recent90_adj")
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

        # キャパシティ
        ttk.Label(form, text="キャパシティ:").grid(row=1, column=2, sticky="w")
        default_cap = HOTEL_CONFIG.get(DEFAULT_HOTEL, {}).get("capacity", 168.0)
        self.df_capacity_var = tk.StringVar(value=str(default_cap))
        ttk.Entry(form, textvariable=self.df_capacity_var, width=6).grid(
            row=1, column=3, padx=4, pady=2
        )

        # 実行ボタン
        run_btn = ttk.Button(form, text="読み込み", command=self._on_load_daily_forecast)
        run_btn.grid(row=1, column=5, padx=4, pady=2, sticky="e")

        # Treeview (テーブル)
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
        self.df_tree = ttk.Treeview(frame, columns=columns, show="headings", height=25)
        for col in columns:
            self.df_tree.heading(col, text=col)
            self.df_tree.column(col, width=120, anchor="e")

        self.df_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        # スクロールバー
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.df_tree.yview)
        self.df_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_load_daily_forecast(self) -> None:
        try:
            hotel = self.df_hotel_var.get()
            month = self.df_month_var.get()
            asof = self.df_asof_var.get()
            model = self.df_model_var.get()
            capacity = float(self.df_capacity_var.get())

            df = get_daily_forecast_table(
                hotel_tag=hotel,
                target_month=month,
                as_of_date=asof,
                gui_model=model,
                capacity=capacity,
            )
        except Exception as e:
            messagebox.showerror("エラー", f"日別フォーキャスト読み込みに失敗しました:\n{e}")
            return

        # 既存行クリア
        for row_id in self.df_tree.get_children():
            self.df_tree.delete(row_id)

        # DataFrame を Treeview に流し込む
        for _, row in df.iterrows():
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
            self.df_tree.insert("", tk.END, values=values)

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
    # 1) ブッキングカーブタブ (枠だけ)
    # =========================
    def _init_booking_curve_tab(self) -> None:
        frame = self.tab_booking_curve

        info = ttk.Label(
            frame,
            text="ブッキングカーブ画面は今後実装予定です。\n"
                 "曜日別LTカーブ + 3ヶ月平均 + 予測線を表示するタブになります。",
            justify="left",
        )
        info.pack(side=tk.TOP, anchor="w", padx=8, pady=8)

        self._add_placeholder_plot(frame, "Booking Curve Preview")

    # =========================
    # 2) 月次カーブタブ (枠だけ)
    # =========================
    def _init_monthly_curve_tab(self) -> None:
        frame = self.tab_monthly_curve

        info = ttk.Label(
            frame,
            text="月次ブッキングカーブ画面は今後実装予定です。\n"
                 "120〜ACT の月次カーブと、前年同月を重ねるオプションを想定しています。",
            justify="left",
        )
        info.pack(side=tk.TOP, anchor="w", padx=8, pady=8)

        self._add_placeholder_plot(frame, "Monthly Curve Preview")

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
