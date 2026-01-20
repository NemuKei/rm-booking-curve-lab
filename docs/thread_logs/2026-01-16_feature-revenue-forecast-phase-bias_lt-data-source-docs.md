# ファイル名案: docs/thread_logs/2026-01-16_feature-revenue-forecast-phase-bias_lt-data-source-docs.md

# Thread Log: LT_DATA source（daily_snapshots）デフォルト化と docs 整合

## Meta

* Date: 2026-01-16（推定：本スレッドの会話日時）
* Branch: feature/revenue-forecast-phase-bias
* Commit: 8db40f3
* Zip: rm-booking-curve-lab_20260113_1424_samp_feature-revenue-forecast-phase-bias_8db40f3_full.zip
* Scope: make_release_zip.py 実行方法整理／LT_DATA 生成で timeseries 設定が空でも落ちないようにする方針確認／docs（spec_*・README）反映内容の整理と更新チェック

## Done（実装・変更）

* make_release_zip.py の実行方法（repo 直下で `python make_release_zip.py`）と主要オプション（--with-output-samples / --max-logs / --tag / --outdir / --profile / --no-git-only）を整理。
* LT_ALL 実行時のエラー原因を特定：`hotels.json` の `daikokucho` で `data_subdir` / `timeseries_file` が空文字のため設定不備扱いで例外。
* 「timeseries を使わない運用」前提で、`source="daily_snapshots"` の場合は `data_subdir` / `timeseries_file` が未設定でもエラーにしない方針を明確化。
* GUI 側の `source` デフォルトを `daily_snapshots` に寄せ、事故（未設定 timeseries による停止）を減らす方向を合意。
* docs 反映の必要箇所を抽出（spec_overview / spec_data_layer / BookingCurveLab_README）。
* docs 更新チェックを実施し、反映済みポイントと未整合（`data_subdir` 二重定義・セル定義 rooms 固定）を指摘。
* 未整合を解消するための md コピペ用修正文（置換ブロック）を提示。

## Decisions（決定）

* Decision:

  * `source="daily_snapshots"` のときは `hotels.json` の `data_subdir` / `timeseries_file` を必須にしない（未設定でも処理継続）。
  * `source="timeseries"` のときのみ `data_subdir` / `timeseries_file` を必須として厳格チェックし、欠損なら安全側に STOP。
  * LT_DATA は互換ファイル（従来名）を維持しつつ、指標別（rooms/pax/revenue）ファイルを追加で出力する前提で docs を整合させる。
* Why:

  * 現行運用（daily_snapshots）で timeseries 設定を要求すると、テンプレ空欄や旧 config により無駄な停止が起きる（機会費用が大きい）。
  * 一方で legacy 比較用途として timeseries ルートは残すため、必要時だけ厳格チェックにするのが最小リスク。
  * 出力成果物が増えている以上、「唯一の正」である spec_* と README が追従しないと再現性・引き継ぎ性が崩れる。

## Docs impact（反映先の候補）

* spec_overview: `hotels.json` の `data_subdir` / `timeseries_file` の位置づけ（legacy）と、source 別必須条件の明記。二重定義の解消。
* spec_data_layer: LT_DATA 出力ファイル（互換名＋指標別）と、セルの意味を value_type（rooms/pax/revenue）で一般化。
* spec_models: （今回は必須変更なし）モデルが rooms 前提のままなら位置づけ注記のみ検討。
* spec_evaluation: （今回は必須変更なし）収益系評価を正式にやる場合に別タスクで。
* BookingCurveLab_README: 生成物一覧を互換名＋指標別に更新（txt 形式でコピペ文を用意）。

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: `hotels.json` の `data_subdir` / `timeseries_file` を source 別に必須条件を分ける旨を明記

    * 理由: 実装が `daily_snapshots` では不要・`timeseries` では必須に変わっており、仕様が追従しないと混乱・再発が確実
    * Status: 一部反映／要整合（`data_subdir` 二重定義が残存）
    * 反映先: docs/spec_overview.md（ホテル設定の説明セクション）
  * 項目: LT_DATA の出力ファイル（互換名＋rooms/pax/revenue 別）を明記

    * 理由: 出力成果物が増えているため、再現・確認・引き継ぎの前提が崩れる
    * Status: 反映済み（ただし後段のセル定義が rooms 固定で矛盾）
    * 反映先: docs/spec_data_layer.md（LT_DATA 出力の説明セクション）
  * 項目: LT_DATA セル定義を value_type（rooms/pax/revenue）で一般化

    * 理由: 仕様本文が rooms 固定のままだと “唯一の正” が実装と矛盾する
    * Status: 未反映（置換ブロック提示済み）
    * 反映先: docs/spec_data_layer.md（「セルの意味」セクション）
  * 項目: GUI 実行後の生成物一覧を更新（txt）

    * 理由: 運用者が成果物を誤認するリスクが高い
    * Status: 反映済み
    * 反映先: BookingCurveLab_README.txt（5-2 月次 LT_DATA 手順）
* docs不要:

  * 項目: spec_evaluation の更新

    * 理由: 今回は評価指標定義そのものを変更していない（収益系評価の正式導入は別タスク）
  * 項目: spec_models の大改訂

    * 理由: 今回は LT_DATA の多指標出力と source デフォルトの扱いが中心で、モデル定義の数式・仕様変更までは不要

## Known issues / Open

* docs/spec_overview.md に `data_subdir` の旧定義が残り、二重定義で矛盾している（要整理）。
* docs/spec_data_layer.md の「セルの意味」が rooms 固定の説明のまま（value_type 一般化が未反映）。
* README.md 側の LT_DATA 出力例が単一ファイル前提のまま残っている可能性（運用事故防止の観点で追記推奨）。

## Next

* P0:

  * spec_overview: `data_subdir` 二重定義を解消し、source 別必須条件を一貫した表現に統一する。
  * spec_data_layer: 「セルの意味」を value_type（rooms/pax/revenue）で一般化し、本文に “rooms を例にする” 注記を入れて矛盾を消す。
* P1:

  * README.md: LT_DATA 出力（互換名＋指標別）と `--source`（default daily_snapshots）を追記し、利用者の再現手順を強化する。
