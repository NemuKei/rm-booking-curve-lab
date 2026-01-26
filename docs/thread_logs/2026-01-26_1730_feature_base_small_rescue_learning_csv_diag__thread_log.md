Proposed file path: docs/thread_logs/2026-01-26_1730_feature_base_small_rescue_learning_csv_diag__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-26
- Branch: feature/pace14_market_power_and_clip
- Commit: e24223a
- Version: v0.6.10
- Release Zip: rm-booking-curve-lab_20260126_1727_samp_feature-pace14_market_power_and_clip_e24223a_full.zip
- Scope: base_small_rescue learning (weekshape) + forecast CSV diagnostics

## Context
- “ベース小救済（加算/ハイブリッド）” の導入に向け、weekshape帯（LT15–45）の学習結果（cap_ratio P90/P95/P97.5）を運用で扱える形にする必要があった。
- あわせて、救済がどの日に効いたかを検証できるよう、forecast CSV に診断列を出力する必要があった。

## Done
- weekshape帯の base-small 学習（quantile算出）を GUI運用向けに実装し、hotels.json の learned_params に保存。
  - `src/booking_curve/gui_backend.py`: `train_base_small_weekshape_for_gui`（window候補の自動拡張、skip条件、payload整形、保存）
  - `src/booking_curve/config.py`: learned_params 更新（hotels.json の永続化）
  - `tools/learn_base_small_weekshape.py`: CLI入口（学習実行）
- 学習ゲートの挙動を、window-months=3/6/12 で検証し、結果差分（n_samples等）とskip条件が意図どおりであることを確認（daikokucho/kansai）。
- forecast CSV（run_forecast_batch）に診断列を出すため、detail_df の列を whitelist（rename_map）に追加。
  - `src/run_forecast_batch.py`: `weekshape_gated` / `base_small_rescue_*` の出力対応
- AppData側 output フォルダを対象に、生成されたCSVのヘッダで診断列が出ることを確認。

## Decisions (non-spec)
- base-small救済（weekshape帯）の上限候補は、residual_rate 分布の分位（P90/P95/P97.5）から提示し、まずは p95 を中心に検証を進める。
- 学習結果は `learned_params.base_small_rescue.weekshape` に保存し、`trained_until_asof/n_samples/n_unique_stay_dates/window_months_used` を残す。
- forecast CSV 出力では、detail_df に列が存在する場合のみ診断列を出す（後方互換を維持）。

## Pending / Next
- P0: 診断列を用いて、救済が gated 日にだけ適用され、pickup が cap を超えないことを daikokucho/kansai で検証ログ化する
  - 完了条件：ホテルごとに1本、適用日の整合と cap 超過なしを示すログ（またはmd）が残る
- P1: Docs Gate=Yes のため、spec_models 追記案（ベース小救済weekshape＋診断列）を作成する
  - 完了条件：`docs/templates/prompt_docs_update.md` 手順に沿った差分案が用意できる

## Risks / Notes
- forecast CSV の診断列は run_forecast_batch 経由では担保したが、GUI側に別のCSV export 経路がある場合は同様の whitelist が必要になる可能性がある。
- 学習窓（3/6/12）の運用方針は、ホテル特性で最適が変わり得るため、固定する場合はホテル別に持つ設計が望ましい。

## References
- `docs/spec_models.md`: pace14_weekshape_flow 章（追記先候補）
- `AGENTS.md`: 仕様/運用ルール（唯一の正）
- `src/booking_curve/gui_backend.py`: 学習ゲート＋保存payload
- `src/booking_curve/config.py`: hotels.json 永続化
- `src/booking_curve/forecast_simple.py`: 診断列を detail_df に載せる実装本体
- `src/run_forecast_batch.py`: CSV出力 whitelist（rename_map）
- `tools/learn_base_small_weekshape.py`: 学習CLI入口
