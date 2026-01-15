# ファイル名案: docs/thread_logs/2026-01-10_feature-revenue-forecast-phase-bias_topdown-revpar-bands.md

# Thread Log: TopDown RevPAR（回転表示・p10–p90帯A/C・表形式ログ）＋日別Forecast ADR PU

## Meta

* Date: 2026-01-10（推定：ログ内ZIP日付より）
* Branch: feature/revenue-forecast-phase-bias
* Commit: 4c6fd8a（最新明示なし／直近ZIPから推定）
* Zip: rm-booking-curve-lab_20260110_1543_samp_feature-revenue-forecast-phase-bias_4c6fd8a_full.zip
* Scope: TopDown RevPARの表示品質改善（回転モード、seam、予測描画、p10–p90帯の仕様拡張と表示、下部数値の可視化）／日別ForecastのADR Pickup（ADR PU）表示・サマリ追加

## Done（実装・変更）

* TopDown RevPARの「回転」表示モードで、切替時に更新中のまま/例外発生する問題を調査・修正（matplotlib color二重指定等）。
* 予測範囲方針を「最新ASOF+90日後にかかる月まで」＋「日別Forecastが計算可能（月次Forecastが全日程揃う）な月のみ描画」へ寄せて運用。
* 予測CSVが存在しても一部日程のみ予測の月（INCOMPLETE）を検知し、TopDown描画から除外（スパイク対策）。
* 回転モードのseam（年度の谷間）表示を整理し、年度跨ぎの誤接続（誤った月への接続）を修正。
* p10–p90帯の注釈テキストをUI上部に追記（別ポップアップは不要の方針）。
* p10–p90帯の描画範囲を拡張し、回転モードでは窓の右端まで帯を描画（途中で切れる問題を段階的に改善）。
* 下部のp10–p90数値表示を表形式に刷新（YYYYMM / FcRevPAR / A:p10 A:p90 / C:p10 C:p90 / notes）。
* p10–p90帯を2系統化：

  * A: 直近着地月アンカー帯
  * C: 前月アンカー帯（前月が予測でもOK）
* A/C帯はチェックボックスで「同時表示」または「片方のみ表示」が可能な構成へ。
* 回転モードのp10–p90帯について、帯が月跨ぎで途切れる箇所は同色で接続して良い方針で整備。
* 日別ForecastでADR Pickup（ADR PU）のTotalを表示するよう改善。
* サマリにPickup行（またはPickup相当）を追加し、ADR PUを見える化（Standard表示にADR PUが無い問題の補完）。

## Decisions（決定）

* Decision:

  * TopDownの予測範囲は「最新ASOF+90日後にかかる月まで」を上限とし、描画対象は「日別Forecastが全日程分そろう月のみ」（INCOMPLETEは描画しない）。
  * 回転モードは再計算なしの再描画（表示切替のみ）でOK。
  * p10–p90帯は2本（A:直近着地アンカー / C:前月アンカー）をハイブリッド運用（同時表示も単独表示も可能）。
  * 前月アンカー帯（C）は前月が予測でもOK。予測が無い期間は「最後に存在する予測」を起点に帯を出す。
  * 帯の説明はUIの1行追記で足りる（別ポップアップ不要）。
* Why:

  * 「CSV有無」だけではスパイクを防げず、一部日程のみ予測（INCOMPLETE）が混入するため、描画条件を「全日程揃い」に引き上げる必要があった。
  * 回転モードは計算結果の差異を生まないUI表現の切替で十分であり、再計算は待ち/不具合/時間ロスを誘発する。
  * 3ヶ月予測の運用では「当月帯」だけでなく「前月起点の帯」を見たいニーズがあり、A/C二本立てが意思決定に有効。
  * 説明UIは軽量で良く、運用速度を優先（更新再実行のロス削減）。

## Docs impact（反映先の候補）

* spec_overview: TopDown RevPARの表示モード（年度固定/回転）とp10–p90帯の概念（A/C二本）を概念レベルで追記候補
* spec_data_layer: INCOMPLETE（全日程未充足）判定の扱いを「描画・比較から除外」とするルールの明文化候補
* spec_models: 影響なし（モデル定義自体は変更なし）
* spec_evaluation: 影響なし（評価指標追加は無し、表示上の比較ロジック中心）
* BookingCurveLab_README: GUI操作（TopDownのチェック、A/C切替、ADR PU確認）を簡易追記候補

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: TopDownのp10–p90帯（A=直近着地アンカー / C=前月アンカー）の意味と運用

    * 理由: 画面上で2本の帯が同時表示可能になり、解釈を誤ると意思決定事故につながるため
    * Status: 未反映
    * 反映先: docs/spec_overview.md（TopDownセクション）
  * 項目: TopDown描画対象月の条件（Forecast CSVがあってもINCOMPLETEは除外）

    * 理由: スパイク誤読の再発防止のため、仕様としてのガード条件が必要
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（Forecast出力／欠損・不完全の扱い）
* docs不要:

  * 項目: 回転モードのseam補助線の色/接続の微調整

    * 理由: UI表現の微細調整であり仕様化すると保守コストが増える
  * 項目: 下部数値表示を表形式にしたUI改善

    * 理由: 機能仕様ではなく表示改善（READMEの操作説明に留めれば十分）

## Known issues / Open

* TopDown RevPAR更新でエラーが発生する場合あり：`Given date string "671" not likely a datetime`（再現スクショあり）。
* 前月アンカー帯（C）が、予測区間（例：12月〜3月）で「帯」ではなく「線」になってしまう不具合が残存。

  * 期待挙動：各予測月ごとに「その月の予測点を起点」に次月までの帯を描画し、最終予測月以降は右端まで延長。
* A/C帯の数値出力に「着地済み月」が混入するケースが残存（例：12月が入る）。除外条件の調整が必要。

## Next

* P0:

  * `Given date string "671"` エラーの原因特定と修正（TopDown更新の安定化）。
  * 前月アンカー帯（C）を「各予測月起点の帯」にする（線→帯、月ごとの起点更新、最終予測月以降の延長）。
  * A/C数値テーブルから着地済み月が混入しないよう、表示対象期間の条件を統一（着地/予測/窓の境界を揃える）。
* P1:

  * TopDownのデフォルト設定最適化（前月アンカーCをデフォルトON、A/Cチェック切替をタイムラグ無しで即時再描画）。
