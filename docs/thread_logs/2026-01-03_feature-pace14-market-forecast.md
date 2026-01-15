# Thread Log: feature/pace14-market-forecast（rooms予測モデル拡張）

## Meta
- Branch: feature/pace14-market-forecast
- Anchor (zip/commit): （不明→後で追記）
- Scope: rooms予測モデル（pace14 / pace14_market）追加、BookingCurve/MonthlyCurve表示仕様整理

## Done (実装・仕様整理)
- モデル整理：
  - adj系は精度差が小さく、予測曲線が描けない弱点が大きい → 重要度を下げる
  - 主力は recent90 / recent90w
- 新モデル追加：
  - pace14（直近勢い＝pace factor）
  - pace14_market（market_pace補正）
- 評価・比較対象は基本4本（recent90, recent90w, pace14, pace14_market）を中心に運用する方向

## Decisions（モデル/パラメータ）
- pace factor（倍率）clip 初期値：
  - 通常 clip: 0.7〜1.3
  - 強 clip: 0.85〜1.15
- スパイク判定：SP-A方式で確定
  - スパイクは機械判定し、UIに診断情報を表示する
  - 表示：⚠ spike / Δ / q_hi q_lo / PF / 適用clip（通常 or 強）

## Decisions（曲線生成）
- 予測曲線の第一実装は「方法1：最終着地 × 平均cum_ratio配分」
- 重要：日別フォーキャストの最終着地と、ブッキングカーブ予測曲線は一致必須

## Decisions（表示仕様）
- BookingCurve baseline（薄青）を avg ではなく recent90 に変更
- avg（3ヶ月平均）の線は表示から外す
- 欠損補完（NOCB等）は “表示用のみ” で導入（BookingCurve / MonthlyCurve）
  - 日別Forecastへの適用は後回し
- MonthlyCurve欠損補完ON時：
  - 未着地範囲まで補完線が伸びる問題 → 未着地範囲は描画対象外
  - 中間値補完（前後中間）も候補（未決）
- 「前年同月データがない」ポップアップは廃止（ノイズ）
- 性能改善：
  - gui_backend.get_booking_curve_data() の history LT_DATA 読み込みを月ごと1回（辞書キャッシュ）

## Docs impact
- spec_models: pace14 / pace14_market の定義、PF/clip、スパイク判定・診断項目
- spec_overview: baseline定義変更、欠損補完（表示用のみ）、UIポップアップ廃止
- spec_data_layer: （必要なら）curve生成の“平均cum_ratio”前提の説明

## Known issues / Open
- MonthlyCurveの補完方式（NOCB vs 中間値）は未決
- “adj系”の扱い（完全廃止/残置/非表示）をdocsにどう表現するか

## Next
- feature/revenue-forecast-phase-bias（rooms→pax→revenueへ拡張）へ
