# rm-booking-curve-lab

ホテル宿泊部門のレベニューマネジメント向けに、PMSデータから

- 日別 / 月次ブッキングカーブの生成・可視化
- シンプルなフォーキャスト（複数モデル）
- モデル精度評価（MAE / MAPE / Bias / RMSE / MPE など）

を行うツール（GUI: Tkinter / EXE配布想定）です。

---

## 現在の状態（v0.6.6 相当）

- **daily snapshots レイヤー（標準CSV）**を「唯一の正」として整備済み。
- LT_DATA / 月次カーブは **2ルート切替**に対応
  - `source="timeseries"`（従来の時系列Excel / 比較・互換用）
  - `source="daily_snapshots"`（推奨ルート）
- **GUI から LT_DATA / monthly_curve を生成できる導線**あり（source切替、snapshots更新オプションなど）。
- **欠損値（NaN）はデータレイヤーで保持**し、描画・評価などのビュー側で補完（LT方向の LOCF を採用）。

---

## データパイプライン（推奨）

PMS 生データ  
→ **daily snapshots（標準CSV）**  
→ LT_DATA / monthly_curve  
→ forecast / evaluation

daily snapshots は「LT や評価を再現できる」ことを前提にした中核データです。

---

## データ形式（概要）

### daily snapshots（標準日別スナップショット）
- 出力例: `output/daily_snapshots_<hotel_id>.csv`
- 主な列: `hotel_id`, `as_of_date`, `stay_date`, `rooms_oh`, `pax_oh`, `revenue_oh`

### LT_DATA（宿泊日×LT）
- 出力例: `output/lt_data_YYYYMM_<hotel>.csv`
- 列: `LT=-1(=ACT), 0..max_lt`
- `ACT(-1)` は「stay_date より後の as_of_date が存在する場合のみ」算出し、それ以外は NaN（未着地）として保持。

### monthly_curve（月次ブッキングカーブ）
- 出力例: `output/monthly_curve_YYYYMM_<hotel>.csv`
- 内容: ASOF×宿泊月の「月次合計 Rooms vs LT カーブ」。

---

## 使い方

- **一般ユーザー（EXE利用）**  
  操作手順は `BookingCurveLab_README.txt` を参照してください（GUI操作・フォルダ構成・注意点）。

- **開発者（Python実行）**  
  仕様の「唯一の正」は `docs/` 配下にあります：
  - `docs/spec_overview.md`（全体仕様）
  - `docs/spec_data_layer.md`（データ仕様）
  - `docs/spec_models.md`（モデル仕様）
  - `docs/spec_evaluation.md`（評価仕様）
  - `docs/roadmap.md` / `docs/tasks_backlog.md`（計画とタスク）
  - `AGENTS.md`（AI/Codex運用ルール）

---

## 重要な設計ポリシー

### 欠損値（NaN）
- データレイヤー（daily snapshots / LT_DATA / monthly_curve）は **生のNaNを保持**。
- グラフ描画や評価の「ビュー用 DataFrame」に対して **LT方向の補完（LOCF）**を適用する。

---

## 次のフェーズ（予定）

- daily snapshots の **部分生成（Partial build / Upsert）** を実装し、週次運用で重くならないようにする。
