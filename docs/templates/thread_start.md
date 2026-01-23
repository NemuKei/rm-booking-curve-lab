# スレッド冒頭テンプレ（貼り付け用）

## 0) 参照の唯一の正
- 共有物の唯一の正：このスレッドのアンカーZIP（添付のZIP。スレッド内は固定）
- 仕様の唯一の正：docs/spec_*.md と AGENTS.md
- スレッド途中で修正版ZIPを渡して確認する場合は candidate_zip（検証対象）として扱い、アンカーZIPは固定する（アンカー更新したい場合は新スレッドへ移行）。

## 1) このスレッドの目的（1〜3行）
- docs/handovers/ の最新を参照（なければ docs/START_HERE.md の Thread Start Gate に従う）

## 2) 入力（必須）
- アンカーZIP：添付参照
- Branch：添付参照
- Commit：添付参照
- 優先して見るファイル：
  - docs/handovers/<latest>.md（あれば）
  - docs/thread_logs/<latest>.md
  - docs/decision_log.md（末尾10〜20件）
  - 関連 spec_*（必要分）

## 3) 会話カウンタ（安全策：必須）
- assistant は各回答の先頭に **A-001 / A-002 ...** を付ける
- user も各発言の先頭に **U-001 / U-002 ...** を付ける（推奨）

### ハードリミット（強制）
- **A-25 到達で“締めモード”**：議論停止 → Closeout Pack（docs/templates/prompt_closeout_pack.md）を作って終了
- **A-10 / A-20 でチェックポイント**：継続するなら、目的/スコープ/完了条件を再掲して固定

### 逸脱検知（強制）
- assistant が A-番号を付け忘れたら、その時点で危険域とみなし、次のどちらかを実行：
  1) 直ちに締めモード（ログ作成）へ
  2) 新スレッド移行（アンカーZIP＋handoverファイル指定）

## 4) スレ冒頭 Docs Gate
- Docs Gate が Yes の場合、docs更新は `docs/templates/prompt_docs_update.md` を唯一の手順として行う