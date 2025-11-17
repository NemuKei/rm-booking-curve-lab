from pathlib import Path

# プロジェクトのルートディレクトリ（src/ から2つ上に上がる想定）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# データを置くディレクトリ（必要に応じて変更）
DATA_DIR = PROJECT_ROOT / "data"

# 出力ディレクトリ（LT_DATA や図を吐き出す場所）
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
