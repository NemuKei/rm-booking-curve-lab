# スレッド冒頭テンプレ（貼り付け用）

## 0) 参照の唯一の正
- 共有物の唯一の正：最新ZIP（make_release_zip.py で作成）
- 仕様の唯一の正：docs/spec_*.md と AGENTS.md

## 1) このスレッドの目的（1〜3行）
- 目的：
- スコープ（触るファイル）：
- 完了条件：

## 2) 入力（必須）
- 最新ZIP：<zip filename>
- Branch：<branch>
- Commit：<commit>
- 優先して見るファイル：
  - docs/handovers/<...>.md（あれば）
  - docs/thread_logs/<latest>.md
  - docs/decision_log.md（末尾10〜20件）
  - 関連 spec_*（必要分）

## 3) 会話カウンタ（安全策：必須）
- assistant は各回答の先頭に **A-001 / A-002 ...** を付ける
- user も各発言の先頭に **U-001 / U-002 ...** を付ける（推奨）

### ハードリミット（強制）
- **A-25 到達で“締めモード”**：議論停止 → Thread Log / Decision Log / Handover を作って終了
- **A-10 / A-20 でチェックポイント**：継続するなら、目的/スコープ/完了条件を再掲して固定

### 逸脱検知（強制）
- assistant が A-番号を付け忘れたら、その時点で危険域とみなし、次のどちらかを実行：
  1) 直ちに締めモード（ログ作成）へ
  2) 新スレッド移行（最新ZIP＋handoverファイル指定）

## 4) 次スレ冒頭 Docs Gate
- Docs Gate が Yes の場合、docs更新は `docs/templates/prompt_docs_update.md` を唯一の手順として行う
