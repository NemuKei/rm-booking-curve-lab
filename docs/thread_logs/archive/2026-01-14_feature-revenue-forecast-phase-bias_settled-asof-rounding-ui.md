# ファイル名案: docs/thread_logs/2026-01-14_feature-revenue-forecast-phase-bias_settled-asof-rounding-ui.md

# Thread Log: 着地済ASOFエラー解消・月次丸め改善・UI調整（phase_bias）

## Meta

* Date: 2026-01-14（推定：ZIP/ログ/スクショ時系列より）
* Branch: feature/revenue-forecast-phase-bias
* Commit: a6aee1b
* Zip: rm-booking-curve-lab_20260114_1212_samp_feature-revenue-forecast-phase-bias_a6aee1b_full.zip
* Scope: TopDown RevPAR（phase補正UI含む）/ Pax予測（DOR経由→直接）/ 月次丸め（ホテル別単位・ASOF跨ぎ・display整合）/ 着地済ASOFでのForecast実行エラー修正 / TOTAL行表示改善

## Done（実装・変更）

* 月次丸め（Forecast整合）をホテル別設定（Rooms/Pax/Revの丸め単位）に拡張
* 月次丸めは「display列のみ」丸め、内部forecastは保持する方針で固定
* 月次丸めは「着地済（stay_date < ASOF）を一切触らない」原則を固定
* 丸め差分の配分先を「対象月内 かつ stay_date>=ASOF（未来日）のみ」に固定
* 丸め適用条件を「対象月内の未来日数N>=20のときのみ」に固定
* ASOFが前月以前（例：前月末）でも、上記条件を満たせば丸めが適用されるよう不具合修正
* TOTAL行の曜日（Wk）が `<NA>` 表示になる問題を、空欄表示に修正（UI/CSVの見栄え改善）
* Pax予測をDOR経由ではなく直接forecast（A案）へ切替（過大DOR/PU DORを緩和）
* TopDown RevPARポップアップUIのレイアウト調整（A帯/C帯チェック配置、余白等）を実施し「一旦完成」で合意
* フェーズ補正（売上）で「中立」時に強弱選択が可能だった混乱を解消（中立時は強弱選択不可：A案）
* 着地済ターゲット月（target_monthがASOFより過去）のForecast実行で発生していた `cannot safely cast non-equivalent object to int64` を解消
* 着地済ターゲット月は予測生成をSKIPし、ログに `[SKIP] target_month settled: ...` を出す挙動に整理
* 着地済ターゲット月のサマリ表示を整理（Forecast/Pickup等を表示しない方向で調整）
* TOTAL行付与周りで pandas FutureWarning（concat/全NA列のdtype決定）が再出現（動作はするが技術負債として残存）

## Decisions（決定）

* Decision:

  * 月次丸め単位はホテル別設定（Rooms/Pax/Rev）とする
  * 丸めはdisplay（表/サマリ/CSVの表示値整合）にのみ適用し、内部forecastは保持する
  * 着地済（stay_date < ASOF）は丸め・配分・改変の対象外
  * 丸め差分の配分先は「対象月内」かつ「stay_date>=ASOF」の未来日のみ
  * 丸めの適用条件は「対象月内の未来日数N>=20」のときのみ
  * フェーズ補正の「中立」は強弱差が無いため、強弱を選択不可にする（A案）
  * 着地済ターゲット月はForecast生成を行わず、実績表示として扱う（SKIPログを出す）
* Why:

  * 丸めは運用上の見栄え・整合のための調整であり、予測本体（内部forecast）を毀損しないため
  * 着地済を触らないことで実績改変リスクを排除し、説明可能性を担保するため
  * 配分先を対象月内・未来日に限定することで「当月の表示整合」を崩さず副作用を抑えるため
  * N>=20条件で小サンプル月の過剰調整を防ぎ、境界条件の納得感を確保するため
  * 中立で強弱が選べるのはUI上の誤誘導で、運用ミス/混乱の原因になるため
  * 着地済ターゲット月の予測生成は意味がなく、例外や型変換エラーの温床になるため

## Docs impact（反映先の候補）

* spec_overview: 予測/表示整合ポリシー（displayのみ丸め、着地済非改変、着地済月の扱い）の追記候補
* spec_data_layer: 追加設定（ホテル別丸め単位）の保持先・CSV出力への含有（丸め単位出力）に触れるなら追記候補
* spec_models: Pax予測（DOR経由→直接）と、着地済月の扱い（SKIP）に関するモデル仕様/前提の追記候補
* spec_evaluation: 直接影響は小（評価ロジック自体の変更ではない）が、着地済月の扱いが評価データ生成に絡むなら注記候補
* BookingCurveLab_README: 「月次丸め」「着地済月の挙動」「phase補正（中立）UI」などユーザー操作説明に追記候補

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: 月次丸め（Forecast整合）の仕様（displayのみ丸め/着地済非改変/配分先/適用条件N>=20/ホテル別単位）

    * 理由: 実装が複雑で運用判断に直結し、specとズレると再発しやすい
    * Status: 未反映
    * 反映先: docs/spec_models.md（該当：月次丸め・表示整合ポリシーの節／または末尾追記）
  * 項目: Pax予測の方針変更（DOR経由→直接forecast）

    * 理由: 予測値の意味・解釈が変わるため、モデル仕様として明文化が必要
    * Status: 未反映
    * 反映先: docs/spec_models.md（Pax関連モデルの説明）
  * 項目: 着地済ターゲット月の扱い（Forecast生成SKIP、実績表示として扱う）

    * 理由: GUI挙動/出力/運用手順に直結し、エラー回避の根本仕様だから
    * Status: 未反映
    * 反映先: BookingCurveLab_README.txt（操作説明）＋ docs/spec_overview.md（挙動サマリ）
* docs不要:

  * 項目: TopDown RevPARポップアップUIの細かなレイアウト調整（余白・配置）

    * 理由: 仕様ではなくUI微調整であり、Thread Logで追える
  * 項目: TOTAL行Wkの表示を空欄化（見栄え改善）

    * 理由: 仕様というより表示品質の話で、影響が軽微（必要ならREADMEに一言程度）
  * 項目: pandas FutureWarning（concat系）の再出現

    * 理由: 仕様ではなく技術負債。別途リファクタ/保守タスクとして管理すべき

## Known issues / Open

* pandas FutureWarning（TOTAL行付与周り：concat/全NA列のdtype決定）が残存（将来のpandasで挙動変化リスク）
* ログ/例外の採取が弱く、原因特定に時間がかかった（詳細な例外トレース・入力条件のログ出力強化が課題）
* calendar_features_*（カレンダーCSV）の位置づけが曖昧：GUI上のAdjモデルは廃止済みだが、内部実装が残っているため「無いとエラー」化を避ける設計が未整理
* フェーズ補正（中立）の強弱を選択不可にする対応は合意済みだが、最終的なUI/設定の整合確認は次ステップ（マージ前チェック項目）

## Next

* P0:

  * リファクタ方針の策定（対象：gui_backend肥大化、例外/ログ強化、TOTAL行生成のFutureWarning解消）
  * 変更点のdocs反映範囲を確定（spec_models/spec_overview/READMEのどこに何を書くか）
* P1:

  * mainへマージ（回帰チェック済み前提で、マージ手順とコミット整理）
  * リリース（make_release_zip.pyでZIP作成、リリースノート整備）
  * docs更新（確定した反映先へ追記、ズレのない運用ルール明文化）
