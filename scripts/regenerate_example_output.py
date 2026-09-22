#!/usr/bin/env python3
"""Regenerate every artifact derived from the worked example, from one place.

There are two derived surfaces: ``example_output/`` (figures, CSV, JSON, PDF report) and
the transcript block in ``README.md``. Both are outputs of the same calculation, and both
were being maintained by hand. At the audit baseline the README transcript was stale by a
whole release: it showed five checks and a 70.69 uA limiting current where the package
prints nine checks and 141.4 uA. A number that a reader can check in ten seconds and that
disagrees with the code is the cheapest kind of defect to find and the most damaging to
find in review.

So this script owns both, and ``--check`` fails when either has drifted. Every numeric
commit in the repair reruns it instead of hand-editing eight surfaces.

Usage
-----
::

    python scripts/regenerate_example_output.py            # rewrite both
    python scripts/regenerate_example_output.py --check    # fail if the README has drifted
    python scripts/regenerate_example_output.py --readme-only

``example_output/`` is not tracked by git (see ``.gitignore``). It is a *generated*
directory, reproducible from this script on demand, so committing a few hundred kilobytes
of binary that would be rewritten by every one of the remaining numeric commits buys
nothing. The tracked, byte-compared artifact is the README transcript.

Reproducibility: ``SOURCE_DATE_EPOCH`` is set if it is not already, so the figures and the
PDF are byte-identical run to run. See :mod:`neurostim._repro`.
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
WORKED_EXAMPLE = REPO_ROOT / "examples" / "worked_example.py"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "example_output"

BEGIN_MARKER = "<!-- BEGIN GENERATED: quickstart-transcript -->"
END_MARKER = "<!-- END GENERATED: quickstart-transcript -->"

DEFAULT_SOURCE_DATE_EPOCH = "1767225600"
"""2026-01-01T00:00:00Z. Arbitrary but fixed, so two regenerations agree."""

DETAIL_INDENT = "    "
"""Per-check detail in ``describe()`` is indented four spaces; headlines are not."""


def quickstart_transcript() -> str:
    """The README quick-start output: ``calc.describe()`` with per-check detail elided.

    Every retained line is verbatim from ``describe()``. The elision rule is mechanical --
    drop the lines the renderer indents as detail -- so the block cannot say anything the
    package does not print.
    """
    from neurostim import RingElectrode, SafetyCalculator, StimProtocol

    electrode = RingElectrode(330, 270, "Pt")
    protocol = StimProtocol(80, 200, 130, 1)
    calc = SafetyCalculator(electrode, protocol, compliance_V=10.0)

    lines = calc.describe().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("Overall:"))
    except StopIteration:  # pragma: no cover - would mean describe() changed shape
        raise SystemExit(
            "error: describe() no longer contains an 'Overall:' line"
        ) from None
    end = next(
        (i for i, line in enumerate(lines[start:], start) if set(line.strip()) == {"-"}),
        len(lines),
    )

    kept = [line for line in lines[start:end] if not line.startswith(DETAIL_INDENT)]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def readme_block(transcript: str) -> str:
    """The generated region of README.md, markers included."""
    return "\n".join(
        [
            BEGIN_MARKER,
            "",
            "```",
            transcript,
            "```",
            "",
            "Each check also prints the conditions its limit was measured under and the",
            "source it came from; that detail is elided above.",
            "",
            END_MARKER,
        ]
    )


def split_readme(text: str) -> tuple[str, str, str]:
    """``(before, generated_region, after)``. Raises if the markers are missing."""
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(
            f"error: {README.name} is missing the generated-transcript markers\n"
            f"expected {BEGIN_MARKER!r} ... {END_MARKER!r}"
        )
    return text[:start], text[start : end + len(END_MARKER)], text[end + len(END_MARKER) :]


def regenerate_readme(*, write: bool) -> bool:
    """Return True when the committed README already matches. Rewrite it if asked."""
    current = README.read_text(encoding="utf-8")
    before, existing, after = split_readme(current)
    expected = readme_block(quickstart_transcript())
    if existing == expected:
        return True
    if write:
        README.write_text(before + expected + after, encoding="utf-8")
        print(f"rewrote the generated transcript in {README.name}")
        return True
    diff = difflib.unified_diff(
        existing.splitlines(),
        expected.splitlines(),
        fromfile=f"{README.name} (committed)",
        tofile=f"{README.name} (regenerated)",
        lineterm="",
    )
    print("\n".join(diff), file=sys.stderr)
    return False


def regenerate_example_output(output_dir: Path) -> None:
    """Run the worked example into ``output_dir`` with the build date pinned."""
    env = {**os.environ, "MPLBACKEND": "Agg"}
    env.setdefault("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)
    result = subprocess.run(
        [sys.executable, str(WORKED_EXAMPLE), str(output_dir)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"error: the worked example exited {result.returncode}")
    written = sorted(p.name for p in output_dir.iterdir())
    print(f"wrote {len(written)} artifacts to {output_dir}:")
    for name in written:
        print(f"  {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed README transcript, write nothing, exit 1 on drift",
    )
    parser.add_argument(
        "--readme-only",
        action="store_true",
        help="skip example_output/ and regenerate only the README transcript",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"where the example artifacts go (default: {DEFAULT_OUTPUT_DIR.name}/)",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)

    if not regenerate_readme(write=not args.check):
        print("FAIL: the README transcript is stale; run this script without --check",
              file=sys.stderr)
        return 1
    if args.check:
        print("OK: the README transcript matches the package's own output")
        return 0
    if not args.readme_only:
        regenerate_example_output(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
