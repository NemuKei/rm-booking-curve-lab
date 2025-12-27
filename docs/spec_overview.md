# BookingCurveLab 仕様概要（spec_overview）

この文書は、`rm-booking-curve-lab` リポジトリ全体の仕様を上位レベルで整理したものです。  
詳細な利用方法は `BookingCurveLab_README.txt` を、AI エージェント向け運用ルールは `AGENTS.md` を参照してください。

---

## 1. 目的

BookingCurveLab の主目的は、ホテルの PMS から取得したオンハンド（OH）データとリードタイム（LT）データを用いて、

- **日別・月次ブッキングカーブの可視化**
- **複数モデル（avg / recent90 / recent90w / recent90_adj 等）による簡易フォーキャスト**
- **MAE / MAPE / バイアス / RMSE / MPE などによるモデル精度評価**
- **悲観 / 基準 / 楽観シナリオの算出と比較**

を、GUI（Tkinter）および CLI スクリプトから一貫して行えるようにすることです。

加えて、将来的に以下を満たす「共通エンジン」として機能することを狙います。

- 複数ホテル・複数モデルを横断的に扱える拡張性
- 標準化された CSV（縦持ち）や LT_DATA を、他ツールからも再利用できること
- GUI と CLI が同じモジュール群（`booking_curve/` 配下）を共有し、運用を一本化できること

---

## 2. 対象ホテル・データソース

### 2-1. 対象ホテル

ホテル情報は `config/hotels.json` で一元管理し、少なくとも以下のホテルを想定しています。

- `daikokucho`：なんば大国町
- `kansai`：ホテル関西  
  （将来的には `domemae` など他拠点追加も前提）

各ホテルについて、以下の情報を保持します。

- `display_name`：GUI に表示する名称
- `data_subdir`：PMS 時系列データや生データを置くサブフォルダ
- `capacity`：理論最大稼働室数
- `forecast_cap`：予測時に上限として用いる稼働室数（安全マージン込み）
- `raw_root_dir`：RAW Excel の取り込み元フォルダ（唯一の正）
- `include_subfolders`：サブフォルダも探索対象にするか
- `adapter_type`：PMSアダプタ種別（現状は nface）

これらは「外部仕様」として扱い、互換性を壊す変更は行わない方針です。
hotels.json が欠けている／必須キー不足の場合は 安全側に STOP し、推測で続行しない

### 2-2. データソースと中間生成物

#### (1) PMS 生データ

- 各 PMS からエクスポートされた OH データ（N@FACE など）
- ASOF × 月ごとに 1 ファイルを想定（例：`202512_20251208.xlsx`）
- 宿泊日・室数・人数・室料などを含む
- フォーマットは PMS により異なるため、**PMS アダプタ層**で標準化します。

#### (2) 標準日別スナップショット CSV（daily snapshots）

PMS 生データを正規化し、ホテル共通で扱える形として定義する「唯一の正」のデータレイヤーです。

- ファイル例：`output/daily_snapshots_daikokucho.csv`
- 主なカラム：
  - `hotel_id`（例：`daikokucho`）
  - `as_of_date`（取得日、`YYYY-MM-DD`）
  - `stay_date`（宿泊日、`YYYY-MM-DD`）
  - `rooms_oh`（オンハンド室数）
  - `pax_oh`（オンハンド人数）
  - `revenue_oh`（オンハンド宿泊売上）

この標準CSVから、LT_DATA や月次カーブ、ADR / RevPAR 時系列などを再構成する方針です。

#### (3) LT データ（LT_DATA CSV）

- ファイル例：`output/lt_data_YYYYMM_<hotel>.csv`
- 内容：宿泊月 × LT（-1 = ACT, 0〜max_lt）の **Rooms 数推移**
- 生成元：
  - 現行：PMS 時系列オンハンド Excel
  - 今後：標準日別スナップショット CSV から生成するルートに移行予定
- ブッキングカーブ描画・モデル評価・日別フォーキャストの中核となるデータ。

#### (4) 月次ブッキングカーブ CSV（monthly_curve）

- ファイル例：`output/monthly_curve_YYYYMM_<hotel>.csv`
- 内容：ASOF × 宿泊月の「月次合計 Rooms vs LT カーブ」
- v0.6.3 以降、**時系列 OH データの列合計から直接集計**する方式に刷新済み。
- GUI の「月次カーブ」タブは、この CSV を優先的に読み込みます。

