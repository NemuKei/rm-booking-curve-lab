from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from booking_curve.config import OUTPUT_DIR

try:
    import jpholiday
except ImportError:
    jpholiday = None

# ===== 設定ここから =====
HOTEL_TAG = "daikokucho"

# カレンダーを作りたい日付範囲
# ※必要に応じてユーザーが変更できるようにハードコードでOK。
START_DATE = date(2023, 11, 1)
END_DATE = date(2026, 12, 31)
# ===== 設定ここまで =====


def is_jp_holiday(d: date) -> bool:
    """
    日本の祝日判定。
    jpholiday がインストールされていればそれを使い、
    無ければ False を返す。
    """
    if jpholiday is None:
        return False
    return jpholiday.is_holiday(d)


def build_calendar_df(start: date, end: date) -> pd.DataFrame:
    """
    start〜end の全日についてカレンダー特徴量を作成する。
    """
    dates = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date": dates})
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day
    df["weekday"] = df["date"].dt.weekday  # 0=Mon,6=Sun

    # 週末フラグ
    df["is_weekend"] = df["weekday"] >= 5

    # 祝日フラグ
    df["is_jp_holiday"] = df["date"].dt.date.map(is_jp_holiday)

    # 祝日 or 週末
    df["is_holiday_or_weekend"] = df["is_weekend"] | df["is_jp_holiday"]

    # 前後の日の情報を使うためにシフト
    df["is_before_holiday"] = df["is_holiday_or_weekend"].shift(-1, fill_value=False)
    df["is_after_holiday"] = df["is_holiday_or_weekend"].shift(1, fill_value=False)

    # 連続する holiday_or_weekend ブロックにIDを振る
    block_ids: list[int | None] = []
    current_block_id = 0
    in_block = False
    for is_h in df["is_holiday_or_weekend"]:
        if is_h:
            if not in_block:
                current_block_id += 1
                in_block = True
            block_ids.append(current_block_id)
        else:
            in_block = False
            block_ids.append(None)
    df["holiday_block_id"] = block_ids

    # 各ブロックの長さを計算
    block_len = (
        df.groupby("holiday_block_id")["date"]
        .transform("count")
        .where(df["holiday_block_id"].notna(), other=0)
    )
    df["holiday_block_len"] = block_len.astype(int)

    # ブロック内での位置(single/first/middle/last)
    positions: list[str] = []
    for _, row in df.iterrows():
        bid = row["holiday_block_id"]
        blen = row["holiday_block_len"]
        if pd.isna(bid) or blen == 0:
            positions.append("none")
            continue
        if blen == 1:
            positions.append("single")
        else:
            # ブロック内の index 位置を調べる
            # True/False の連続部分なので、前後の行で block_id を見て判定する
            # 現在の行の index
            idx = row.name
            # 前後の block_id
            prev_bid = df.loc[idx - 1, "holiday_block_id"] if idx > df.index.min() else None
            next_bid = df.loc[idx + 1, "holiday_block_id"] if idx < df.index.max() else None
            if prev_bid != bid and next_bid == bid:
                positions.append("first")
            elif prev_bid == bid and next_bid == bid:
                positions.append("middle")
            elif prev_bid == bid and next_bid != bid:
                positions.append("last")
            else:
                # 安全策として single 扱い
                positions.append("single")
    df["holiday_position"] = positions

    # 3連休以上の中日
    df["is_long_holiday_middle"] = (df["holiday_block_len"] >= 3) & (
        df["holiday_position"] == "middle"
    )

    return df


def build_calendar_for_hotel(hotel_tag: str, start_date: date, end_date: date) -> Path:
    """
    指定ホテル・期間のカレンダーデータを生成し、CSV に保存する。

    Args:
        hotel_tag: ホテル識別子 (例: "daikokucho", "kansai")
        start_date: 生成開始日
        end_date: 生成終了日

    Returns:
        生成された CSV ファイルのパス。
    """
    df = build_calendar_df(start_date, end_date)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"calendar_features_{hotel_tag}.csv"
    df.to_csv(out_path, index=False)
    return out_path


def ensure_calendar_for_dates(
    hotel_tag: str,
    dates: pd.DatetimeIndex,
    *,
    min_span_days: int = 365,
) -> Path:
    """
    calendar_features_{hotel_tag}.csv が存在しない/範囲不足の場合に自動生成する。
    """
    out_path = Path(OUTPUT_DIR) / f"calendar_features_{hotel_tag}.csv"

    dates = pd.to_datetime(pd.Index(dates), errors="coerce")
    dates = dates[~pd.isna(dates)]
    if dates.empty:
        if out_path.exists():
            return out_path
        today = date.today()
        return build_calendar_for_hotel(
            hotel_tag=hotel_tag,
            start_date=today,
            end_date=today + timedelta(days=min_span_days),
        )

    needed_start = dates.min().normalize().date()
    needed_end = dates.max().normalize().date()

    existing_ok = False
    if out_path.exists():
        try:
            df = pd.read_csv(out_path, parse_dates=["date"])
            if not df.empty and "date" in df.columns:
                min_dt = pd.to_datetime(df["date"]).min()
                max_dt = pd.to_datetime(df["date"]).max()
                if not pd.isna(min_dt) and not pd.isna(max_dt):
                    existing_ok = (min_dt.date() <= needed_start) and (max_dt.date() >= needed_end)
        except Exception:
            existing_ok = False

    if existing_ok:
        return out_path

    start = needed_start
    end = needed_end
    if (end - start).days < min_span_days:
        end = start + timedelta(days=min_span_days)

    return build_calendar_for_hotel(
        hotel_tag=hotel_tag,
        start_date=start,
        end_date=end,
    )


def main() -> None:
    out_path = build_calendar_for_hotel(
        hotel_tag=HOTEL_TAG,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    print(f"[OK] カレンダーファイルを作成しました: {out_path}")


if __name__ == "__main__":
    main()
