# データレイヤ仕様（spec_data_layer）

このドキュメントは、`rm-booking-curve-lab` における **データ構造とファイル仕様** を整理したものです。  
特に以下の 3 レイヤーを対象とします。

1. `daily snapshots`（標準日別スナップショット）
2. `LT_DATA`（宿泊日×LT テーブル＋月次カーブ）
3. 評価用データ（モデル精度評価・日別誤差・セグメント別要約）

> 補足：パスの基準（重要）
>
> 本仕様中の `output/...` / `config/...` は **論理パス** を表す。
> 実体の保存先は **APP_BASE_DIR** 配下（Windows 既定：`%LOCALAPPDATA%/BookingCurveLab/`）であり、
> EXE配下（配置フォルダ）には出力しない。

---

## 1. daily snapshots（標準日別スナップショット）

### 1-1. 役割と位置づけ

`daily snapshots` は、PMS 生データをホテル横断で扱えるようにした **「唯一の正」** となる日別 OH データです。

- 入力：PMS 生データ（現在は N@FACE 想定）
- 中間：PMS アダプタ（例：`pms_adapter_nface.py`）
- 出力：標準 CSV（`daily_snapshots_<hotel>.csv`）
- 利用先：
  - LT_DATA（宿泊日×LT）の生成（今後、このルートに寄せていく想定）
  - ADR / RevPAR 履歴、売上予測モデル
  - その他、日別ベースの分析

今後は、「**LT や評価は daily snapshots から再現できること**」を前提とした設計に移行していきます。

---

### 1-2. ファイル仕様

- パス：`OUTPUT_DIR / f"daily_snapshots_{hotel_id}.csv"`
  - 例：`output/daily_snapshots_daikokucho.csv`
- 管理単位：**hotel_id ごとに 1 ファイル**

#### カラム定義

`daily_snapshots.py` の `STANDARD_COLUMNS` に対応：

| カラム名      | 型（論理）      | 説明                                                |
|--------------|-----------------|-----------------------------------------------------|
| `hotel_id`   | str             | ホテル識別子（例：`daikokucho`, `kansai`）         |
| `as_of_date` | date            | 取得日（ASOF）                                      |
| `stay_date`  | date            | 宿泊日                                              |
| `rooms_oh`   | int or float    | 当該 ASOF 時点での OH 室数                          |
| `pax_oh`     | int or float    | 当該 ASOF 時点での OH 人数                          |
| `revenue_oh` | int or float    | 当該 ASOF 時点での OH 宿泊売上（金額）              |

※ 実装上は `pandas.to_datetime`・`to_numeric` で変換し、欠損は NaT / NaN として扱う。
※ revenue_oh は税別の日本円金額（int, 円単位）とする。

#### 一意性と重複処理

- 論理的なキーは **`(hotel_id, as_of_date, stay_date)`**。
- `append_daily_snapshots()` 内で：
  - 既存 CSV を読み込み
  - 新規 DF と縦結合
  - `(hotel_id, as_of_date, stay_date)` で **重複は `keep="last"` で後勝ち** にしてドロップ
  - `as_of_date`・`stay_date` 昇順でソートして書き出す  
  → 後から同じ ASOF を再取り込みしても、最新の値で上書きされる設計。

---

### 1-3. API と利用パターン

`daily_snapshots.py` 提供関数（抜粋）：

- `get_daily_snapshots_path(hotel_id, output_dir=OUTPUT_DIR) -> Path`
  - ホテルごとの CSV パスを返す。
- `normalize_daily_snapshots_df(df, hotel_id=None, as_of_date=None) -> pd.DataFrame`
  - 任意の DataFrame を標準カラムに揃える。
  - 不足カラムは追加（NaN 埋め）、日付列は datetime 化。
  - `hotel_id` / `as_of_date` が単一値ならカラムに埋め込む。
- `append_daily_snapshots(df_new, hotel_id, output_dir=None) -> Path`
  - 正規化 → 既存 CSV とのマージ → 重複処理 → 保存。
  - N@FACE アダプタからの入口。
