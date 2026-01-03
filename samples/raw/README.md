# RAW Fixture Samples (nface) — README

このフォルダは、PMS RAW（Excel）→ daily snapshots / LT_DATA 変換の **回帰テスト用 fixture** を置く場所です。  
目的は「値の正しさ」よりも、**レイアウト判定・STOP条件・ASOF取得ルール**が将来の改修で壊れていないかを素早く検出することです。

---

## このフォルダについて（RAW fixture の目的）

この `samples/raw/` は、PMS帳票そのものの種類違いに対応するためのものではなく、
N@FACE の「売上予算実績表」を **現場で加工した結果の揺れ** に対して、
安全に取り込める／取り込めない（STOPする）を回帰テストできるようにした fixture 集です。

### 前提（このRAWで“変えない”構造）
- 宿泊日（stay_date）は **A列**（ただし日付探索は **9行目以降のみ**）
- 曜日は **C列**（存在する場合、「曜日がある行＝予算行」の確定に使用）
- 実績OHの主要列は **E/F/G列**（列位置を動かす加工は対応対象外＝欠損扱い）
- 判定不能は推測で続行せず **STOP（欠損扱い）** とする（誤取り込み防止が最優先）

### 代表的な加工パターン
- 予算行の削除（1行持ち）
- 日付行のずらし（予算行の日付を下段へ移動）
- A列の空白除外コピー（OHだけを抜きやすくするための加工）
- 同日付が2行連続する（dup2）／混在（mix）
- 曜日列の削除
- 一部セルの手入力（例：A1にASOF日付が入っている）

---

## 前提（このプロジェクトの安全側ルール）

- **宿泊日（stay_date）は A列が唯一の正**
  - A列に宿泊日が無いRAWは **STOP**（誤取り込み防止）
- **OHデータ列は E/F/G（室数・人数・売上）を前提**
- **1行持ち / 2行持ち（shifted）** の2択で処理
  - 2行持ち判定は「空白行」または「同日付が2連続（dup2）」で判断
  - 1ファイル内に1行持ちと2行持ちが混在するケースは **想定しない**（判定不能はSTOP）
- **ASOF は原則セル（例：Q1）**
  - セルASOFが欠損している場合のみ **ファイル名からfallback**
- fixtureは機密対策として **0埋め（Privacy）** または **連番ダミー（Signal）** を使用する  
  - Signalは「行ズレ・列ズレが起きたら即バレる」ためのもの

---

## 期待される動作（ざっくり）

- OK系：daily snapshots が生成され、LT_DATA に反映できる（値はダミーでも良い）
- STOP系：変換を継続せず、ログに「判定不能/日付列なし」等が出る
- ASOF fallback：Q1欠損でも、ファイル名ASOFで継続し、ログにfallbackが残る

---

## Fixture一覧（現状）

> ※ファイル名は「仕様観点が一目で分かる」ことを優先しています  
> 例：`rawfx_nface_A_shifted_cell_dup2.xlsx`
> - nface：adapter
> - A：日付列（A列）
> - shifted/inline：レイアウト
> - cell/name：ASOF取得元
> - dup2/blank/mix/stop：ケース

### ✅ 正常系（OK）

#### 1) `rawfx_nface_A_inline_cell_ok.xlsx`
- 目的：**1行持ち（inline）の基準形**
- 期待：A列日付行と同じ行の E/F/G をOHとして読む
- 備考：Signal（連番ダミー推奨）

#### 2) `rawfx_nface_A_shifted_cell_blank.xlsx`
- 目的：**2行持ち（shifted）＋空白行パターン**
- 期待：日付行の1つ下の行の E/F/G をOHとして読む

#### 3) `rawfx_nface_A_shifted_cell_dup2.xlsx`
- 目的：**2行持ち（shifted）＋同日付2連続（dup2）**
- 期待：同一日付が2行連続する場合、2行目側をOHとして読む（全体を2行持ち扱い）

#### 4) `rawfx_nface_A_shifted_cell_mix.xlsx`
- 目的：**dup2 と blank が混在しても“全体として2行持ち”に固定できるか**
- 期待：混在でもブレずに2行持ち扱いでOH行を決定

#### 5) `rawfx_nface_A_inline_cell_weekday_spacer.xlsx`
- 目的：**A列日付が2行おきに出るが、間の行が「曜日のみ＋数値ゼロ」のスペーサ**
- 期待：
  - diffs>1 でも shifted と誤判定しない（OHを日付行+1にしない）
  - OHは日付行と同じ行（inline）で読む
  - スペーサ行（曜日だけ/ゼロ行）をOHとして採用しない

---

### ⛔ 異常系（STOP/要確認）

#### 6) `rawfx_nface_noA_stop.xlsx`
- 目的：**A列に宿泊日が無いケース**
- 期待：STOP（誤取り込み防止）

#### 7) `rawfx_nface_A_unknown_stop.xlsx`
- 目的：**1行/2行判定が取れない（規則性が崩れている）**
- 期待：STOP（部分取り込みはしない）

---

### ⚠️ fallback/不整合系（要件確認用）

- 方針：原則は「中身＞ファイル名」。ただし中身にASOFが無い場合のみファイル名にfallbackする。

#### 8) `rawfx_nface_A_inline_name_asof_fallback.xlsx`
- 目的：**セルASOF（Q1等）が欠損しているため、ファイル名ASOFにfallback**
- 期待：処理は継続し、ログに「ASOF fallback」が残る

#### 9) `rawfx_nface_A_shifted_cell_mismatch_name_vs_sheet__202311_20230501.xlsx`
- 目的：**ファイル名（target_month/asof）とシート中身（宿泊月/ASOF）が不一致**のケース
- 期待：**中身優先で継続**（シート側の宿泊月・ASOFを採用）
  - ただしログに mismatch を残す（後でRAW整理の棚卸しに使う）
- 補足：
  - 末尾 `__202311_20230501` は「パース可能なダミー（YYYYMM_YYYYMMDD）」を付与して、
    **“ファイル名パースは可能だが中身と矛盾する”** 状況を再現するためのもの


---

## 運用メモ（ZIP同梱の方針）

- RAW fixture は `samples/raw/` に置き、実運用RAWフォルダと混ぜない
- ZIPに同梱する場合は `make_release_zip.py` の `OUTPUT_SAMPLE_GLOBS` に
  - `samples/raw/*.xlsx`
  を追加する
- 共有前に、個人名・施設名・実売上などが残っていないかを必ず確認する

---