#### (5) モデル評価・フォーキャスト CSV

- `evaluation_<hotel>_*.csv`：モデル評価結果（MAE / MAPE / Bias / RMSE / MPE など）
- `forecast_*.csv`：日別フォーキャスト結果（OCC / ADR / RevPAR 等）
- これらは GUI の「モデル評価」タブ・「日別フォーキャスト」タブで利用されます。

---

## 3. 前提

### 3-1. 技術的前提

- 実装言語：**Python**（3 系、開発環境は 3.11 想定）
- GUI フレームワーク：**Tkinter**（他フレームワークへの置き換えは禁止）
- 一般ユーザー向け配布形態：
  - `BookingCurveLab.exe`（pyinstaller でビルド）として Windows 10 / 11 上で動作
  - EXE 利用者には Python は不要
- 管理者・開発者：
  - Python 実行環境＋必要ライブラリを整備し、CLI スクリプトやモジュールを直接実行・編集できる前提

### 3-2. データ仕様・外部仕様に関する前提

- `booking_curve/` 配下は **共通ロジックのモジュール** として設計されており、GUI・CLI 両方から利用されます。
  - 既存の関数シグネチャ（引数・戻り値）は、できる限り互換性を維持する。
- 標準CSV（daily snapshots）や LT_DATA CSV の列構成・意味は **外部仕様** として扱い、
  - 列名・型・意味を理由なく変更しない。
  - 変更が必要な場合は、新列追加やマイグレーションを明示する。
- ASOF / ACT の扱い：
  - ASOF より先の日付について、実績（ACT）が存在しないのに「埋まっているように見える」挙動は禁止。
  - グラフ上の ACT は ASOF 時点までで止まること。
- モデルロジック（avg / recent90 / recent90w 等）・評価ロジック（MAE / MAPE / Bias / RMSE / MPE 等）は、
  - 既存実装（`booking_curve/forecast_simple.py`, `run_full_evaluation.py` 等）に揃える。

### 3-3. 運用・ユーザーロール

- 想定ユーザー：
  - ホテルのレベニューマネージャー／支配人／予約担当
- 利用シーン：
  - 日々のブッキングカーブ確認
  - 月次会議での進捗・シナリオ確認
  - モデル精度の定期レビューと、最適モデルの選択
- 役割分担：
  - 一般ユーザー：
    - EXE 起動、GUI 操作（タブ切替・描画ボタン・条件指定など）
  - 管理者・開発者：
    - PMS データの投入・前処理
    - LT_DATA / monthly_curve / 評価 CSV 再生成
    - 新機能実装・モデル追加・バグ修正

---

## 4. 現在のバージョン構成

### 4-1. バージョン一覧

#### v0.6.3

- 対象ホテルは大国町・関西・ドーム前の 3 館。
- LT_DATA 生成はすべて「時系列 Excel ベース」。
  - `data/timeseries/<hotel>/` 配下の「日別オンハンド推移」Excel を読み取り、
    `build_lt_data_from_timeseries_for_month(...)` で LT_DATA を生成。
- 月次ブッキングカーブも、同じ時系列 Excel から直接集計して作成。
- GUI から見た挙動：
  - 日別カーブ / 月次カーブともに「時系列 Excel を唯一のソース」として動作。

#### v0.6.4（`feature/standard-daily-snapshots` マージ後）

- PMS（N@FACE）生データを「標準日別スナップショット CSV」に正規化するレイヤーを追加。
  - `build_daily_snapshots_from_folder.py`
  - `pms_adapter_nface.py`
  - `daily_snapshots.py`
- 出力される標準 CSV：
  - `daily_snapshots_<hotel_id>.csv`
  - カラム：`hotel_id`, `as_of_date`, `stay_date`, `rooms_oh`, `pax_oh`, `revenue_oh`
- この時点では **LT_DATA / 月次カーブは依然として時系列 Excel ベース**。
  - 標準スナップショットは「あくまで次フェーズ用のインフラ」。

#### v0.6.5（`feature/lt-from-daily-snapshots` マージ後）

- **LT_DATA を daily_snapshots ベースで生成できるルートを追加。**
  - `booking_curve.lt_builder.build_lt_data_from_daily_snapshots_for_month(...)`
  - `run_build_lt_csv.py` の `run_build_lt_for_gui(...)` に `source` 引数を追加。
    - `source="timeseries"` … 既存の Excel ベース
    - `source="daily_snapshots"` … 新しい snapshots ベース
