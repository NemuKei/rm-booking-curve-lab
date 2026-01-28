Proposed file path: docs/thread_logs/2026-01-28_0958_feature_pace14_market_power_and_clip__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-28
- Branch: feature/pace14_market_power_and_clip
- Commit: feb4668
- Version: v0.6.10
- Release Zip: rm-booking-curve-lab_20260128_0238_samp_feature-pace14_market_power_and_clip_feb4668_full.zip
- Scope: pace14_market のdecay_k暫定FIXと説明可能な診断ツール整備

## Context
- market_pace_7d が強いケースで market_factor が上限clipに張り付きやすく、clipを緩めるだけでは「張り付き」も「効き過ぎ」も解消しにくい状況だった。
- decay_k（LTが進むほど市場影響を弱める係数）を調整し、ASOF違い・ホテル違いでも自然な挙動になるポイントを探索した。
- あわせて、deltaが大きい理由を base_delta で説明できるよう診断情報とツールを整備した。

## Done
- `MARKET_PACE_DECAY_K=0.25` を暫定採用し、`MARKET_PACE_CLIP=(0.85,1.25)` と組み合わせて挙動確認（ASOF差・ホテル差）
  - 変更ファイル：`src/booking_curve/forecast_simple.py`
- pace14_market の detail（pf_info）に説明用列（`current_oh/base_now/base_final/base_delta/final_forecast`）を追加
  - 変更ファイル：`src/booking_curve/forecast_simple.py`
- 恒久診断ツール `tools/diag_market_effect.py` を追加し、market帯のTop10を再現可能にした
  - 追加ファイル：`tools/diag_market_effect.py`

## Decisions (non-spec)
- pace14_market のデフォルト運用として、`decay_k=0.25` を暫定採用し、clipは 0.85–1.25 を維持する（追加ASOF・kansaiで確認）
- deltaが大きい/小さい理由を説明できることを重視し、detailに base_delta 等の列を露出し、診断ツールで確認できるようにする
- ローカル設定ファイルを除き、ホテル固有名（実名）はコード上から排除する方針で進める（実装は次タスク）

## Pending / Next
- P0: docs反映（Docs Gate判定→Yesなら `docs/templates/prompt_docs_update.md` に従い差分作成）
  - 完了条件：specにデフォルト値と診断ツールの導線が追記される
- P0: 固有名排除（`HOTEL_TAG` 撤去、hotel_tag未指定時の挙動統一）
  - 完了条件：実名デフォルトがコードから消え、誤適用事故が起きない
- P1: 追加検証（target_monthやASOFを増やして diagログ蓄積）
  - 完了条件：0.25採用の説明ログが揃う

## Risks / Notes
- LT=15付近は構造的に raw が大きくなりやすく、clipで潰れる日が残り得る（必要なら設計調整が必要）
- hotel_tag 未指定時の実名デフォルトは事故要因なので、早めに必須化/中立化が必要

## References
- `AGENTS.md`：運用ルール（唯一の正、Docs Gate、推測禁止）
- `docs/spec_models.md`：pace14_market 仕様反映先
- `src/booking_curve/forecast_simple.py`：decay_k/clip と診断列
- `tools/diag_market_effect.py`：市場効果の再現診断
- `docs/decision_log.md`：今回の合意を追記する導線
