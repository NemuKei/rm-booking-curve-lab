# 引き継ぎ書

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）

このスレッドは **docs運用（アンカーZIP/Docs Gate/テンプレ整備/Decision Log整流化）** の整理と、関連ドキュメントの齟齬解消を行った作業ログです。
次スレッドでは、まず **Thread Start Gate（アンカーZIP検算）** を実施し、問題がなければ **次にやる開発タスクの整理（優先度付け）** に入ります。

* アンカーZIP（この引継の参照唯一の正）: `rm-booking-curve-lab_20260121_1722_samp_main_fe21886_full.zip`
* Branch: `main`
* Commit: `fe21886`

**次スレ冒頭 Docs Gate 判定:** **No（spec_* 更新は不要）**
（このスレッドは運用docsとテンプレ整備が中心。spec_* 反映が必要な未処理は見当たりません）

---

## 2. 現在地サマリ（できたこと / 未完）

### できたこと

* 「参照の唯一の正」を **アンカーZIP** に統一する運用に寄せ、docs一式を整備・整合。
* `docs/templates/thread_start.md` を「手動で目的/入力を書き換えなくても回る」形に調整（目的は handover/START_HERE 参照へ）。
* `docs/templates/prompt_docs_update.md` / `docs/templates/prompt_thread_log_generate.md` を **アンカーZIP（作業開始点）** 前提の表現に整理し、パラドックスにならない定義に修正。
* `docs/templates/prompt_decision_log_update.md` の見出しレベルを調整（Decision Log 本体と # 階層がズレて増殖しないように）。
* `tools/assign_decision_ids.py` をZIP同梱し、`--sort`（古→新、新しいものが末尾）を追加した状態に更新。
* `docs/decision_log.md` が **日付で単調増加（時系列）** になっていることを検算済み（XXX placeholder なし）。
* プロジェクト事前指示の「憲法」相当を docs 側にも残す目的で `docs/ai_preamble_reference.md` を整備。
* `AGENTS.md` 冒頭に「憲法 / Quick Rules」を置き、アンカーZIP運用・推測禁止・Codex定型などを最優先に明示。
* `docs/dev_style.md` もアンカーZIP運用の用語定義・手順に追随するよう更新済み（※ユーザー側で修正完了宣言あり）。

### 未完（残課題）

* 次スレッドでやるべき **開発タスク（P0/P1/P2）の棚卸し・優先度付け** は未実施（次スレ冒頭で実施予定）。
* （軽微）`docs/decision_log.md` 内の一部Decisionの `Status` が、実態（反映済）とズレている可能性があるため、次スレッド開始時の検算で「更新要否」を再確認する余地あり。

---

## 3. 決定事項（仕様として合意したこと）

※ここでの「決定事項」は **運用・docs整備の合意**（spec_* の外）です。

* 「共有物の唯一の正」は **アンカーZIP**：

  * 1スレッド内で参照点を固定し、途中で作った新ZIPは **次スレのアンカーZIP** として扱う。
* Thread Log / Docs Update / Decision Log Update のテンプレは、**“この依頼に添付されたZIP＝作業開始点（アンカーZIP）”** を根拠に書く。

  * 引継依頼で渡すZIPと、次スレ冒頭で渡すZIPが一致すれば、自然に「次スレのアンカーZIP」になる（矛盾しない）。
* Decision Log の並びは **古→新（新しいものが末尾）** を正とし、`tools/assign_decision_ids.py --sort` で整流化できるようにする。
* システム側の事前指示（ガードレール）は短く圧縮し、詳細は **AGENTS / docs側** に寄せる方針。

---

## 4. 未解決の課題・バグ

* **重大バグ：なし**（このスレッドはdocs整備中心）
* 注意点（軽微）:

  * `docs/thread_logs/2026-01-21_1146_main_docs-governance.md` の Meta に記載の ZIP/commit が、現在のアンカーZIP（fe21886）と一致しない場合があり得る。

    * これは「Thread Log作成時点のメタ」としては整合するが、運用上混乱するなら次スレで扱いを統一（更新 or 追記）する。

---

## 5. 次にやる作業（P0/P1/P2）

### P0（最大2〜3件）

1. **次スレ冒頭チェック（Thread Start Gate）**

   * 完了条件：アンカーZIP展開 → `docs/thread_logs/<latest>` / `docs/decision_log.md 末尾10〜20` / `AGENTS.md` / `docs/spec_*` を確認し、矛盾がないと判断できる（Yes/Noで固定）。
