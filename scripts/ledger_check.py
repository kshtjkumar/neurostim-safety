#!/usr/bin/env python3
"""Gate ``CODE_MISTAKES_LOG.md``: every row parses, and every entry is scheduled.

The ledger is this repository's record of what was wrong and what was done about it. A
row that does not parse is a defect that has quietly left the record. Two had already:
rows 8 and 46 carried unescaped pipes inside ``min(|cathodic|,|anodic|)``, which split
them into 11 and 9 fields against the header's 7. Markdown renders the overflow as extra
columns, and every reader of the table -- a person skimming it, or any script that tries
to audit it -- misreads the row without being told.

What this gate asserts
----------------------
1. Every data row has exactly as many fields as the header.
2. Entry numbers are unique and contiguous from 1.
3. Every entry is scheduled in section 9 of the fix plan, as a plain number or under a
   sub-finding label (``61/M3``, ``67(a)``). Entries whose severity is ``(plan defect)``
   are exempt: those are defects *in* the plan, disposed of in its section 1b, and by
   construction have no row in its coverage table.
4. Any commit id a row records is a commit that exists. A ledger claiming a fix landed in
   a commit that was never made is worse than one claiming nothing.

Usage
-----
::

    python scripts/ledger_check.py
    python scripts/ledger_check.py --ledger CODE_MISTAKES_LOG.md --plan docs/audit/FIX_PLAN_v2.md

Exit status: ``0`` clean, ``1`` a failed assertion, ``2`` an input that could not be read.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "CODE_MISTAKES_LOG.md"
DEFAULT_PLAN = REPO_ROOT / "docs" / "audit" / "FIX_PLAN_v2.md"

PLAN_DEFECT_SEVERITY = "(plan defect)"
"""Severity marking an entry against the fix plan rather than against the package."""

SECTION_9_HEADING = "## 9. Ledger coverage"
SECTION_10_HEADING = "## 10."

_HASH = re.compile(r"^[0-9a-f]{7,40}$")
_ENTRY_LABEL = re.compile(r"^(\d+)(?:[/(].*)?$")


@dataclass(frozen=True)
class Row:
    """One data row of the ledger table."""

    line_number: int
    fields: list[str]

    @property
    def number(self) -> int | None:
        return int(self.fields[0]) if self.fields[0].isdigit() else None

    @property
    def severity(self) -> str:
        return self.fields[2] if len(self.fields) > 2 else ""

    @property
    def commit(self) -> str:
        return self.fields[-1].strip("`") if self.fields else ""


@dataclass(frozen=True)
class Table:
    """The parsed ledger."""

    header: list[str]
    rows: list[Row]

    @property
    def entries(self) -> list[Row]:
        return [row for row in self.rows if row.number is not None]


def _cells(line: str) -> list[str]:
    """Markdown table cells. ``\\|`` is an escaped pipe and does not split a cell."""
    placeholder = "\x00"
    body = line.strip().strip("|")
    return [c.replace(placeholder, "|").strip() for c in body.replace(r"\|", placeholder).split("|")]


def parse_table(text: str) -> Table:
    """Parse the first markdown table in ``text``."""
    header: list[str] | None = None
    rows: list[Row] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _cells(stripped)
        if header is None:
            header = cells
            continue
        if all(set(cell) <= set("-: ") and cell for cell in cells):
            continue  # the ---|--- separator
        rows.append(Row(number, cells))
    if header is None:
        _abort("error: no markdown table found in the ledger")
    return Table(header, rows)


def plan_entry_numbers(text: str) -> set[int]:
    """Entry numbers scheduled in section 9 of the fix plan.

    Sub-findings are labelled ``61/M3``, ``67(a)``, ``78/S-24``; the entry is the leading
    integer.
    """
    start = text.find(SECTION_9_HEADING)
    if start < 0:
        _abort(f"error: the plan has no {SECTION_9_HEADING!r} section")
    end = text.find(SECTION_10_HEADING, start)
    section = text[start : end if end > 0 else len(text)]

    numbers: set[int] = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        match = _ENTRY_LABEL.match(_cells(stripped)[0])
        if match:
            numbers.add(int(match.group(1)))
    return numbers


def commit_exists(sha: str) -> bool:
    """Whether ``sha`` names a commit in this repository."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def check(ledger_text: str, plan_text: str) -> list[str]:
    """Every failed assertion, as a list of messages. Empty means clean."""
    failures: list[str] = []
    table = parse_table(ledger_text)
    width = len(table.header)

    for row in table.rows:
        if len(row.fields) != width:
            failures.append(
                f"line {row.line_number}: {len(row.fields)} fields against the header's "
                f"{width} -- an unescaped '|' in the cell text splits the row "
                f"(write it as '\\|'): {row.fields[0]!r}"
            )

    numbers = [row.number for row in table.entries]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        failures.append(f"duplicate entry numbers: {duplicates}")
    if numbers:
        missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        if missing:
            failures.append(
                f"gaps in the entry numbering: {missing} -- the ledger says never delete"
            )

    scheduled = plan_entry_numbers(plan_text)
    unscheduled = sorted(
        row.number
        for row in table.entries
        if row.severity != PLAN_DEFECT_SEVERITY and row.number not in scheduled
    )
    if unscheduled:
        failures.append(
            f"entries absent from the plan's section 9: {unscheduled} -- every defect must "
            f"be scheduled or declared a {PLAN_DEFECT_SEVERITY} entry"
        )

    for row in table.entries:
        sha = row.commit
        if _HASH.match(sha) and not commit_exists(sha):
            failures.append(
                f"entry {row.number} records commit {sha}, which does not exist in this "
                f"repository"
            )

    return failures


def _abort(*lines: str) -> NoReturn:
    for line in lines:
        print(line, file=sys.stderr)
    raise SystemExit(2)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _abort(f"error: cannot read {path}: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args(argv)

    failures = check(_read(args.ledger), _read(args.plan))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    table = parse_table(_read(args.ledger))
    print(
        f"OK: {len(table.entries)} entries, {len(table.header)} fields each, "
        f"every package defect scheduled in the plan"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
