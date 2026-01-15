<!-- docs/spec_models.md -->

# モデル仕様（spec_models）

本ドキュメントでは、BookingCurveLab における **予測モデルの仕様** を整理する。

- 対象：
  - rooms（稼働室数）予測モデル（実装済）
  - pax（人数）予測（V1：roomsと同型で直接予測／DORは派生指標）
  - revenue（売上）予測（V1：OH revenue + 残pickup rooms×推定ADR）
  - phase_bias（手動フェーズ補正：V1はrevenue側にのみ適用）
- データレイヤの仕様は `spec_data_layer.md` を参照すること。
- アプリ全体の目的・前提は `spec_overview.md` を参照すること。
- 評価ロジックの詳細は `spec_evaluation.md` を参照すること。

---

## 1. モデルの分類

本ツールのモデルは、概念的に以下の2段階構造で考える。

1. **OCC（室数）の予測モデル** … LT_DATA を入力に、将来の「販売済み室数」を予測する。
2. **ADR / 売上モデル** … 上記の室数予測と組み合わせて、単価・売上を推計する（構想段階）。

本書で「モデル」と呼ぶときは、特に断りがなければ **OCC 予測モデル** を指す。

---

## 2. 入力データと ASOF / 評価との関係

### 2.1 LT_DATA 前提

OCC モデルの主な入力は、`lt_data_YYYYMM_<hotel>.csv` に代表される **LT_DATA** である。

- 1ファイル = 1ホテル × 1宿泊月。
- 行：`stay_date`（宿泊日）
- 列：`LT`（-1, 0, 1, ..., MAX_LT）
  - `LT = -1` … 宿泊月の最終着地（ACT）
  - `LT = 0` … 宿泊日の当日残り
  - `LT > 0` … 宿泊日から数えて「何日前か」
- セル値：`rooms`（その LT 時点での販売済み室数）

詳細な形式は `spec_data_layer.md` の「LT_DATA」を参照。

### 2.2 ASOF と評価とのつながり

- **ASOF（日付）**  
  「ある時点までに見えていた予約情報を使って、将来の宿泊日を予測する」ための基準日。

- `run_full_evaluation.py` / `run_evaluate_forecasts.py` では、概ね次の流れを取る：
  1. 評価対象の ASOF を列挙する（例：`M-2_END`, `M-1_END`, `M10`, `M20`）。
  2. 各 ASOF について、対象月（`target_month`）の LT_DATA とモデルを使い、
     **宿泊月トータルの室数（合計）** を予測する。
  3. 実績の最終室数（`LT = -1` の合計）と比較し、誤差を計算する。

- 月次評価の基本式（概念）：

  - 実績合計  
    \[
      A = \sum_{\text{stay\_date}} \text{actual\_rooms}(\text{stay\_date})
    \]
  - 予測合計  
    \[
      \hat{A} = \sum_{\text{stay\_date}} \text{forecast\_rooms}(\text{stay\_date})
    \]
  - 誤差（室数）  
    \[
      \text{error} = \hat{A} - A
    \]
  - 誤差率（％）  
    \[
      \text{error\_pct} = 
      \begin{cases}
        \dfrac{\hat{A} - A}{A} \times 100 & (A > 0) \\
        0                                  & (A = 0)
      \end{cases}
    \]

- 評価結果の `evaluation_*_multi.csv` では、ASOF を跨いでモデルごとに集計した
  `mean_error_pct` / `mae_pct` が算出される（詳細は `spec_evaluation.md` 参照）。

  さらに GUI では `evaluation_*_detail.csv` から以下も算出して表示する：

  - `rmse_pct` … **RMSE（%）** に相当  
    \[
      \text{rmse\_pct} = \sqrt{\frac{1}{n}\sum_{\text{ASOF}}\left(\text{error\_pct}^{(m)}\right)^2}
    \]
  - `n_samples` … 集計に使ったサンプル数（ASOF数）

  本書では便宜上、以下のように読み替える：

  - `mean_error_pct` … **バイアス（%） / MPE** に相当  
    （正なら「攻め気味」、負なら「守り気味」）
  - `mae_pct` … **MAPE（%）** に相当  
    （誤差の方向は無視した平均的な外れ具合）
  - `rmse_pct` … **RMSE（%）** に相当  
    （大きな外しにやや敏感な、平均的な外れ具合の指標）

  ※ RMSE は「正式採用して仕様固定」しているわけではないが、
  GUIでは参考値として `rmse_pct`（誤差率 error_pct を元にした RMSE% 相当）を表示することがある。
  売上予測も含めた評価設計の再考フェーズで、指標体系（rooms / % / 売上）を再整理する。


