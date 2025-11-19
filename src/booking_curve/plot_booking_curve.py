import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt

# 日本語フォント & マイナス表示対策（Windows想定）
matplotlib.rcParams["font.family"] = "Meiryo"
matplotlib.rcParams["axes.unicode_minus"] = False

# X軸に使う LT ピッチ（カテゴリ）: 左から右へ 90,84,...,0,ACT(-1)
LEAD_TIME_PITCHES = [
    90, 84, 78, 72, 67, 60, 53, 46, 39, 32,
    29, 26, 23, 20, 18, 17, 16, 15, 14, 13,
    12, 11, 10, 9, 8, 7, 6, 5, 4, 3,
    2, 1, 0, -1,  # -1 は ACT
]


def filter_by_weekday(lt_df: pd.DataFrame, weekday: int) -> pd.DataFrame:
    """
    宿泊日インデックスの DataFrame から、指定 weekday の行だけを抽出する。

    weekday: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    """
    if lt_df.empty:
        return lt_df

    idx = pd.to_datetime(lt_df.index)
    mask = idx.weekday == weekday
    filtered = lt_df.loc[mask].copy()
    filtered.index = idx[mask]  # index を datetime64 に揃える
    return filtered


def compute_average_curve(lt_df: pd.DataFrame) -> pd.Series:
    """
    宿泊日 × LT の DataFrame から、LT ごとの平均カーブを計算する。

    戻り値:
        index = LT (列ラベルを int にしたもの)
        values = 平均室数 (NaN 無視)
    """
    if lt_df.empty:
        return pd.Series(dtype=float)

    # 列ラベルを LT(int) として扱う
    cols = [int(c) for c in lt_df.columns]
    df = lt_df.copy()
    df.columns = cols

    avg = df.mean(axis=0, skipna=True)
    avg.sort_index(inplace=True)
    return avg


def export_weekday_lt_table(
    lt_df: pd.DataFrame,
    weekday: int,
    output_path: str,
) -> None:
    """
    指定曜日の LT_DATA をそのまま CSV に書き出す補助関数。
    """
    idx = pd.to_datetime(lt_df.index)
    lt_df = lt_df.copy()
    lt_df.index = idx

    df_week = filter_by_weekday(lt_df, weekday=weekday)
    df_week.to_csv(output_path, index=True)


def plot_booking_curves_for_weekday(
    lt_df: pd.DataFrame,
    weekday: int,
    title: str = "",
    output_path: str | None = None,
    external_avg: pd.Series | None = None,
    external_avg_label: str = "3-month avg",
) -> None:
    """
    指定された LT_DATA (宿泊日 × LT) から、
    特定曜日のブッキングカーブを描画する。

    - 各宿泊日のカーブ: 細線、日付ごとに色分け
    - 平均カーブ:
        external_avg があればそれを使用（3ヶ月平均など）
        なければ df_week から当月平均を計算して使用
    - X軸: LEAD_TIME_PITCHES を等間隔カテゴリとして表示
    - Y軸: 0〜180、20刻み（10刻みの補助目盛＋グリッド）
    """
    if lt_df.empty:
        print("[WARN] lt_df is empty. Nothing to plot.")
        return

    # index を datetime に揃える
    lt_df = lt_df.copy()
    lt_df.index = pd.to_datetime(lt_df.index)

    # 指定曜日のみ抽出
    df_week = filter_by_weekday(lt_df, weekday=weekday)
    if df_week.empty:
        print(f"[WARN] No data for weekday={weekday}. Nothing to plot.")
        return

    # 列ラベルを LT(int) にそろえる
    df_week.columns = [int(c) for c in df_week.columns]

    # X 軸の準備（カテゴリインデックス）
    x_positions = np.arange(len(LEAD_TIME_PITCHES))
    x_labels = ["ACT" if lt == -1 else str(lt) for lt in LEAD_TIME_PITCHES]

    # 図と軸
    fig, ax = plt.subplots(figsize=(12, 5))

    # 日別ライン用のカラーパレット（落ち着いたトーン）
    line_colors = [
        "#4C72B0",  # muted blue
        "#DD8452",  # muted orange
        "#55A868",  # muted green
        "#C44E52",  # muted red
        "#8172B2",  # muted purple/pink-ish
    ]

    # 宿泊日を昇順にしてループ
    stay_dates = sorted(df_week.index)

    for i, stay_date in enumerate(stay_dates):
        color = line_colors[i % len(line_colors)]
        stay_row = df_week.loc[stay_date]

        # LEAD_TIME_PITCHES 順に y を並べる
        y_values = []
        for lt in LEAD_TIME_PITCHES:
            y_values.append(stay_row.get(lt, np.nan))

        # 凡例用ラベル（MM/DD）
        label = stay_date.strftime("%m/%d")

        ax.plot(
            x_positions,
            y_values,
            color=color,
            linewidth=1.8,
            alpha=0.9,
            label=label,
        )

    # 平均カーブ：外部から渡されていればそれを使用、なければ当月平均
    if external_avg is None:
        avg_series = compute_average_curve(df_week)
        avg_label = "Average curve"
    else:
        avg_series = external_avg
        avg_label = external_avg_label

    # LEAD_TIME_PITCHES に沿って y を並べる
    y_avg = [avg_series.get(lt, np.nan) for lt in LEAD_TIME_PITCHES]

    avg_color = "#1F3F75"
    ax.plot(
        x_positions,
        y_avg,
        color=avg_color,
        linewidth=4.5,
        alpha=0.2,  # 太くてかなり透過
        label=avg_label,
    )

    # X軸の設定
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel("Lead Time (days)")

    # Y軸の設定：0〜180、20刻み & 10刻みの補助目盛
    ax.set_ylabel("Rooms")
    ax.set_ylim(0, 180)
    ax.set_yticks(range(0, 181, 20))         # 主メモリ
    ax.set_yticks(range(0, 181, 10), minor=True)  # 補助メモリ

    # グリッド
    ax.grid(axis="y", which="major", linestyle="--", alpha=0.3)
    ax.grid(axis="y", which="minor", linestyle=":", alpha=0.15)
    ax.grid(axis="x", which="major", linestyle=":", alpha=0.15)

    # タイトル
    ax.set_title(title)

    # 凡例：右側外に出す
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
        frameon=True,
        fontsize=8,
    )

    fig.tight_layout()

    # 出力 or 表示
    if output_path:
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    # 簡易テスト用：CSVパスと曜日を聞いて1枚描画
    csv_path = input("LT_DATA CSV のパスを入力してください（空なら終了）: ").strip()
    if csv_path:
        try:
            df = pd.read_csv(csv_path, index_col=0)
            wd = int(input("曜日を 0=月 ... 6=日 で指定してください: ").strip())
            plot_booking_curves_for_weekday(
                lt_df=df,
                weekday=wd,
                title=f"Booking Curve (weekday={wd})",
            )
        except Exception as e:
            print(f"[ERROR] {e}")
