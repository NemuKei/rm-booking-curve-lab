# ファイル名案: docs/thread_logs/2026-01-20_feature-daily-snapshots-partial-build_2mode-missing-report.md

# Thread Log: 欠損検知2モード設計と月次カーブ整合・評価再計算の安定化

## Meta

* Date: 2026-01-20（推定：会話のタイムスタンプより）
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

  * 月次カーブ生成は「daily_snapshots → monthly_curve生成」を正とし、LT_DATAフォールバックは使わない。
  * monthly_curve生成物は rawのまま保存（NaN保持）し、欠損補完はGUI表示直前のみ（NOCB）。
  * 予測/評価は当面「欠損補完なし（サンプル除外）」を基本とし、補完モードは後回し。
  * RAWサブフォルダ対応は導入するが、重複検知とセットで実装し、重複は即エラー停止（安全側）。
  * 欠損レポートは「運用欠損（入れ忘れ）」と「監査欠損（歴史的ギャップ）」の2モードに分離する。
  * 運用欠損モードのASOF期待列は日次（案C：日次期待＋severityで緩急）とし、ASOF丸抜け（asof_missing）を検知対象に加える。
  * 運用欠損モードのASOF窓は180日とする。
  * 監査欠損モードはSTAY MONTHの最古〜最新範囲に限定し、期待ASOFは日次で良い。
  * 欠損一覧からの再取り込みを容易にするため、「欠損のみ取り込み」ボタンを実装する（raw_missingのみ対象、asof_missingは案内のみ）。
* Why:

  * 月次カーブのLT定義が分裂し、LT_DATA由来の崩れが生じるため（ASOF月次LT定義へ統一が必要）。
  * データレイヤのNaN保持思想と整合させ、後続分析・監査で生データの欠損を保持するため（補完は表示用途に限定）。
  * 欠損補完（特に0補完）は将来の歪み・未来リーク・ACT整合のリスクが高いため、まずは欠損除外で評価する。
  * サブフォルダ取り込みは利便性が高いが、重複が事故要因なので強いガード（即エラー）が必須。
  * 現行の欠損抽出は「観測されたASOF起点」ゆえ、ASOF丸抜けが検知できず、また古い時代の保存粒度差でノイズが出るため、運用/監査を分ける必要がある。
  * 運用は入れ忘れ検知が目的で、監査は棚卸しが目的であり、同一ロジックだとどちらも運用不能になるため。

## Docs impact（反映先の候補）

* spec_overview:

  * `booking_curve/evaluation_multi.py` の参照誤りが疑われ、実際にファイルが存在しない問題が発覚（差し替え済み報告あり、残存参照の有無を要確認）。
* spec_data_layer:

  * 「データレイヤはNaN保持、補完はGUI表示直前のみ（NOCB）」を明文化候補。
  * missing_report（欠損レポート）の位置づけ（運用/監査モード、出力CSV）を追記候補。
* spec_models:

  * 予測/評価における欠損値扱いの原則（当面：補完なし、サンプル除外）を明文化候補。
* spec_evaluation:

  * ACT欠損の扱い（評価遮断/除外）、ASOF欠損時の扱い（丸めない/警告等）方針の追記候補。
* BookingCurveLab_README:

  * RAW配置（サブフォルダ可）、重複即エラー、欠損チェック（CSV）、運用ASOF窓（180日）など運用ガイド追記候補。

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: `booking_curve/evaluation_multi.py` 参照の整合確認

    * 理由: 実ファイル不在が発覚。docs参照が残ると新規参加者が確実に迷う。
    * Status: 未反映（差し替え済み報告はあるが、残存参照の有無が未確認）
    * 反映先: docs/spec_overview.md（該当のファイル一覧/構成セクション）
  * 項目: 「monthly_curveはraw保存（NaN保持）、NOCBはGUI表示直前のみ」の思想明文化

    * 理由: 実装方針の根幹で、今後の予測/評価や監査機能の設計判断に直結する。
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（monthly_curve/daily_snapshots/補完ポリシーの節）
* docs不要:

  * 項目: 個別の一時的なエラー（ruff指摘、キャッシュ表示不具合）の詳細ログ

    * 理由: Thread Logに証跡として残せば十分。仕様として固定する情報ではない。
    * Status: N/A

## Known issues / Open

* missing_reportの現行ロジックは「観測されたASOF起点」なため、ASOFが全STAY MONTHで丸ごと欠けるケースが欠損として上がらない（asof_missing未実装の穴）。
* ASOF起点の期待セット生成により、最古のSTAY MONTHより前の月が欠損扱いで大量に出るノイズ（監査モードの必要性）。
* snapshot_missing（生成後欠損）の定義が危険：ASOFより過去の宿泊日が載らない前提、ACTは例外（特に月末ACTは翌月1日ASOF以降で取得）を踏まえた厳密設計が必要。
* 「欠損のみ取り込み」機能は合意済みだが、運用/監査2モード化・asof_missing導入と併せて実装予定（未実装）。

## Next

* P0:

  * missing_reportを2モード化（ops/audit）し、運用モードに asof_missing（ASOF丸抜け）を追加。
  * 運用モード：ASOF窓180日、日次期待＋severity設計（C案）。raw_missingは当月+翌3ヶ月の取りこぼし検知に限定。
  * 監査モード：STAY MONTHのmin..max範囲に限定し、期待ASOFを日次で生成してギャップ可視化。
  * GUI（マスタ設定）に「欠損チェック（運用）」「欠損監査（全期間）」「欠損のみ取り込み（raw_missingのみ）」導線を追加/整備。
  * today と latest_asof の鮮度warning（GUI表示）を追加。
* P1:

  * snapshot_missingの定義を厳密化（ACT例外・月末ACTの強調、誤爆抑制）。
  * docs更新（spec_overview/spec_data_layer/spec_models/spec_evaluation/README）を、実装反映後に差分で整理して追記。
