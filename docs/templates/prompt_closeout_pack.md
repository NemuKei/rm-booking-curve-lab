# Closeout Pack 生成プロンプト（テンプレ）
（= Handover / Thread Log / Decision Log Patch を **1回の依頼で**まとめて作る）

## 目的
このスレッドをクローズするために、以下の成果物を **同一の根拠（最新ZIP＋会話ログ）** から参照齟齬なく生成する。

- A) 引き継ぎ（正本）：`docs/handovers/` に追加する 1本
- B) Thread Log：`docs/thread_logs/` に追加する 1本
- C) Decision Log 追記差分（必要な場合のみ）：`docs/decision_log.md` に追記する **差分（追加分のみ）**

※この依頼は「議論」ではなく「クローズ作業」です。余計な提案・拡張はしない。

---

## 重要：唯一の正（必ず遵守）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：**この依頼に添付された最新ZIP（make_release_zip.py で作成したもの）**
  - 単体ファイル添付での推測運用は禁止
  - ZIPがない場合は作業を止め、ZIP添付を要求する

---

## 運用ルール（必ず遵守）
- 推測禁止。不足があれば「不足」として明示し、最後に Questions（最大5つ）
- 個人情報・企業情報・機密の具体例は書かない（ダミー化）
- 既存ファイルの全文再出力は禁止（Decision Logは追加差分のみ）
- ファイル名は **英数字・ハイフン・アンダースコアのみ**（`【】` `：` 等は使わない）
- HHMM は作成時刻（JST, 24h）

---

## 参照齟齬防止（品質ゲート：必須）
作業開始前に ZIP 内で以下を確認し、矛盾がないか検算する。

1) `docs/handovers/` の最新（あれば最優先で読む）  
2) `docs/thread_logs/` の直近1本  
3) `docs/decision_log.md` の末尾（直近10〜20件）

矛盾・不明があれば、成果物を埋めずに最後の Questions に入れる（最大5つ）。

---

## 入力（必ず貼り付ける）
- 最新 release ZIP 名（この依頼に添付されたZIP）：`<<<ここにZIPファイル名>>>`
- Branch：`<<<例: main / feature-xxxx>>>`
- Commit：`<<<例: 18c7624>>>`
- Version：`<<<例: v0.6.10>>>`
- Scope（短い要約1行）：`<<<例: fix-stabilize-before-phase3>>>`
- スレッド会話ログ：`<<<ここにこのスレッドの会話ログを貼る>>>`

---

# 出力（厳守）
以下の順番で、**3成果物をそれぞれ“完成品”として**出力する。
（前置き・解説・余談は不要）
Markdownのコードブロック形式（コピー可能な枠内）で分けて出力すること。

---

## A) 引き継ぎ（正本）
- `docs/templates/handover_body.md` の **見出し順・項目構造に完全準拠**して作成する
- 先頭行は必ずこれ：
  - `Proposed file path: docs/handovers/YYYY-MM-DD_HHMM_<branch>_<scope>.md`
- 以降は **handover_body.md のテンプレを埋めた本文のみ**を出力する
- 「決定事項」は *仕様* ではない（仕様の唯一の正は spec_* と AGENTS.md）。ここは“合意ログ”として要点のみ。

---

## B) Thread Log（1本）
- `docs/templates/prompt_thread_log_generate.md` の **出力フォーマットに完全準拠**して作成する
- 先頭に必ず以下を含める：
  - `Proposed file path: docs/thread_logs/YYYY-MM-DD_HHMM_<branch>_<scope>.md`
- 本文の見出し構成は、テンプレ内の「Thread Log 本文フォーマット（この順序で出力）」に完全準拠

---

## C) Decision Log 追記差分（条件付き）
### 生成条件
- このスレッドで「横断して効く決定」が **発生した場合のみ** 生成する
- 発生していない場合は、次の **1行のみ** を出力して終了：
  - `Decision Log patch: none`

### 生成する場合（差分のみ）
- `docs/templates/prompt_decision_log_update.md` の **運用ルール・IDルール・出力思想に完全準拠**
- 先頭に必ず以下を出す：
  - `Proposed patch target: docs/decision_log.md`
- 既存エントリの全文再出力は禁止。**追加するエントリ（差分）だけ**を Markdown で出す
- 決定IDは `D-YYYYMMDD-XXX`、**XXXは必ずXXXのまま**（001等にしない）
- 各決定に **spec_* への導線（どのspecに反映が必要か）** を必ず書く

---

## Questions（不足がある場合のみ）
- 最大5つ
- Yes/No か短文で答えられる形を優先