---

## 3. OCC 予測モデル（実装済）

この章では、現時点で GUI / 評価で利用している OCC モデルを仕様レベルで定義する。

- `avg`
- `recent90`
- `recent90_adj`
- `recent90w`
- `recent90w_adj`
- `pace14`
- `pace14_market`

### 3.1 avg モデル（moving_average_3months）

**モデル名**

- GUI / 評価タブ上の表示名：`avg`
- 実装上のコア関数：
  - `moving_average_3months(...)`（`forecast_simple.py`）
  - `forecast_final_from_avg(...)`（月別の最終室数を組み立てるラッパ）

**概要**

- **直近3ヶ月の LT カーブの平均**を LT ごとに計算し、
  それをベースに **宿泊月の最終室数（LT = -1）** を予測するモデル。
- 「あまり市況が急変していない前提」で、安定した基準値を提供する。

**入力イメージ**

- `lt_df: pd.DataFrame`
  - 複数月の LT_DATA を縦方向に連結した DataFrame。
- `lt_min, lt_max`
  - 使用する LT の範囲（例：`-1`〜`90`）。
- `as_of_date`
  - 評価の ASOF。`avg` モデルは ASOF に強く依存しないが、
    実装上はウィンドウの中心や履歴期間の選定に使用される。

**計算イメージ（概念）**

1. ASOF を中心に、前後数ヶ月分の宿泊月を取得する。
2. 各月について LT_DATA を読み込み、同じ LT ごとに値を並べる。
3. LT ごとに平均値を取り、`avg(LT)` カーブを作成。
4. ASOF 時点の埋まりを足し合わせて、対象月の最終室数を予測。

**用途**

- 「この LT のとき最終的にどれくらい埋まることが多いか」の、安定した基準値。
- 市況変化が比較的小さいときのベンチマークモデル。

---

### 3.2 recent90 / recent90_adj モデル（moving_average_recent_90days）

**モデル名**

- `recent90`
- `recent90_adj`  
  - `recent90` の予測結果に対して、**カレンダー／セグメント情報に基づく調整**を適用したバージョン。

**実装上のコア関数**

- `moving_average_recent_90days(lt_df, as_of_date, lt_min, lt_max)`（`forecast_simple.py`）
- `forecast_month_from_recent90(...)`（ASOF 時点から日別予測を組み立てる）
- `apply_segment_adjustment(...)`（`segment_adjustment.py`）  
  ※ `recent90_adj` / `recent90w_adj` 共通で利用

**概要**

- ASOF を基準に、**直近90日間の観測**だけを使って LT ごとの平均カーブを作るモデル。
- `avg` よりも「直近の市況変化」に敏感になりやすい。

**ウィンドウの考え方（重要なポイント）**

`moving_average_recent_90days` は、LT ごとに次のような stay_date ウィンドウを取る：

- ASOF 日付を `T`、LT を `L` とすると、
  - ウィンドウの開始日：`T - (90 - L) 日`
  - ウィンドウの終了日：`T + L 日`
- これは「観測日（= stay_date）と ASOF の差（= 観測時点から見た“年齢”）」が
  おおむね **過去90日以内**になるように調整したものと解釈できる。

実装では、LT 列ごとに上記ウィンドウで `values.mean()` を取っている。

**計算イメージ**

