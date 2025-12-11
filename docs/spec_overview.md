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

これらは「外部仕様」として扱い、互換性を壊す変更は行わない方針です。

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
  - 既存実装（`booking_curve/forecast_simple.py`, `booking_curve/evaluation_multi.py` 等）に揃える。

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

ここでは、フォルダ構成と役割、バージョンごとの主な変更点をまとめます。

### 4-1. フォルダ構成と役割（概要）

`BookingCurveLab/`（EXE 配布版）および `src/`（開発版）を含む構造は概ね以下のとおりです。

- `BookingCurveLab.exe`
  - GUI アプリ本体（一般ユーザーはこれのみ利用）。
- `config/`
  - `hotels.json`：ホテルごとの設定（表示名・データサブフォルダ・キャパシティ等）。
- `data/`
  - PMS から出力した **時系列オンハンド Excel** や、生の PMS データ置き場。
  - サブフォルダは `config/hotels.json` の `data_subdir` と対応。
- `output/`
  - `lt_data_YYYYMM_<hotel>.csv`：LTデータ
  - `monthly_curve_YYYYMM_<hotel>.csv`：月次ブッキングカーブ
  - `forecast_*.csv`：日別フォーキャスト
  - `evaluation_*.csv`：モデル評価結果
  - `daily_snapshots_<hotel>.csv`：標準日別スナップショット（開発版で追加）
- `booking_curve/`（開発版）
  - LT構築：`lt_builder.py`
  - 予測モデル：`forecast_simple.py`
  - 評価ロジック：`evaluation_multi.py`
  - セグメント調整：`segment_adjustment.py`
  - GUI バックエンド：`gui_backend.py`
  - その他共通ユーティリティ
- `gui_main.py`（開発版）
  - Tkinter ベースの GUI エントリーポイント。
- `run_*.py`（開発版）
  - CLI ランナー（LT生成・評価バッチ・日別FCバッチなど）。
  - 可能な限り `booking_curve/` モジュールを呼び出す薄いラッパーとして実装する方針。

### 4-2. バージョン別の主な変更点

#### v0.6.3

- 月次ブッキングカーブ生成ロジックを刷新。
  - PMS 時系列 OH データから **列合計を直接集計**し、
  - `monthly_curve_YYYYMM_<hotel>.csv` を出力。
  - GUI「月次カーブ」タブはこの CSV を優先して使用。
- 宿泊月合計とグラフ最終値の不整合を解消。

#### v0.6.4

- 標準日別スナップショットレイヤーを導入（インフラフェーズ）。
  - `daily_snapshots_<hotel>.csv` を定義。
  - `pms_adapter_nface.py`・`daily_snapshots.py`・`build_daily_snapshots_from_folder.py` を追加。
- 既存 LT 生成・GUI・評価ロジックにはまだ直接手を入れておらず、
  - 今後のバージョンで「LT_DATA を daily snapshots ベースへ移行」する前段階。

#### 今後の予定（概要）

- `feature/lt-from-daily-snapshots`：
  - daily snapshots から LT_DATA を生成する新ルートを追加。
- その後のフェーズ：
  - ADR モデルを組み込んだ日別売上予測
  - ペース比較＋料金レコメンド
  - 評価ロジックのアップデート（バイアス補正・日別評価）
  - 会議用レポート出力、recent90w ウェイトマスタ化 等

---

今後、機能追加や外部仕様の変更が入る際には、以下のルールでドキュメントを更新する。

- 新しいデータレイヤや中間ファイルを追加した場合：
  - `spec_data_layer.md` と本書（`spec_overview.md`）を両方更新する。
- モデルロジック（avg / recent90 / recent90w 等）の定義を変更した場合：
  - `spec_models.md`（将来追加）と本書を更新する。

役割の整理：

- 利用者向けの操作説明・FAQ：`BookingCurveLab_README.txt`
- 開発者・AI エージェント向けの運用ルール：`AGENTS.md`
- 仕様の上位整理：本書 `spec_overview.md`
- データ構造の詳細：`spec_data_layer.md`

