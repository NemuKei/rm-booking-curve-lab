from __future__ import annotations

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
    get_model_evaluation_table,
    get_monthly_curve_data,
    HOTEL_CONFIG,
)
from booking_curve.plot_booking_curve import LEAD_TIME_PITCHES

# デフォルトホテル (現状は大国町のみ想定)
DEFAULT_HOTEL = next(iter(HOTEL_CONFIG.keys()), "daikokucho")


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

        ttk.Label(form, text="対象月 (YYYYMM):").grid(row=0, column=2, sticky="w")
        self.bc_month_var = tk.StringVar(value="202506")
        ttk.Entry(form, textvariable=self.bc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(form, text="曜日:").grid(row=0, column=4, sticky="w")
        self.bc_weekday_var = tk.StringVar(value="5:Sat")
        weekday_combo = ttk.Combobox(form, textvariable=self.bc_weekday_var, state="readonly", width=8)
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

        ttk.Label(form, text="AS OF (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.bc_asof_var = tk.StringVar(value="2025-06-20")
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

        ttk.Label(form, text="モデル:").grid(row=1, column=2, sticky="w", pady=(4, 2))
        self.bc_model_var = tk.StringVar(value="recent90")
        model_combo = ttk.Combobox(form, textvariable=self.bc_model_var, state="readonly", width=12)
        model_combo["values"] = ["avg", "recent90", "recent90w"]
        model_combo.grid(row=1, column=3, padx=4, pady=(4, 2))

        draw_btn = ttk.Button(form, text="描画", command=self._on_draw_booking_curve)
        draw_btn.grid(row=1, column=5, padx=4, pady=(4, 2))

        plot_frame = ttk.Frame(frame)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.bc_fig = Figure(figsize=(10, 5))
        self.bc_ax = self.bc_fig.add_subplot(111)
        self.bc_ax.text(0.5, 0.5, "No data", ha="center", va="center")
        self.bc_ax.set_axis_off()
        self.bc_canvas = FigureCanvasTkAgg(self.bc_fig, master=plot_frame)
        self.bc_canvas.draw()
        self.bc_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _on_draw_booking_curve(self) -> None:
        hotel_tag = self.bc_hotel_var.get()
        target_month = self.bc_month_var.get().strip()
        weekday_label = self.bc_weekday_var.get().strip()
        as_of_date = self.bc_asof_var.get().strip()
        model = self.bc_model_var.get().strip()

        try:
            weekday_int = int(weekday_label.split(":")[0])
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

        if not avg_series.empty:
            avg_series.index = [int(i) for i in avg_series.index]
            avg_series = avg_series.reindex(LEAD_TIME_PITCHES)

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

            if avg_series is None or avg_series.empty:
                continue

            y_array = np.array(y_values, dtype=float)

            last_idx = None
            for idx in range(len(LEAD_TIME_PITCHES) - 1, -1, -1):
                if not np.isnan(y_array[idx]):
                    last_idx = idx
                    break

            if last_idx is None or last_idx == len(LEAD_TIME_PITCHES) - 1:
                continue

            base_lt = LEAD_TIME_PITCHES[last_idx]
            base_actual = y_array[last_idx]
            base_model = avg_series.get(base_lt, np.nan)

            if np.isnan(base_actual) or np.isnan(base_model):
                continue

            y_dash = [np.nan] * len(LEAD_TIME_PITCHES)
            for j in range(last_idx + 1, len(LEAD_TIME_PITCHES)):
                lt = LEAD_TIME_PITCHES[j]
                model_val = avg_series.get(lt, np.nan)
                if np.isnan(model_val):
                    continue
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

        self.bc_ax.set_ylabel("Rooms")
        self.bc_ax.set_ylim(0, 180)
        self.bc_ax.set_yticks(range(0, 181, 20))
        self.bc_ax.set_yticks(range(0, 181, 10), minor=True)

        if len(target_month) == 6 and target_month.isdigit():
            title_month = f"{target_month[:4]}-{target_month[4:]}"
        else:
            title_month = target_month
        self.bc_ax.set_title(f"{title_month} Booking Curve")

        self.bc_ax.grid(axis="y", which="major", linestyle="--", alpha=0.3)
        self.bc_ax.grid(axis="y", which="minor", linestyle=":", alpha=0.15)
        self.bc_ax.grid(axis="x", which="major", linestyle=":", alpha=0.15)

        self.bc_ax.legend(bbox_to_anchor=(1.02, 1.0), loc="upper left")

        self.bc_canvas.draw()

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
        self.mc_month_var = tk.StringVar(value="202502")
        ttk.Entry(form, textvariable=self.mc_month_var, width=8).grid(row=0, column=3, padx=4, pady=2)

        self.mc_show_prev_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="前年同月を重ねる", variable=self.mc_show_prev_var).grid(
            row=0, column=4, padx=8, pady=2, sticky="w"
        )

        draw_btn = ttk.Button(form, text="描画", command=self._on_draw_monthly_curve)
        draw_btn.grid(row=0, column=5, padx=4, pady=2)

        plot_frame = ttk.Frame(frame)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.mc_fig = Figure(figsize=(10, 5))
        self.mc_ax = self.mc_fig.add_subplot(111)
        self.mc_ax.text(0.5, 0.5, "No data", ha="center", va="center")
        self.mc_ax.set_axis_off()
        self.mc_canvas = FigureCanvasTkAgg(self.mc_fig, master=plot_frame)
        self.mc_canvas.draw()
        self.mc_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _on_draw_monthly_curve(self) -> None:
        hotel_tag = self.mc_hotel_var.get()
        target_month = self.mc_month_var.get().strip()
        show_prev = bool(self.mc_show_prev_var.get())

        try:
            df = get_monthly_curve_data(hotel_tag, target_month)
        except Exception as e:
            messagebox.showerror("Error", f"月次カーブ取得に失敗しました: {e}")
            return

        if "rooms_total" in df.columns:
            y = df["rooms_total"]
        else:
            y = df.iloc[:, 0]

        x = df.index
        x_num = np.arange(len(df))
        x_labels = [str(v) for v in x]

        self.mc_ax.clear()
        self.mc_ax.plot(x_num, y.values, label=target_month, linewidth=2.0)

        if show_prev:
            if len(target_month) == 6 and target_month.isdigit():
                prev_year = int(target_month[:4]) - 1
                prev_month = f"{prev_year}{target_month[4:]}"
                try:
                    df_prev = get_monthly_curve_data(hotel_tag, prev_month)
                    if "rooms_total" in df_prev.columns:
                        y_prev = df_prev["rooms_total"]
                    else:
                        y_prev = df_prev.iloc[:, 0]
                    x_prev_num = np.arange(len(df_prev))
                    self.mc_ax.plot(
                        x_prev_num,
                        y_prev.values,
                        linestyle="--",
                        linewidth=1.8,
                        label=prev_month,
                    )
                except FileNotFoundError:
                    pass
                except Exception as e:
                    messagebox.showerror("Error", f"前年同月の取得に失敗しました: {e}")
            else:
                pass

        self.mc_ax.set_xlabel("Lead Time (days)")
        self.mc_ax.set_ylabel("Rooms (monthly cumulative)")

        if len(target_month) == 6 and target_month.isdigit():
            title_month = f"{target_month[:4]}-{target_month[4:]}"
        else:
            title_month = target_month
        self.mc_ax.set_title(f"Monthly booking curve {title_month} (all)")

        self.mc_ax.set_xticks(x_num)
        self.mc_ax.set_xticklabels(x_labels, rotation=90)

        max_y = float(y.max()) if len(y) > 0 else 0.0
        if max_y > 0:
            self.mc_ax.set_ylim(0, max_y * 1.1)

        self.mc_ax.grid(True, linestyle=":", linewidth=0.5)
        self.mc_ax.legend(loc="best")

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
