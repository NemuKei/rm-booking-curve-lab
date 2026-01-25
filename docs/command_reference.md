# Command Reference (rm-booking-curve-lab)

このドキュメントは「定常運用で使うコマンド」だけを載せる。
一時的な調査コマンドや個人環境依存のTipsは増やさない（腐るため）。

---

## 0) 前提
- すべて **リポジトリ直下**で実行する（PowerShell想定）
- 初回は venv を作る
- GUIの起点は `src/gui_main.py`（プロジェクトの現状に合わせて更新）

---

## 1) 仮想環境（初回のみ）
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip

# 推奨（開発者）：pyproject.toml の依存＋dev（ruff）を一括導入
pip install -e ".[dev]"

# 代替（最小）：requirements.txt のみ（ruff等は別途）
# pip install -r requirements.txt
````

---

## 2) GUI実行

```powershell
.\.venv\Scripts\activate
python src\gui_main.py
```

※起動でコケる/原因が見えないときは、まずはPowerShell上で起動してエラー表示を確認する。

---

## 3) PyInstaller（EXEビルド）

### 3-1) spec を使う（推奨：再現性が高い）

```powershell
.\.venv\Scripts\activate
pyinstaller BookingCurveLab.spec --clean --noconfirm
```

* 生成物：`dist/BookingCurveLab/` 配下（onedir形式）
* アイコンは `.spec` 内の `icon=` を参照

### 3-2) コマンド直打ち（spec未整備/検証用）

```powershell
.\.venv\Scripts\activate
pyinstaller `
  --noconsole `
  --onefile `
  --name BookingCurveLab `
  --icon assets\icon\BookingCurveLab_logo_neon_requested.ico `
  --paths src `
  --add-data "config;config" `
  src\gui_main.py
```

* 生成物：`dist/BookingCurveLab.exe`（onefile形式）

---

## 4) Release ZIP（配布用パッケージ）

```powershell
.\.venv\Scripts\activate
python make_release_zip.py
```

---

## 5) Lint / Format（導入している場合）

※ ruff は pyproject.toml の dev extras（.[dev]）で導入する前提。

```powershell
.\.venv\Scripts\activate
ruff check .
ruff format .
```

---

## 6) トラブルシュート（最小）

### PyInstallerで起動しない

* まず `--noconsole` を外して、エラー表示を出す
* `config` が必要な処理は `--add-data "config;config"` が無いと落ちる

### ModuleNotFoundError が出る

* `--paths src` が抜けている可能性が高い
