# ファイル名案: docs/thread_logs/2026-01-13_feature-revenue-forecast-phase-bias_topdown-pax-rounding.md

# Thread Log: TopDown帯整理 / Pax直接予測 / 月次丸め（ホテル別）導入

## Meta
- Date: 2026-01-13（推定：最終zip名より）
- Branch: feature/revenue-forecast-phase-bias
- Commit: （未記載）
- Zip: rm-booking-curve-lab_20260113_1433_samp_feature-revenue-forecast-phase-bias_96c184e_full.zip
- Scope: TopDown RevPARポップアップ（A/C帯・UI）、DOR過大→Pax予測方針転換、月次丸め（ホテル別設定/CSV反映/着地済除外）、警告（pandas FutureWarning）解消、既知バグの切り分け

## Done（実装・変更）
- TopDown RevPARのp10–p90帯（A帯=直近着地月アンカー / C帯=前月アンカー）の意味を再整理（帯同士の「連続しない」挙動が正しい前提に合意）
- TopDown RevPARポップアップのUIレイアウト調整（A/C帯チェックの配置・余白詰め）
- DOR過大（=Pax過大）の原因整理（DORはLTで構造的に動きやすく、DOR推定→Pax算出は事故りやすい）
- PaxをRoomsと同様に「直接Forecast」する方針へ変更（DORは派生指標として算出）
- Pax側にもRooms同様の曜日別モデル分岐を適用
- 日別の予測キャップ（破綻防止）が必要という前提を確認
- 月次丸め単位（Rooms/Pax/Rev）をホテル別に持てるようにし、GUI（マスタ設定）から編集・保存・反映できるようにした
- CSV出力に丸め単位を反映する方針を採用（出力にも情報を残す）
- 月次丸めON時、表示（display）は日別合計と整合するように調整（Rooms/Paxに加えRevも整合対象）
- 着地済（stay_date < ASOF）は一切触らない（丸め対象外）仕様を採用
- 丸め差分の配分先は「当月の未来日（stay_date >= ASOF）の全日」に限定する仕様を採用
- サマリ表示に丸めが反映されない不具合を修正（サマリも丸め反映OK）
- pandas FutureWarning（concat/empty・all-NA列のdtype推論）を解消（TOTAL行付与ロジックを調整）
- （見た目課題）TOTAL行の曜日が`<NA>`表示になる点を認識（空白化したい要望）

## Decisions（決定）
- Decision:
  - PaxはDOR推定経由ではなく、Roomsと同じ枠組みで直接Forecastする
  - DORは予測せず、派生指標（Pax/Rooms）として算出する
  - 月次丸め単位（Rooms/Pax/Rev）はホテル別設定とし、GUIで変更可能にする
  - 丸めは着地済（stay_date < ASOF）に適用しない
  - 丸め差分は「当月の未来日（stay_date >= ASOF）の全日」に配分する
  - RevもRooms/Paxと同様に「displayは日別合計と整合」させる
  - CSV出力にも丸め単位（設定値）を出力する
- Why:
  - DORはLT・需要構造・キャンセル等で変動しやすく、DOR推定→Pax算出は過大推定リスクが高い
  - 丸めは未着地部分の「配分用途」で価値がある一方、着地済に介入すると不自然・監査性が落ちる
  - 施設キャパやホテル特性で最適単位が変わるため、複雑な自動丸めロジックよりホテル別カスタムが合理的
  - display整合（サマリ含む）を担保しないと運用上の誤差・誤読が発生する

## Docs impact（反映先の候補）
- spec_overview: 予測パイプラインの概要（Pax予測の位置づけ、丸めの概念）
- spec_data_layer: Forecast出力（CSV）への丸め単位出力、丸め適用範囲（当月未来日限定/着地済除外）
- spec_models: Paxの予測方式（DOR推定→Pax算出を廃止し、Pax直接Forecastへ）
- spec_evaluation: 直接的な評価指標追加はなし（ただしPax予測の評価が必要なら追記候補）
- BookingCurveLab_README: マスタ設定（丸め単位）の操作/保存、CSV出力項目の説明

### Docs impact 判定（必須/不要 + Status）
- 必須:
  - 項目: Paxを直接Forecast（DOR推定経由を廃止）
    - 理由: 予測ロジックの根幹変更で、モデル仕様（入力/出力/派生指標）が変わる
    - Status: 未反映
    - 反映先: docs/spec_models.md（Pax/DORの定義・予測手順の節）
  - 項目: 月次丸めの適用範囲（着地済除外、当月未来日限定、差分配分ルール）
    - 理由: 運用・表示整合に直結する仕様で、誤解すると数値が一致しない/監査性が落ちる
    - Status: 未反映
    - 反映先: docs/spec_overview.md（Forecast整形/丸めの概念）＋ docs/spec_data_layer.md（出力・加工ルール）
  - 項目: 丸め単位（Rooms/Pax/Rev）のホテル別設定とGUI（マスタ設定）からの編集・保存
    - 理由: 設定スキーマと運用手順が増えたため、設定の所在と反映手順の明文化が必要
    - Status: 未反映
    - 反映先: docs/spec_overview.md（設定体系）＋ BookingCurveLab_README.txt（操作手順）
  - 項目: CSV出力に丸め単位を含める
    - 理由: 出力の再現性・説明責任（どの丸めで出た値か）が変わる
    - Status: 未反映
    - 反映先: docs/spec_data_layer.md（forecast出力スキーマ）＋ BookingCurveLab_README.txt
- docs不要:
  - 項目: TopDown RevPARポップアップのUI余白・配置調整（A/C帯チェック位置など）
    - 理由: 仕様ではなくUI微調整のため（UI仕様書を別途持たない前提なら作業記録に留める）
  - 項目: pandas FutureWarningの解消（concat挙動）
    - 理由: 内部実装上の保守対応で、ユーザー仕様やデータ仕様の変更ではない

## Known issues / Open
- ASOFが前月以前の場合、丸めが適用されない（例：1月予測でASOF=12/31だと不適用、ASOF=1/1だと適用）
  - 影響: ASOFが対象月外のケースで当月丸めルールが効かず、翌月以降も丸めが崩れる可能性
  - 観察: 12月予測でもASOF日付のある閾値以降で不適用になるケースがあり、判定条件がASOF月依存になっている疑い
- （軽微）TOTAL行の曜日が`<NA>`表示になっている（空白表示にしたい）

## Next
- P0:
  - 丸め適用判定の修正（「当月=対象月」判定がASOF月依存になっている箇所の見直し）
  - 完了条件: ASOFが前月/当月いずれでも「対象月の当月未来日」の丸めが同一ルールで適用されること（再現テストで確認）
- P1:
  - TOTAL行の曜日`<NA>`を空白表示に変更
  - docs更新タイミングの検討（spec_*.mdへの反映範囲と順序を整理）
  - 完了条件: 表示上`<NA>`が消え、docsの反映対象が明確化されていること
