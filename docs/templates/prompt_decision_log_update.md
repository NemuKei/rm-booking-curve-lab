【目的】
直近スレッドの Thread Log から「横断して効く決定」だけを抽出し、docs/decision_log.md に追記する差分を作ってください。
注意：Decision Logは仕様ではない。必ず spec_* への導線（どのspecに反映が必要か）を書くこと。

【入力】
- Thread Log（このスレッド分）：<<<ここにThread Log全文を貼る>>>

【IDルール（厳守）】
- 決定IDは必ず `D-YYYYMMDD-XXX` 形式で出力する。
- YYYYMMDD は Thread Log の `Meta Date` を使う（例：2026-01-05 → 20260105）。
- 連番（XXX）は採番スクリプトが付与するので、必ず `XXX` のままにする（001等にしない）。

【出力フォーマット（厳守）】
- 追加するエントリのみを Markdown で出してください（全文再出力しない）。
- 各エントリは以下の形。

## D-YYYYMMDD-XXX <短いタイトル>
- Decision:
  - ...
- Why:
  - ...
- Spec link:
  - docs/spec_overview.md: （節名 or 追記予定）
  - docs/spec_models.md: ...
  - docs/spec_data_layer.md: ...
  - docs/spec_evaluation.md: ...
- Status: （spec反映済 / 未反映）

【抽出ルール】
- “実装しただけ” はDecisionに入れない
- “運用ルールとして固定した”“以後こうする” だけを入れる
- 数値（clip、閾値、対象範囲、保存先）を決めたものは必ず入れる
