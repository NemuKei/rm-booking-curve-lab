# Thread Log

## Meta

* Date: 2026-01-24
* Branch: feature/pace14_market_power_and_clip
* Commit: 148b294
* Version: tag 20260124_0942_samp_feature-pace14_market_power_and_clip_148b294
* Release Zip: rm-booking-curve-lab_20260124_0942_samp_feature-pace14_market_power_and_clip_148b294_full.zip
* Scope: pace14_market の power化＋clip調整、weekshape_flow追加、calendar自動生成の実装・検証

## Context

* 直前のmain安定化・リリース後、`pace14_market` の market補正をより効かせるために「線形→power」へ変更する設計を固め、実装へ反映した。
* さらに、pace14の守備範囲外（LT 15–45）で「週単位の強弱」を拾う補正（weekshape_flow）を新モデルとして追加した。
* calendar_features が無い場合に手動生成が不要になるよう、自動生成の仕組みも入れた。
* 実装後、コードチェックを行い、P0のクラッシュと計測定義不一致を次スレッド課題として切り出した。

## Done

* `pace14_market` の market_factor を線形から power に変更し、clip等のパラメータを調整

  * `src/booking_curve/forecast_simple.py`
* 新モデル `pace14_weekshape_flow`（W=7 / LT 15–45 / clip 0.85–1.15）を追加し、バッチ・評価・GUIから選択可能に拡張

  * `src/booking_curve/forecast_simple.py`
  * `src/run_forecast_batch.py`
  * `src/run_full_evaluation.py`
  * `src/booking_curve/gui_backend.py`
  * `src/gui_main.py`
* calendar_features が無い／範囲不足のときに自動生成する関数を追加

  * `src/build_calendar_features.py`
  * `src/booking_curve/segment_adjustment.py`（呼び出し側へ接続）

## Decisions (non-spec)

* weekshape はフロー（B2）を採用し、窓幅は W=7 とする（当面固定）
* weekshape/market系の factor clip 初期値は 0.85–1.15 を採用（管理容易性を優先）
* calendar_features が無い場合は自動生成して手動オペを不要にする
* Decision Log 起票が必要：あり（power化・weekshape_flow・calendar自動生成の横断決定）

## Pending / Next

* P0: segment_adjustment の UnboundLocalError 修正

  * 完了条件：該当モデルがクラッシュせず、GUI/バッチでスモーク実行できる
* P0: compute_market_pace_7d をツールと同定義へ移植（7日合算比＋母数ゲート）

  * 完了条件：計測器と本体の market_pace_7d の値感が整合し、調整議論が安定する
* P1: weekshape の週境界（ISO週のままか、日〜土等へ変更か）を方針決定して反映

  * 完了条件：週境界の仕様が明文化され、実装がその仕様で一貫する
* P2: CRLF→LF一括変換（.gitattributes＋VSCode）を検討・実施

  * 完了条件：意図しない改行差分が発生しない

## Risks / Notes

* segment_adjustment のクラッシュは影響が大きく、早期修正が必要（モデル選択で回避はできるが恒久対応必須）。
* market_pace の「計測器」と「本体」の定義不一致があると、clip/パラメータの最適化が不安定になる。
* docs/spec_models.md は現状コードとズレる可能性があるため、Docs Gate 後に整合が必要。

## References

* `docs/spec_models.md`：モデル定義（後でpower化/新モデル反映が必要な可能性）
* `AGENTS.md`：運用の正
* `src/booking_curve/forecast_simple.py`：power化・weekshape_flow実装
* `src/build_calendar_features.py`：calendar自動生成
* `src/booking_curve/segment_adjustment.py`：P0クラッシュ箇所
* `docs/thread_logs/2026-01-23_1527_main_samp_main.md`：直前スレッドログ
* `docs/decision_log.md`：決定の追記先

## Questions (if any)

（なし）

---