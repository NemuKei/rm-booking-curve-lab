# Decision Log（横断決定ログ）

> 目的：スレッドを跨いでも「何を決めたか」を見失わないための決定集。
> 注意：仕様の唯一の正は spec_*。本ログは spec_* への導線。

---

## D-001 hotels.json テンプレ運用（v0.6.8）
- Decision:
  - 配布用hotels.jsonテンプレは「まっさら配布で安全な最小雛形」に寄せる
  - テンプレデフォルト仮値は 0 ではなく固定整数 100
  - capは「hotels.json」と「GUIローカル上書き」の二層運用
- Why: 配布安全性・匿名性・事故防止
- Spec link: spec_overview / README（要反映）

## D-002 GUI設定の保存先（v0.6.9）
- Decision: GUIでの上書き設定は local_overrides/ に集約（output/ から移動）
- Why: 端末ローカル上書きの置き場所統一、APP_BASE_DIR運用の一貫性
- Spec link: spec_overview / README（要反映）

---

## D-010 roomsモデル整理（pace14系追加）
- Decision:
  - 主力モデルは recent90 / recent90w
  - pace14 / pace14_market を追加し、比較の基本4本に整理
  - adj系は重要度を下げる（曲線が描けない等の理由）
- Why: 市況急変への追従力、運用の分かりやすさ
- Spec link: spec_models（要反映）

## D-011 pace factor clip 初期値
- Decision:
  - 通常clip: 0.7〜1.3
  - 強clip: 0.85〜1.15
- Why: スパイクでの過補正抑制
- Spec link: spec_models（要反映）

## D-012 スパイク判定（SP-A）
- Decision: スパイクは機械判定し、UIに診断情報（Δ / q_hi q_lo / PF / clip種別等）を表示
- Why: ブラックボックス化を避け、運用判断しやすくする
- Spec link: spec_models / spec_overview（要反映）

## D-013 予測曲線の生成（方法1）
- Decision: 予測曲線は「最終着地 × 平均cum_ratio配分」から開始
- Must: 日別Forecastの最終着地とBookingCurve予測曲線は一致必須
- Spec link: spec_overview（要反映）

---

## D-020 BookingCurve baseline定義変更
- Decision: baseline（薄青）は avg ではなく recent90
- Decision: avg線（3ヶ月平均）は表示不要（外す）
- Why: 実務で使う基準として recent90 の方が妥当
- Spec link: spec_overview（要反映）

## D-021 欠損補完の導入範囲
- Decision: 欠損補完はまず「表示用のみ」導入（BookingCurve / MonthlyCurve）
- Decision: 日別Forecastへの適用は後回し
- Spec link: spec_overview（要反映）

## D-022 MonthlyCurve 欠損補完ON時の未着地扱い
- Decision: 未着地範囲は描画対象外（補完線を伸ばさない）
- Open: 中間値補完（前後中間）方式は候補だが未決
- Spec link: spec_overview（要反映）

## D-023 月次カーブ：前年同月データ無しポップアップ廃止
- Decision: ポップアップは運用ノイズなので廃止
- Spec link: spec_overview（要反映）

## D-024 Kalman（状態空間モデル）
- Decision: 今はやらない（優先度を落とす）
- Why: 実装・説明負荷が高い
- Spec link: spec_models（構想として書くなら“未実装”明記）

---

## D-030 評価の重心（best model）
- Decision: 最も重視する評価基準は M-1_END（前月末時点）
- Decision: Best model表示は「M-1_ENDベスト + ALL平均ベスト」の2段表示が誤解少ない
- Spec link: spec_evaluation（要反映）

---

## D-040 Revenue Forecast V1（rooms/pax/revenueへ）
- Decision: LT_DATAは3系統（rooms/pax/revenue）へ拡張
- Decision: ADR定義A＝税抜宿泊売上のみ（朝食等除外）
- Decision: revenue V1式＝ revenue_oh_now + remaining_rooms × adr_pickup_est
- Decision: phase_biasは当面 revenue のみに適用（roomsとは独立）
- Spec link: spec_data_layer / spec_models（要反映）

## D-041 phase_bias UI（手動）
- Decision: 3ヶ月（当月/翌月/翌々月）× フェーズ（悪化/中立/回復）× 強度（弱/中/強）
- Decision: スライダー不採用
- Decision: AUTO表示は矢印＋ラベル＋信頼度（数値詳細は後回し）
- Decision: 保存先は local_overrides
- Spec link: spec_models / spec_overview（要反映）

## D-042 丸め（Forecast整合）の原則
- Decision: 内部計算値は保持し、displayのみ丸める
- Decision: 丸め単位はホテル別設定（rooms/pax/rev）
- Decision: 着地済（stay_date < ASOF）は対象外
- Decision: 配分は未来日（stay_date >= ASOF）のみ
- Decision: 適用条件は未来日数 N>=20
- Spec link: spec_models（要反映）

## D-043 Pax予測方針転換
- Decision: PaxはDOR経由で予測しない。Paxを直接forecast（rooms同型）
- Decision: DORは派生指標（Pax/Rooms）
- Why: DOR/LTの構造変動でPaxが過大になりやすい
- Spec link: spec_models（要反映）

## D-044 着地済ターゲット月の扱い
- Decision: 対象月が着地後ASOFの場合、forecast生成はSKIPし実績表示として扱う（ログで明示）
- Spec link: spec_overview（要反映）

---

## D-050 TopDown RevPAR（V1）
- Decision: TopDownは別窓（ポップアップ）
- Decision: 指標はRevPARのみから開始
- Decision: 過去年数は直近6年
- Decision: 年度開始月は6月固定（将来ホテル別設定）
- Decision: 予測範囲は「最新ASOFが属する月」起点〜「最新ASOF+90日後にかかる月」まで
- Decision: Forecast CSVが無い月はグラフに載せない（欠損扱い）
- Spec link: spec_overview（要反映）

## D-051 p10–p90帯（A/C帯）の意味
- Decision: A帯（直近着地月アンカー）とC帯（前月アンカー）は“連続しない”のが正しい
- Decision: 帯は「過去年の月比率分布（p10–p90）の傾き幅」可視化
- Spec link: spec_overview / spec_data_layer（必要なら前提追記）
