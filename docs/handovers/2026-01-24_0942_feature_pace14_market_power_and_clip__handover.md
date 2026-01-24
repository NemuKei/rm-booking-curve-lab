## 1. スレッド移行宣言（新スレッドに貼る前提の文面）

* このスレッドは、`pace14_market` の market補正を **power化**し、あわせて **weekshape_flow（週×グループのフロー補正）** と **calendar自動生成** を実装・検証した作業ログです。
* 次スレッドでは、**segment_adjustment の実行時クラッシュ修正（P0）** と、**market_pace 計測定義の本体移植（P0）** を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと

* `pace14_market` の market_factor を **線形 → power** に変更し、clip等のパラメータを調整した。
* 新モデル `pace14_weekshape_flow`（LT 15–45 / W=7 / clip 0.85–1.15）を追加した。
* `calendar_features_{hotel}.csv` が無い／範囲不足のときに **自動生成**する関数を追加した。

  * 主要変更ファイル：`src/booking_curve/forecast_simple.py`, `src/run_forecast_batch.py`, `src/run_full_evaluation.py`, `src/booking_curve/gui_backend.py`, `src/gui_main.py`, `src/build_calendar_features.py`, `src/booking_curve/segment_adjustment.py`

### 未完（残課題）

* **P0**：`segment_adjustment.py` に `df` 未定義参照があり、実行時に `UnboundLocalError` で落ちる（モデルによってはクラッシュ）。
* **P0**：`compute_market_pace_7d()` の定義がツール（print_market_pace_series.py）と揃っておらず、GUI/評価と計測器の数値感がズレうる（合算比＋母数ゲート等の移植が必要）。
* **P1**：weekshape の週境界（ISO週のままか、日〜土などへ変更するか）の方針を確定して反映する。
* **P2**：CRLF→LFの一括変換（.gitattributes＋VSCode設定）を検討・実施する（次スレッド扱い）。
* **P2**：`docs/spec_models.md` と実装（power化 / weekshape_flow 追加）のズレを整合する（Docs Gate判定後）。

---

## 3. 決定事項（仕様として合意したこと）

* weekshape は **フロー（B2）** を採用し、まず **W=7** で進める。
* weekshape factor の clip 初期値は **0.85–1.15**（market補正と揃える）。
* calendar_features は「無ければ自動生成（手動生成不要）」方針とする。
* 週境界は現時点で未確定だが、感覚としては「並んだ日月をセットで扱う」方向が有力（次スレで壁打ちして確定）。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：segment_adjustment が UnboundLocalError で落ちる

* 再現条件：`apply_segment_adjustment()` を通るモデル（例：`recent90_adj` など）を実行し、`segment_adjustment.py` 内で `df` 未定義参照が発生。
* 影響範囲：該当モデルが **実行時クラッシュ**。GUI/バッチ双方で影響する可能性。
* 暫定回避策：該当モデルを選ばない／segment_adjustment を一時的に無効化（恒久対応は次スレP0で修正）。
* 備考：コードチェックで発見。修正は次スレッドで対応する。

### 課題2：market_pace の計測定義がツールと本体で不一致

* 再現条件：`tools/print_market_pace_series.py` の結果と、`pace14_market`（GUI/評価）の market_pace_7d の値感が一致しない可能性。
* 影響範囲：market補正の効き具合が想定とズレる（clip/パラメータ調整の議論が不安定になる）。
* 暫定回避策：当面はツール側の series を基準にレンジ感を把握し、本体側の定義移植後に再調整する。
* 備考：本体は「平均」ベースのままの箇所が残っているため、合算比＋母数ゲートへ寄せる。

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）

1. segment_adjustment の UnboundLocalError 修正

   * 完了条件：`apply_segment_adjustment()` を通るモデルがクラッシュせず、最低限スモーク実行できる。

2. compute_market_pace_7d の定義をツールと揃える（7日合算比＋母数ゲート）

   * 完了条件：同条件でツール出力と本体側 market_pace_7d の値感が整合し、評価/GUIでレンジ検討ができる。

### P1（次）

3. weekshape の週境界（ISO週 vs 日〜土など）を確定し、必要なら実装修正

   * 完了条件：週境界の仕様が明文化され、モデルがその仕様で一貫して動く。

### P2（余裕があれば）

4. CRLF→LF一括変換（.gitattributes＋VSCode）方針整理と実施

   * 完了条件：改行が運用で安定し、意図しない改行差分が発生しない。

5. docs/spec_models.md 等の整合（Docs Gate判定後）

   * 完了条件：specと実装のズレが解消し、次回以降の参照齟齬が減る。

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）

* `docs/spec_overview.md`：モデル群と全体像の前提（仕様の正）。
* `docs/spec_models.md`：モデル定義（power化／weekshape_flow 追加の反映先候補）。
* `docs/spec_evaluation.md`：評価の前提（モデル追加時の整合確認に使用）。
* `AGENTS.md`：運用・役割・手順の正。
* `src/booking_curve/forecast_simple.py`：pace14_market power化／weekshape_flow 実装本体。
* `src/build_calendar_features.py`：calendar自動生成（ensure_calendar_for_dates）追加。
* `src/booking_curve/segment_adjustment.py`：クラッシュ箇所（P0修正対象）。
* `src/run_forecast_batch.py`：モデル追加（CSV出力）側の入口。
* `src/run_full_evaluation.py`：評価側でのモデル選択・実行の入口。
* `docs/thread_logs/2026-01-23_1527_main_samp_main.md`：直前スレッドのログ（参照整合チェック用）。
* `docs/decision_log.md`：運用・決定の蓄積（末尾整合チェック用）。

---

## 7. 実行コマンド／手順（分かっている範囲で）

* 起動：`python src/gui_main.py`
* バッチ：`python src/run_forecast_batch.py`（ファイル内の設定値で実行）
* 評価：`python src/run_full_evaluation.py`（スクリプト側の設定に従う）
* ログ：`gui_app.log`（環境により配置は異なる）
* source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260124_0942_samp_feature-pace14_market_power_and_clip_148b294_full.zip`
* anchor_zip（次スレで添付するアンカーZIP）：`rm-booking-curve-lab_20260124_0942_samp_feature-pace14_market_power_and_clip_148b294_full.zip`

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）

* 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
* 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
* 推測禁止：不足は不足として明記し、質問は最大5つまで
* 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）
* Docs Gate が Yes の場合、docs更新は `docs/templates/prompt_docs_update.md` を唯一の手順として行う（独自手順禁止）

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）

1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. `docs/handovers/<...>.md` を読んだ（引き継ぎ正本）
3. `docs/thread_logs/` の直近ログが追跡できる（Date/Branch/Commit/Zip/Scope）
4. `docs/decision_log.md` 末尾10〜20件と矛盾しない
5. Docs Gate 判定を実施し、Yes の場合は `docs/templates/prompt_docs_update.md` に従って更新案を作成

---

## 10. 質問（最大5つ・必要なもののみ）

（なし）