- `read_daily_snapshots(hotel_id, output_dir=None) -> pd.DataFrame`
  - ホテル単位で全期間の snapshots を読み込み。
  - ファイル不存在時は空 DataFrame を返す。
- `read_daily_snapshots_for_month(hotel_id, target_month, output_dir=None) -> pd.DataFrame`
  - `target_month`（"YYYYMM"）の月初〜月末で `stay_date` をフィルタした DF を返す。
  - LT_DATA 生成の入口として利用。

---

### 1-4. 生成モード（全量再生成 / 部分生成）

daily snapshots は **「唯一の正」** のレイヤーであり、LT_DATA / monthly_curve の生成元となるため、
運用上は「いつ・どの範囲を再生成するか」を明確にする必要があります。

#### (A) 全量再生成（Full rebuild）
- 対象：指定ホテルの *元データ一式*（N@FACE 生データフォルダ）
- 出力：`output/daily_snapshots_<hotel_id>.csv` を **原則として作り直す**
- 用途：
  - 初期導入（過去2〜3年分を一括投入）
  - 元データの構造変更や、変換ロジック（アダプタ）修正後の整合性取り直し

#### (B) 部分生成（Partial rebuild / Upsert）
- 対象：指定ホテルの *元データの一部*（例：直近の ASOF のみ / 直近数ヶ月のみ）
- 目的：週次運用などで、データ量増加による処理時間の悪化を避ける
- 方式（推奨）：
  1. 既存 `daily_snapshots_<hotel_id>.csv` を読み込む
  2. 「今回再生成する対象範囲（例：as_of_date の範囲）」に該当する行を既存CSVから除外
  3. 元データから対象範囲だけ再生成して append
  4. `(hotel_id, as_of_date, stay_date)` をキーに `drop_duplicates(keep="last")` 等で重複排除
  5. ソートして保存（`hotel_id, as_of_date, stay_date`）
- 注意：
  - daily snapshots 自体は **欠損（NaN）を保持**する（補完はビュー/評価レイヤーで行う）
  - upsert の「対象範囲の定義」は、GUI・CLI で統一する

#### (C) GUI からの再生成（LT生成時の連動）
GUI では、LT_DATA 生成時に daily snapshots を更新できるオプションを持つ（チェックボックス等）。

- `LTソース = daily_snapshots` のときのみ有効
- 目的：検証時に「daily snapshots → LT_DATA → monthly_curve」を一気通貫で更新し、整合性確認を容易にする
- 初期実装は Full rebuild でもよいが、運用フェーズでは Partial rebuild を優先して実装する（別ブランチで対応）。

---

### 1-5. N@FACE アダプタとの関係（参考）

`pms_adapter_nface.py` にて、N@FACE の生 Excel を読み込み、  
`normalize_daily_snapshots_df` → `append_daily_snapshots` を通して標準 CSV に変換する。

- レイアウト種別：
  - `"shifted"`：宿泊日行の **1 行下** が OH（無加工 / 加工A / 加工B）
  - `"inline"`：宿泊日行と **同じ行** が OH（加工C）
  - `"auto"`：A 列の日付インデックス間隔から自動判定
- ASOF：
  - 原則 Q1 セルの値
  - 欠損時はファイル名の `YYYYMMDD` から推定

このアダプタ層は「PMS ごとの差異を吸収し、daily snapshots 仕様に揃える」役割を持ちます。

---

## 2. LT_DATA

### 2-1. 役割と位置づけ

LT_DATA は、**宿泊日 × LT（Lead Time）** のブッキングカーブを表現する中核データです。  
主な利用先：

- GUI の日別ブッキングカーブタブ
- モデル評価（各モデルの月次 Forecast 元）
- 日別 Forecast の Rooms 部分（将来の売上予測のベース）

現在は、次の 2 つの生成ルートが並存している。

1. **PMS 時系列 Excel → LT_DATA（従来ルート / legacy）**
2. **daily snapshots → LT_DATA（新ルート / 推奨）**

どちらのルートも、最終的には同じフォーマットの `lt_data_YYYYMM_<hotel>.csv` を出力する。  
今後は daily snapshots ルートを標準とし、時系列 Excel ルートは互換性維持と比較用に残す方針。

