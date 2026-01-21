# Handover（本文テンプレ）

Proposed file path: docs/handovers/YYYY-MM-DD_<branch>_<scope>.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、<何をしたスレッドか（1〜2行）> の作業ログです。
- 次スレッドでは、<次にやるP0（1〜2行）> を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- <完了1>
- <完了2>
- <完了3>
  - 主要変更ファイル：`<path>`, `<path>`

### 未完（残課題）
- <未完1（P0候補）>
- <未完2（P1候補）>

---

## 3. 決定事項（仕様として合意したこと）
- <決定1（要点だけ）>
- <決定2>
- <決定3>

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：<タイトル>
- 再現条件：
- 影響範囲：
- 暫定回避策：
- 備考：

### 課題2：<タイトル>
- 再現条件：
- 影響範囲：
- 暫定回避策：
- 備考：

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. <タスク名>
   - 完了条件：<何ができていればOKか（1行）>

2. <タスク名>
   - 完了条件：<1行>

### P1（次）
3. <タスク名>
   - 完了条件：<1行>

### P2（余裕があれば）
4. <タスク名>
   - 完了条件：<1行>

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `docs/spec_overview.md`：<理由>
- `docs/spec_data_layer.md`：<理由>
- `docs/spec_models.md`：<理由>
- `docs/spec_evaluation.md`：<理由>
- `AGENTS.md`：<理由>
- `<src/...>`：<理由>
- `docs/thread_logs/<...>.md`：<理由>
- `docs/decision_log.md`：<理由>

---

## 7. 実行コマンド／手順（分かっている範囲で）
- 起動：`python src/gui_main.py`
- バッチ：`python src/run_forecast_batch.py ...`
- ログ：`<log path>`（例：`gui_app.log`）
- リリースZIP：`<zip filename>`

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）
- Docs Gate が Yes の場合、docs更新は docs/templates/prompt_docs_update.md を唯一の手順として行う（独自手順禁止）

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. `docs/handovers/<...>.md` を読んだ（引き継ぎ正本）
3. `docs/thread_logs/` の直近ログが追跡できる（Date/Branch/Commit/Zip/Scope）
4. `docs/decision_log.md` 末尾10〜20件と矛盾しない
5. Docs Gate 判定を実施し、Yes の場合は docs/templates/prompt_docs_update.md に従って更新案を作成

---

## 10. 質問（最大5つ・必要なもののみ）
1. <質問1（Yes/No or 短文）>
2. <質問2>
3. <質問3>
4. <質問4>
5. <質問5>