1. `lt_df` の index を日付に揃える。
2. 各 LT について、上記の stay_date ウィンドウ内の観測値を抽出。
3. 抽出した値の平均を取り、`recent90(LT)` カーブを構成。
4. `forecast_month_from_recent90` で ASOF 以降の日別予測を作る：
   - ASOF より前の日付 … 実績 (`actual_rooms`)
   - ASOF 以降の日付 … `recent90(LT)` に基づく予測値
5. 日別予測を合計して宿泊月トータルの室数を得る。

**recent90 と recent90_adj の違い**

- `recent90`
  - 上記の「直近90日平均」だけで日別の `projected_rooms` を作る。
- `recent90_adj`
  - `projected_rooms` に対して、`apply_segment_adjustment` を通し、
    カレンダー要因（連休の位置など）に基づく微調整を加える。
  - 現状のルール（`segment_adjustment.py`）：
    - `holiday_block_len >= 3` かつ `holiday_position == "middle"` の日のみ
      `projected_rooms * 0.98` とし、それ以外は 1.0 倍。
    - 補正後は四捨五入し、`adjusted_projected_rooms` として保持。
  - `_adj` モデルは、この `adjusted_projected_rooms` を合計して予測総室数を出す。

> 補足：  
> 将来的には、月次評価から得られる「モデルバイアス（mean_error_pct）」を
> さらに掛け合わせる形でのバイアス補正を検討しているが、
> 現時点の `_adj` は **カレンダー起点の微調整**に留まる。

---

### 3.3 recent90w / recent90w_adj モデル（moving_average_recent_90days_weighted）

**モデル名**

- `recent90w`
- `recent90w_adj`（`recent90w` に対して `apply_segment_adjustment` をかけたもの）

**実装上のコア関数**

- `moving_average_recent_90days_weighted(...)`（`forecast_simple.py`）
- `forecast_month_from_recent90(...)`
- `apply_segment_adjustment(...)`（`segment_adjustment.py`）

**概要**

- `recent90` と同様に「直近90日」を対象とするが、
  **観測日ごとに重みを変えた平均**を取るモデル。
- 直近の30日をより重く、それ以前の60日を軽く扱うことで、
  「直近の動き」をより強く反映することを狙う。

**デフォルトの重み**

- 絶対日数差 `d = |obs_date - as_of_date|` に対して：

  - `0 ≤ d ≤ 14` … 重み 3.0
  - `15 ≤ d ≤ 30` … 重み 2.0
  - `31 ≤ d ≤ 90` … 重み 1.0
  - それ以外 … 重み 0（無視）

- `weights=(w_recent, w_mid, w_old)` を渡すことで上記3つの値は変更可能。

**計算イメージ**

1. `recent90` と同様に、LT ごとに stay_date のウィンドウを決める。
2. ウィンドウ内の各観測値に対し、`age_days = (obs_date - as_of_date).days` から
   上記の重みを割り当てる。
3. 「加重平均 = (値 × 重み) の合計 / 重み合計」を LT ごとに計算。
4. 以降は `recent90` と同様に、`forecast_month_from_recent90` → 日別予測 → 月次総室数。

**recent90w と recent90w_adj の違い**

- `recent90w`
  - 加重平均で作った `projected_rooms` をそのまま使う。
- `recent90w_adj`
  - `apply_segment_adjustment` を通して、
    `adjusted_projected_rooms` を用いた予測とする（連休の中日を少し抑える等）。

---

### pace14 / pace14_market（追加モデル）

**目的**
- 市況急変や直近の勢い（直近1〜2週間のpickupの強弱）を、ベースモデル（recent90系）の着地見込みに安全に反映する。
- 「差分」ではなく **倍率（比率）= Pace Factor（PF）** として反映する（スケールが違う日でも扱いやすい）。

**実装上のコア関数（参照）**
- `src/booking_curve/forecast_simple.py`
  - `build_pace14_spike_thresholds()`（スパイク閾値の作成）
  - `_calc_pace14_pf()`（PF算出・スパイク判定・clip）
  - `forecast_final_from_pace14()`（最終着地の算出）
  - `compute_market_pace_7d()` / `forecast_final_from_pace14_market()`（market補正）