LT_DATA の出力ファイルは、互換性維持と多指標対応のため以下の扱いとする。

### 互換ファイル（従来名）
- `lt_data_YYYYMM_<hotel>.csv`
  - rooms を出力する（従来運用・既存コードとの互換のため）

### 指標別ファイル（追加）
- `lt_data_rooms_YYYYMM_<hotel>.csv`
- `lt_data_pax_YYYYMM_<hotel>.csv`
- `lt_data_revenue_YYYYMM_<hotel>.csv`

いずれもテーブル構造（行=stay_date、列=LT）は同一で、セル値の意味（value_type）のみが異なる。

- rooms：当該宿泊月の月累計 Rooms（従来どおり）
- pax：当該宿泊月の月累計 Pax
- revenue：当該宿泊月の月累計 Revenue

---

### 2-2. LT_DATA テーブル仕様

- ファイル例：`output/lt_data_YYYYMM_<hotel>.csv`
  - 例：`lt_data_202512_daikokucho.csv`
- インデックス：`stay_date`（宿泊日）
  - 文字列 or 日付文字列だが、読み込み側では `pd.to_datetime` 前提。
- 列：LT 値（整数）
  - 範囲：`-1, 0, 1, ..., max_lt`
    - `-1`：ACT（最終実績）
    - `0..max_lt`：宿泊日から見たリードタイム日数
  - 実装上の並び：
    - 内部処理中は `-1..max_lt` 昇順で扱い、
    - 最終的な出力は `max_lt..-1` の降順（`lt_desc_columns`）に並び替えて保存。

#### セルの意味

`lt_data[stay_date][lt]`：

- `lt >= 0`：  
  「**LT = lt の時点での、当該宿泊月の月累計（value_type）**」
  - rooms：月累計 Rooms
  - pax：月累計 Pax
  - revenue：月累計 Revenue
  - 例：`lt=30` なら「宿泊月末から 30 日前 ASOF における、その宿泊月の月累計（value_type）」。

- `lt = -1`：  
  「**実績最終値（ACT）**」。  
  - `stay_date` より後の日付に ASOF が存在する場合  
    → 最初に出現する `as_of_date > stay_date` の月累計（value_type）を ACT として採用。  
  - `stay_date` 以降の ASOF が存在しない場合  
    → ACT は `NaN` のまま（未着地）。

※以降の説明は便宜上 rooms を例に書くが、pax / revenue も同一ロジックで「値（value_type）が差し替わるだけ」として読み替える。

#### 欠損と補間

LT_DATA の「欠損セル（NaN）」は、ルートごとに扱いが異なる。

##### (A) 時系列 Excel ルート（従来）

`lt_builder.build_lt_data_from_timeseries_for_month(...)` の要約：

1. 原データ（宿泊日×取得日）から、`stay_date`, `lt`, `rooms` のレコードを生成。
2. `pivot_table(index="stay_date", columns="lt", values="rooms", aggfunc="last")`。
3. 全 LT を `-1..max_lt` で reindex（欠損は NaN）。
4. 横方向（LT 方向）に `interpolate(limit_direction="both")` で補間。
   - **行全体が NaN の場合は補間しない**（その宿泊日は警告ログ）。
5. 四捨五入して `Int64` 型にキャスト。
6. 列を `max_lt..-1` の降順で並べ替えた DataFrame を返す。

このため legacy ルートでは：

- 観測されていない LT の値も、同一宿泊日の他 LT から補間値が入る。
- PMS 側に一切データがない宿泊日は、全 LT が NaN のまま残る。

##### (B) daily snapshots ルート（新）

`build_lt_data_from_daily_snapshots_for_month(...)` の要約：

1. `read_daily_snapshots_for_month(hotel_id, target_month)` で、
   対象月の `as_of_date × stay_date` 行を取得。
2. ASOF ごとに「当該宿泊月の月累計 Rooms」を計算。
3. `LT = (stay_date - as_of_date).days` を計算し、`LT > max_lt` は切り捨て。
4. `stay_date × lt` でピボット（aggfunc="last"）。  
   → この時点では **補間を行わず、存在しないセルは NaN のまま**。
