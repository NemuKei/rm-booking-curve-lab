from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from booking_curve.config import get_hotel_output_dir

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"
TARGET_MONTH = "202502"  # 例: 2025年2月のブッキングカーブを見たい場合

# 集計対象の LT 範囲（ACT=-1 も含める）
LT_MIN = -1
LT_MAX = 120

# 図の保存/表示の制御
SAVE_FIG = True  # True のとき output_path が指定されていれば PNG 保存
SHOW_FIG = True  # True のとき plt.show() でウィンドウ表示

# 集計方法: "mean" または "sum"
AGG_METHOD = "sum"

# 曜日フィルタ: None の場合は全日、0〜6 で月〜日のみを対象とする
WEEKDAY_FILTER = None  # 例: 4 (金曜だけ) にすると金曜だけで月次カーブを作れる

# 月次合計モード（AGG_METHOD=="sum"）のときのY軸設定
Y_MAX_SUM = 5000  # このホテルの想定上限（必要に応じて手動変更）
Y_TICK_STEP_SUM = 500  # 目盛り間隔
# ===== 設定ここまで =====

# リードタイムのピッチ（既存Excelと同じ）
LEAD_TIME_PITCHES = [
    90,
    84,
    78,
    72,
    67,
    60,
    53,
    46,
    39,
    32,
    29,
    26,
    23,
    20,
    18,
    17,
    16,
    15,
    14,
    13,
    12,
    11,
    10,
    9,
    8,
    7,
    6,
    5,
    4,
    3,
    2,
    1,
    0,
    -1,
]


def load_lt_data() -> pd.DataFrame:
    """
    対象月の LT_DATA CSV を読み込んで DataFrame を返す。
    index: 宿泊日 (DatetimeIndex)
    columns: LT (int 変換可能な列のみを使う)
    """
    file_name = f"lt_data_{TARGET_MONTH}.csv"
    path = get_hotel_output_dir(HOTEL_TAG) / file_name
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index)

    # LT 列だけに絞り、列名を int に揃える
    lt_cols = {}
    for col in df.columns:
        try:
            lt = int(col)
        except Exception:
            continue
        lt_cols[col] = lt

    if not lt_cols:
        raise ValueError("LT 列が見つかりませんでした。")

    df_lt = df[list(lt_cols.keys())].copy()
    df_lt.columns = [lt_cols[c] for c in df_lt.columns]
    return df_lt


def compute_monthly_curve(
    df_lt: pd.DataFrame,
    lt_min: int = LT_MIN,
    lt_max: int = LT_MAX,
    agg: str = AGG_METHOD,
    weekday_filter: int | None = WEEKDAY_FILTER,
) -> pd.Series:
    """
    宿泊日×LT の表から、月次ブッキングカーブ（LTごとの平均or合計）を作る。
    - df_lt: index=宿泊日(DatetimeIndex), columns=LT(int)
    - agg:
        "mean": 各 LT で宿泊日の平均室数
        "sum" : 各 LT で宿泊日の合計室数
    - weekday_filter:
        None の場合は全日、
        0〜6 の場合はその曜日の宿泊日のみ対象とする。
    """
    df = df_lt.copy()

    # 宿泊月で絞り込む（安全のため）
    month_str = TARGET_MONTH
    year = int(month_str[:4])
    month = int(month_str[4:])
    df = df[(df.index.year == year) & (df.index.month == month)]

    if weekday_filter is not None:
        df = df[df.index.weekday == weekday_filter]

    if df.empty:
        raise ValueError("対象条件の宿泊日がありません。")

    # 対象 LT 範囲で列を絞る
    valid_lts = [lt for lt in df.columns if lt_min <= lt <= lt_max]
    if not valid_lts:
        raise ValueError("指定LT範囲内の列がありません。")

    df_sub = df[valid_lts]

    if agg == "sum":
        curve = df_sub.sum(axis=0, skipna=True)
    else:
        curve = df_sub.mean(axis=0, skipna=True)

    curve = curve.astype(float)
    curve.index.name = "LT"

    # 指定LT範囲でフィルタして昇順ソート
    curve = curve[(curve.index >= lt_min) & (curve.index <= lt_max)]
    curve = curve.sort_index()

    return curve


def plot_monthly_curve(
    curve: pd.Series, title: str | None = None, output_path: Path | None = None
) -> None:
    """
    月次ブッキングカーブ Series をプロットする。
    x軸: LT（日）
    y軸: 室数（平均 or 合計）
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # x軸は LT、Excelと同じく「右側がACT(-1)」になるように反転する
    x = curve.index.values
    y = curve.values
    ax.plot(x, y, linewidth=2)

    ax.set_xlabel("リードタイム（日）")
    if AGG_METHOD == "sum":
        ax.set_ylabel("室数（合計）")
    else:
        ax.set_ylabel("室数（平均）")

    if AGG_METHOD == "sum":
        # 0〜Y_MAX_SUM の範囲で固定し、目盛りを Y_TICK_STEP_SUM ごとに打つ
        ax.set_ylim(0, Y_MAX_SUM)
        ax.set_yticks(list(range(0, Y_MAX_SUM + 1, Y_TICK_STEP_SUM)))
    # AGG_METHOD=="mean" のときは特に設定せず、Matplotlib の自動スケールに任せる

    if title:
        ax.set_title(title)

    # グリッドと軸の向き
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.invert_xaxis()  # LT が大きい方（120日）が左、小さい方（ACT）が右

    # x軸の目盛りとラベル設定: LT=-1 は "ACT" と表示
    xticks = list(curve.index.values)
    xticklabels = [str(lt) for lt in xticks]
    if -1 in curve.index:
        idx = xticks.index(-1)
        xticklabels[idx] = "ACT"
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=90, fontsize=8)

    plt.tight_layout()
    if SAVE_FIG and output_path is not None:
        plt.savefig(output_path, bbox_inches="tight")

    if SHOW_FIG:
        plt.show()
    else:
        plt.close(fig)


def main() -> None:
    df_lt = load_lt_data()
    curve = compute_monthly_curve(df_lt)

    if WEEKDAY_FILTER is None:
        wd_label = "all"
    else:
        wd_label = f"wd{WEEKDAY_FILTER}"

    title = f"Monthly booking curve {TARGET_MONTH} ({wd_label})"

    out_name = f"monthly_curve_{TARGET_MONTH}_{wd_label}.png"
    out_path = get_hotel_output_dir(HOTEL_TAG) / out_name

    plot_monthly_curve(curve, title=title, output_path=out_path)
    print(f"[OK] 保存しました: {out_path}")


if __name__ == "__main__":
    main()
