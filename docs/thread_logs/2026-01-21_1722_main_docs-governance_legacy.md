このログは旧運用（ZIP一致等）を含み、D-20260121-009/010 により superseded。現行は decision_log / dev_style / START_HERE を参照
* **現行根拠の参照先（3点）**

  * `docs/decision_log.md`（D-009/D-010）
  * `docs/dev_style.md`
  * `docs/START_HERE.md`
* **正本ログへのリンク**

  * `docs/thread_logs/2026-01-21_1146_main_docs-governance.md`

# Thread Log

## Meta

* Date: 2026-01-21
* Branch: main
* Commit: fe21886
* Version: tag 20260121_1722_samp_main_fe21886
* Release Zip: rm-booking-curve-lab_20260121_1722_samp_main_fe21886_full.zip
* Scope: docs運用（アンカーZIP/Docs Gate/テンプレ/AGENTS整流）の齟齬解消と統一

## Context

* docs運用ルールの「唯一の正（参照点）」が “最新ZIP” と “スレッド内固定” の間でブレており、再現性と運用の両方で事故る余地があった。
* 「アンカーZIP（作業開始点）」という概念で統一し、Thread Log / Decision Log / Docs更新テンプレ、AGENTS、dev_style を同じ思想・用語で揃える作業を実施。
* 併せて Decision Log の時系列整流（ソート）をツール側で担保できるようにした。

## Done

* docs運用の参照点を **アンカーZIP（この依頼に添付されたZIP＝作業開始点）** に統一（用語・手順の整合）。

  * `AGENTS.md`：冒頭に「憲法 / Quick Rules」を追加し、アンカーZIP/推測禁止/役割分担/定型プロンプト規約を最優先に明示。
  * `docs/dev_style.md`：アンカーZIP定義・スレッド内固定/スレッド間更新・Docs Gate 手順を明文化し、既存記述（最新ZIP表現）を統一。
  * `docs/ai_preamble_reference.md`：システム側事前指示の盲点を潰すため、docs側に参照用の写し（冗長さを抑えた形）を整備。
* スレッド開始・ログ生成・docs更新のテンプレを、アンカーZIP前提の運用に合わせて調整。

  * `docs/templates/thread_start.md`：手動書き換えが最小になるよう導線整理（目的は handover/START_HERE 参照に寄せる）。
  * `docs/templates/prompt_thread_log_generate.md`：アンカーZIP（作業開始点）を根拠にThread Logを作る前提に統一。
  * `docs/templates/prompt_docs_update.md`：Docs Gate 手順の整合（アンカーZIP前提・推測禁止・spec_*優先）。
  * `docs/templates/prompt_decision_log_update.md`：Decision Log 本体の見出し階層に合わせ、`#` 増殖が起きないよう調整。
* Decision Log の時系列が崩れる問題に対し、ツール側で整流可能にした。

  * `tools/assign_decision_ids.py`：ZIP同梱を前提に追加/更新。`--sort` を追加し **古→新（新しいものが末尾）** の並びを担保。

## Decisions (non-spec)

* 参照の唯一の正は **アンカーZIP**：

  * スレッド内では参照点を固定し、途中で作られた新ZIPは次スレのアンカーZIPとして扱う（スナップショット連鎖）。
  * 引継依頼で渡すZIPと次スレ冒頭で渡すZIPは **一致** させる（不一致は参照事故）。
* Docs Gate（Yes/No判定）を運用の必須チェックとして明文化：

  * Yesなら `docs/templates/prompt_docs_update.md` を唯一の手順として docs/spec 更新を先に行う。
* Decision Log は **古→新** を正とし、`assign_decision_ids.py --sort` で並びを整える（ログを人力で並べ替える前提にしない）。
* 「システム側の事前指示」は短いガードレール（憲法）に圧縮し、詳細は AGENTS/dev_style/docsテンプレへ寄せる。

## Pending / Next

### P0

* 次スレ冒頭で Thread Start Gate（アンカーZIP検算）を実施する

  * 完了条件：アンカーZIP展開→`docs/thread_logs`直近1本 / `docs/decision_log.md`末尾10〜20 / `AGENTS.md` / `docs/spec_*` の矛盾有無をYes/Noで確定できる。
* 問題がなければ、次スレで「次にやる開発タスク整理（P0/P1/P2）」を開始する

  * 完了条件：P0が2〜3件に絞れ、各タスクに完了条件が付いている。

### P1

* `docs/decision_log.md` の末尾10〜20件の Status と実態の整合チェック（必要なら最小限修正）

  * 完了条件：未反映/反映済の表現が運用上誤解を生まない状態になっている。

## Risks / Notes

* 「最新ZIP」という語をアンカーZIPと混用すると、スレッド内参照点が揺れて再現性が壊れる。テンプレや運用文面は今後も **アンカーZIP** に統一すること。
* ZIP未添付で引継/新スレを始めると参照事故が確定するため、運用上は「未添付なら作業開始しない」を継続。

## References

* `AGENTS.md`：憲法/Quick Rules、役割分担、docs編集ルール、ZIP運用の最優先根拠
* `docs/dev_style.md`：スレッド運用OS（アンカーZIP定義、Docs Gate、ログ生成導線）
* `docs/START_HERE.md`：スレッド開始の導線
* `docs/ai_preamble_reference.md`：システム側事前指示の写し（盲点防止）
* `docs/templates/thread_start.md`：スレッド冒頭テンプレ
* `docs/templates/prompt_thread_log_generate.md`：Thread Log生成テンプレ
* `docs/templates/prompt_docs_update.md`：Docs Gate が Yes のときの唯一手順
* `docs/templates/prompt_decision_log_update.md`：Decision Log更新テンプレ
* `docs/decision_log.md`：決定の横断ログ（末尾10〜20件の検算対象）
* `tools/assign_decision_ids.py`：Decision Log採番/整流（`--sort`）

## Questions (if any)

* なし（次スレ冒頭のゲート検算で矛盾が出た場合のみ質問を作る運用）