5. ACT(-1) 列を構成：
   - `stay_date < max_as_of_date` の行だけ、
     最初に現れる `as_of_date > stay_date` の月累計を ACT(-1) に設定。
   - `stay_date >= max_as_of_date` の行は ACT(-1) を NaN のまま保持。
6. 列を `max_lt..-1` の降順に並べ替えて返す。

→ **daily snapshots ルートでは、データレイヤーで補間はしない。**  
　NaN は「そもそも snapshots 上に観測がなかった LT」として、そのまま保持する。  
　NOCB 等の補完は、ビュー / 評価レイヤー側（グラフ描画・モデル評価）で行う方針。

---

### 2-3. LT_DATA の生成ルート

#### (1) 時系列 Excel から（legacy）

- 前提フォーマット：
  - 1 行目：各列の取得日（Excel シリアル）
  - 1 列目：各行の宿泊日（Excel シリアル or 日付）
  - 2 行目以降：OH 室数
- フロー：
  1. `load_time_series_excel()` 相当の処理で DataFrame に読み込み。
  2. 対象宿泊月だけをフィルタ。
  3. `build_lt_data_from_timeseries_for_month(df, max_lt)` を実行。
  4. `lt_data_YYYYMM_<hotel>.csv` として書き出し。

（CLI 実行は `run_build_lt_csv.py` の `source="timeseries"` が担当）

#### (2) daily snapshots から（新・推奨）

- 入力：`output/daily_snapshots_<hotel_id>.csv`

- フロー：

  1. `read_daily_snapshots_for_month(hotel_id, target_month)` で  
     `stay_date` が `target_month` に属するレコードのみ抽出。

  2. 各レコードについて `LT = (stay_date - as_of_date).days` を計算。
     - `LT > max_lt` は無視（切り捨て）。
     - `LT >= 0` のレコードは「LT テーブル用」のデータとして残す。
     - `LT < 0`（D+ 側）のレコードは、後で ACT(-1) を組み立てるときだけ使う。

  3. `LT >= 0` のレコードについて、  
     `(stay_date, LT)` ごとに `rooms = rooms_oh` を `last` で集計し、  
     `pivot(index="stay_date", columns="lt")` で **宿泊日×LT テーブル** を作成。
     - この段階では補間は行わず、観測がない LT は `NaN` のまま。

  4. ACT(-1) 列を追加する：
     - 各 `stay_date` について `as_of_date > stay_date` の D+ スナップショットを探し、
       - あれば「一番早い `as_of_date` の `rooms_oh`」を ACT(-1) として採用。
       - なければ ACT(-1) は `NaN`（未着地）のまま残す。

  5. 列を `max_lt..-1` の降順（`lt_desc_columns`）に並べ替え、  
     `lt_data_YYYYMM_<hotel>.csv` として出力。

→ これにより「PMS 生データ → daily_snapshots → LT_DATA」が一貫パイプラインとして完成する。  
　時系列 Excel がなくても、daily_snapshots さえ生成できれば LT_DATA を再作成できる。

---

### 2-4. 月次ブッキングカーブ（monthly_curve）

LT_DATA と並ぶ、もう一つの重要な LT 系データが **月次ブッキングカーブ** です。  
これは「宿泊月トータルの Rooms を LT ごとに集計したカーブ」です。

- ファイル例：`output/monthly_curve_YYYYMM_<hotel>.csv`
- インデックス：`lt`（整数、`max_lt..-1` の降順）
- 列：
  - `rooms_total`：当該 LT 時点での「宿泊月の累計 Rooms」

#### 概念（ASOF ベース）

- ある宿泊月（例：2025-12）の月次カーブは、
  各 ASOF 時点での「その宿泊月の累計予約室数」を LT 軸に並べ替えたもの。
- LT の定義：
  - `LT = (month_end_date - as_of_date).days`
  - `LT < 0` は `-1`（ACT）としてまとめる。
    - 例：12 月の ACT は、翌 1/1 ASOF の月累計に相当。
  - `LT > max_lt` は集計から除外。

