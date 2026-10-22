"""Collapse duplicate span columns; audit other repetitions without deleting them.

Run with Python (no dependencies). Defaults to a dry run; --write backs up and
updates the corpus. Only adjacent columns are combined, and only when every
row agrees or contains complementary currency/number/percentage fragments.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

DATA_DIR = Path(__file__).resolve().parent
MARKDOWN_DIR = DATA_DIR / "markdown"
CELL_SEPARATOR = re.compile(r"(?<!\\)\|")
NUMBER = re.compile(r"\(?\s*[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?\s*\)?(?:\s*\(\d+\))?")


def merge_cells(left: str, right: str) -> str | None:
    if not left or not right:
        return left or right
    first = re.sub(r"\s+", " ", left)
    second = re.sub(r"\s+", " ", right)
    if first == second:
        return left
    # SEC layout tables split currency and punctuation from the actual amount.
    if re.fullmatch(r"[$£€¥](?:\s*\()?|\(", first) and NUMBER.fullmatch(second):
        return first + " " + right
    amount = re.sub(r"^[$£€¥]\s*", "", first)
    if second in ("%", ")") and NUMBER.fullmatch(amount):
        if second == ")" and (not amount.startswith("(") or amount.endswith(")")):
            return None
        if second == "%" and "%" in first:
            return None
        return left + " " + second
    for decorated, bare in ((left, right), (right, left)):
        amount = re.sub(r"^[$£€¥]\s*", "", decorated)
        if amount != decorated and NUMBER.fullmatch(amount) and amount == bare:
            return decorated
    return None


def collapse_columns(columns: list[tuple[str, ...]]) -> tuple[list[tuple[str, ...]], list[dict], list[int]]:
    kept = []
    retained = []
    duplicates = []
    empty = []
    for index, column in enumerate(columns):
        if not any(column):
            empty.append(index + 1)
            continue
        merged = [merge_cells(left, right) for left, right in zip(kept[-1], column)] if kept else []
        overlap = kept and any(left and right for left, right in zip(kept[-1], column))
        if overlap and all(cell is not None for cell in merged):
            kept[-1] = tuple(merged)
            duplicates.append({"removed": index + 1, "retained": retained[-1]})
        else:
            kept.append(column)
            retained.append(index + 1)
    return kept, duplicates, empty


def parse_table(lines: list[str]) -> list[list[str]] | None:
    rows = [CELL_SEPARATOR.split(line.strip())[1:-1] for line in lines]
    rows = [[cell.strip() for cell in row] for row in rows]
    if len(rows) < 2 or not rows[1]:
        return None
    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
        return None
    if len({len(row) for row in rows}) != 1:
        return None
    return rows


def table_spans(lines: list[str]):
    index = 0
    fence = None
    while index < len(lines):
        stripped = lines[index].lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        if fence is None and stripped.startswith("|") and stripped.rstrip().endswith("|"):
            start = index
            while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
                index += 1
            yield start, index, parse_table(lines[start:index])
        else:
            index += 1


def clean_markdown(text: str) -> tuple[str, dict]:
    lines = text.splitlines(keepends=True)
    output = []
    cursor = 0
    changes = []
    skipped = []
    totals = dict(tables_scanned=0, duplicate_columns_removed=0,
                  empty_columns_removed=0, empty_tables_removed=0)
    for start, end, rows in table_spans(lines):
        output.extend(lines[cursor:start])
        cursor = end
        if rows is None:
            skipped.append(start + 1)
            output.extend(lines[start:end])
            continue
        totals["tables_scanned"] += 1
        columns = list(zip(rows[0], *rows[2:]))
        kept, duplicates, empty = collapse_columns(columns)
        if not duplicates and not empty:
            output.extend(lines[start:end])
            continue
        totals["duplicate_columns_removed"] += len(duplicates)
        totals["empty_columns_removed"] += len(empty)
        if not kept:
            totals["empty_tables_removed"] += 1
        else:
            data_rows = iter(zip(*kept))
            removed = set(empty) | {change["removed"] for change in duplicates}
            separators = [cell for index, cell in enumerate(rows[1], 1) if index not in removed]
            for row_index, row in enumerate(rows):
                ending = "\r\n" if lines[start + row_index].endswith("\r\n") else "\n"
                if not lines[start + row_index].endswith("\n"):
                    ending = ""
                cells = separators if row_index == 1 else next(data_rows)
                output.append("| " + " | ".join(cells) + " |" + ending)
        changes.append({"original_line": start + 1, "original_columns": len(columns),
                        "remaining_columns": len(kept), "duplicate_columns": duplicates,
                        "empty_columns": empty})
    output.extend(lines[cursor:])
    return "".join(output), {**totals, "changes": changes, "skipped_table_lines": skipped}


def repeated_groups(groups: dict) -> list[dict]:
    return [{"sha256": hashlib.sha256(value.encode()).hexdigest(),
             "excerpt": value[:300], "occurrences": locations}
            for value, locations in groups.items() if len(locations) > 1]


def audit_repetitions(text: str) -> tuple[dict, dict]:
    lines = text.splitlines()
    tables = defaultdict(list)
    repeated_rows = []
    table_lines = set()
    for start, end, rows in table_spans(lines):
        table_lines.update(range(start, end))
        if rows is None:
            continue
        content = [rows[0], *rows[2:]]
        if not any(any(row) for row in content):
            continue
        key = json.dumps(content, ensure_ascii=False)
        tables[key].append(start + 1)
        row_groups = defaultdict(list)
        for offset, row in enumerate(rows[2:], start + 2):
            if any(row):
                row_groups[json.dumps(row, ensure_ascii=False)].append(offset + 1)
        for group in repeated_groups(row_groups):
            repeated_rows.append({"table_line": start + 1, **group})
    paragraphs = defaultdict(list)
    block = []
    block_start = 0
    for index in range(len(lines) + 1):
        if index == len(lines) or index in table_lines or not lines[index].strip():
            value = re.sub(r"\s+", " ", " ".join(block)).strip()
            if len(value) >= 80 and any(char.isalpha() for char in value):
                paragraphs[value].append(block_start + 1)
            block = []
        else:
            if not block:
                block_start = index
            block.append(lines[index])
    return {"repeated_tables": repeated_groups(tables),
            "repeated_data_rows": repeated_rows,
            "repeated_paragraphs": repeated_groups(paragraphs)}, paragraphs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Back up and update Markdown files")
    args = parser.parse_args()
    paths = sorted(MARKDOWN_DIR.rglob("*.md"))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = DATA_DIR / "markdown_backups" / stamp if args.write else None
    report = {"generated_at_utc": datetime.now(UTC).isoformat(), "applied": args.write,
              "backup_directory": str(backup) if backup else None,
              "policy": "Combine adjacent columns only when every row agrees or contains complementary currency/number/percentage fragments; remove empty layout columns/tables; preserve distinct values and all repeated prose, rows, and nonempty tables.",
              "files": [], "totals": {"files_scanned": len(paths), "files_changed": 0}}
    cross_paragraphs = defaultdict(list)
    file_hashes = defaultdict(list)
    for path in paths:
        relative = path.relative_to(MARKDOWN_DIR)
        with path.open(encoding="utf-8", newline="") as source:
            original = source.read()
        cleaned, stats = clean_markdown(original)
        # A second pass must not discover further removals.
        if clean_markdown(cleaned)[0] != cleaned:
            raise ValueError(f"Cleanup is not idempotent: {path}")
        audit, paragraphs = audit_repetitions(cleaned)
        name = relative.as_posix()
        for paragraph, locations in paragraphs.items():
            cross_paragraphs[paragraph].append({"file": name, "lines": locations})
        file_hashes[hashlib.sha256(cleaned.encode()).hexdigest()].append(name)
        changed = original != cleaned
        report["totals"]["files_changed"] += int(changed)
        for key in ("tables_scanned", "duplicate_columns_removed", "empty_columns_removed", "empty_tables_removed"):
            report["totals"][key] = report["totals"].get(key, 0) + stats[key]
        report["files"].append({"file": name, "changed": changed,
                                "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                                "cleaned_sha256": hashlib.sha256(cleaned.encode()).hexdigest(),
                                **stats, **audit})
        if args.write and changed:
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            with path.open("w", encoding="utf-8", newline="") as target:
                target.write(cleaned)
    report["cross_file_repeated_paragraphs"] = repeated_groups(cross_paragraphs)
    report["duplicate_files"] = [names for names in file_hashes.values() if len(names) > 1]
    report_path = DATA_DIR / "markdown_cleanup_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["totals"], indent=2))
    print(f"Report: {report_path}")
    if backup:
        print(f"Backups: {backup}")


if __name__ == "__main__":
    main()
