Proposed file path: docs/handovers/2026-01-30_1344_feature_output-hotel-dir_topdown-band-mad__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、出力先をホテル別ディレクトリへ整理し、TopDownRevPARの帯（A/C）をdelta+MAD外れ値除外+min/maxへ変更して違和感を解消した作業ログです。
- 次スレッドでは、TopDownのGUI表現（p10–p90表記の撤去/名称整理）を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- output配下の生成物がホテル別ディレクトリに分かれるよう整理（混在を解消）
  - 主要変更ファイル：`src/gui_main.py`, `src/booking_curve/gui_backend.py`（ほか出力スクリプト群）
- TopDownRevPARの帯（A/C）が 12→1 付近で暴れる問題について、帯定義を「傾き（delta）レンジ」に寄せて改善
  - 年度サンプル n>=5 のときのみ MAD で外れ値除外し、残りの min/max を帯に採用
  - abs guard（絶対値クランプ）を撤去
  - notes に `(A:mad=k/n)(A:mad_rm=x)` / `(C:mad=...)` を付与
  - 主要変更ファイル：`src/booking_curve/gui_backend.py`
- マスタ設定の「出力先フォルダ」表示がホテル切替で更新されない件は動作OKを確認

### 未完（残課題）
- TopDownの表示・命名が「p10–p90」のまま（ロジックはmin/maxレンジになったため誤解余地あり）
- コード内の変数名が旧来（ratio命名）で残存（機能影響なし、可読性のみ）

---

## 3. 決定事項（仕様として合意したこと）
- TopDownRevPARの帯（A/C）は「ストック（比率）よりフロー（傾き）」を表現する方向とし、deltaレンジ（外れ値除外後min/max）で出す
- 年度サンプルが少ない前提で、外れ値は MAD により「明らかな外れ」だけ落とす（n>=5で適用、n<5はスキップ）
- abs guard（絶対値クランプ）は副作用が大きいため外す方向

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：TopDownのp10–p90表記が残っている（実態はmin/maxレンジ）
- 再現条件：TopDownRevPAR画面を開く（帯チェックや凡例、診断テーブル列名）
- 影響範囲：ユーザーが「分位点」と誤解する可能性
- 暫定回避策：notesにMAD適用状況が出るため、当面はそこを見て判断
- 備考：次スレッドでUI/列名/凡例/内部キーを整理

### 課題2：TopDown帯算出部の命名（ratio_* / last_ratio_band等）が旧来のまま
- 再現条件：コードリーディング時
- 影響範囲：可読性のみ（挙動には影響なし）
- 暫定回避策：なし（後回しでOK）
- 備考：リネームのみの安全なリファクタとしてP2扱い

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. TopDownの表現を「p10–p90」から「range（min–max）」へ名称整理（GUI文言・凡例・表ヘッダ）
   - 完了条件：TopDown画面内に「p10–p90」の誤解を招く表記が残らない（A/Cとも）

### P1（次）
2. bandキー/列名の互換方針を決める（`band_p10`等を維持するか、`band_low/high`へ移行するか）
   - 完了条件：コード上の命名方針が決まり、必要最小限の変更で一貫する

### P2（余裕があれば）
3. TopDown帯算出の変数名リネーム（ratio→delta 等）
   - 完了条件：機能変更なしで可読性が改善し、既存テスト/動作確認が通る

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `AGENTS.md`：運用ルール（唯一の正、テンプレ準拠、推測禁止など）
- `docs/spec_*.md`：仕様の唯一の正（TopDownの仕様が未記載なら追記先の候補）
- `src/booking_curve/gui_backend.py`：TopDown帯（A/C）の算出ロジック（delta+MAD+min/max）
- `src/gui_main.py`：TopDown画面の文言/凡例/表ヘッダ（p10–p90表記の残存箇所）
- `make_release_zip.py` / `VERSION.txt`：ZIP作成とメタ情報

---

## 7. 実行コマンド／手順（分かっている範囲で）
- 起動：`python src/gui_main.py`
- ログ：`%LOCALAPPDATA%\\BookingCurveLab\\output\\logs\\gui_app.log`
- source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260130_1344_samp_feature-output_hotel_dir_reset_5b0597f_full.zip`
- anchor_zip（次スレで添付するアンカーZIP）：`rm-booking-curve-lab_20260130_1344_samp_feature-output_hotel_dir_reset_5b0597f_full.zip`

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. この引き継ぎ（正本）を読んだ
3. TopDown画面でA/C帯が意図どおりのレンジになっている（12→1が暴れない）
4. p10–p90表記が残っている箇所を洗い出せる（GUI/凡例/表/コード）
5. Docs Gate 判定（必要なら）を実施

---

## 10. 質問（最大5つ・必要なもののみ）
1. TopDownの列名変更（A:p10→A:low等）は、CSV/他機能との互換性を優先して段階的に進める方針でOK？
2. 「帯」の公式名称は `range(min–max)` / `傾きレンジ` / `low–high` のどれを採用する？
