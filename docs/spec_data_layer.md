# データレイヤ仕様（spec_data_layer）

このドキュメントは、`rm-booking-curve-lab` における **データ構造とファイル仕様** を整理したものです。  
特に以下の 3 レイヤーを対象とします。

1. `daily snapshots`（標準日別スナップショット）
2. `LT_DATA`（宿泊日×LT テーブル＋月次カーブ）
3. 評価用データ（モデル精度評価・日別誤差・セグメント別要約）

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

### 1-4. N@FACE アダプタとの関係（参考）

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

LT_DATA は、**宿泊日×LT（Lead Time）** のブッキングカーブを表現する中核データです。  
主な利用先：

- GUI の日別ブッキングカーブタブ
- モデル評価（各モデルの月次 Forecast 元）
- 日別 Forecast の Rooms 部分（将来の売上予測のベース）

現状は「PMS 時系列 Excel → `lt_builder.build_lt_data()`」のルートが稼働中。  
今後は「daily snapshots → LT_DATA」のルートを追加し、徐々に移行していく想定です。

---

### 2-2. LT_DATA テーブル仕様

- ファイル例：`output/lt_data_YYYYMM_<hotel>.csv`
  - 例：`lt_data_202512_daikokucho.csv`
- インデックス：`stay_date`（宿泊日）
  - 文字列 or 日付文字列だが、読み込み側では `pd.to_datetime` で扱う前提。
- 列：LT 値（整数）  
  - 範囲：`-1, 0, 1, ..., max_lt`
    - `-1`：ACT（最終実績）
    - `0..max_lt`：宿泊日から見たリードタイム日数
  - 実装上の並び：
    - 内部処理中は `-1..max_lt` 昇順で補間を行い、
    - 最終的な出力は `max_lt..-1` の降順（`lt_desc_columns`）に並び替えて保存。

#### セルの意味

`lt_data[stay_date][lt]`：

- `lt >= 0`：  
  「**LT = lt の時点での ON HAND 室数**」
- `lt = -1`：  
  「**実績最終値（ACT）**」。  
  ASOF を越えた未来 LT に実績が入ることはない。

#### 欠損と補間

`lt_builder.build_lt_data()` のロジック（要約）：

1. 原データ（宿泊日×取得日）から、`stay_date`, `lt`, `rooms` のレコードを生成。
2. `pivot_table(index="stay_date", columns="lt", values="rooms", aggfunc="last")`。
3. 全 LT を `-1..max_lt` で reindex（欠損は NaN）。
4. 横方向（LT 方向）に `interpolate(limit_direction="both")` で補間。
   - **行全体が NaN の場合は補間しない**（その宿泊日は警告ログ）。
5. 四捨五入して `Int64` 型にキャスト。
6. 列を `max_lt..-1` の降順で並べ替えた DataFrame を返す。

※ 同一 (stay_date, lt) に複数レコードがある場合は、aggfunc="last" で「後から生成された値」を優先する（PMS再出力などの再取り込みを想定）。

このため：

- **観測されていない LT の値は、同一宿泊日の他 LT から補間**される。
- ただし、データが 1 つもない宿泊日は全 LT が NaN のまま。

---

### 2-3. LT_DATA の生成ルート

#### (1) 時系列 Excel から

- 前提フォーマット：
  - 1 行目：各列の取得日（Excel シリアル）
  - 1 列目：各行の宿泊日（Excel シリアル or 日付）
  - 2 行目以降：OH 室数
- フロー：
  1. `load_time_series_excel()`（仮）で DataFrame に読み込み。
  2. 対象宿泊月だけをフィルタ。
  3. `lt_builder.build_lt_data(df, max_lt)` を実行。
  4. `lt_data_YYYYMM_<hotel>.csv` として書き出し。

（CLI 実行は `run_build_lt_csv.py` 相当のスクリプトが担当）

#### (2) daily snapshots から（今後）

- フロー（想定）：
  1. `read_daily_snapshots_for_month(hotel_id, target_month)` で対象月の `(as_of, stay_date)` 行を取得。
  2. `lt = (stay_date - as_of_date).days` を計算。
     - `lt < 0` の場合は `-1` にまとめる（ACT 相当）。
     - `lt > max_lt` は無視。
  3. `(stay_date, lt)` ごとに `rooms_oh` を集計（通常は `last` or `sum`）。
  4. `build_lt_data` 同様に pivot → 補間 → 四捨五入 → DataFrame。
  5. 既存の LT_DATA と同じフォーマットで `lt_data_YYYYMM_<hotel>.csv` を出力。

→ これにより、「どの PMS でも daily snapshots さえ作れば LT_DATA が再生成できる」状態を目指す。

---

### 2-4. 月次ブッキングカーブ（monthly_curve）

LT_DATA と並ぶ、もう一つの重要な LT 系データが **月次ブッキングカーブ** です。  
これは「宿泊月トータルの Rooms を LT ごとに集計したカーブ」です。

- ファイル例：`output/monthly_curve_YYYYMM_<hotel>.csv`
- インデックス：`lt`（整数、max_lt..-1 の降順）
- 列：
  - `rooms_total`：当該 LT 時点での宿泊月累計 Rooms

`lt_builder.build_monthly_curve_from_timeseries()`（現行）は、  
**PMS 時系列 Excel の「列合計」をベースに** 以下を行います：

1. 各取得日列について、対象宿泊月の OH 室数を列合計。
2. 取得日から見た **月末までの残日数** を LT として計算。
   - `lt < 0` は `-1`（ACT）として扱う。
   - `lt > max_lt` は無視。
3. LT ごとに `rooms_total` を加算。
4. `lt` 降順の DataFrame（1 列）として返却。

GUI の月次カーブタブは、この `monthly_curve_YYYYMM_<hotel>.csv` を優先的に読み込み、  
最終値が宿泊月合計と一致することを保証しています。

（現状は時系列Excelをソースとするが、将来的には daily snapshots からも同等の monthly_curve を生成できるように設計する。）

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

この `spec_data_layer.md` は、**「どのデータが、どのファイルに、どの形式で置かれているか」** を整理するための基礎仕様書です。  
新しい指標の追加や評価ロジックの変更を行う場合は、ここで定義したファイル構造との整合性を確認しながら進めてください。