2. **次にやる開発タスク整理（優先度付け）**

   * 完了条件：P0/P1/P2 のタスク一覧が確定し、P0が2〜3件に絞れている（各タスクに完了条件あり）。

### P1

* Decision Log の `Status` が実態と一致しているか最終チェック（必要なら最小限更新）。

  * 完了条件：末尾10〜20件について「未反映/反映済」の整合が取れている。
* docs/templates 周りの表現ゆれ（アンカーZIP/作業開始点/次スレ）を、気になる箇所があれば最小限で統一。

  * 完了条件：混乱しそうな用語が残っていない。

### P2

* docs運用の自動化（例：Decision Log 整流化コマンドをREADME/運用OSに明示、CI化など）

  * 完了条件：運用負債になりそうな手作業が1つ減る。

---

## 6. 参照すべきファイル一覧（パス＋理由）

* `AGENTS.md`：憲法（Quick Rules）含む、AI運用の最優先ルール。
* `docs/START_HERE.md`：スレッド開始時の導線（Thread Start Gate）。
* `docs/dev_style.md`：アンカーZIP運用、スレッド運用OS（参照齟齬防止の実務ルール）。
* `docs/ai_preamble_reference.md`：システム側ガードレールの写し（盲点防止）。
* `docs/templates/thread_start.md`：新スレ冒頭テンプレ。
* `docs/templates/prompt_docs_update.md`：Docs GateがYesのときの唯一手順。
* `docs/templates/prompt_thread_log_generate.md`：Thread Log生成テンプレ（アンカーZIP＝作業開始点）。
* `docs/templates/prompt_decision_log_update.md`：Decision Log更新テンプレ（見出し階層をDecision Logに合わせる）。
* `docs/decision_log.md`：末尾10〜20件の整合確認が必須。
* `docs/thread_logs/2026-01-21_1146_main_docs-governance.md`：この整理作業のThread Log。
* `tools/assign_decision_ids.py`：Decision Log のID採番・時系列ソート。
* `docs/thread_logs/2026-01-21_1722_main_docs-governance_legacy.md`：1146の後続（旧運用を含むが履歴として参照）。冒頭のLEGACY宣言を読んだ上で参照。

---

## 7. 実行コマンド／手順（分かっている範囲）

### Decision Log の整流化（例）

* ソート（古→新、新しいものが末尾）＋ in-place 更新:

  * `python tools/assign_decision_ids.py --file docs/decision_log.md --sort --in-place`
* XXX が残っていないかチェック（残っていれば非0で落ちる）:

  * `python tools/assign_decision_ids.py --file docs/decision_log.md --check-only`
* まず挙動を見る（dry-run）:

  * `python tools/assign_decision_ids.py --file docs/decision_log.md --sort --verbose`

---

## 8. 注意点（参照齟齬・データ・トークン等）

* **唯一の正はアンカーZIP**：スレッド内で参照点を動かさない（作業中にZIPを差し替えない）。
* Thread Log / Decision Log は仕様ではない。仕様は **spec_* が唯一の正**。
* docs更新が必要なら **次スレ冒頭でDocs Gate** を通し、`docs/templates/prompt_docs_update.md` 以外の手順で更新しない。
* 長文化で事故りやすいので、次スレでも **A-10/A-20チェックポイント** と **A-25締めモード** を厳守。

---

## 9. 次スレッドで最初に確認すべきチェックリスト（最大5項目）

1. アンカーZIP（fe21886）を展開し、`AGENTS.md` / `docs/dev_style.md` の「アンカーZIP定義」が一致している → Yes/No
2. `docs/decision_log.md` 末尾10〜20件に、spec_* 反映が必要なのに未反映の項目が残っていない → Yes/No
3. `docs/thread_logs/<latest>` と `docs/decision_log.md` の主張が矛盾していない → Yes/No
4. Docs Gate 判定は **No**（spec_*更新不要）で問題ない → Yes/No

   * Noの場合：更新対象 spec_* は **なし**
5. 次にやる作業（P0）が2〜3件に絞れている → Yes/No

---

## 10. Questions（最大5つまで）

1. `docs/decision_log.md` 内で「反映済みのはずだが Status が未反映」のものが見つかった場合、次スレで **Status更新までをP0に含める** でOKですか？（Yes/No）
回答：OK
2. `docs/thread_logs/2026-01-21_1146_main_docs-governance.md` の Meta がアンカーZIPと異なる点は「作成時点メタ」として許容し、**原則は更新しない**運用で確定でOKですか？（Yes/No）
回答：Yes