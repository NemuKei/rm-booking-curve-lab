# ファイル名案: docs/thread_logs/2025-12-20_feature-daily-snapshots-partial-build_2mode-missing-report.md

# Thread Log: 欠損検知2モード設計と月次カーブ整合・評価再計算の安定化

## Meta

* Date: 2025-12-20（ユーザー指定：引継書作成日を採用）
* Branch: feature/daily-snapshots-partial-build
* Commit: （未提示）
* Zip: （未提示）
* Scope:

  * 月次カーブのLT定義崩れを修正し、daily_snapshots基準へ統一
  * 欠損補完（NOCB）を「GUI表示直前のみ」に限定（データレイヤはNaN保持）
  * RAW取り込みの安全性向上（サブフォルダ対応、重複即エラー）
  * missing_report（欠損レポート）機能の導入・運用導線追加
  * 欠損検知の穴（ASOF丸抜け・古い月ノイズ）を発見し、運用/監査の2モード化を合意

## Done（実装・変更）

* GUI月次カーブ生成を、LT_DATAフォールバック無しで daily_snapshots から生成するロジックへ統一（ASOFベース月次LT定義へ寄せた）。
* monthly_curve CSVは raw（NaN保持）で保存し、GUI表示に渡す直前のみNOCBで欠損補完する方針へ整理・合意。
* 予測/評価の欠損値対応は、当面「補完せずサンプル除外」を基本とする方針に合意（0補完はしない）。
* 評価再計算が通らないエラーの切り分け・修正（最終的に再計算が通る状態を確認）。
* ASOF比較タブで特定月しか表示されない事象を、キャッシュ起因として特定し解消（CSVは全期間出ていた）。
* RAWデータのサブフォルダ配置（例：月フォルダ配下）でも更新が通るように対応し、動作確認。
* (target_month, asof) の同一キー重複（拡張子違い等含む）を即エラー停止し、両パス表示する安全側挙動を実装・確認。
* マスタ設定に「欠損チェック（CSV生成→開く）」導線を追加し、`output/missing_report_{hotel}.csv` 生成・閲覧を確認。
* 意図的に当月ファイルを1日分抜くテストで、missing_reportに `raw_missing` が出ることを確認。
* GUIバックエンド内の lint 指摘（未import/未使用変数）を手修正で解消（`re`未import等）。

## Decisions（決定）

* Decision:

  * 月次カーブ（monthly_curve）は `daily_snapshots` から生成する方式を正とする。
  * 月次カーブ生成で `LT_DATA` をフォールバック経路として使用しない（禁止）。
  * 月次LT定義は **ASOFベース（month_end - asof_date）** を採用する。
  * `monthly_curve` 生成物は **rawのまま保存（NaN保持）** し、欠損補完（NOCB）は **GUI表示直前のみ** 適用する。
  * 予測・評価の計算は当面 **欠損補完を行わず、欠損サンプルは除外**を基本とする（0補完は採用しない）。
  * RAW取り込みは **サブフォルダ配置を許可**するが、同一キー **(target_month, asof)** の重複は **即エラー停止**（両パス表示）とする。
  * 欠損検知（missing_report）は **運用（入れ忘れ）/監査（歴史ギャップ）** の2モードに分離する。
  * 運用欠損チェックのASOF窓は **180日** とする。
  * 運用モードは **ASOF丸抜け（asof_missing）** と **(ASOF, STAY MONTH)取りこぼし（raw_missing）** を別種として扱う（asof_missingは取り込み対象外）。
  * 監査モードは **STAY MONTHの最古〜最新範囲** に限定し、期待ASOFは日次で生成する。
* Why:

  * 月次カーブのLT定義が分裂すると曲線が崩れ、LT_DATA由来の不整合が再発するため。
  * データレイヤのNaN保持思想と整合させ、監査・再現性・後続分析に影響を出さないため（補完は表示用途に限定）。
  * 欠損補完（特に0補完）は歪み・未来リーク・ACT整合のリスクが高いため、まず安全側（除外）でベースラインを確立するため。
  * サブフォルダ取り込みは利便性が高いが、重複が事故要因なので強いガード（即エラー）が必須なため。
  * 現行の欠損抽出は「観測されたASOF起点」ゆえ、ASOF丸抜けが検知できず、また古い期間の保存粒度差でノイズが出るため、運用/監査を分ける必要があるため。

