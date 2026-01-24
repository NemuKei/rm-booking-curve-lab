Proposed file path: docs/thread_logs/2026-01-24_1940_feature_pace14_weekshape_min_events_gate__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-24
- Branch: feature/pace14_market_power_and_clip
- Commit: fcfb300
- Version: tag 20260124_1935_samp_feature-pace14_market_power_and_clip_fcfb300
- Release Zip: rm-booking-curve-lab_20260124_1935_samp_feature-pace14_market_power_and_clip_fcfb300_full.zip
- Scope: pace14_weekshape_flow の週境界検証と、gating到達不能（MIN_EVENTS）の原因特定

## Context
- `pace14_weekshape_flow` の週境界トグル（iso/sun）で「結果が変わらない」現象を検証した。
- 週境界自体は week_id 切替として有効だが、weekshape係数が gating により全て 1.0 になっており、結果が一致していた。
- 原因は `(week_id, group)` 集計の性質上 `n_events` が最大7（group分割でさらに小）になり得るのに、`WEEKSHAPE_MIN_EVENTS=10` が設定されていたため。

## Done
- `tools/diag_weekshape_factors.py` を用いて iso/sun の week_id 変更が起きていることを確認（週境界トグル自体は有効）
  - `tools/diag_weekshape_factors.py`
- gating 状態（gated_true、factor!=1、factor stats）を観測し、係数が全て 1.0 になっていたことを確認
  - `src/booking_curve/forecast_simple.py`（実装参照）
- 一時的に `WEEKSHAPE_MIN_EVENTS=2` として診断し、係数が `0.85–1.15` の範囲で発生し、iso/sun で予測差分が出ることを確認
  - `tools/diag_weekshape_factors.py`（一時変更で検証）

## Decisions (non-spec)
- `WEEKSHAPE_MIN_EVENTS=10` は `(week_id, group)` 集計前提では到達不能になり得るため、デフォルトは到達可能な値（<=7）へ変更する必要がある
- 週境界トグル（iso/sun）で差が出ない主因は境界ではなく gating 側である
- Decision Log 起票が必要：あり（weekshape の gating閾値を仕様前提に合わせる決定）

## Pending / Next
- P0: `WEEKSHAPE_MIN_EVENTS` のデフォルト修正（2 or 3）
  - 完了条件：デフォルトのまま `factor!=1 > 0` が観測される（全件gatedにならない）
- P0: `docs/spec_models.md` の既定値表記（デフォルト10）を修正し、到達不能になり得る注意を追記
  - 完了条件：specと実装が一致し、参照齟齬がなくなる
- P1: `tools/diag_weekshape_factors.py` の Ruff 警告（E402/E501）対応
  - 完了条件：警告が消える、または lint 対象外の運用が合意される

## Risks / Notes
- 現状のままだと weekshape_flow が実質OFFになり、週境界（iso/sun）検討の議論が空振りする。
- tools スクリプトを repo に置く運用なら、lint 方針（修正 or 除外）を決めないと差分ノイズが出る。

## References
- `src/booking_curve/forecast_simple.py`：weekshape_flow 実装・gating条件・閾値定義
- `docs/spec_models.md`：weekshape_flow の既定値表記（更新対象）
- `tools/diag_weekshape_factors.py`：今回の再現・診断スクリプト
- `docs/handovers/2026-01-24_0942_feature_pace14_market_power_and_clip__handover.md`：既存の残課題（segment_adjustment, market_pace移植）
- `docs/thread_logs/2026-01-24_0942_feature_pace14_market_power_and_clip__thread_log.md`：当日AM時点の実装ログ
- `docs/decision_log.md`：決定追記先