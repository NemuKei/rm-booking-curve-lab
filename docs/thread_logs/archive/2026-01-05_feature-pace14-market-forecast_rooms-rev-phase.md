# ファイル名案: docs/thread_logs/2026-01-05_feature-pace14-market-forecast_rooms-rev-phase.md

# Thread Log: pace14/market_pace導入と売上予測V1設計（docs反映前提の合意整理）

## Meta

* Date: 2026-01-05（推定：共有ZIPのタイムスタンプ群より）
* Branch: feature/pace14-market-forecast（主）／関連: fix/hotels-template-and-caps, fix/move-gui-settings-to-local-overrides
* Commit: 不明（スレッド内で確定情報なし）
* Zip:

  * rm-booking-curve-lab_20260105_1818_samp_feature-pace14-market-forecast_e2ba92f_full.zip
  * （途中共有）rm-booking-curve-lab_20260105_1534... / 1629... / 1728... / 1758... 等
* Scope: rooms予測モデル（pace14/pace14_market）・BookingCurve/MonthlyCurve表示（baseline/欠損補完）・評価方針（M-1_END）・売上予測V1（LT_DATA拡張＋phase_bias＋丸め）に関する合意と実装反映

## Done（実装・変更）

* hotels.jsonテンプレ運用を安全最小雛形へ寄せる修正（v0.6.8文脈）
* デフォルト仮値（匿名性目的）を 100 採用（0以外の固定整数）
* forecast_capは「hotels.json＋GUIローカル上書き」の二層運用を前提化
* GUI設定出力先を output/ から local_overrides/ へ移す（v0.6.9文脈）
* roomsモデルに pace14 / pace14_market を追加し、運用主軸を4本へ整理
* PF（pace factor）を倍率として扱い、通常clip/強clipを導入
* スパイク判定（SP-A）を採用し、スパイク日フラグ＋診断値表示を追加
* BookingCurve予測曲線を「最終着地×baseline cum_ratio配分」で出す方針で実装
* BookingCurveのbaseline（薄青）を avg→recent90へ（avg線は不要の方向）
* 欠損補完チェックボックスを BookingCurve＋MonthlyCurve に導入（表示用）
* MonthlyCurveで未着地月の補完線が未着地範囲まで出る問題を修正（未着地範囲は描画対象外）
* MonthlyCurveの前年同月データ欠如ポップアップを廃止
* gui_backend.get_booking_curve_data() のhistory LT_DATA読み込みを月ごと1回へ（キャッシュ化）

## Decisions（決定）

* Decision:

  * rooms予測の標準モデルは recent90 / recent90w / pace14 / pace14_market の4本を主軸とする（adjは主ライン外）
  * PFは倍率（比率）で扱い、通常clip=0.7〜1.3、スパイク時clip=0.85〜1.15 を初期値として固定
  * スパイク判定はSP-A（機械判定＋フラグ表示＋診断表示）を標準運用とする
  * 予測曲線は「最終着地×baseline cum_ratio配分」を採用し、日別Forecastと最終着地を一致させる（必須要件）
  * BookingCurveのbaseline（薄青）は recent90、avg線は不要（表示から外す）
  * 欠損補完はまず「表示用のみ」で導入し、適用範囲は BookingCurve＋MonthlyCurve（Forecastは後回し）
  * Kalman（状態空間モデル）は今回はやらない（優先度外）
  * 売上予測V1に向けてLT_DATAを rooms/pax/revenue の3ファイルに拡張する
  * revenue（ADR定義A）は税抜宿泊売上のみ、CSVは生値、丸めはGUI表示のみ（rooms/pax=100単位、revenue=10万円単位）
  * phase_biasは「月別（当月/翌月/翌々月）×フェーズ（悪化/中立/回復）×強度3段階」、保存先はlocal_overrides、適用先は当面revenueのみ
  * ベストモデル評価基準は当面 M-1_END 固定を最優先、UI表示は M-1_ENDベスト＋ALL平均ベストの2段が誤解が少ない
* Why:

  * 市況急変で過去寄りモデルが過大予測になりやすく、直近ペース反映モデルを標準化する必要があるため
  * 倍率PF＋clipで補正の暴れを抑え、事故率を下げるため
  * スパイク（例外日）を透明化し、現場の判断材料として残すため
  * UI間の最終着地不一致は誤解・運用事故の最大要因なので仕様として固定するため
  * baselineをrecent90に統一し、avg基準の誤解（悲観寄り）を避けるため
  * 欠損補完は計算に混ぜると再現性/評価が崩れるため、まず表示用に限定するため
  * 売上予測には roomsだけのLT_DATAでは不十分で、pax/revenueの同型データが必要なため
  * phase_biasは人が違和感に応じて補正できる余地を残しつつ、端末ローカルで混乱を避けるため
  * 評価期間が可変だと優先軸が曖昧になるため、M-1_ENDに固定して運用の基準点を作るため