## Docs impact（反映先の候補）

* spec_overview:

  * 存在しない `booking_curve/evaluation_multi.py` 参照が混入していた可能性（差し替え済み報告あり）。残存参照の有無を要確認。
* spec_data_layer:

  * 「monthly_curveはNaN保持、補完はGUI表示直前のみ（NOCB）」の明文化。
  * missing_report（運用/監査2モード、ASOF窓180日、asof_missing/raw_missing種別）を追記。
  * RAWのサブフォルダ許可、重複即エラー、拡張子方針（読めるものは許可）を追記。
* spec_models:

  * 予測/評価の欠損値取り扱い（当面：補完なし、サンプル除外、0補完禁止）の明文化。
* spec_evaluation:

  * ACT欠損を含む場合の評価遮断/除外の方針導線、欠損検知の扱い（asof_missingの意味）を注記。
* BookingCurveLab_README:

  * RAW配置（サブフォルダ可）、重複即エラー、欠損チェック（CSV）、運用ASOF窓（180日）等の運用ガイド追記。

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: `booking_curve/evaluation_multi.py` 参照の整合確認

    * 理由: 実ファイル不在が発覚。docs参照が残ると新規参加者が迷う。
    * Status: 未反映（差し替え済み報告はあるが、残存参照の有無が未確認）
    * 反映先: docs/spec_overview.md（ファイル構成/参照箇所）
  * 項目: 「monthly_curveはNaN保持、補完はGUI表示直前のみ（NOCB）」

    * 理由: データレイヤ思想の根幹で、以後の設計判断に直結。
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（欠損・補完ポリシー節）
  * 項目: 欠損検知2モード（運用/監査）＋ASOF窓180日＋asof_missing/raw_missing

    * 理由: 運用ルールとして固定する決定であり、UI/運用手順にも影響。
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（missing_report節）、docs/spec_overview.md（運用フロー節）
  * 項目: 予測/評価は欠損補完なし（サンプル除外）、0補完禁止

    * 理由: モデル精度評価の前提が変わるため。
    * Status: 未反映
    * 反映先: docs/spec_models.md（欠損値の扱い節）、docs/spec_evaluation.md（評価対象の除外ルール節）
  * 項目: RAWサブフォルダ許可＋(target_month, asof)重複即エラー停止

    * 理由: 入力データ運用の固定ルールで、事故防止のため明文化が必要。
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（raw取り込みルール節）、BookingCurveLab_README（入力準備）
* docs不要:

  * 項目: Ruffの個別指摘（re未import、未使用変数）そのもの

    * 理由: 実装上のlint是正であり、運用ルールとして固定する内容ではない。
    * Status: N/A

## Known issues / Open

* snapshot_missing（生成後欠損）の定義は誤爆リスクが高い。ACT例外と月末ACT（11/30 ACTは 12/1以降ASOFで取得）に注意して厳密化が必要。
* 欠損検知2モード・asof_missing導入・欠損のみ取り込み（raw_missingのみ）等は合意済みだが、実装は次工程（未完了の可能性あり：状態要確認）。

## Next

* P0:

  * missing_reportを2モード化（ops/audit）し、運用モードに asof_missing（ASOF丸抜け）を追加。
  * 運用モード：ASOF窓180日、日次期待＋severity設計。raw_missingは当月+翌3ヶ月の取りこぼし検知に限定。
  * 監査モード：STAY MONTHのmin..max範囲に限定し、期待ASOFを日次で生成してギャップ可視化。
  * GUI（マスタ設定）に「欠損チェック（運用）」「欠損監査（全期間）」「欠損のみ取り込み（raw_missingのみ）」導線を追加/整備。
  * today と latest_asof の鮮度warning（GUI表示）を追加。
* P1:

  * snapshot_missingの定義を厳密化（ACT例外・月末ACTの強調、誤爆抑制）。
  * docs更新（spec_overview/spec_data_layer/spec_models/spec_evaluation/README）を、実装反映後に差分で整理して追記。

