import sys

import pandas as pd

sys.path.append("src")

import booking_curve.forecast_simple as fs
import run_full_evaluation as r

HOTEL = "daikokucho"
ASOF = "20260120"
TARGET = "202602"
MODEL = "pace14_weekshape_flow"

asof_ts = pd.to_datetime(ASOF)
lt = r.load_lt_csv(TARGET, HOTEL)

# 1) 予測の一致/不一致（既に見たやつ）
def run_forecast(boundary: str):
    fs.WEEKSHAPE_WEEK_BOUNDARY = boundary
    s = r.build_monthly_forecast(lt, MODEL, ASOF, HOTEL)
    s = pd.to_numeric(s, errors="coerce")
    return s

iso = run_forecast("iso")
sun = run_forecast("sun")

print("=== Forecast compare ===")
print("hotel=", HOTEL, "asof=", ASOF, "target=", TARGET, "len=", len(iso))
print("sum_iso=", float(iso.sum(skipna=True)), "sum_sun=", float(sun.sum(skipna=True)), "delta=", float((sun - iso).sum(skipna=True)))
diff_days = int((iso.fillna(0).round().astype("Int64") != sun.fillna(0).round().astype("Int64")).sum())
print("different_days=", diff_days, "of", len(iso))

# 2) week_id が本当に変わってるか（トグルの効き確認）
# 　target月の日付に対して、iso と sun の week_id を比較
dates = pd.to_datetime(iso.index)

fs.WEEKSHAPE_WEEK_BOUNDARY = "iso"
iso_wid = pd.Series([fs._get_week_id(d) for d in dates], index=dates)

fs.WEEKSHAPE_WEEK_BOUNDARY = "sun"
sun_wid = pd.Series([fs._get_week_id(d) for d in dates], index=dates)

changed = int((iso_wid != sun_wid).sum())
print("\n=== Week-id compare (iso vs sun) ===")
print("changed_week_id_days=", changed, "of", len(dates))
print("iso_week_id_unique=", int(iso_wid.nunique()), "sun_week_id_unique=", int(sun_wid.nunique()))

# 3) weekshape係数が “ニュートラル固定” っぽいかをざっくり見る
#    - 係数詳細（detail_df）を取れるなら gated/factor!=1 を確認
print("\n=== Weekshape factor diagnostics ===")
try:
    # baseline_curves_by_weekday は build_monthly_forecast 内部で作られているが、
    # ここでは「取得不能」なので、関数のシグネチャだけ表示して次の一手に繋ぐ。
    import inspect
    print("compute_weekshape_flow_factors sig:", inspect.signature(fs.compute_weekshape_flow_factors))
    print("NOTE: to inspect gated/factor, we need baseline_curves_by_weekday actually used in the model.")
except Exception as e:
    print("signature check failed:", e)
