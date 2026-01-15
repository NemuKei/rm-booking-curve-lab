# Thread Log: feature/revenue-forecast-phase-bias（TopDown表示改善・丸め仕様の実装フェーズ）

## Meta
- Branch: feature/revenue-forecast-phase-bias
- Anchor (zip/commit): rm-booking-curve-lab_20260114_1212_samp_feature-revenue-forecast-phase-bias_a6aee1b_full.zip / commit a6aee1b（※テキスト内に明示）
- Scope: TopDown RevPAR UI改善、p10–p90帯（A/C）整備、Pax直接forecast、月次丸め（Forecast整合）実装、着地済月SKIP

## Done（実装・変更）
- 月次丸め（Forecast整合）をホテル別設定で運用可能に
  - 丸めは display のみに適用、内部値は保持
  - stay_date < ASOF（着地済）は対象外
  - 配分先は stay_date >= ASOF（未来日）のみ
  - 適用条件：未来日数 N>=20
  - CSV出力にも丸め単位を出す方針
- 不具合修正：
  - (A) ASOFが前月以前でも N条件を満たせば丸めが適用されるよう修正（跨ぎ不具合）
  - (B) TOTAL行の曜日が<NA>になる問題：UI上は空欄表示に統一
  - (C) 対象月が着地後ASOFのときエラー：着地済月はforecast生成SKIPし、ログで明示（[SKIP]）
- Pax予測：
  - DOR経由をやめ、Paxを直接forecast（roomsと同型）へ変更
  - DORは派生指標（Pax/Rooms）
- UI/UX：
  - TopDown RevPARポップアップ：配置・余白調整（A/C帯チェック等）
  - phase_bias：中立時に強弱が選べる混乱を解消（中立時は強弱disabled）

## Decisions（TopDown帯の意味）
- A帯（直近着地月アンカー）とC帯（前月アンカー）は “同じ帯として連続しない” のが正しい（起点が違う）
- 帯は「過去年の月比率分布（p10–p90）の傾き幅」を可視化するもの
- 乖離検知（予測が帯の外）として意味がある

## Known issues / Tech debt
- TOTAL行付与まわりでFutureWarningが再出現する可能性（技術負債として残る）
- （過去スレッドで出ていた）TopDown更新時のdatetime変換エラー系は、別途再発チェックが必要

## Files touched（中核）
- src/booking_curve/gui_backend.py
- src/booking_curve/monthly_rounding.py
- src/gui_main.py

## Docs impact
- spec_overview: TopDownポップアップ / A帯C帯の意味 / 着地済月SKIP / Pax直接forecastの説明
- spec_models: 丸め（displayのみ）・適用条件（N>=20）・対象範囲（未来日のみ）・phase_bias中立UI
- spec_data_layer: （必要なら）TopDown帯が参照する“過去年の月比率分布”の前提説明

## Next
- docs/spec_models.md の該当節に「pace14/pace14_market」「pax/revenue/phase_bias/丸め（V1）」の記述を厚く入れる
