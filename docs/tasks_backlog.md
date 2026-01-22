# Tasks Backlog

本ファイルは BookingCurveLab プロジェクトのタスク一覧（バックログ）です。  
フェーズ別に `P<phase>-<連番>` のIDを付与し、GitHub Issues などと同期して管理することを想定しています。

- `[ ]` … 未着手
- `[~]` … 着手中
- `[x]` … 完了（Issue Close 済みなど）

---

## Phase 1: LT from daily snapshots への移行

### 目的
- LT_DATA を daily snapshots ベースに統一し、
  「PMS 生データ → daily_snapshots → LT_DATA → 月次/日次ブッキングカーブ」の一貫パイプラインを完成させる。

### タスク

- [x] **P1-01** `lt_builder.py` に `build_lt_data_from_daily_snapshots_for_month(...)` を追加する  
  - daily_snapshots から対象月の `stay_date` を抽出し、`stay_date × lt` テーブルを生成する。
- [x] **P1-02** daily snapshots 読み出し用のヘルパー関数を実装する  
  - `read_daily_snapshots_for_month(hotel_id, target_month)` を追加済み。
- [x] **P1-03** `run_build_lt_csv.py` から snapshots ルートを呼べるようにする  
  - `source` 引数で `timeseries` / `daily_snapshots` を切り替え可能。
- [x] **P1-04** 月次ブッキングカーブを snapshots ルートに対応させる  
  - `build_monthly_curve_from_daily_snapshots_for_month(...)` を追加。
  - v0.6.3 の時系列ルートと数値一致することを確認済み。
- [x] **P1-05** ACT(-1) の定義を整理する  
  - `stay_date < max_as_of_date` のみ ACT を算出（`as_of_date > stay_date` の最初の値）。  
  - それ以外は `NaN` として保持。
- [x] **P1-06** 差分検証結果を仕様に反映する  
  - `spec_data_layer.md` / `spec_overview.md` を snapshots ルート前提に更新。
- [ ] **P1-07** 将来的なデフォルト切り替えのフラグを設計する  
  - 設定ファイル（JSON 等）に `lt_source_default` のようなキーを追加する案を検討。  
  - 現状は GUI から `source` を明示指定する運用で暫定対応。


---
## Phase 1.5: 欠損値 NOCB 補完

### 目的
- LT_DATA に残した「生の NaN」を、
  ビュー / 評価レイヤーで一貫して NOCB 補完できるようにする。
- 欠損の位置と補完範囲を可視化し、どこまで実データかを把握できるようにする。

### タスク

- [x] **P1.5-01** NOCB 補完ヘルパーを実装する  
  - `booking_curve.utils` などに以下の関数を用意：  
    - `apply_nocb_along_lt(df, max_gap=None)`  
      - 行：`stay_date`、列：`lt` を想定。  
      - 各 `stay_date` 行について `lt` 昇順に NOCB を適用。  
      - `max_gap=None` の場合はギャップ無制限で補完。  
      - `max_gap` に数値を指定した場合、そのギャップを超える連続 NaN は補完せず NaN のまま残す。
- [x] **P1.5-02** 日別ブッキングカーブ描画に NOCB を適用する  
  - GUI の日別カーブ描画前に `apply_nocb_along_lt` を適用。  
  - 別途「raw（補完なし）」を選べる設計も検討する。
- [x] **P1.5-03** 月次ブッキングカーブ描画に NOCB を適用する  
  - 月次カーブ用の LT_DATA / monthly_curve 読み込み後に NOCB を適用。  
  - 欠損による折れ線の途切れが消えることを確認。
- [ ] **P1.5-04** 欠損マップの出力機能  
  - `stay_date × lt` の NaN/非 NaN を 0/1 マスクとして CSV または PNG で出力。  
  - どの LT / 宿泊日で実データが存在しないかを一目で確認できるようにする。
- [ ] **P1.5-05** 評価ロジックへの反映  
  - モデル評価に使うデータにも `apply_nocb_along_lt` を適用するかどうかをオプション化。  
  - 「補完あり」「補完なし」で評価値がどう変わるかを比較できるようにする。

---

## Phase 1.6：daily snapshots の部分生成（partial build / upsert）
**狙い:** 初期投入（過去2〜3年の全量）後の週次運用で、処理時間が劣化しない運用導線を作る。

