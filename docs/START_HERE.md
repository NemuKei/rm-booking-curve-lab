# START_HERE

このリポジトリは **「仕様の唯一の正」** と **「共有物の唯一の正」** を明確に分けて運用します。  
迷ったらこのページに戻ってください。

---

## 唯一の正

### 仕様の唯一の正（外部仕様・ロジック定義）
- `docs/spec_overview.md`
- `docs/spec_data_layer.md`
- `docs/spec_models.md`
- `docs/spec_evaluation.md`

### AI運用ルールの唯一の正（プロンプト規約・禁止事項）
- `AGENTS.md`

### 共有物の唯一の正（参照齟齬防止）
- **make_release_zip.py で作成した最新ZIP**
  - 手作業で単体ファイルを添付して運用しない（参照齟齬の温床）
  - 各スレッドではアンカーZIPを固定し、スレッド間で共有する際は常に最新ZIPを唯一の正とする

- スレッド途中で修正版ZIPを渡して検証する場合は candidate_zip（検証対象）として扱い、アンカーZIPは固定する（アンカー更新したい場合は新スレッドへ移行）。

---

## 基本ディレクトリ（どこを見ればいいか）

- 引き継ぎ（正本）：`docs/handovers/`
- Thread Log：`docs/thread_logs/`
- Decision Log：`docs/decision_log.md`
- プロンプト／テンプレ：`docs/templates/`

---

## スレッド開始時の最小手順（Thread Start Gate）

1. 最新ZIPを確認（ファイル名／branch／commit）
2. `docs/handovers/` の最新を読む（あれば最優先）
3. `docs/thread_logs/` の直近1本を読む
4. `docs/decision_log.md` の末尾（直近10〜20件）を読む
5. 今スレッドの目的・スコープ・完了条件を 1〜3 行で固定する

---

## Docs Gate（次スレ冒頭で迷わないための規律）

スレッド終盤はトークン溢れで事故りやすいので、次スレ冒頭で必ず以下を判定します。

### 判定
- **Yes（docs更新が必要）**：未反映の決定が spec_* に影響する／Thread Log に docs残がある／仕様と実装の乖離が運用事故になりうる
- **No（docs更新不要）**：直近の決定は spec_* に反映済／未反映は将来検討 or 実装のみ

### Yes の場合の唯一の手順
- `docs/templates/prompt_docs_update.md` に従って更新案を作成し、**実装作業より先に spec_* を更新**する

---

## スレッド終了時（Close Gate）

スレッドを閉じる前に、以下を残します（最低限）。

1. Closeout Pack を作成（1回の依頼でまとめて生成）
   - 引き継ぎ（正本）：`docs/handovers/`
   - Thread Log：`docs/thread_logs/`
   - Decision Log 追記（必要な場合のみ）：`docs/decision_log.md`
2. make_release_zip.py でアンカーZIPを作成し、それを唯一の共有物とする
※スレッド終了時に作成するアンカーZIPは、次スレッド開始時点のアンカーZIP（Start Anchor）として引き継ぐ。以後の参照の唯一の正はそのアンカーZIPで固定する。

---

## テンプレ一覧（ここから使う）

- Thread Log 生成：`docs/templates/prompt_thread_log_generate.md`
- Decision Log 更新：`docs/templates/prompt_decision_log_update.md`
- docs 更新：`docs/templates/prompt_docs_update.md`
- Closeout Pack（1本化）：`docs/templates/prompt_closeout_pack.md`
- 引き継ぎ依頼：`docs/templates/handover_request.md`
- 引き継ぎ本文（型）：`docs/templates/handover_body.md`
- スレッド冒頭テンプレ（貼り付け用・任意）：`docs/templates/thread_start.md`（ある場合）

---

## 命名ルール（最低限）

### handovers
- `docs/handovers/YYYY-MM-DD_HHMM_<type>_<scope>__handover.md`

### thread_logs
- `docs/thread_logs/YYYY-MM-DD_HHMM_<type>_<scope>__thread_log.md`

共通：
- ファイル名は **英数字・ハイフン・アンダースコアのみ**
- `【】` `：` などの記号は避ける（将来の自動処理で詰む）
- HHMM は作成時刻（JST, 24h）。同日・同scopeの衝突を機械的に避けるため、新規作成は原則 HHMM 付きとする。

---

## 機密・サンプルデータのルール（例外なし）
- ZIPに含める `output/` `log/` `sample/` は **必ずダミー**
- 個人情報・企業機密が混入し得る実データは同梱しない

---

## トークン溢れ対策（運用で潰す）
- 長文化したら議論を止め、Close Gate（Thread Log / Handover）に移行する
- 次スレ冒頭で Docs Gate を必ず実施する
- （必要なら）会話カウンタ運用（A-### / U-###）を `docs/dev_style.md` の規約として採用する

---

## 最後に
迷ったら順番はこれです：
1) `AGENTS.md`  
2) `docs/spec_*.md`  
3) `docs/handovers/` → `docs/thread_logs/` → `docs/decision_log.md`  
4) `docs/templates/`（手順はテンプレに従う）