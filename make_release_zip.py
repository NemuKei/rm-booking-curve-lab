from __future__ import annotations

import argparse
import fnmatch
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

JST = timezone(timedelta(hours=9))

# --- ここを必要に応じて調整 ---
INCLUDE_GLOBS = [
    # ★重要：** はディレクトリ中心になるので **/* にする
    "src/**/*",
    "booking_curve/**/*",  # もし存在しないなら消してOK
    "docs/**/*",
    "config/**/*",
    "pyproject.toml",
    "requirements.txt",
    "README.md",
    "AGENTS.md",
    "make_release_zip.py",
    "BookingCurveLab.spec",
    "assets/**/*",
    "tools/**/*",
    "patches/**/*",
]

# 「サンプル出力」を入れるときだけ追加する（git管理外でも入る想定）
OUTPUT_SAMPLE_GLOBS = [
    # 欠損レポート（ops/audit）
    "output/missing_report_*_ops.csv",
    "output/missing_report_*_audit.csv",
    # RAW fixture
    "samples/raw/*.xlsx",
    "samples/raw/*.md",
]

EXCLUDE_GLOBS = [
    ".git/**",
    ".venv/**",
    "venv/**",
    "src/.venv/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "dist/**",
    "build/**",
    "outputs/**",
    "output/**",  # ★with-output-samples のときだけ無効化
    "logs/**",  # ★with-output-samples のときだけ無効化
    "tmp/**",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    ".idea/**",
    ".vscode/**",
    "*.zip",
    "*.7z",
    "packages/**",
]

DANGEROUS_HINTS = [
    ".env",
    "secrets",
    "secret",
    "apikey",
    "api_key",
    "token",
    "password",
    "credentials",
    "private_key",
]


def safe_slug(s: str, max_len: int = 80) -> str:
    """
    ファイル名に安全な形へ簡易正規化（Windows想定）。
    """
    out = (
        s.strip()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace("?", "-")
        .replace('"', "-")
        .replace("<", "-")
        .replace(">", "-")
        .replace("|", "-")
    )
    # 連続ハイフンを雑に間引き（軽く見やすく）
    while "--" in out:
        out = out.replace("--", "-")
    if not out:
        out = "unknown"
    return out[:max_len] if len(out) > max_len else out


def run_git(cmd: list[str], cwd: Path) -> str:
    try:
        out = subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True).strip()
        return out
    except Exception:
        return ""


def get_git_meta(repo_root: Path) -> tuple[str, str]:
    branch = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root) or "(unknown)"
    commit = run_git(["git", "rev-parse", "--short", "HEAD"], repo_root) or "(unknown)"
    return branch, commit


def git_ls_files(repo_root: Path) -> set[Path]:
    try:
        out = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo_root, stderr=subprocess.DEVNULL)
        paths: set[Path] = set()
        for b in out.split(b"\x00"):
            if not b:
                continue
            rel = b.decode("utf-8", errors="replace")
            p = repo_root / rel
            if p.is_file():
                paths.add(p)
        return paths
    except Exception:
        return set()


def match_any(path_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path_posix, pat) for pat in patterns)


def expand_include_globs(repo_root: Path, include_globs: list[str]) -> set[Path]:
    candidates: set[Path] = set()
    for g in include_globs:
        for p in repo_root.glob(g):
            if p.is_file():
                candidates.add(p)
    return candidates


def filter_files(repo_root: Path, candidates: set[Path], exclude_globs: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in sorted(candidates):
        rel = p.relative_to(repo_root).as_posix()
        if match_any(rel, exclude_globs):
            continue

        # 親ディレクトリ由来のexcludeも反映
        parts = rel.split("/")
        blocked = False
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i]) + "/**"
            if match_any(parent, exclude_globs):
                blocked = True
                break
        if blocked:
            continue

        files.append(p)
    return files


def scan_suspicious(repo_root: Path) -> list[str]:
    """
    共有前の雑な安全装置：いかにも危ない名称を含むファイルを列挙。
    venv/.venv はノイズなのでスキップ。
    """
    suspicious: list[str] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_root).as_posix().lower()
        if rel.startswith(".git/") or rel.startswith(".venv/") or rel.startswith("src/.venv/") or rel.startswith("venv/"):
            continue
        if any(h in rel for h in DANGEROUS_HINTS):
            suspicious.append(rel)
    return sorted(set(suspicious))


def pick_latest_logs(repo_root: Path, max_logs: int) -> set[Path]:
    """
    最新ログを最大N本選ぶ。
    優先順位：
      1) full_all_*.log（ルート + output/logs 配下）
      2) それ以外（output/logs の *.log）
    """
    if max_logs <= 0:
        return set()

    preferred: list[Path] = []
    others: list[Path] = []

    # ルートの full_all を最優先
    preferred += [p for p in repo_root.glob("full_all_*.log") if p.is_file()]

    # output/logs 配下
    out_logs_dir = repo_root / "output" / "logs"
    if out_logs_dir.exists():
        for p in out_logs_dir.glob("*.log"):
            if not p.is_file():
                continue
            if p.name.startswith("full_all_"):
                preferred.append(p)
            else:
                others.append(p)

    # 重複排除しつつ mtime で新しい順
    preferred = sorted(set(preferred), key=lambda p: p.stat().st_mtime, reverse=True)
    others = sorted(set(others), key=lambda p: p.stat().st_mtime, reverse=True)

    chosen = preferred[:max_logs]
    if len(chosen) < max_logs:
        chosen += others[: (max_logs - len(chosen))]

    return set(chosen)


def build_auto_tag(*, profile: str, with_output_samples: bool, branch: str, commit: str) -> str:
    """
    --tag 未指定時の自動タグ。
    例: 20251224_1720_samp_feature-daily-snapshots-partial-build_0ecb0ff
    """
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M")
    samp = "samp" if with_output_samples else "code"
    b = safe_slug(branch, max_len=60)
    c = safe_slug(commit, max_len=16)
    return f"{ts}_{samp}_{b}_{c}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    ap.add_argument("--outdir", default="packages")
    ap.add_argument("--profile", choices=["handover", "full"], default="full")  # 互換のため残す
    ap.add_argument("--no-git-only", action="store_true")
    ap.add_argument("--with-output-samples", action="store_true")
    ap.add_argument("--max-logs", type=int, default=1)
    args = ap.parse_args()

    repo_root = Path.cwd()
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    branch, commit = get_git_meta(repo_root)

    # --tag 未指定なら自動生成（時刻＋samples有無＋branch＋commit）
    tag = args.tag or build_auto_tag(
        profile=args.profile,
        with_output_samples=bool(args.with_output_samples),
        branch=branch,
        commit=commit,
    )

    include_candidates = expand_include_globs(repo_root, INCLUDE_GLOBS)

    # git 管理ファイルだけに絞る（デフォルト）
    if not args.no_git_only:
        tracked = git_ls_files(repo_root)
        if tracked:
            include_candidates = include_candidates.intersection(tracked)

    # ★出力サンプルは untracked が多いので、ここで別途追加（git-only を無視して union）
    if args.with_output_samples:
        include_candidates |= expand_include_globs(repo_root, OUTPUT_SAMPLE_GLOBS)
        include_candidates |= pick_latest_logs(repo_root, args.max_logs)

    # ★with-output-samples のときだけ output/logs の全除外を解除（他の除外は維持）
    exclude_globs = list(EXCLUDE_GLOBS)
    if args.with_output_samples:
        exclude_globs = [g for g in exclude_globs if g not in ("output/**", "logs/**")]

    files = filter_files(repo_root, include_candidates, exclude_globs)

    zip_path = outdir / f"{repo_root.name}_{tag}_{args.profile}.zip"
    now = datetime.now(JST).isoformat(timespec="seconds")

    version_txt = (
        f"package: {repo_root.name}\n"
        f"tag: {tag}\n"
        f"generated_at: {now}\n"
        f"branch: {branch}\n"
        f"commit: {commit}\n"
        f"profile: {args.profile}\n"
        f"with_output_samples: {bool(args.with_output_samples)}\n"
        f"max_logs: {args.max_logs}\n"
    )

    manifest_lines: list[str] = []
    manifest_lines.append(f"package: {repo_root.name}")
    manifest_lines.append(f"tag: {tag}")
    manifest_lines.append(f"generated_at: {now}")
    manifest_lines.append(f"branch: {branch}")
    manifest_lines.append(f"commit: {commit}")
    manifest_lines.append(f"profile: {args.profile}")
    manifest_lines.append(f"with_output_samples: {bool(args.with_output_samples)}")
    manifest_lines.append(f"max_logs: {args.max_logs}")
    manifest_lines.append("")
    manifest_lines.append(f"files_count: {len(files)}")
    manifest_lines.append("files:")
    for p in files:
        manifest_lines.append(p.relative_to(repo_root).as_posix())
    manifest_txt = "\n".join(manifest_lines) + "\n"

    suspicious = scan_suspicious(repo_root)

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("VERSION.txt", version_txt)
        zf.writestr("MANIFEST.txt", manifest_txt)
        for p in files:
            rel = p.relative_to(repo_root).as_posix()
            zf.write(p, rel)

    print(f"[OK] created: {zip_path}")
    print(f"[OK] profile: {args.profile} (with_output_samples={bool(args.with_output_samples)})")
    print(f"[OK] files: {len(files)} (+ VERSION.txt, MANIFEST.txt)")
    print(f"[OK] branch: {branch} / commit: {commit}")
    print(f"[OK] tag: {tag}")

    if suspicious:
        head = suspicious[:20]
        print("[WARN] suspicious files exist in repo (review before sharing):")
        for r in head:
            print(f"  - {r}")
        if len(suspicious) > len(head):
            print(f"  ... and {len(suspicious) - len(head)} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
