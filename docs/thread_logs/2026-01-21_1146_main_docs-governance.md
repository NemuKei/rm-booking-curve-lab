Proposed file path: docs/thread_logs/2026-01-21_main_docs-governance.md

* `Note: 本ファイルは改名済み（YYYY-MM-DD_HHMM 命名）。続編は legacy を参照：`
  * `docs/thread_logs/2026-01-21_1722_main_docs-governance_legacy.md`

# Thread Log

## Meta

* Date: 2026-01-21
* Branch: main
* Commit: 11f166b
* Version: v0.6.10
* Release Zip: rm-booking-curve-lab_20260121_1146_samp_main_11f166b_full.zip
* Scope: docs運用（Docs Gate/Close Gate）とテンプレ体系の整備、START_HERE新設

## Context

* Thread Log / Decision Log / 引継書の運用を「参照齟齬が起きない型」に落とし込むことを目的に、docs一式と templates を整備した。
* スレッド終盤のトークン溢れ（事故）を前提に、次スレ冒頭での **Docs Gate** を必須化し、更新手順をテンプレに固定した。
* “引継書単体で成立（連結作業ゼロ）”を目標に、handover_request/body をテンプレとして運用する形を整理した。

## Done

* 運用入口ドキュメントを新設

  * `docs/START_HERE.md` を追加（唯一の正、参照先、Gate、命名ルール、テンプレ一覧を集約）
* テンプレ体系を `docs/templates/` に集約し、次スレ/次担当が迷わないように標準手順を固定

  * `docs/templates/prompt_docs_update.md`（Docs Gate が Yes の場合の唯一手順）
  * `docs/templates/prompt_thread_log_generate.md`（Thread Log 生成テンプレ）
  * `docs/templates/prompt_decision_log_update.md`（Decision Log 更新テンプレ）
  * `docs/templates/handover_request.md` / `docs/templates/handover_body.md`（引継書生成と本文型）
  * `docs/templates/thread_start.md`（スレ冒頭の貼り付け用テンプレ）
* 運用ルールの正本を更新

  * `docs/dev_style.md` を更新し、Docs Gate/テンプレ参照先/運用上の注意（長文化時の締め）を明文化
* `docs/decision_log.md` の Status（未反映/反映済）を「実態に合わせて全件更新する」方針を合意（運用方針として確定）
* 次スレで「このスレ後半で追加・更新した docs/ルールの精査」をP0として行う方針を合意（不安点の前倒しチェック）

## Decisions (non-spec)

* スレッド終盤の事故回避のため、**次スレ冒頭で Docs Gate を必ず実施**し、Yesなら docs 更新を実装より先に行う（手順は `docs/templates/prompt_docs_update.md` を唯一の正とする）。
* 引継書は **ファイルとして `docs/handovers/` に格納**し、次スレは「ZIP＋そのファイルパス参照」で開始する運用に寄せる（連結作業を不要化）。
* `docs/decision_log.md` の Status は「今回の全洗い」で **実態に合わせて更新してよい**（合意済）。
* 次スレで `docs/decision_log.md` の並びを **時系列に揃える方針**（Yesで確定。実施方法は次スレで詰める）。

## Pending / Next

### P0

* 運用docs精査（Docs Gate：運用docs限定）

  * 対象：`docs/START_HERE.md` / `docs/dev_style.md` / `docs/templates/*`
  * 完了条件：参照先・Gate手順・唯一の正・命名ルールが矛盾なく接続し、運用上の迷いが出ない状態になっている
* このスレッド分の引継書を `docs/handovers/` に追加（スレ移行用）

  * 完了条件：次スレ冒頭が「ZIP＋handoverファイル参照」で開始できる

### P1

* `docs/decision_log.md` の並びを時系列に揃える（運用上の見落とし対策）

  * 完了条件：末尾10〜20件確認で“最新決定の見落とし”が起きない状態（並び替え or 代替ルール明文化のいずれか）

## Risks / Notes

* スレッド終盤はコンテキスト圧縮で前提が崩れやすい。議論を続けるより **Thread Log / Handover 作成に切り替えて閉じる**方が安全。
* Decision Log が時系列順でない場合、「末尾確認」だけでは見落としが出る。次スレで並びの是正（または検索ルールの併用）を検討する。
* 後半で追加・更新した docs は“運用の正本”として効くため、軽微な表現ズレでも事故に直結しうる。次スレ冒頭での精査を優先する。

## References

* `AGENTS.md`：AI運用ルールの唯一の正
* `docs/START_HERE.md`：入口（唯一の正、Gate、参照先、命名ルール）
* `docs/dev_style.md`：運用ルールの正本（Docs Gate、テンプレ参照）
* `docs/templates/prompt_docs_update.md`：Docs Gate Yes時の唯一手順
* `docs/templates/handover_request.md` / `docs/templates/handover_body.md`：引継書（依頼・本文型）
* `docs/templates/prompt_thread_log_generate.md`：Thread Log生成テンプレ
* `docs/templates/prompt_decision_log_update.md`：Decision Log更新テンプレ
* `docs/decision_log.md`：決定事項ログ（Status更新・並び順の課題あり）
* `docs/thread_logs/2026-01-20_main_release-v0.6.10_docs-spec-models-fix.md`：直近Thread Log（今回スレ分は未記載）

## Questions (if any)

* なし

この後続の検討は 2026-01-21_1722_main_docs-governance_legacy.md