<!-- docs/spec_evaluation.md -->

# 評価仕様（spec_evaluation）

本ドキュメントでは、BookingCurveLab における **モデル評価ロジック** を整理する。

- 対象スクリプト：
  - `run_full_evaluation.py`
  - `run_evaluate_forecasts.py`
  - `run_segment_error_summary.py`
- 評価に用いるデータレイヤの仕様は `spec_data_layer.md` を参照すること。
- モデル側の仕様は `spec_models.md` を参照すること。

---

## 1. 目的

1. 各モデル（`avg`, `recent90`, `recent90_adj`, `recent90w`, `recent90w_adj`, `pace14`, `pace14_market`, `pace14_weekshape_flow`）が
   **どの程度の誤差で月次室数を予測しているか** を定量化する。
2. ASOF 別（`M-2_END`, `M-1_END`, `M10`, `M20`）の「読め具合」を比較し、
   **悲観 / 基準 / 楽観シナリオ** の根拠とする。
3. `recent90_adj` / `recent90w_adj` など、カレンダー調整の有無が  
   どのように誤差に効いているかを確認する。
4. 将来的には、月別・曜日別・祝日ポジション別などの誤差パターンを把握し、  
   バイアス補正やセグメント調整ルールの改善に役立てる。

---

## 2. 評価対象の単位

### 2.1 月次評価（主用途）

`run_full_evaluation.py` および `run_evaluate_forecasts.py` は、

- ホテル：`hotel_tag`
- 宿泊月：`target_month`（例：`202512`）
- モデル：`model`（`avg`, `recent90`, `recent90_adj`, `recent90w`, `recent90w_adj`, `pace14`, `pace14_market`, `pace14_weekshape_flow`）
- ASOF：`asof`（日付そのもの、および `asof_type`）

の組み合わせごとに、**宿泊月トータルの室数誤差**を計算する。

`resolve_asof_dates_for_month(target_month)` により、以下の ASOF 候補を生成する：

- `("M-2_END", 前々月末)`
- `("M-1_END", 前月末)`
- `("M10", 当月10日)`
- `("M20", 当月20日)`

### 2.2 日別誤差の集計（セグメント分析用途）

`run_segment_error_summary.py` は、日別誤差を格納した

- `daily_errors_<hotel>.csv`

を入力として、次の粒度で誤差サマリを作る。

- モデル × 曜日（`weekday`: 0=Mon, …, 6=Sun）
- モデル × `holiday_position`（連休の「first/middle/last」など）
- モデル × `day_type`（平日 / 祝前 / 休日など）

これにより、たとえば

- 「連休中日の `recent90` は一貫して +X% 出がち」
- 「平日の `recent90w_adj` は若干守り気味」

といった **カレンダー別のクセ** を可視化できる。

---

## 3. 入力データ

### 3.1 LT_DATA（run_full_evaluation 経由）

`run_full_evaluation.py` では、次を前提とする。

- `lt_data_YYYYMM_<hotel>.csv`
  - index：`stay_date`
  - columns：`LT`（-1, 0, 1, …）
  - 値：その LT 時点での販売済み室数

`build_monthly_forecast(...)` により、

- ASOF ごとに
- モデルごとの
- 「日別予測（projected/adjusted_projected_rooms）」

を組み立て、その合計を月次の予測室数として扱う。

### 3.2 forecast CSV（run_evaluate_forecasts 経由）

`run_evaluate_forecasts.py` は、

- 事前に出力済みの forecast CSV  
  例：`forecast_recent90_202506_daikokucho_asof_20250531.csv`

を読み込み、同様に「日別の actual / forecast 列を集計して月次の誤差」を計算する。

想定される列（一例）：

- `actual_rooms`
- `projected_rooms`
- `adjusted_projected_rooms`
- 必要に応じて `weekday`, `holiday_position` など（のちのセグメント分析用）

---

## 4. 指標の定義