### 1.6.1 要件（仕様）
- Full rebuild（全量再生成）と Partial rebuild（部分生成）の両方を提供する。
- Partial rebuild は「指定ホテル × 指定範囲（例：as_of_date の範囲）」を対象に upsert する。
- 重複排除キーは原則 `(hotel_id, as_of_date, stay_date)` とし、`keep="last"` を採用する。
- daily snapshots 自体は NaN を保持（補完はビュー側）。

### 1.6.2 実装内容（現状）
- `booking_curve/daily_snapshots.py`
  - `build_daily_snapshots_partial(..., as_of_min, as_of_max, ...)` の追加
  - upsert（既存CSVの該当範囲削除 → append → dedupe → save）の共通関数化
- `build_daily_snapshots_from_folder.py`
  - 全量/部分の CLI オプション追加（または別スクリプト）
- GUI
  - 「LT生成時にdaily snapshots更新」を Partial 方式へ切替（範囲は当月〜翌3ヶ月、または直近N日ASOF等）
  - 進捗ログと、処理対象範囲の表示（誤操作防止）
  - FULL_ALL / RANGE_REBUILD が運用可能

### 1.6.3 検証
- 既存 daily_snapshots に対して、同一 as_of_date 範囲を partial 再生成しても値が一致すること
- LT_DATA / monthly_curve の出力が、full と partial で一致すること（少なくとも対象範囲内）

---

## Phase 1.7：欠損レポート（ops）のACK（確認済み除外）＋GUI欠損一覧

### 目的
- 欠損検査（ops）で毎回出る「確定欠損」を運用上 ACK（確認済み）として除外し、
  ops 集計（ERROR/WARN件数）から外せるようにする。
- ただし全体の欠損状態は「欠損監査（audit）」で保持する（auditはACK除外しない）。

### タスク
- [x] **P1.7-01** ACK保存先（CSV）とスキーマを確定する
  - ファイル：`LOCALAPPDATA/BookingCurveLab/acks/missing_ack_<hotel_id>_ops.csv`
  - 同一性キー：`kind + target_month + asof_date + path`
  - 対象：`severity in (ERROR, WARN)` のみ

- [x] **P1.7-02** GUIに欠損一覧（ops）を表示し、行ごとに「確認済」チェックを付けられるようにする
  - 対象は ops のみ（auditはGUI一覧に出さない前提）

- [x] **P1.7-03** ops の集計（ERROR/WARN件数）から ACK を除外する
  - 表示：`ERROR:x / WARN:y` は「未ACK分」の件数にする

- [x] **P1.7-04** 欠損監査（audit）はACKを除外しないことを仕様として固定する

---

## Phase 2: Daily Revenue Forecast（ADRモデル＋ハイブリッド）

### 目的
- OCC 予測（室数）に ADR モデルを掛け合わせ、日別売上予測（Revenue Forecast）を出せるようにする。
- 副業での「診断レポート／助言」の武器にする。

### タスク

- [ ] **P2-01** `daily_snapshots` から ADR / RevPAR 時系列を生成する機能を追加  
  - 入力：`daily_snapshots_<hotel>.csv`  
  - 出力：`stay_date` ごとの `rooms_oh` / `revenue_oh` / `occ` / `adr` / `revpar` を持つ `DataFrame`  
  - 仕様は `spec_data_layer.md` に追記済の内容と整合させる

- [ ] **P2-02** ベースラインADRテーブル生成ロジックを実装する  
  - 集計単位：`year × month × weekday`  
  - ベースライン：直近2〜3年の平均（初期実装）  
  - 将来の「類似年選択」に備えて、インターフェイスは拡張しやすい形にしておく

- [ ] **P2-03** インフレ調整ロジックを実装する  
  - 直近3〜6ヶ月の ADR 実績から「今年の水準へのスケール係数」を推定  
  - ベースラインADRに掛けて「今年の期待水準ADR」を算出

- [ ] **P2-04** 短期トレンド調整ロジックを実装する  
  - 直近7〜14日間の ADR / RevPAR の移動平均と、ベースラインとの差を算出  
  - 過度な振れ幅にならないようクリッピング処理を含める

- [ ] **P2-05** RevPARマクロとの整合チェック処理を実装する  
  - 月別RevPAR フロー（前年対比など）と、日別売上予測の合計を比較  
  - 明らかに高すぎ／低すぎる場合の補正係数ロジックを設計

- [ ] **P2-06** OCC予測とADRモデルを組み合わせる関数を実装する  
  - 引数：OCC予測（`rooms_forecast`）と ADR モデルの予測値  
  - 出力：日別売上予測 `revenue_forecast`  
  - 月次・日次の評価用データへの書き込みも行う