#### 3.4.1 pace14（自館の直近pickupを反映）
- ベースカーブ：weekday別の `recent90`（moving average）をベースとして使用する（※`avg` ではない）。
- 直近のpickupの強弱を、**LT=14→LT=7 の1週間**を基本窓として評価する。

**Pace Factor（PF）の計算（概念）**
- `upper_lt = 14`
- `lower_lt = max(lt_now, 7)`（到着が近い日は、比較窓を縮める）
- `delta_actual = OH(lower_lt) - OH(upper_lt)`
- `delta_base   = baseline_curve[lower_lt] - baseline_curve[upper_lt]`
- `pf_raw = delta_actual / max(delta_base, eps)`（ゼロ割回避のためepsを入れる）

**到着が遠い日の“効きすぎ”を抑える（shrink）**
- `alpha = (upper_lt - lower_lt) / 7`（0〜1）
- `pf_shrunk = 1 + alpha * (pf_raw - 1)`
  - `lt_now=14` なら `alpha=0` で **PFは 1 に戻る**（=補正しない）
  - `lt_now=7` なら `alpha=1` で **PFが最大に効く**

**スパイク判定とclip（安全弁）**
- スパイク判定は機械的に行う（SP-A）。
  - `build_pace14_spike_thresholds()` で、過去の `delta_actual` 分布から `q_lo/q_hi`（分位点）を作り、外れ値をスパイク扱いにする。
- 初期clip（合意済みの初期値）：
  - 通常clip：`0.7 .. 1.3`（`PACE14_CLIP_RANGE`）
  - スパイク時の強clip：`0.85 .. 1.15`（`PACE14_CLIP_SPIKE`）

**最終着地の算出**
- `base_now   = baseline_curve[lt_now]`
- `base_final = baseline_curve[final_lt]`（最終着地側）
- `base_delta = base_final - base_now`（この先の“残りpickup”のベース見込み）
- `final_forecast = OH_now + pf_clipped * base_delta`

#### 3.4.2 pace14_market（market_pace で派生補正）
- `pace14` をベースに、**市場側の直近pickup傾向（market_pace）** を加味する派生モデル。
- 実装の狙い：自館の直近pickupが薄い/ブレる中LT帯で、marketの情報を少しだけ混ぜて事故を減らす（混ぜすぎない）。

**market補正の適用イメージ（概念）**
- `market_pace_7d = compute_market_pace_7d(...)`（7日窓）
- `market_beta = exp(-k * (lt_now - MARKET_PACE_LT_MIN))`（LTが遠いほど影響を弱める）
- `market_factor = clip(1 + market_beta * (market_pace_7d - 1), MARKET_PACE_CLIP)`
- `final_forecast = OH_now + (pf_clipped * market_factor) * base_delta`

#### 3.4.3 診断情報（UI表示用）
- `pace14` 系は、内部的に以下の診断情報（例）を返し、GUIで「⚠ spike」等を表示できるようにしている：
  - `delta_actual / delta_base`
  - `pf_raw / pf_shrunk / pf_clipped`
  - `q_lo / q_hi`（閾値）と `is_spike`
  - （`pace14_market` の場合）`market_pace_7d`, `market_beta`, `market_factor`

**注意**
- 必要なLT_DATA（履歴）が不足する場合、PFや閾値が安定しないため、ベースモデル（recent90系）へフォールバックすることがある（運用上は「まずベースで外さない」が優先）。

---

## 4. 売上予測モデル（ADRモデル）の構想レベル仕様

> ※4.1〜4.4はロードマップ（Phase 1.1〜1.2）の設計メモ（=構想レベル仕様）です。  
> v0.6.10 以降は、末尾の **4.5（V1仕様：実装済）** を採用しています。

### 4.1 基本構造

将来の売上予測は、以下の分解を基本とする：

> 日別売上予測 ＝ 日別室数予測（OCC） × ADRモデル（1室あたり単価）

- 日別室数予測：
  - 本書の `avg / recent90 / recent90w` など、既存 LT ベースモデルを利用。
- ADRモデル（案）：
  - ベースライン ADR
  - インフレ調整
  - 直近トレンドによる微調整（短期）

