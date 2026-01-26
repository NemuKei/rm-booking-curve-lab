Proposed file path: docs/handovers/2026-01-26_1730_feature_base_small_rescue_learning_csv_diag__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、`pace14_weekshape_flow` の “ベース小救済（加算/ハイブリッド）” に向けて **weekshape帯の学習（P90/P95/P97.5）を hotels.json に保存**し、あわせて **forecast CSV に診断列（weekshape_gated / base_small_rescue_*）を出す**対応を行った作業ログです。
- 次スレッドでは、**診断列を使って救済が「gated日にだけ適用」されているかを検証（P0）**し、Docs Gate=Yes のため **spec_models 追記案（P1）**を作成します。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- weekshape帯（LT15–45）の “ベース小救済” のために、`residual_rate` 分布から **cap_ratio の候補（P90/P95/P97.5）を学習**して hotels.json に保存できるようにした。
  - 学習は `tools/learn_base_small_weekshape.py` から実行（GUI運用を想定した `train_base_small_weekshape_for_gui` を呼ぶ）。
  - 主要変更ファイル：`src/booking_curve/gui_backend.py`, `src/booking_curve/config.py`, `tools/learn_base_small_weekshape.py`
- 学習ゲート（P0-3）の厳密確認として、`window-months=3/6/12` の結果差分（ok/skip, hotels.json差分）を確認し、**短窓→長窓の自動拡張が意図どおり動作**することを確認した（daikokucho/kansai）。
- forecast CSV（run_forecast_batch経由）に、**weekshape_gated と base_small_rescue_* の診断列を出力**できるようにした（P2）。
  - 主要変更ファイル：`src/run_forecast_batch.py`
- ローカル側の output（AppData）を対象に、PowerShellで **最新CSVのヘッダ確認**まで実施し、診断列が出ていることを確認した。

### 未完（残課題）
- **P0**：診断列を使って、救済が「gated=True の日だけ適用」になっているか、pickupが cap を超えていないか等の検証を daikokucho/kansai で1本ずつ残す（ログ or md）。
- **P1**：Docs Gate=Yes のため、`docs/spec_models.md` の `pace14_weekshape_flow` 章へ “ベース小救済（weekshape）” と「診断列」の追記案を作る（テンプレ手順厳守）。
- **P1**：GUI側のマスタ設定で（必要なら）mode/cap_ratio の override と学習更新頻度の運用を詰める。

---

## 3. 決定事項（仕様として合意したこと）
- “ベース小救済（weekshape帯）” は、`residual_rate` 分布の分位（P90/P95/P97.5）を **cap_ratio 候補**として扱い、運用上はまず **p95相当を上限候補**として採用する前提で検証を進める（暴れ防止のため上限必須）。
- 学習結果は hotels.json の `learned_params.base_small_rescue.weekshape` に保存し、`trained_until_asof / n_samples / n_unique_stay_dates / window_months_used` を残す（再現性・監査性）。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：救済が適用された “証跡（どの日にどれだけ効いたか）” の検証ログが未整備
- 再現条件：forecast CSV に診断列は出るが、適用日・cap・pickupの妥当性を要約した検証ログがまだ無い。
- 影響範囲：仕様追記や運用開始時に説明責任が弱くなる。
- 暫定回避策：`weekshape_gated/base_small_rescue_*` 列で、gated日のみ適用・cap超過なしを確認してログを残す。
- 備考：daikokucho/kansai 各1本で十分。

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. 救済の適用妥当性を診断列で検証（daikokucho/kansai）
   - 完了条件：`weekshape_gated=True` の行だけ `base_small_rescue_applied=True` になり、`base_small_rescue_pickup` が cap を超えないことを確認したログ（またはmd）が残る。

2. “学習窓” の運用方針を固定（ホテル別の既定窓を持つか）
   - 完了条件：既定窓（例：daikokucho=3, kansai=6 など）を「運用ルール」として1行で明文化できる（暫定でOK）。

### P1（次）
3. spec_models 追記案の作成（Docs Gate=Yes）
   - 完了条件：`docs/templates/prompt_docs_update.md` 手順に沿った追記案（差分）が用意できる（実適用は別タスクでも可）。

### P2（余裕があれば）
4. run_forecast_batch 以外のCSV出力ルート（GUI export 等）があれば同列を出す
   - 完了条件：どの出力経路でも診断列が欠けない（または “経路別に出ない” を仕様として明記）。

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `docs/spec_models.md`：`pace14_weekshape_flow` の仕様章（ベース小救済/診断列の追記先）
- `AGENTS.md`：仕様と運用ルールの唯一の正
- `src/booking_curve/gui_backend.py`：学習ゲート（window候補/skip条件/保存payload）
- `src/booking_curve/config.py`：hotels.json の読み書き（learned_params 更新）
- `src/booking_curve/forecast_simple.py`：`weekshape_gated` と `base_small_rescue_*` を detail_df に載せる本体
- `src/run_forecast_batch.py`：detail_df → CSV への列ホワイトリスト（rename_map）
- `tools/learn_base_small_weekshape.py`：CLI学習入口
- `docs/thread_logs/2026-01-26_1730_feature_base_small_rescue_learning_csv_diag__thread_log.md`：本スレッドログ（作成物）
- `docs/decision_log.md`：横断決定の追記先

---

## 7. 実行コマンド／手順（分かっている範囲で）
- GUI：`python src/gui_main.py`
- 学習（例）：
  - `python tools/learn_base_small_weekshape.py --hotel daikokucho --window-months 3 --stride-days 7`
  - `python tools/learn_base_small_weekshape.py --hotel kansai --window-months 3 --stride-days 7`
- 予測（例）：`python src/run_forecast_batch.py --hotel daikokucho --model pace14_weekshape_flow --target 202602 --asof 20260126`
- ローカル出力確認（AppData）：
  - `C:\Users\<USER>\AppData\Local\BookingCurveLab\output\forecast_pace14_weekshape_flow_*.csv`
- source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260126_1727_samp_feature-pace14_market_power_and_clip_e24223a_full.zip`
- anchor_zip（次スレで添付するアンカーZIP）：TBD（クローズ時に make_release_zip.py で作成し、次スレ冒頭で添付する）

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）
- 診断列は “detail_df 側に列がある場合だけ出力する” 方針（後方互換）を維持する。

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. `docs/handovers/<...>__handover.md` を読んだ（引き継ぎ正本）
3. `tools/learn_base_small_weekshape.py` が `ok:true` で学習結果を保存できる
4. forecast CSV に `weekshape_gated/base_small_rescue_*` 列が出る
5. `docs/decision_log.md` 末尾と矛盾しない（必要なら追記差分を適用）

---

## 10. 質問（最大5つ・必要なもののみ）
（なし）
