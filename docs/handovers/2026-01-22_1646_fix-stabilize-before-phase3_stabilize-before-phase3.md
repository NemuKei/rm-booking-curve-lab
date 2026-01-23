Proposed file path: docs/handovers/2026-01-22_1646_fix-stabilize-before-phase3_stabilize-before-phase3.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）

* このスレッドは、Phase3着手前の安定化ブランチ（`fix/stabilize-before-phase3`）を切り、未解決バグをP0で潰す準備を整えた作業ログです。
* 次スレッドでは、(1) recent90のcalendar_features欠損時クラッシュ修正、(2) LT_ALLエラーの再現→修正、(3) TopDownRevPAR不一致の再現→修正 を進めます。
* Docs Gate 判定：**No**（直近の運用決定は docs に反映済み。今回は実装修正が主。）

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと

* スレッド運用（anchor/source/candidate ZIP、HHMM命名、legacy扱い、Docs Gate）を docs に反映し、参照事故を潰した

  * 主要変更ファイル：`docs/dev_style.md`, `docs/START_HERE.md`, `docs/templates/*`, `docs/decision_log.md`
* `_v2` 相当ログを `_legacy` に改名し、正本ログ⇄legacyログ⇄handover の参照導線を成立させた

  * 主要ファイル：`docs/thread_logs/2026-01-21_1146_main_docs-governance.md`, `docs/thread_logs/2026-01-21_1722_main_docs-governance_legacy.md`, `docs/handovers/2026-01-21_main_docs-governance-close.md`
* Phase3前の安定化ブランチを作成し、最新release ZIP（本ZIP）を作成した（次スレのアンカーとして使用可能）

### 未完（残課題）

* recent90モデル：`calendar_features_{hotel_tag}.csv` 欠損でクラッシュ（P0）
* LT_ALL 実行時のエラー：再現条件とログ/スクショ待ち（P0）
* TopDownRevPAR：予測値と異なる値を取る不具合：再現条件とログ/スクショ待ち（P0）

---

## 3. 決定事項（仕様として合意したこと）

* 参照の唯一の正は「次スレ冒頭で添付する anchor_zip」で固定し、スレッド途中の検証ZIPは candidate_zip として扱う（source/anchor/candidate の役割分離）。
* handovers / thread_logs の命名に HHMM を追加し、同日衝突（`_v2` 乱立）を根絶する。
* Docs Gate を次スレ冒頭の最優先チェックに置き、必要なら実装より先に docs/spec を更新する（手順は `docs/templates/prompt_docs_update.md`）。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：recent90モデルで calendar_features CSV欠損時にクラッシュ

* 再現条件：

  * recent90系モデルで補正（segment_adjustment）が走る条件で、`output/calendar_features_{hotel_tag}.csv` が存在しない状態
  * `src/booking_curve/segment_adjustment.py::_load_calendar()` が `pd.read_csv(path)` を存在チェックなしで実行
* 影響範囲：

  * recent90モデルの実行が FileNotFoundError で停止（GUI/バッチ双方で落ちる可能性）
* 暫定回避策：

  * `output/calendar_features_{hotel_tag}.csv` を事前生成しておく（生成手順が未整備なら手動作成が必要）
* 備考：

  * OUTPUT_DIR は `src/booking_curve/config.py`（`OUTPUT_DIR = APP_BASE_DIR / "output"`）
  * 期待動作は「欠損時は補正スキップ（係数=1.0）で継続」が妥当

### 課題2：LT_ALL 実行時にエラー

* 再現条件：

  * 不明（次スレでスクショ/ログ提示予定）
* 影響範囲：

  * LT_ALL（複数月一括処理）が止まる／一部処理が完了しない可能性
* 暫定回避策：

  * 現時点は月単位で個別実行する等（ただし根本ではない）
* 備考：

  * 導線候補：`src/gui_main.py` → `src/booking_curve/gui_backend.py` → `src/run_build_lt_csv.py`（LT_ALL処理）
  * 方針候補：月ごと try/except にして「失敗月一覧＋成功分出力」を残す（ログ化/欠損扱い）

### 課題3：TopDownRevPARで予測値と異なる値を取る

* 再現条件：

  * 不明（次スレでスクショ/ログ提示予定）
* 影響範囲：

  * GUI上のTopDownRevPAR表示が誤りとなり、意思決定を誤誘導するリスク
* 暫定回避策：

  * 予測CSVから別途集計した値を暫定の正とする（差分原因が確定するまで）
* 備考：

  * 実装候補：`src/booking_curve/gui_backend.py::_get_projected_monthly_revpar()` など
  * `forecast_revenue` の日次化が `groupby(level=0).max()` になっており、index重複がある場合にズレ要因になり得る（要再現確認）

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）

1. recent90：calendar_features欠損時に落ちないフォールバックを実装

   * 完了条件：`output/calendar_features_{hotel_tag}.csv` が無い状態でも recent90 の実行が継続し、補正は無効化（係数=1.0相当）で結果が出る。