## Docs impact（反映先の候補）

* spec_overview: 要（モデル体系/表示方針、local_overrides運用、phase_bias/丸めの位置づけ）
* spec_data_layer: 要（LT_DATA 3ファイル化、欠損補完の位置づけ）
* spec_models: 要（pace14/pace14_market、PF/clip、スパイクSP-A、baseline定義、曲線生成）
* spec_evaluation: 要（M-1_END固定、ベスト表示2段の方針）
* BookingCurveLab_README: 要（baseline=recent90、欠損補完チェック、phase_bias導線、丸めは表示のみ）

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: rooms標準モデル4本（recent90/recent90w/pace14/pace14_market）とadjの位置づけ

    * 理由: モデル一覧・推奨がdocsとズレると、UI表示/評価/運用判断が混乱する
    * Status: 未反映
    * 反映先: docs/spec_models.md（モデル一覧・推奨/非推奨）, docs/spec_overview.md（概要）
  * 項目: PF倍率定義＋clip初期値（通常0.7–1.3、強0.85–1.15）

    * 理由: 数値が無いと再現不能になり、担当者/端末差で結果が一致しない
    * Status: 未反映
    * 反映先: docs/spec_models.md（pace14定義）
  * 項目: スパイク判定SP-A（診断表示項目＋強clip適用）

    * 理由: 例外処理の有無が不明だと「なぜその日だけ違うか」を説明できず運用事故になる
    * Status: 未反映
    * 反映先: docs/spec_models.md（スパイク判定）, docs/spec_overview.md（運用観点）
  * 項目: 予測曲線生成方式＋日別Forecastと最終着地一致（必須要件）

    * 理由: 画面間の数値不一致は誤解の温床で、仕様固定しないと再発する
    * Status: 未反映
    * 反映先: docs/spec_models.md（曲線生成）, docs/spec_overview.md（整合原則）
  * 項目: BookingCurve baseline=recent90、avg線廃止

    * 理由: 基準線の意味が変わると解釈が変わり、判断を誤る
    * Status: 未反映
    * 反映先: BookingCurveLab_README.txt（画面説明）, docs/spec_overview.md（UI概要）
  * 項目: 欠損補完は「表示用のみ」＋適用範囲（BookingCurve/MonthlyCurve限定）

    * 理由: 計算に混ぜたと誤解されると評価が信用できなくなる／適用範囲が曖昧だと運用が壊れる
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（欠損扱い）, BookingCurveLab_README.txt（操作説明）
  * 項目: LT_DATAを rooms/pax/revenue の3ファイルへ拡張、revenue定義（税抜宿泊売上のみ）

    * 理由: データレイヤー変更は互換・入出力・下流処理全体に影響し、docs未反映は即事故
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（LT_DATA仕様）, docs/spec_models.md（指標定義）
  * 項目: phase_bias UI仕様（3ヶ月×フェーズ×強度3）＋保存先local_overrides＋適用先revenueのみ

    * 理由: 保存先/適用範囲が曖昧だと設定混乱と評価比較破綻が起きる
    * Status: 未反映
    * 反映先: docs/spec_overview.md（運用）, docs/spec_models.md（適用範囲）, docs/spec_data_layer.md（local_overrides）
  * 項目: CSVは生値、丸めはGUI表示のみ（丸め単位）

    * 理由: 丸めが計算に入ったと誤解されると再現性と評価が崩れる
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（出力方針）, BookingCurveLab_README.txt（表示説明）
  * 項目: ベストモデル基準M-1_END固定＋UI2段表示方針

    * 理由: 優先すべき評価軸が統一されないと意思決定が迷走する
    * Status: 未反映
    * 反映先: docs/spec_evaluation.md（ベスト定義）, docs/spec_overview.md（使い方）
* docs不要:

  * 項目: Kalmanを今回はやらない

    * 理由: 仕様固定というより計画/優先度の話で、roadmap/tasks_backlogで管理する方が誤解が少ない（ただし「現状対象外」を明記したい場合のみ注記）

## Known issues / Open

* MonthlyCurveの欠損補完方式（NOCBだと違和感が出るため、中間補完等の候補は継続検討）
* 不要モデル（avg/adj）が表示に残る箇所がないか、最終レビューで取り切る必要あり
* market_paceの診断UIは負荷が上がる可能性があるため、精度優先で後回し（診断は最小限）

## Next

* P0:

  * 最新ZIP（feature/pace14-market-forecast）のレビューと最終取り切り（不要モデル表示、月次カーブ未着地補完、baseline確認）
  * 売上予測V1のP0実装（LT_DATA 3本化＋pax/revenue予測＋phase_bias UI＋表示丸め）
* P1:

  * docs更新（spec_* / READMEの整合：モデル定義、データレイヤー、評価基準、運用導線）