### 4.1 日別レベル

日別の誤差（`daily_errors_<hotel>.csv` 等）では、少なくとも次の量を定義する。

- 実績室数  
  \[
    y_t = \text{actual\_rooms}(t)
  \]

- 予測室数（モデル `m` の projected）  
  \[
    \hat{y}_t^{(m)} = \text{forecast\_rooms}(t)
  \]
  または、`_adj` モデルの場合：
  \[
    \hat{y}_t^{(m)} = \text{adjusted\_projected\_rooms}(t)
  \]

- 誤差（室数）  
  \[
    e_t^{(m)} = \hat{y}_t^{(m)} - y_t
  \]

- 誤差率（％）  
  \[
    \text{error\_pct}_t^{(m)} =
      \begin{cases}
        \dfrac{e_t^{(m)}}{y_t} \times 100 & (y_t > 0) \\
        \text{NaN} & (y_t = 0)
      \end{cases}
  \]

これを `run_segment_error_summary.py` 側で集計する。

### 4.2 月次レベル（主指標）

`run_full_evaluation.py` / `run_evaluate_forecasts.py` では、ASOF × モデルごとに

- 宿泊月トータルの実績室数：

  \[
    A^{(m)} = \sum_{t \in \text{month}} y_t
  \]

- 宿泊月トータルの予測室数：

  \[
    \hat{A}^{(m)} = \sum_{t \in \text{month}} \hat{y}_t^{(m)}
  \]

を計算し、以下を定義する。

1. **誤差（室数）**

   \[
     \text{error}^{(m)} = \hat{A}^{(m)} - A^{(m)}
   \]

2. **誤差率（％）**

   \[
     \text{error\_pct}^{(m)} =
       \begin{cases}
         \dfrac{\hat{A}^{(m)} - A^{(m)}}{A^{(m)}} \times 100 & (A^{(m)} > 0) \\
         0 & (A^{(m)} = 0)
       \end{cases}
   \]

3. **絶対誤差率（％）**

   \[
     \text{abs\_error\_pct}^{(m)} = \left| \text{error\_pct}^{(m)} \right|
   \]

「1レコード = 1 target_month × 1 model × 1 ASOF」という形で `evaluation_*_detail.csv` に蓄積する。

### 4.3 モデルごとの集計値（mean_error_pct / mae_pct）

`evaluation_*_multi.csv` では、ASOF を跨いでモデルごとに集約する。

- 集約キー：
  - `target_month`
  - `model`

- 集約内容：

  - 件数  
    \[
      n = \text{count of } \text{error\_pct}
    \]

  - 平均誤差率（％）  
    \[
      \text{mean\_error\_pct} = \frac{1}{n}\sum_{\text{ASOF}} \text{error\_pct}^{(m)}
    \]

  - 絶対誤差率の平均（％）  
    \[
      \text{mae\_pct} = \frac{1}{n}\sum_{\text{ASOF}} \left|\text{error\_pct}^{(m)}\right|
    \]

補足（GUI表示での派生値）：

- 現状の `evaluation_*_multi.csv` には `rmse_pct` / `n_samples` を **出力列としては持たない**。
- GUI では、`evaluation_*_detail.csv`（ASOF明細）から `rmse_pct` / `n_samples` を計算して表示することがある。
  - `rmse_pct` は誤差率ベースの RMSE（%）相当（`sqrt(mean(error_pct^2))`）
  - `n_samples` は集計に使った ASOF 数
- これらは **仕様として固定しきらず**、売上予測も含めた評価設計の再考フェーズで整理する。

本書および README では、これらを以下のように読み替える：

- `mean_error_pct` … **モデルのバイアス / MPE** として解釈する  
  - 正なら「平均して攻め気味（過大予測）」  
  - 負なら「平均して守り気味（過小予測）」
- `mae_pct` … **MAPE** として解釈する  
  - 「平均して何％くらい外れているか」を表す。

---