### 4.2 ベースライン ADR（中長期）

- 「平日 / 休前日 / 連休中日 × 月」などの粒度で、
  過去の最終着地ADRの平均をテーブル化する。
- コロナ期間等の歪みは除外し、概ね 2019・2023・2024 など
  「構造が似ている年」の平均を使うことを想定。

### 4.3 インフレ・トレンド調整（中期）

- 「直近3〜6ヶ月の ADR トレンド」などから、ベースラインへの倍率を推計する。
- 例）前年同月比 ADR が +8% 程度で推移しているなら、
  ベースライン ADR に 1.08 を掛ける、など。

### 4.4 短期のフロー情報（直近3ヶ月）

- 直近〜今後3ヶ月程度の短期では、
  すでに見えている **OHベースの ADR（実績 + 予約分）** のトレンドを重視する。
- 具体例：
  - 1週間ごとに、対象月の「今見えている ADR の水準」を記録し、
    上がり／下がりの傾向を係数として反映する。

### 4.5 V1仕様（実装済）：pax / revenue / phase_bias / 月次丸め（表示）

この節は **現行実装（v0.6.10）** の仕様をまとめる。4.1〜4.4の設計メモと混同しないこと。

#### 4.5.1 入力データ（LT_DATA）
- LT_DATA は rooms だけでなく **rooms / pax / revenue の3系統**を扱う。
  - rooms：従来の後方互換名（例：`lt_data_YYYYMM_{hotel}.csv`）も探索対象に含む。
  - pax：例 `lt_data_pax_YYYYMM_{hotel}.csv`
  - revenue：例 `lt_data_revenue_YYYYMM_{hotel}.csv`
- データレイヤの詳細は `docs/spec_data_layer.md` を優先（本章はモデル側の前提のみ記述）。

#### 4.5.2 pax（人数）予測（DOR経由ではなく直接forecast）
- paxは **roomsと同型のモデル**で直接forecastする（weekday別も同様）。
- DORは派生指標として `DOR = Pax / Rooms` で算出する（DOR自体は予測しない）。
- 上限制約：`pax_cap`（設定が空の場合は自動推定）
  - GUI入力が **空(None)** の場合は無制限ではなく、`infer_pax_capacity_p99()` により **p99（上位1%）** を上限として推定する。
  - 母集団は直近Nヶ月（デフォルト6ヶ月）の各日 `act_pax` を使用する（maxではない）。

#### 4.5.3 revenue（税抜宿泊売上）予測（V1の安全側）
- revenue定義：**税抜の宿泊売上**（朝食等は含めない）。
- V1の基本式：
  - `adr_pickup_est = (revenue_oh_now / max(rooms_oh_now, eps)) × phase_factor`
  - `forecast_revenue = revenue_oh_now + remaining_rooms × adr_pickup_est`
- `phase_factor` は `phase_bias` の手動設定（悪化/中立/回復 × 強度）を **倍率** として反映する。
  - `rooms_oh_now` が極小の場合は `eps` を用いてゼロ割を回避する。

#### 4.5.4 phase_bias（手動フェーズ補正）
- UI：3ヶ月（当月/翌月/翌々月）× フェーズ（悪化/中立/回復）× 強度（弱/中/強）。
- 保存先：`local_overrides`（端末ローカル上書き）。
- 適用先：当面は **revenue（ADR推定）へのみ適用**し、rooms/pax のOCC側モデルとは独立で運用する。

#### 4.5.5 月次丸め（Forecast整合：表示のみ）
- 目的：報告資料向けに、**月次合計が指定単位で“キリ良く”見える**ようにする（ただし内部forecast値は保持する）。
- 丸め対象：対象月内の未来日（`stay_date >= ASOF` かつ 対象月内）の display 列のみ。
- 適用条件：対象月内の未来日数 `N >= 20` のときのみ。
- 丸め差分は、対象月内の未来日にのみ配分する（着地済 `stay_date < ASOF` は一切触らない）。
- 丸め単位：ホテル別設定（Rooms / Pax / Rev）。