#### 生成ルート

1. **時系列 Excel から**
   - 各取得日列について、対象宿泊月の OH 室数を列合計。
   - その列合計を「その ASOF における月累計 Rooms」とみなし、上記の LT 定義で `lt` に割り付ける。
   - `lt` ごとに `rooms_total` を加算し、`max_lt..-1` の降順 DataFrame として出力。

2. **daily snapshots から（新ルート）**
   - `daily_snapshots_<hotel_id>.csv` から対象月レコードを読み込み。
   - `as_of_date` ごとに、当該宿泊月の Rooms を合計（＝その ASOF における月累計）。
   - あとは時系列ルートと同じく、`LT = (month_end_date - as_of_date).days` で LT に割り付け、
     `lt` ごとに `rooms_total` を加算して出力。

現状の実装では：

- 時系列ルート・daily snapshots ルートともに、同じ ASOF 定義で集計しており、
  `monthly_curve_YYYYMM_<hotel>.csv` の数値は両ルートで一致することを確認済み。
- GUI の月次カーブタブは、この `monthly_curve_YYYYMM_<hotel>.csv` を読み込んで描画する。  
  欠損セルが存在する場合でも、**monthly_curve レベルでは補間は行わない**（描画時に NOCB 適用予定）。
---

## 3. 評価用データ

評価レイヤーのデータは、大きく以下の 3 種類に分かれます。

1. **月次合計ベースのモデル評価（detail / multi）**
2. **日別誤差テーブル（daily_errors）**
3. **セグメント別誤差サマリー（weekday / holiday position / before-holiday）**

---

### 3-1. 月次合計ベースのモデル評価

#### (1) 詳細テーブル：`evaluation_<hotel>_detail.csv`

生成元：

- 旧：`run_evaluate_forecasts.py`
- 新：`run_full_evaluation.py` 系（`build_evaluation_detail`）

新仕様（`run_full_evaluation` ベース）を基準とします。

- パス：`OUTPUT_DIR / f"evaluation_{hotel_tag}_detail.csv"`
- カラム（新仕様の例）：

| カラム名               | 説明                                               |
|------------------------|----------------------------------------------------|
| `target_month`         | 対象宿泊月（"YYYYMM"）                             |
| `asof_date`            | 評価に用いた ASOF 日付（`YYYY-MM-DD`）             |
| `asof_type`            | ASOF の種別（例：`M-2_END`, `M-1_END`, `M_START` など） |
| `model`                | モデル名（`avg`, `recent90`, `recent90w` など）   |
| `actual_total_rooms`   | 宿泊月の実績トータル Rooms                         |
| `forecast_total_rooms` | 該当モデル・ASOF での予測トータル Rooms            |
| `error`                | `forecast_total_rooms - actual_total_rooms`        |
| `error_pct`            | `error / actual_total_rooms * 100`（%）           |
| `abs_error_pct`        | `abs(error_pct)`                                   |

旧スクリプト（`run_evaluate_forecasts.py`）ではカラム名が若干異なりますが、  
**意味としては同じもの**（ASOF ごとの月次トータル誤差）です。

#### (2) サマリテーブル：`evaluation_<hotel>_multi.csv`

`build_evaluation_summary()` / `run_evaluate_forecasts.main()` で生成。

- パス：`OUTPUT_DIR / f"evaluation_{hotel_tag}_multi.csv"`
- カラム：

| カラム名        | 説明                                         |
|-----------------|----------------------------------------------|
| `target_month`  | 対象宿泊月                                  |
| `model`         | モデル名                                     |
| `mean_error_pct`| `error_pct` の平均（＝月次バイアスの％）     |
| `mae_pct`       | `abs_error_pct` の平均（＝月次 MAPE 相当）  |

GUI の「モデル評価」タブは、このサマリをベースに

- モデルごとの **バイアス（攻め/守りのクセ）**
- 平均誤差率（MAPE のような感覚値）

を表示・比較する用途で使います。

補足（GUI表示の派生列）：