- [ ] **P2-07** 評価タブに売上指標を追加する  
  - 月次評価に「売上ベースの MAPE / バイアス」などを追加  
  - GUI の表示変更が必要な場合は `spec_evaluation.md` にも反映

- [ ] **P2-08** `spec_models.md` に ADRモデルの確定仕様を反映する  
  - ベースライン／インフレ／短期トレンド／マクロ調整の実装内容を更新  
  - 「案」から「実装仕様」に格上げする

---

## Phase 2.x: 安定化（Phase3着手前のバグ修正）

### 目的
- Phase3へ進む前に「予測が回る」「落ちない」「表示が正しい」を満たす。

### タスク
- [ ] **P2.x-01** recent90系：calendar_features CSV欠損時にエラーにせずフォールバックする
  - 対象：`src/booking_curve/segment_adjustment.py`（`_load_calendar`）
  - 期待：calendar_features が無い場合でも forecast を継続（adjustmentは無効化/係数=1.0）
  - 欠損レポート（ops）に WARN で理由を残す（可能なら）

- [ ] **P2.x-02** LT_ALL：一部月の失敗で全体停止しない（スキップ＋失敗ログ化）
  - 対象：`src/run_build_lt_csv.py` / `src/booking_curve/gui_backend.py`
  - 期待：LT_ALL 実行で「失敗月一覧」を残し、成功分は出力される
  - 仕様リンク：`spec_data_layer.md` の Raw Parse Failures / missing ops の扱いに整合

- [ ] **P2.x-03** TopDownRevPAR：月次RevPAR算出が forecast と一致することを保証（ズレ原因の特定＋修正）
  - 対象：`src/booking_curve/gui_backend.py`（`_get_projected_monthly_revpar`, `build_topdown_revpar_panel`）
  - 期待：同一 as_of / 同一モデルで、TopDown表示のRevPARが「forecast_revenue合計÷(cap×days)」と一致
  - 追加：不一致時に診断情報（対象CSV名・集計ロジック・日付欠損有無）を表示/ログに残す

---

## Phase 3: ペース比較＋料金レコメンド（Decision Support）

### 目的
- ペース（net pickup）の良し悪しを定量化し、
  「レートを上げても良い／下げるべき」の判断材料を提示する。

### タスク

- [ ] **P3-01** ベンチマークASOFの選択ロジックを設計する  
  - 候補：`M-2_END` / `M-1_END` / 「1週間前のASOF」など  
  - 評価タブのASOFと整合が取れる仕様にする

- [ ] **P3-02** ペース指標（net pickup）の定義と計算ロジックを実装する  
  - 期間例：直近7日間の `net pickup`（予約−取消）  
  - 指標例：稼働率ベース／売上ベースの両方を検討

- [ ] **P3-03** 外れ値（大口キャンセル等）の除外ロジックを設計・実装  
  - 一定室数以上のキャンセルを「特異イベント」とみなす  
  - ペース評価に含める／含めない条件を明文化し、`spec_evaluation.md` に追記

- [ ] **P3-04** レートアクションのルールベースロジックを実装する  
  - 例：
    - ペースが基準より +X% 以上 → ADR を Y% まで上げてもよいゾーン  
    - ペースが基準より −X% 以上 → ADR を Z% まで下げる推奨  
  - 初期実装は if文ベースの単純ルールで良い

- [ ] **P3-05** レコメンド出力フォーマットを設計する  
  - 出力例：
    - 「ペース良好：+15%。来週末はADR+1,000円まで許容」  
    - 「ペース弱い：-10%。平日の連泊プラン割引を検討」  
  - GUI or CSV 出力として、人間が読める形で出す

- [ ] **P3-06** GUIへの組み込み（将来）  
  - ブッキングカーブタブ、もしくは日別FCタブに「ペース評価＋レコメンド」の表示枠を追加  
  - 表示に必要な追加項目があれば `spec_overview.md` / `spec_models.md` を更新

---

## Phase 4: 評価ロジックのアップデート（バイアス補正＋日別評価）

### 目的
- 「どのモデルが使えるか」「どこまで攻めて良いか」を、
  月次だけでなく日次の誤差も含めて説明できるようにする。

### タスク

- [ ] **P4-01** 月別バイアスの集計・可視化ロジックを実装する  
  - 直近12ヶ月程度の月次バイアス（MPE）を算出  
  - 「+3%出がち」「−2%守りがち」などのクセを一覧化