- **月次ブッキングカーブも daily_snapshots ベースに対応。**
  - `build_monthly_curve_from_daily_snapshots_for_month(...)` を追加。
  - ASOF ごとの月累計を算出し、LT 軸（120〜0, ACT）に並べ替える挙動は、
    v0.6.3 の時系列ルートと数値一致することを確認済み。
- **ACT(-1) の定義を整理。**
  - `stay_date < max_as_of_date` のとき：
    - 最初の `as_of_date > stay_date` の月累計を ACT(-1) として採用。
      - 例）`stay_date=12/8` に対して、`as_of_date=12/9` のスナップショットが ACT。
  - `stay_date >= max_as_of_date` のとき：
    - ACT(-1) は `NaN` のまま保持（未着地）。
- 互換性：
  - LT_DATA の列構造（`lt=-1,0,1,...,120`）と CSV 形式は従来と互換。
  - 月次カーブ CSV も、ファイル名・形式とも従来の `monthly_curve_YYYYMM_<hotel>.csv` を踏襲。
- GUI から見た挙動：
  - 現状は **LT_DATA / 月次カーブの生成ルートが切り替え可能になった段階**。
  - 欠損値の補完（NOCB）はまだ実装しておらず、生の NaN がそのままグラフに反映される。
    → これは次フェーズ（欠損 NOCB ブランチ）で対応する。

#### v0.6.6（`feature/missing-values-nocb` マージ後）

- **欠損値補完ポリシーを整理（データレイヤーは生の NaN を保持）。**
  - daily snapshots / LT_DATA / monthly_curve は **生の NaN を保持**する。
  - グラフ描画・評価で参照する「ビュー用 DataFrame」に対して、LT方向の補完を適用する。
    - 実装上は「LTが若い方向へ進む」ことを時系列とみなし、**LOCF（Carry Forward）** を採用。
    - `LT=-1 (ACT)` を `LT=0` から埋めるような補完は行わない（軸の並びと意味に反するため）。

- **日別フォーキャストタブの表示仕様をハイブリッド化。**
  - `Actual`：着地済み日の ACT（最終実績）を表示（未着地は NaN / 空欄）。
  - `ASOF_OH`：指定ASOF時点の OH を表示（着地済み日も「その時点の月累計」として値を持つ）。
  - `Forecast`：指定ASOFを起点にモデルで算出した予測値。
  - これにより、
    - 「予測 vs 最終着地（検証用途）」
    - 「予測時点のOH（当時の前提）と、その後の伸び」
    の両方を同一画面で確認できる。

- **GUI から LT_DATA / monthly_curve を生成できる導線を整備。**
  - `LTソース`（timeseries / daily_snapshots）を選択可能。
  - `daily_snapshots` をソースにする場合、LT生成時に snapshots 更新を任意で実行できる。
  - `timeseries` 選択時は snapshots 更新オプションを無効化（不要な処理時間を発生させない）。

#### v0.6.7（`feature/daily-snapshots-partial-build` 開発中）

- daily snapshots の部分生成（RANGE_REBUILD 等）の運用安定化。
- RAW（N@FACE）現場加工パターン差への対応強化（誤取り込み防止、STOP条件の明確化）。
- 欠損検査（ops）/ 欠損監査（audit）による運用警告の整理（マスタ設定タブ）。
- 欠損検査（ops）のACK（確認済み除外）＋GUI欠損一覧（opsのみ）を同ブランチで完走する方針。
  - 同一性キー：`kind + target_month + asof_date + path`
  - 対象：`severity in (ERROR, WARN)`
  - audit は全体像のためACK除外しない


#### 今後の予定（概要）

- その後のフェーズ：
  - ADR モデルを組み込んだ日別売上予測
  - ペース比較＋料金レコメンド
  - 評価ロジックのアップデート（バイアス補正・日別評価）
  - 会議用レポート出力、recent90w ウェイトマスタ化 等

---

今後、機能追加や外部仕様の変更が入る際には、以下のルールでドキュメントを更新する。

- 仕様の唯一の正（外部仕様・ロジック定義）：
  - `docs/spec_overview.md`
  - `docs/spec_data_layer.md`
  - `docs/spec_models.md`
  - `docs/spec_evaluation.md`
- AI運用ルールの唯一の正：
  - `AGENTS.md`
- 計画（実装状況と混同しない）：
  - `docs/roadmap.md`
  - `docs/tasks_backlog.md`