- GUI の「モデル評価」タブでは、`evaluation_*_detail.csv` から
  - `rmse_pct`（RMSE%）
  - `n_samples`（ASOF数）
  を算出して表示する。
- `evaluation_*_multi.csv` 自体には、現状この2列は含めない（将来、出力列として追加する余地はある）。


---

### 3-2. 日別誤差テーブル：`daily_errors_<hotel>.csv`

`run_segment_error_summary.py` の入力となる日別粒度の誤差テーブルです。

- パス：`OUTPUT_DIR / f"daily_errors_{HOTEL_TAG}.csv"`
- 想定カラム（コードから読み取れる範囲）：

| カラム名                 | 説明                                                         |
|--------------------------|--------------------------------------------------------------|
| `stay_date`              | 宿泊日（datetime）                                          |
| `as_of`                  | ASOF 日（`YYYYMMDD` → datetime 化して使用）               |
| `target_month`           | 対象宿泊月（"YYYYMM"）                                      |
| `model`                  | モデル名（`avg`, `recent90`, `recent90_adj`, …）           |
| `error_pct`              | 日別誤差率（`(FC − 実績) / 実績 * 100`）                   |
| `weekday`                | 曜日（0=Mon,…,6=Sun）                                       |
| `is_holiday_or_weekend`  | 祝日 or 週末かどうかのフラグ（ブール）                     |
| `is_before_holiday`      | 翌日が休日かどうかのフラグ（ブール）                       |
| `holiday_block_len`      | 連休長（3連休以上を識別するための整数）                    |
| `holiday_position`       | 連休内での位置（"first", "middle", "last", "single", "none" など） |
| …                        | 必要に応じて追加される説明用カラム                         |

`load_daily_errors()` では以下のフィルタを掛けています：

- `stay_date >= as_of`（**future 部分のみ**に絞る）
- `error_pct.notna()`（誤差率が NaN の行は除外）

→ 評価対象は「**ASOF 時点で未来だった日付に対する誤差**」のみ。

---

### 3-3. セグメント別誤差サマリー

`run_segment_error_summary.py` は、`daily_errors_<hotel>.csv` から  
以下の 3 種類のサマリを生成します。

1. `error_summary_weekday_<hotel>.csv`
2. `error_summary_holiday_position_<hotel>.csv`
3. `error_summary_before_holiday_<hotel>.csv`

#### (1) weekday 別サマリー

- 関数：`summarize_by_weekday(df)`
- 出力カラム（例）：

| カラム名        | 説明                                                |
|-----------------|-----------------------------------------------------|
| `model`         | モデル名                                            |
| `weekday`       | 曜日（0=Mon,…,6=Sun）                               |
| `n`             | 件数                                                |
| `mean_error_pct`| 平均誤差率（バイアス）                              |
| `mae_pct`       | 絶対誤差率の平均（曜日別の MAPE 的な値）           |

#### (2) 連休内ポジション別サマリー

- 関数：`summarize_by_holiday_position(df)`
- 対象：`holiday_block_len >= 3` かつ `holiday_position != "none"` の行
- 連休内の位置ごとのクセ（「連休初日だけは過小予測になりがち」など）を見る。

#### (3) 祝前日／平日／休日カテゴリ別サマリー

- 関数：`categorize_before_holiday(df)` → `summarize_by_before_holiday_category(df)`
- カテゴリ例：
  - `weekday_before_holiday`：平日かつ祝前日
  - `normal_weekday`：平日かつ祝前日でもない
  - `holiday_or_weekend`：休日 or 週末

---

### 3-4. 評価データの使い分け

- **月次合計ベース（evaluation_〜）**
  - モデル全体のクセ（バイアス / MAPE）をざっくり把握する用途。
  - GUI の悲観 / 基準 / 楽観シナリオ設定の元データ。
- **日別誤差（daily_errors_〜）**
  - 「どの曜日／どのパターンで外しやすいか」を掘るための素材。
  - 副業でのコンサル時には、「現状の運用がどこでブレているか」の説明に使える。
- **セグメント別サマリ（error_summary_〜）**
  - モデルのクセ＋運用のクセ（例：三連休中日の価格設定が甘い）を短時間で把握するための要約ビュー。