---

## 5. 更新ルール

- モデルを追加・削除・ロジック変更する場合、必ず更新するファイル：
  - 本書 `spec_models.md`
  - `spec_evaluation.md`（評価方法や指標に影響する場合）
  - 関連する実装ファイル（`forecast_simple.py`, `run_full_evaluation.py` 等）
- 特に以下のケースでは、本書の更新を **必須** とする：
  - `avg / recent90 / recent90w` の定義を変更した場合
  - `_adj` 系モデルの調整ロジック（`segment_adjustment.py`）を変更した場合
  - ADR / 売上モデルの実装を追加・変更した場合
  - 評価指標の定義（分母や集計粒度）を変更した場合

## 6. 日別フォーキャストタブの表示定義

本節では、GUI の「日別フォーキャスト」タブにおける主な列の意味を整理する。  
OCC モデル自体の計算方法は前節までの記述（`avg` / `recent90` / `recent90w` など）に従うものとする。

### 6.1 基本コンセプト

日別フォーキャストタブでは、1 行を 1 日（`stay_date`）とし、同じ日について

- **Actual**：現時点で分かっている「最終実績」
- **ASOF_OH**：指定 ASOF 時点での「その時点までの積み上がり（OH）」
- **Forecast**：指定 ASOF と選択モデルに基づく「最終着地予測」

の 3 レイヤーを並べて表示する。

将来的に人数・売上などの指標を追加する場合も、  
「Actual / ASOF_OH / Forecast の 3 レイヤーにそれぞれ Rooms / Pax / Revenue / OCC / ADR / RevPAR をぶら下げる」  
という構成を基本とする。

### 6.2 Rooms 列の定義

現行実装で意味を持つ列は以下の通り。

- `actual_rooms`
  - 「最終的にどこまで埋まったか（あるいは現時点でどこまで埋まっているか）」を表す。
  - 定義：
    - **着地済み日** … LT_DATA の ACT(-1)（D+ スナップショット由来の最終室数）
    - **未着地日** … 現在利用可能な **最新 ASOF** の `rooms_oh`
  - ASOF を変えても値は変化しない（**ASOF 非依存の最終実績**）。

- `asof_oh_rooms`
  - GUI で指定した `AS_OF_DATE` に対して、  
    「その ASOF 時点で、各 `stay_date` が何室積み上がっていたか」を表す。
  - 定義：
    - `stay_date ≤ AS_OF_DATE` … その時点では結果が確定しているため、ACT(-1) と同じ値
    - `stay_date > AS_OF_DATE` … daily_snapshots から、当該 ASOF の `rooms_oh`
  - ASOF を変更すると値が変化する（**ASOF 依存の OH スナップショット**）。

- `forecast_rooms`
  - 選択したモデル（`avg` / `recent90` / `recent90w` など）と `AS_OF_DATE` に基づく、  
    各 `stay_date` の「最終着地予測」。
  - 定義：
    - `stay_date < AS_OF_DATE` … 実績である `actual_rooms` をそのまま用いる
    - `stay_date ≥ AS_OF_DATE` … 各モデルの `forecast_month_from_*` ロジックで算出した予測値

### 6.3 派生指標の例

Rooms 列から、以下のような派生指標を計算する。

- `occ_actual_pct`  … `actual_rooms / capacity`
- `occ_asof_pct`    … `asof_oh_rooms / capacity`
- `occ_forecast_pct` … `forecast_rooms / capacity`

誤差・ギャップについては、次の 2 軸を基本とする。

- 最終実績との誤差（モデル精度評価用）  
  - `diff_rooms_vs_actual = forecast_rooms - actual_rooms`
  - `diff_pct_vs_actual = diff_rooms_vs_actual / actual_rooms`
- 指定 ASOF からの積み増し量（運用・意思決定の振り返り用）  
  - `pickup_expected_from_asof = forecast_rooms - asof_oh_rooms`

将来的に人数・売上の列を追加する場合も、  
同じ考え方で Actual / ASOF_OH / Forecast それぞれに対して派生指標を定義する。


以上。
