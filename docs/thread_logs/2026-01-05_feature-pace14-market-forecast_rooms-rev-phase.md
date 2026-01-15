# ファイル名案: docs/thread_logs/2026-01-05_feature-pace14-market-forecast_pace14-market.md

# Thread Log: pace14/market_pace導入と売上予測V1の設計合意

## Meta

* Date: 2026-01-05（推定：共有ZIPのタイムスタンプ最終日より）
* Branch: feature/pace14-market-forecast（主）／関連: fix/hotels-template-and-caps, fix/move-gui-settings-to-local-overrides
* Commit: 不明（スレッド内で確定情報なし）
* Zip: rm-booking-curve-lab_20260105_1818_samp_feature-pace14-market-forecast_e2ba92f_full.zip（ほか複数あり）
* Scope: rooms予測モデル（pace14/market補正）と曲線表示・欠損補完UIの調整、売上予測V1（LT_DATA拡張＋phase_bias）設計合意、評価方針の見直し

## Done（実装・変更）

* config/hotels.json（テンプレ運用）

  * “まっさら配布用” hotels.json を安全最小雛形へ寄せる方向で修正（v0.6.8）
  * デフォルト仮値（匿名性のための固定整数）は 100 を採用
  * forecast_cap 等は「hotels.json＋GUIローカル上書き」の二層運用を確定（実装/運用整理）
* local_overrides（運用）

  * GUI設定（gui_settings相当）の出力先を output/ から local_overrides/ に移す修正（v0.6.9）
* rooms予測モデル（feature/pace14-market-forecast）

  * モデルを recent90 / recent90w / pace14 / pace14_market の軸で運用する前提を導入
  * スパイク判定（SP-A）を採用し、スパイク日のフラグ表示＋診断値（Δ, q_hi/q_lo, PF, clip種別）表示の方針を反映
* BookingCurve/MonthlyCurve 表示

  * BookingCurveタブの baseline（薄青）を avg ではなく recent90 に変更（avg線は不要で削除方針）
  * 欠損補完チェックボックス（表示用）を BookingCurve＋MonthlyCurve に導入（日別Forecastは後回し）
  * MonthlyCurveで「未着地の月」に補完線が未着地範囲まで描画される問題を修正（未着地範囲は描画対象外）
  * MonthlyCurveで前年同月データ欠如時に出るポップアップを廃止
* src/booking_curve/gui_backend.py（性能）

  * get_booking_curve_data() の history LT_DATA 読み込みを月ごと1回にするキャッシュ化方針（実装対応）

## Decisions（決定）

* Decision:

  * roomsモデルは recent90 / recent90w / pace14 / pace14_market を主軸とする（adjは重要度低）
  * pace factor（PF）は倍率で扱い、通常clip=0.7〜1.3、スパイク時clip=0.85〜1.15
  * スパイク判定は SP-A（機械判定＋GUIでフラグ/診断表示）
  * 予測曲線は「最終着地 × baseline cum_ratio 配分」で生成し、日別Forecastと最終着地を一致させる
  * BookingCurve baseline（薄青）は recent90、avg線は表示不要
  * 欠損補完はまず表示用として BookingCurve＋MonthlyCurve に導入、日別Forecastは後回し
  * Kalman（状態空間モデル）は今やらない
  * 売上予測V1はデータレイヤーを動かす（LT_DATAを rooms/pax/revenue に拡張）
  * revenue定義（ADR定義A）は税抜宿泊売上のみ、CSVは生値、丸めはGUI表示のみ
  * phase_bias は「月別×フェーズ（悪化/中立/回復）×強度3段階」、保存先は local_overrides、適用は当面revenueのみ
  * 評価のベストモデル基準は M-1_END 固定を優先（表示は M-1_ENDベスト＋ALL平均ベストの2段が誤解少）
* Why:

  * 市況急変（崩れ）で過去寄りモデルが過大予測になりやすく、直近ペースを反映する必要があるため
  * PFは倍率の方が安定し、clipで事故率を抑えられるため
  * スパイクは例外挙動をUIで透明化し、運用判断の材料にするため
  * baseline/avg混在は誤解を生みやすく、recent90を基準に統一した方が運用が安定するため
  * NOCB等はまず“表示用”で安全に導入し、モデル計算への影響は別フェーズに分離するため
  * revenueはキャンセル相殺が強く、pickup ADR直当ては事故りやすいので、phase_biasで人が補正できる余地を残すため
  * ベストモデルの評価期間が可変だと現場が優先すべき基準が不明確になるため（M-1_END重視）

## Docs impact（docs反映が必要）

* spec_overview: 要（モデル追加/表示方針、local_overrides運用、phase_biasの位置付け）
* spec_data_layer: 要（LT_DATAの rooms/pax/revenue 3ファイル化、命名/出力/互換方針）
* spec_models: 要（pace14/pace14_market 定義、PF/clip、スパイク判定SP-A、baseline定義）
* spec_evaluation: 要（M-1_END固定のベスト基準、2段表示方針の整理）
* BookingCurveLab_README: 要（baseline=recent90、欠損補完チェック、phase_bias保存先、丸めは表示のみ）

## Known issues / Open（未解決）

* MonthlyCurveの欠損補完方式

  * 再現条件: NOCB補完だと月次カーブで違和感が出るケースあり
  * 暫定回避: 表示用補完としては動作しているが、方式（中間補完等）は継続検討
* 不要モデル表示の残り

  * 再現条件: BookingCurve/日別Forecastで avg や adj が残表示になるケースがあった（都度修正中）
  * 暫定回避: 表示モデルのフィルタを明示し、残存箇所は次スレッドでレビュー対象
* market_pace 診断UIの負荷

  * 再現条件: 診断表などを厚くするとGUIが重くなる可能性
  * 暫定回避: 精度優先で診断UIは後回し（合意済）
* docs未更新

  * 再現条件: 実装先行でspec/READMEが追随していない
  * 暫定回避: 売上予測V1の設計確定→まとめてdocs更新の順で進める

## Next（次スレッドのP0/P1）

* P0:

  * 最新ZIP（feature/pace14-market-forecast）のコードレビュー／仕様整合チェック（完了条件：致命的不具合なし・不要モデル表示や月次カーブ挙動が意図通り）
  * 売上予測V1のP0実装（LT_DATA 3本化＋pax/revenue予測＋phase_bias UI＋表示丸め）（完了条件：当月/翌月/翌々月でrooms/pax/revenueが一貫して出る、phase_biasがlocal_overridesで保存/反映）
* P1:

  * docs更新（spec_* / READMEの整合）（完了条件：データレイヤー、モデル定義、評価基準、運用導線が矛盾なく記述される）
  * 評価ブラッシュアップ（M-1_END基準のベスト表示2段、必要なら日別/曜日別評価の拡張検討）（完了条件：ユーザーが優先すべき評価軸がUI/ docsで明確）
