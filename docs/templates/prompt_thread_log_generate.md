# Thread Log 生成プロンプト（テンプレ）

## 目的
このスレッドの会話ログと最新ZIPを根拠に、`docs/thread_logs/` に追加する **Thread Log（1本）** を作成する。

## 重要：Thread Log は仕様ではない
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- Thread Log は「作業の追跡・再現のためのログ」であり、仕様決定そのものではない

---

## 運用ルール（必ず遵守）
- このスレッドのアンカーZIP（スレッド冒頭で宣言したZIP）を唯一の正として参照
- 推測で埋めない。不足情報は「不足」として明示し、最後に質問を最大5つまでまとめること
- 個人情報・企業情報・機密が含まれる具体例は書かない（ダミー化）
- ここで議論や提案を始めない（まずログ作成が目的）

---

## 入力（貼り付ける）
- 最新 release ZIP 名：`<<<ここにZIPファイル名>>>`
- Branch：`<<<例: main / feature-xxxx>>>`
- Commit：`<<<例: 77ef721>>>`
- Version：`<<<例: v0.6.10>>>`
- スレッド会話ログ：`<<<ここにこのスレッドの会話ログを貼る>>>`

※補足：可能なら ZIP 内の `docs/decision_log.md` 末尾（直近10〜20件）も確認したうえで、Thread Log の「決定事項」や「反映状況」が矛盾しないように書くこと。

---

## 出力（厳守）
### 1) Proposed file path（必須・1行）
- `Proposed file path: docs/thread_logs/YYYY-MM-DD_<branch>_<scope>.md`

命名ルール：
- YYYY-MM-DD は Thread Log の作成日
- `<scope>` は短く（例：`docs-align` / `release-v0.6.10` / `pace14-market`）
- ファイル名は英数字・ハイフン・アンダースコアのみ（記号【】：は使わない）

### 2) 本文（Markdown）
- 以下の見出し構成で、**Thread Log 1本分の本文のみ**を出力する
- 余計な前置き・解説は不要

---

## Thread Log 本文フォーマット（この順序で出力）

# Thread Log

## Meta
- Date: YYYY-MM-DD
- Branch: <branch>
- Commit: <commit>
- Version: <version>
- Release Zip: <zip filename>
- Scope: <短い要約（1行）>

## Context
- このスレッドで何をやっていたか（2〜5行）

## Done
- 完了したこと（箇条書き）
  - 変更した主なファイルパスを必ず含める（例：`docs/spec_data_layer.md`）
  - 「何をどう変えたか」を短く（仕様の唯一の正への反映など）

## Decisions (non-spec)
- このスレッドで「合意として扱われたこと」を箇条書き
  - ただし仕様は spec_* が唯一の正。ここは “ログ” として書く
  - Decision Log に起票/更新が必要なものがあれば明示（例：`D-...`）

## Pending / Next
- 未完・次にやること（P0/P1 で箇条書き）
- それぞれに「完了条件」を1行で付ける

## Risks / Notes
- 参照齟齬・将来事故りそうな点（短く）
- 例：仕様と実装がズレている等（必要なら）

## References
- 参照ファイル（パス＋一言理由）
  - `docs/spec_*.md` / `AGENTS.md` / 該当コード / ログ など

## Questions (if any)
- 不足情報がある場合のみ。最大5つ。
- Yes/No か短文で答えられる形を優先。