---

## 4. 運用・監査（欠損レポート）

daily snapshots を「唯一の正」として運用する前提では、
「そもそも daily snapshots が最新まで揃っているか」「RAW→snapshots 変換が落ちていないか」を
GUI上で安全に検知できる必要がある。

この目的のために、欠損レポート（missing report）を以下2系統で提供する。

- 欠損検査（ops）：日常運用向け（最新〜近未来の取りこぼし検知）
- 欠損監査（audit）：全期間監査向け（歴史的なギャップの検知）

### 4-1. 出力ファイル

- `output/missing_report_<hotel_id>_ops.csv`
- `output/missing_report_<hotel_id>_audit.csv`
- `output/raw_parse_failures_<hotel_id>.csv`（欠損レポートに取り込まれる）
- ops（運用）のみ ACK（確認済み）を持つ：
  - 保存先：`acks/missing_ack_<hotel_id>_ops.csv`（端末ローカル）
  - ops の集計（ERROR/WARN件数）は ACK 済みを除外する（運用ノイズ除去のため）
  - audit（監査）は全体像の保持を優先し、ACK除外しない

### 4-2. CSV列仕様（共通）

missing_report および raw_parse_failures は、以下の列構造を共通で持つ。

| column | 内容 |
|---|---|
| kind | 欠損・異常の種類（例：layout_unknown 等） |
| hotel_id | ホテルID |
| asof_date | ASOF日付（必要な場合のみ） |
| target_month | 対象宿泊月（必要な場合のみ） |
| missing_count | 件数（または 0） |
| missing_sample | サンプル（任意） |
| message | 人間向け説明 |
| path | 対象ファイルのパス（フルパス運用可） |
| severity | `ERROR` / `WARN` / `INFO` |

#### severity の運用方針
- `ERROR`：運用上「見逃すと危ない」もの（STOP相当、未生成、致命的欠損など）
- `WARN`：品質警告（運用は可能だが注意）
- `INFO`：参考情報（集計対象外でもよい）

### 4-3. 欠損検査（ops）の定義（運用）

目的：日々の更新運用で「直近の取りこぼし」を素早く検知する。

- 対象は「最新ASOF近辺」と「直近〜近未来の対象月」に絞る（全期間は見ない）
- 例：ASOF窓（既定：180日）＋ forward_months（既定：3ヶ月）など
- 出力は `missing_report_<hotel_id>_ops.csv`

GUIのマスタ設定タブでは、欠損検査（ops）の結果サマリを表示する。

### 4-4. 欠損監査（audit）の定義（全期間）

目的：データの網羅性を監査する（運用者が「全体の欠損状態」を把握するため）。

- 対象は「stay_month 全域」に広げ、歴史的なギャップも検知する
- 出力は `missing_report_<hotel_id>_audit.csv`

※監査は「運用上の除外（ACK）」を反映しない（全体像を保つため）。

### 4-5. raw_parse_failures（変換失敗ログ）

`raw_parse_failures_<hotel_id>.csv` は、RAW→daily snapshots 変換での失敗（例：layout_unknown）を記録する。
欠損レポート生成時に読み込まれ、missing_report に統合される。

- フルパス運用は許容する（ZIP共有時はダミーパス置換など運用側で対応）

### 4-6. （予定）欠損ACK（確認済み除外）

運用上「欠損が確定しており、毎回アラートに出てほしくない」項目を除外できるようにする。

- ACKは欠損検査（ops）の集計（ERROR/WARN件数）から除外する
- 欠損監査（audit）は除外しない（全体の欠損状態を保持）

ACKの同一性キー（運用の最小要件）：
- `kind + target_month + asof_date + path`
ACK対象：
- `severity in (ERROR, WARN)` のみ

---

この `spec_data_layer.md` は、**「どのデータが、どのファイルに、どの形式で置かれているか」** を整理するための基礎仕様書です。  
新しい指標の追加や評価ロジックの変更を行う場合は、ここで定義したファイル構造との整合性を確認しながら進めてください。
