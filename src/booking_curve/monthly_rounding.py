from __future__ import annotations

import logging

import numpy as np
import pandas as pd


def should_apply_monthly_rounding(
    target_yyyymm: str,
    asof_ts: pd.Timestamp,
    stay_dates: pd.Series,
    *,
    min_future_days: int = 20,
) -> bool:
    """
    対象月内かつ stay_date >= ASOF の日数が min_future_days 以上のときだけ True を返す。

    - target_yyyymm が不正、stay_dates が空、または未来日数が不足している場合は False。
    - stay_dates は datetime 化して normalize する。
    """
    if not target_yyyymm or len(target_yyyymm) != 6 or not target_yyyymm.isdigit():
        logging.debug("Skipping monthly rounding: invalid target_month=%s", target_yyyymm)
        return False

    try:
        target_period = pd.Period(target_yyyymm, freq="M")
    except Exception:
        logging.debug("Skipping monthly rounding: invalid target_month=%s", target_yyyymm)
        return False

    stay_norm = pd.to_datetime(stay_dates, errors="coerce").dt.normalize()
    if stay_norm.empty:
        return False

    asof_norm = pd.to_datetime(asof_ts).normalize()
    month_start = target_period.start_time.normalize()
    month_end = target_period.end_time.normalize()
    month_mask = (stay_norm >= month_start) & (stay_norm <= month_end)
    future_mask = stay_norm >= asof_norm
    future_count = int((future_mask & month_mask).sum())
    if future_count < min_future_days:
        logging.debug(
            "Skipping monthly rounding: future_day_count=%s < %s (target_month=%s, asof=%s)",
            future_count,
            min_future_days,
            target_yyyymm,
            asof_norm.strftime("%Y-%m-%d"),
        )
        return False

    return True


def round_total_goal(total_value: float, unit: float) -> float:
    """
    月合計の丸め目標値を返す。

    - unit <= 0 や NaN は 0.0 を返す。
    - total_value が NaN の場合も 0.0 を返す。
    """
    try:
        unit_value = float(unit)
    except Exception:
        return 0.0
    if unit_value <= 0 or pd.isna(unit_value):
        return 0.0
    try:
        total_float = float(total_value)
    except Exception:
        return 0.0
    if pd.isna(total_float):
        return 0.0
    return float(np.round(total_float / unit_value) * unit_value)


def _month_mask(stay_norm: pd.Series, target_yyyymm: str) -> pd.Series:
    if not target_yyyymm or len(target_yyyymm) != 6 or not target_yyyymm.isdigit():
        return pd.Series(False, index=stay_norm.index)
    try:
        target_period = pd.Period(target_yyyymm, freq="M")
    except Exception:
        return pd.Series(False, index=stay_norm.index)
    month_start = target_period.start_time.normalize()
    month_end = target_period.end_time.normalize()
    return (stay_norm >= month_start) & (stay_norm <= month_end)


def _apply_no_cap_positive(
    base_values: pd.Series,
    remainder: pd.Series,
    need: int,
) -> int:
    order = remainder.sort_values(ascending=False).index
    n = len(order)
    if n == 0 or need <= 0:
        return need
    q, r = divmod(need, n)
    if q:
        base_values.loc[order] += q
    if r:
        base_values.loc[order[:r]] += 1
    return 0


def _apply_no_cap_negative(
    base_values: pd.Series,
    remainder: pd.Series,
    need: int,
) -> int:
    order = remainder.sort_values(ascending=True).index
    if need >= 0:
        return need

    while need < 0:
        candidates = [idx for idx in order if base_values.at[idx] > 0]
        if not candidates:
            break
        n = len(candidates)
        need_abs = -need
        q, r = divmod(need_abs, n)
        decrement = np.full(n, q, dtype=int)
        if r:
            decrement[:r] += 1
        current = base_values.loc[candidates]
        new_values = (current - decrement).clip(lower=0)
        actual_decrease = int((current - new_values).sum())
        base_values.loc[candidates] = new_values
        if actual_decrease == 0:
            break
        need += actual_decrease

    return need


def _apply_with_cap(
    base_values: pd.Series,
    remainder: pd.Series,
    need: int,
    cap_int: int,
) -> int:
    if need == 0:
        return need

    if need > 0:
        order = remainder.sort_values(ascending=False).index.tolist()
        while need > 0:
            progress = False
            for idx in order:
                if need == 0:
                    break
                if base_values.at[idx] >= cap_int:
                    continue
                base_values.at[idx] += 1
                need -= 1
                progress = True
            if not progress:
                break
    else:
        order = remainder.sort_values(ascending=True).index.tolist()
        while need < 0:
            progress = False
            for idx in order:
                if need == 0:
                    break
                if base_values.at[idx] <= 0:
                    continue
                base_values.at[idx] -= 1
                need += 1
                progress = True
            if not progress:
                break

    return need


def apply_remainder_rounding(
    values: pd.Series,
    stay_dates: pd.Series,
    *,
    asof_ts: pd.Timestamp,
    target_yyyymm: str,
    goal_total: float,
    cap_value: float | None,
) -> tuple[pd.Series, float]:
    """
    月次丸めの差分配分を行い、調整後の series と合計を返す。

    - past_mask = stay_date < ASOF は固定。
    - adjustable_mask = stay_date >= ASOF かつ対象月内のみ調整対象。
    - values は numeric に変換し NaN は 0。
    - cap_value が None の場合はベクトル配分で高速化する。
    """
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    stay_norm = pd.to_datetime(stay_dates, errors="coerce").dt.normalize()
    asof_norm = pd.to_datetime(asof_ts).normalize()

    month_mask = _month_mask(stay_norm, target_yyyymm)
    adjustable_mask = (stay_norm >= asof_norm) & month_mask
    fixed_mask = ~adjustable_mask

    fixed_values = numeric.loc[fixed_mask].astype(float)
    adjustable_raw = numeric.loc[adjustable_mask]
    base_adjustable = np.floor(adjustable_raw).astype(int).clip(lower=0)
    remainder = adjustable_raw - base_adjustable

    cap_int: int | None = None
    if cap_value is not None:
        try:
            cap_candidate = int(np.floor(float(cap_value)))
        except Exception:
            cap_candidate = None
        if cap_candidate is not None and cap_candidate >= 0:
            cap_int = cap_candidate

    if cap_int is not None:
        base_adjustable = base_adjustable.clip(upper=cap_int)

    try:
        goal_float = float(goal_total)
    except Exception:
        goal_float = 0.0
    if pd.isna(goal_float):
        goal_float = 0.0

    current_total = float(fixed_values.sum() + base_adjustable.sum())
    need = int(round(goal_float - current_total))

    if need != 0 and not base_adjustable.empty:
        if cap_int is None:
            if need > 0:
                need = _apply_no_cap_positive(base_adjustable, remainder, need)
            else:
                need = _apply_no_cap_negative(base_adjustable, remainder, need)
        else:
            need = _apply_with_cap(base_adjustable, remainder, need, cap_int)

    adjusted = pd.Series(index=values.index, dtype=float)
    adjusted.loc[fixed_mask] = fixed_values.astype(float)
    adjusted.loc[adjustable_mask] = base_adjustable.astype(float)
    adjusted_total = float(adjusted.sum())
    return adjusted, adjusted_total
