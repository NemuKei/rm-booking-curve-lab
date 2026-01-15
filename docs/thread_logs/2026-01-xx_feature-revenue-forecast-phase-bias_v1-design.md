# Thread Log: feature/revenue-forecast-phase-bias（V1設計合意：rooms/pax/revenue）

## Meta
- Branch: feature/revenue-forecast-phase-bias
- Anchor (zip/commit): （不明→後で追記）
- Scope: 予測対象拡張（rooms/pax/revenue）、phase_bias（手動）設計、丸め（表示のみ）方針、TopDownポップアップ方針

## Done（合意・設計）
- LT_DATAを roomsだけでなく 3ファイル（rooms/pax/revenue）へ拡張する方針確定
  - roomsは後方互換の旧命名も探索対象に含める
  - pax/revenueは専用命名
- revenue/ADR定義：
  - ADR定義A：税抜の宿泊売上（朝食等は含めない）
- revenue予測V1式（安全側）：
  - revenue = revenue_oh_now + remaining_rooms × adr_pickup_est
  - pickup ADRをそのまま信用しない（予約−取消の相殺後の歪みがある）
- phase_biasは当面 revenue のみに適用（roomsモデルとは独立）

## Decisions（phase_bias UI）
- 3ヶ月（当月/翌月/翌々月）× フェーズ（悪化/中立/回復）× 強度（弱/中/強）
- スライダー不採用（迷いが増える）
- AUTO表示：矢印＋ラベル＋信頼度（詳細数値は後回し）
- 保存先：local_overrides（端末ローカル）

## Decisions（丸め）
- 計算値は保持し、表示のみ丸める
  - rooms/pax：100単位
  - revenue：10万円単位
- 丸め単位は将来ホテル別設定で持つ

## Decisions（TopDown）
- TopDownは別タブではなく別窓（ポップアップ）
- 指標はRevPARのみから開始
- 過去年数は直近6年
- 年度開始月は6月固定を基本（将来ホテル別設定化）
- 予測範囲：
  - 起点：最新ASOFが属する月
  - 上限：最新ASOF +90日後にかかる月まで
- Forecast CSVが存在しない月はグラフに載せない（欠損扱い）

## Decisions（評価表示）
- 最重視評価基準は M-1_END（前月末時点）
- Best model 表示は「M-1_ENDベスト + ALL平均ベスト」の2段表示が誤解少ない方向

## Docs impact
- spec_data_layer: LT_DATA 3系統（rooms/pax/revenue）命名と探索
- spec_models: revenue V1式、phase_biasの位置付け（revenueのみ）、丸め（表示のみ）
- spec_overview: TopDownポップアップ、評価表示方針
- spec_evaluation: M-1_ENDの優先度・best model表示の説明

## Known issues / Open
- market_index（外部指数）はP2以降（構想のみ）
- Kalmanは優先度を落として「今はやらない」で確定

## Next
- TopDown RevPAR（p10–p90帯）と日別Forecast表示の具体改善へ