2. LT_ALL：エラー再現→原因特定→修正（スキップ＋ログ化を含む）

   * 完了条件：LT_ALLが「全停止」せず、少なくとも成功分は出力され、失敗月は一覧（ログ/欠損扱い）として残る。

3. TopDownRevPAR：不一致の再現→計算根拠の統一→修正

   * 完了条件：同一 as_of / 同一モデル / 同一入力で、TopDownRevPARが「正とする予測値の算出」と一致し、不一致時は診断情報（使ったCSV名、欠損/重複、集計ロジック）が出る。

### P1（次）

4. recent90フォールバック時のWARNを欠損一覧/ログに残す（運用検知性の強化）

   * 完了条件：calendar_features欠損が発生した際に、ユーザーが後から気づけるログ（WARN）が残る。

### P2（余裕があれば）

5. TopDownRevPARの診断表示（GUIで“何を集計したか”を明示）

   * 完了条件：TopDown画面で、参照した forecast CSV / as_of / 集計式（要約）が確認できる。

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）

* `docs/spec_overview.md`：全体構造（Phase/モデルの位置づけ）確認
* `docs/spec_data_layer.md`：LT_DATA/欠損/失敗ログの扱い（「スキップ＋欠損扱い」の整合）
* `docs/spec_models.md`：モデル定義（recent90 / LT_ALL / TopDownRevPARの位置づけ）
* `docs/spec_evaluation.md`：評価出力やASOFの扱い（TopDownの整合確認に使う）
* `AGENTS.md`：運用ガードレール（唯一の正、推測禁止、Docs Gate）
* `docs/decision_log.md`：直近決定（D-20260121-005〜010）確認（特にD-009/D-010）
* `docs/thread_logs/2026-01-21_1146_main_docs-governance.md`：docs運用整備の正本ログ（legacyへの導線あり）
* `docs/thread_logs/2026-01-21_1722_main_docs-governance_legacy.md`：履歴（旧運用含む。冒頭のLEGACY宣言前提）
* `src/booking_curve/segment_adjustment.py`：recent90のcalendar_features読込（クラッシュ原因）
* `src/booking_curve/config.py`：`OUTPUT_DIR` / ログディレクトリ定義
* `src/run_build_lt_csv.py`：LT_ALLの中核導線候補
* `src/booking_curve/gui_backend.py`：LT_ALL呼び出し、TopDownRevPAR算出の候補箇所
* `src/gui_main.py`：GUI起動・メニュー導線

---

## 7. 実行コマンド／手順（分かっている範囲で）

* 起動：`python src/gui_main.py`
* バッチ：`python src/run_forecast_batch.py ...`（必要に応じて）
* ログ：`output/logs/` 配下（例：`gui_app.log` がある場合はそこ）
* source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260122_1641_samp_fix-stabilize-before-phase3_78d20b8_full.zip`（同一なら anchor_zip と同じでOK）
* anchor_zip（次スレで添付するアンカーZIP）：`rm-booking-curve-lab_20260122_1641_samp_fix-stabilize-before-phase3_78d20b8_full.zip`

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）

* 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
* 共有物の唯一の正：make_release_zip.py で作成した最新ZIP（次スレ冒頭で添付したZIPを anchor_zip として固定）
* 推測禁止：エラー再現が不足する場合は、不足を明記して質問（最大5つ）
* 個人情報・企業機密を含むデータ/ログは同梱しない（必要ならダミー化 or 伏字）
* Docs Gate が Yes の場合、docs更新は `docs/templates/prompt_docs_update.md` を唯一の手順として行う（独自手順禁止）
* legacyログは“運用根拠”ではなく“履歴”。根拠は `decision_log` / `dev_style` / `START_HERE` を優先

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）

1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. `docs/handovers/<...>.md` を読んだ（引き継ぎ正本）
3. `docs/thread_logs/` の直近ログが追跡できる（Date/Branch/Commit/Zip/Scope）
4. `docs/decision_log.md` 末尾10〜20件と矛盾しない
5. Docs Gate 判定を実施し、Yes の場合は docs/templates/prompt_docs_update.md に従って更新案を作成（今回は原則No想定）

---

## 10. 質問（最大5つ・必要なもののみ）

1. LT_ALLのエラーは「どの操作（GUI/CLI）」「どのホテルtag」「どの年月」で発生しましたか？（短文でOK）
回答：kansaiで発生。詳細はログとスクショを添付します。
2. LT_ALLのエラーログ/スクショは `output/logs/` のどのファイルに出ていますか？（ファイル名だけ）
回答：lt_all_20260122_1633.log
3. TopDownRevPARの「正とする予測値」は、どの出力（どのCSV/画面/計算式）を根拠にしていますか？（例：forecast出力の合計÷cap×days など）
回答：これはLT_ALLの件が解決してから、提示します
4. TopDownRevPAR不一致が出るのは特定のモデル（recent90 / LT_ALL / その他）に限定されますか？（Yes/No）
回答：これはLT_ALLの件が解決してから、提示します
5. recent90のcalendar_featuresは「本来は必須として生成する設計」か「任意（無ければ補正なし）」のどちらで確定しますか？（二択）
回答：calendar自体は実質、廃止の方向ではあるので、無くても回るようにします