from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HEADER_RE = re.compile(r"^(##\s+)D-(\d{8})-(XXX|\d{3})(\b.*)$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Assign sequential decision IDs for placeholders D-YYYYMMDD-XXX in docs/decision_log.md")
    ap.add_argument("--file", default="docs/decision_log.md", help="Target markdown file")
    ap.add_argument("--in-place", action="store_true", help="Write changes to file (default: dry-run)")
    ap.add_argument("--check-only", action="store_true", help="Exit non-zero if any XXX placeholders exist")
    ap.add_argument("--sort", action="store_true", help="Sort entries old -> new (newest at bottom)")
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


def sort_decision_entries(lines: List[str]) -> Tuple[List[str], int]:
    header_indices = [idx for idx, line in enumerate(lines) if HEADER_RE.match(line)]
    if not header_indices:
        return lines, 0

    preamble_end = header_indices[0]
    preamble = lines[:preamble_end]

    blocks: List[Tuple[int, int, List[str], str, bool, int, int]] = []
    for block_index, start in enumerate(header_indices):
        end = header_indices[block_index + 1] if block_index + 1 < len(header_indices) else len(lines)
        block_lines = lines[start:end]
        match = HEADER_RE.match(block_lines[0])
        if not match:
            continue
        date = match.group(2)
        num = match.group(3)
        is_xxx = num == "XXX"
        num_value = 9999 if is_xxx else int(num)
        blocks.append((start, end, block_lines, date, is_xxx, num_value, block_index))

    original_order = [block[6] for block in blocks]
    blocks.sort(key=lambda item: (item[3], item[4], item[5], item[6]))
    sorted_order = [block[6] for block in blocks]
    moved_blocks = sum(1 for original, sorted_ in zip(original_order, sorted_order) if original != sorted_)

    sorted_lines: List[str] = []
    sorted_lines.extend(preamble)
    for _, _, block_lines, _, _, _, _ in blocks:
        sorted_lines.extend(block_lines)

    return sorted_lines, moved_blocks


def main() -> int:
    args = parse_args()
    path = Path(args.file)

    if not path.exists():
        print(f"[ERROR] file not found: {path}", file=sys.stderr)
        return 2

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)

    if args.check_only:
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
        if total_placeholders > 0:
            print("[FAIL] XXX placeholders exist.", file=sys.stderr)
            return 10
        print("[OK] no XXX placeholders.")
        return 0

    original_lines = list(lines)
    moved_blocks = 0
    if args.sort:
        lines, moved_blocks = sort_decision_entries(lines)

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

    new_lines, replaced = assign_ids(lines, max_by_date)

    if new_lines == original_lines:
        print("[OK] no changes.")
        return 0

    if args.in_place:
        path.write_text("".join(new_lines), encoding="utf-8")
        print(f"[OK] assigned {replaced} decision IDs in-place: {path} (moved blocks: {moved_blocks})")
    else:
        print(f"[DRY-RUN] would assign {replaced} decision IDs in: {path} (moved blocks: {moved_blocks})")
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