## 5. 出力ファイル仕様

### 5.1 evaluation_detail（`evaluation_<hotel>_detail.csv`）

- 出力元：
  - `run_full_evaluation.py`
  - `run_evaluate_forecasts.py`

- 主な列：

  - `target_month` … 宿泊月（例：`202512`）
  - `asof_date` … ASOF 日付（`YYYY-MM-DD`）
  - `asof_type` … `M-2_END`, `M-1_END`, `M10`, `M20` など
  - `model` … `avg`, `recent90`, `recent90_adj`, `recent90w`, `recent90w_adj`, `pace14`, `pace14_market`, `pace14_weekshape_flow`
  - `actual_total_rooms` … 宿泊月トータル実績室数
  - `forecast_total_rooms` … 宿泊月トータル予測室数
  - `error` … `forecast_total_rooms - actual_total_rooms`
  - `error_pct` … 誤差率（％）
  - `abs_error_pct` … 絶対誤差率（％）

※ 列名は実装の `records.append({...})` と整合すること。

### 5.2 evaluation_multi（`evaluation_<hotel>_multi.csv`）

- 出力元：
  - `run_full_evaluation.py`
  - `run_evaluate_forecasts.py`

- 主な列：

  - `target_month`
  - `model`
  - `mean_error_pct`
  - `mae_pct`

ASOF 単位の detail から `groupby(["target_month", "model"])` で集約している。

### 5.3 日別誤差サマリ（`segment_error_*` 出力）

- 入力：
  - `daily_errors_<hotel>.csv`  
    （日別レベルで `error_pct`, `weekday`, `holiday_block_len`, `holiday_position`, `is_holiday_or_weekend` 等を持つ）

- 主な出力（例）：

  - `segment_error_by_weekday_<hotel>.csv`
  - `segment_error_by_holiday_position_<hotel>.csv`
  - `segment_error_by_day_type_<hotel>.csv`

- 各ファイルは `summarize_group(...)` を通して

  - `n`
  - `mean_error_pct`
  - `mae`（日別誤差率の絶対値の平均）

  を持つ。

---

## 6. `_adj` モデルと評価の関係

現状の `_adj` モデルは、次のような位置づけとする：

1. ベースモデル（`recent90` / `recent90w`）で **日別 `projected_rooms`** を作る。
2. `apply_segment_adjustment` を通して、
   連休中日などの特定日をやや抑制した **`adjusted_projected_rooms`** を得る。
3. `_adj` モデルでは月次トータルの予測に `adjusted_projected_rooms` を用いる。
4. 評価では、`recent90` vs `recent90_adj`、`recent90w` vs `recent90w_adj` の
   `mean_error_pct` / `mae_pct` の差を見て、
   カレンダー補正の効果を確認する。

将来的に、

- 月次バイアス（`mean_error_pct`）を利用した追加補正（例：1 ÷ (1 + bias)）や
- 月ごとに異なる補正係数

を `_adj` モデルに組み込む場合は、本書および `spec_models.md` を更新すること。

---

## 7. 今後の拡張と留意点

- **日別ベースの評価への拡張**
  - 現状は「月次トータルの誤差率」を主指標としているが、
    将来的には「日別誤差から再集計した月次 MAPE」等も検討余地あり。
- **RMSE など他指標**
  - 評価指標は将来（売上予測も含めた評価設計の再考フェーズ）で再整理する。
  - 現時点では GUI 表示の参考値として `rmse_pct`（誤差率ベースのRMSE%相当）が出ることがあるが、
    仕様として固定はしていない（roomsベース/売上ベースも含めて再検討対象）。
- **評価期間の選定**
  - 評価に使う宿泊月（`TARGET_MONTHS`）や ASOF セットは、
    ロードマップ／研究の目的に応じて変える。
  - 変更した場合は、評価レポートの解釈にも影響するため、
    README や spec にも簡単にメモを残すこと。

以上。
