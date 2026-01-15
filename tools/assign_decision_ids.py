from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


HEADER_RE = re.compile(r"^(##\s+)D-(\d{8})-(XXX|\d{3})(\b.*)$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Assign sequential decision IDs for placeholders D-YYYYMMDD-XXX in docs/decision_log.md"
    )
    ap.add_argument("--file", default="docs/decision_log.md", help="Target markdown file")
    ap.add_argument("--in-place", action="store_true", help="Write changes to file (default: dry-run)")
    ap.add_argument("--check-only", action="store_true", help="Exit non-zero if any XXX placeholders exist")
    ap.add_argument("--verbose", action="store_true", help="Print details")
    return ap.parse_args()


def compute_max_by_date(lines: List[str]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Returns:
      - max_by_date: date -> max numeric id (e.g., 3)
      - counts_placeholder: date -> number of XXX placeholders found
    """
    max_by_date: Dict[str, int] = {}
    counts_placeholder: Dict[str, int] = {}

    seen_ids: set[str] = set()
    dup_ids: List[str] = []

    for ln in lines:
        m = HEADER_RE.match(ln)
        if not m:
            continue
        date = m.group(2)
        num = m.group(3)

        # duplicate check (only for concrete ids)
        if num != "XXX":
            full_id = f"D-{date}-{num}"
            if full_id in seen_ids:
                dup_ids.append(full_id)
            else:
                seen_ids.add(full_id)

            n = int(num)
            max_by_date[date] = max(max_by_date.get(date, 0), n)
        else:
            counts_placeholder[date] = counts_placeholder.get(date, 0) + 1

    if dup_ids:
        uniq = sorted(set(dup_ids))
        raise ValueError(f"Duplicate decision IDs found: {', '.join(uniq)}")

    return max_by_date, counts_placeholder


def assign_ids(lines: List[str], max_by_date: Dict[str, int]) -> Tuple[List[str], int]:
    """
    Replace D-YYYYMMDD-XXX with D-YYYYMMDD-NNN (NNN is date-local, starting from max+1).
    Numbering is done in file order (top to bottom).
    Returns: (new_lines, replaced_count)
    """
    next_by_date: Dict[str, int] = {d: v + 1 for d, v in max_by_date.items()}
    replaced = 0
    new_lines: List[str] = []

    for ln in lines:
        m = HEADER_RE.match(ln)
        if not m:
            new_lines.append(ln)
            continue

        prefix, date, num, suffix = m.group(1), m.group(2), m.group(3), m.group(4)

        if num != "XXX":
            new_lines.append(ln)
            continue

        n = next_by_date.get(date, 1)  # if no existing numeric, start at 1
        next_by_date[date] = n + 1

        new_id = f"{prefix}D-{date}-{n:03d}{suffix}\n"
        new_lines.append(new_id)
        replaced += 1

    # After assignment, ensure no accidental duplicates created (shouldn't happen, but guard)
    seen: set[str] = set()
    for ln in new_lines:
        m = HEADER_RE.match(ln)
        if not m:
            continue
        date, num = m.group(2), m.group(3)
        if num == "XXX":
            continue
        full_id = f"D-{date}-{num}"
        if full_id in seen:
            raise ValueError(f"Duplicate decision ID produced after assignment: {full_id}")
        seen.add(full_id)

    return new_lines, replaced


def main() -> int:
    args = parse_args()
    path = Path(args.file)

    if not path.exists():
        print(f"[ERROR] file not found: {path}", file=sys.stderr)
        return 2

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)

    try:
        max_by_date, counts_placeholder = compute_max_by_date(lines)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3

    total_placeholders = sum(counts_placeholder.values())
    if args.verbose:
        print(f"[INFO] placeholders: {total_placeholders}")
        if counts_placeholder:
            for d in sorted(counts_placeholder):
                mx = max_by_date.get(d, 0)
                print(f"  - {d}: XXX={counts_placeholder[d]} (current max={mx:03d})")

    if args.check_only:
        if total_placeholders > 0:
            print("[FAIL] XXX placeholders exist.", file=sys.stderr)
            return 10
        print("[OK] no XXX placeholders.")
        return 0

    new_lines, replaced = assign_ids(lines, max_by_date)

    if replaced == 0:
        print("[OK] no changes (no XXX placeholders).")
        return 0

    if args.in_place:
        path.write_text("".join(new_lines), encoding="utf-8")
        print(f"[OK] assigned {replaced} decision IDs in-place: {path}")
    else:
        print(f"[DRY-RUN] would assign {replaced} decision IDs in: {path}")
        # minimal preview: show first 10 changed headers
        shown = 0
        for old, new in zip(lines, new_lines):
            if old != new and HEADER_RE.match(old):
                print(f"  - {old.strip()}  ->  {new.strip()}")
                shown += 1
                if shown >= 10:
                    break
        if replaced > shown:
            print(f"  ... ({replaced - shown} more)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