- [ ] **P4-02** バイアス補正を基準値に反映する仕組みを設計  
  - 基準シナリオ（基準値）に月別のバイアスを加味するかどうかを選択可能にする  
  - 評価タブや設定で ON/OFF できるようにする

- [ ] **P4-03** 日別評価指標（MAPE, RMSE 等）を追加する  
  - `evaluation_daily_errors.csv` の仕様を確定  
  - モデル別・日別での誤差を可視化できるようにする

- [ ] **P4-04** `spec_evaluation.md` に日別評価の仕様を追記  
  - 月次・日次それぞれにどの指標を使うか  
  - 「月次では良いが日次では荒いモデル」などの典型パターンを想定しておく

- [ ] **P4-05** GUI側に日別評価のサマリを表示する  
  - 例：評価タブに「日別MAPEの箱ひげ」や簡易統計を追加  
  - UIの変更があれば `BookingCurveLab_README.txt` も更新

---

## Phase 5: 周辺機能（報告書・ウェイトマスタ・カレンダー）

### 目的
- ツールを「現場で使い倒せる」状態にし、副業での再利用もしやすくする。

### タスク

- [ ] **P5-01** 会議用資料（PPTX/画像）自動出力のテンプレートを設計  
  - 月次ブッキングカーブ＋RevPARサマリ＋MAPE/バイアスを1枚〜数枚にまとめる  
  - フォーマット案を `docs/` にサンプルとして保存

- [ ] **P5-02** PowerPoint 自動出力スクリプトを追加  
  - matplotlib で生成したグラフを画像化 → PPTXに貼り付け  
  - 副業用の「診断レポートひな形」との兼用を想定

- [ ] **P5-03** `recent90w` ウェイトマスタの設計  
  - 設定ファイル（JSON等）にウェイトパターンを定義  
  - ホテル別、シナリオ別に切り替え可能な構造にする

- [ ] **P5-04** `recent90w` ウェイトの読み込み／適用ロジックを実装  
  - `forecast_simple.py` で設定値を読み込み  
  - 評価タブからパターンを選べるようなUI設計も検討

- [ ] **P5-05** 評価用カレンダー生成の自動化  
  - LTレンジ・ASOFレンジに応じた「評価期間カレンダー」を自動生成  
  - 人手での期間設定を最小限にする

---

## Phase 6: 副業ビジネスへのブリッジ

### 目的
- BookingCurveLab の機能群を活かし、  
  「診断レポート＋運用支援」という副業パッケージに落とし込む。

### タスク

- [ ] **P6-01** 副業パッケージの提供価値を整理する  
  - 約束すること（ボトルネック診断／レート戦略の理屈／運用改善支援）  
  - あくまで目安とするもの（売上予測の絶対値）を文章化

- [ ] **P6-02** 診断レポートの標準フォーマットを設計する  
  - 1ホテル用のA4数枚程度のテンプレ  
  - BookingCurveLab の出力（グラフ／指標）をどこに配置するかを決める

- [ ] **P6-03** 診断レポート自動生成との連携仕様を検討  
  - Phase5 で作成した PPTX ひな形との連携  
  - Pythonスクリプトでの自動生成フローを設計

- [ ] **P6-04** 導入〜運用の「サービスフロー」を文書化  
  - 初回ヒアリング → データ受領 → モデル構築 → 診断レポート → 定期フォロー  
  - 料金レンジやスコープも仮決めしておく

- [ ] **P6-05** Webサイト／提案資料向けの説明文を準備  
  - 「何ができるツールか」「どこまで約束するか」を、非エンジニア向けに整理  
  - 将来的にLPや営業資料に転用する前提で書く

---

## 直近タスク（現実追従）

### P0
- hotels.json（raw_root_dir / adapter_type / include_subfolders）を唯一の正にし、config.py の派生値 input_dir をそこから生成する
- RawInventory の探索範囲・ヘルス判定が hotels.json と常に一致することを保証する
- N@FACE アダプタを「宿泊日=A列のみ」「1行/2行持ちのみ」に固定し、判定不能はSTOPにする（誤取り込み防止）

### P1
- Partial build 運用（missing_report ops の raw_missing を入力に daily_snapshots を upsert）を運用導線として完成させる（Phase 1.6）
- 変換/欠損ログを棚卸しCSV（ingestion_issues_{hotel}.csv）として出力し、整理対象を可視化する

### P2
- 欠損検知の2モード（ops/audit）と “NaN保持・補完はGUI表示直前のみ” を docs に明記して迷いを減らす

---
