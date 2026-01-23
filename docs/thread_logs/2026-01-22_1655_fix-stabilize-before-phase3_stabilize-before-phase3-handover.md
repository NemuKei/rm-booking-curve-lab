Proposed file path: docs/thread_logs/2026-01-22_1655_fix-stabilize-before-phase3_stabilize-before-phase3-handover.md

# Thread Log

## Meta

* Date: 2026-01-22
* Branch: fix/stabilize-before-phase3
* Commit: 78d20b8
* Version: tag 20260122_1641_samp_fix-stabilize-before-phase3_78d20b8
* Release Zip: rm-booking-curve-lab_20260122_1641_samp_fix-stabilize-before-phase3_78d20b8_full.zip
* Scope: Phase3前の安定化ブランチ準備＋引継書作成（P0バグ3点の仕込み）

## Context

* docs運用（anchor/source/candidate ZIP、HHMM命名、legacy扱い）が整った状態で、Phase3に入る前の安定化（バグ修正）に着手する方針を固めた。
* 安定化用ブランチ `fix/stabilize-before-phase3` を切り、最新release ZIP（78d20b8）を作成。
* 次スレッドで修正を進める前提で、引継書（handover本文）を作成した。

## Done

* 安定化ブランチ `fix/stabilize-before-phase3` の最新release ZIPを作成し、次スレッドのアンカー候補として整備した。

  * Release Zip: `rm-booking-curve-lab_20260122_1641_samp_fix-stabilize-before-phase3_78d20b8_full.zip`
  * `VERSION.txt` / `MANIFEST.txt` の branch/commit/tag 整合を確認。
* 引継書（本文）ドラフトを作成（次スレでの着手点をP0に整理）。

  * 参照した主なパス（引継に記載）：

    * `src/booking_curve/segment_adjustment.py`（recent90のcalendar_features欠損で落ちる疑い）
    * `src/run_build_lt_csv.py`（LT_ALL導線候補）
    * `src/booking_curve/gui_backend.py`（LT_ALL呼び出し／TopDownRevPAR算出候補）
    * `docs/spec_*.md`, `AGENTS.md`, `docs/decision_log.md`（運用/仕様の唯一の正の確認）

## Decisions (non-spec)

* Phase3着手前に「安定化パック（落ちる・ズレるの是正）」を先に実施する。
* スコープは当面以下の3点に固定（追加拡張しない）：

  * recent90：calendar_features CSV欠損時クラッシュ（P0で修正対象）
  * LT_ALL：エラー（スクショ/ログ提示後に再現→原因特定→修正）
  * TopDownRevPAR：予測値と不一致（スクショ/ログ提示後に再現→原因特定→修正）
* LT_ALL / TopDownRevPAR は、先に推測で方針を固定せず「実ログ提示→切り分け」後に実装修正へ進める。

## Pending / Next

### P0

* recent90：calendar_features欠損時に落ちないフォールバックを実装

  * 完了条件：`output/calendar_features_{hotel_tag}.csv` が無い状態でも recent90 が停止せず、補正は無効化（係数=1.0相当）で結果が出る。
* LT_ALL：エラーのスクショ/ログ受領→再現→修正（失敗月スキップ＋ログ化案含む）

  * 完了条件：LT_ALLが全停止せず、成功分は出力され、失敗月は一覧として残る。
* TopDownRevPAR：不一致のスクショ/ログ受領→再現→集計ロジック特定→修正

  * 完了条件：同一 as_of / 同一モデルで、TopDownRevPARが「正とする予測値の算出」と一致する（不一致時は診断情報を出す）。

### P1

* recent90フォールバック時のWARNを検知可能な形で残す（ログ/欠損一覧）

  * 完了条件：欠損が起きた事実と対象（hotel_tag等）が後から追える。

## Risks / Notes

* LT_ALL / TopDownRevPAR は原因が複数あり得る（入力CSV取り違え、as_of不一致、欠損/重複日付の集計ロジックなど）。ログ無しで先に実装修正へ入ると手戻りが大きい。
* recent90のcalendar_featuresは「必須前提」なのか「任意で補正」なのかが未確定。方針が変わると実装（フォールバックor生成必須）が変わる。

## References

* `AGENTS.md`：運用ガードレール（唯一の正、推測禁止、Docs Gate）
* `docs/spec_overview.md`：Phase/モデルの位置づけ確認
* `docs/spec_data_layer.md`：欠損/失敗ログの扱い（LT_ALLのスキップ設計の整合）
* `docs/spec_models.md`：モデル定義（recent90 / LT_ALL / TopDownRevPAR）
* `docs/spec_evaluation.md`：as_of/評価出力の扱い（TopDown整合確認に使う）
* `docs/decision_log.md`：直近決定（運用側の整合確認）
* `src/booking_curve/segment_adjustment.py`：recent90 calendar_features読込（クラッシュ原因候補）
* `src/run_build_lt_csv.py`：LT_ALL導線候補
* `src/booking_curve/gui_backend.py`：LT_ALL呼び出し、TopDownRevPAR算出候補
* `src/gui_main.py`：GUI起動・導線確認