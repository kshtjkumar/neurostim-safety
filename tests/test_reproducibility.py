"""Two identical runs must produce identical bytes.

At the audit baseline, five of the eight artifacts ``examples/worked_example.py`` writes
differed between two back-to-back runs of unchanged code, with identical file lengths:

* ``figure_*.svg``     -- an ``<dc:date>`` wall-clock stamp, and element ids salted from
  a per-process ``uuid4`` (``rcParams["svg.hashsalt"]`` defaults to ``None``)
* ``figure_*.pdf``     -- matplotlib's ``/CreationDate``
* ``safety_report.pdf`` -- reportlab's ``/CreationDate``, ``/ModDate`` and document id

That makes it impossible to tell a real numeric change from clock noise, which is the
whole point of committing generated output. The contract is the reproducible-builds one:
with ``SOURCE_DATE_EPOCH`` set, every byte is a function of the inputs.

These assertions are diffs between two runs of unchanged code. Nothing in them is
computed by the code under test, so none of them can pass for the wrong reason -- except
by deleting the timestamps outright, which is what ``test_the_pinned_date_reaches_every
_artifact`` exists to catch.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKED_EXAMPLE = REPO_ROOT / "examples" / "worked_example.py"

PINNED_EPOCH = "1234567890"
"""2009-02-13T23:31:30Z -- an arbitrary fixed instant, chosen only to be recognisable."""


def _run_example(target: Path, epoch: str = PINNED_EPOCH) -> None:
    env = {**os.environ, "MPLBACKEND": "Agg", "SOURCE_DATE_EPOCH": epoch}
    result = subprocess.run(
        [sys.executable, str(WORKED_EXAMPLE), str(target)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The worked example, run twice into clean directories at the same pinned date."""
    base = tmp_path_factory.mktemp("repro")
    first, second = base / "a", base / "b"
    _run_example(first)
    _run_example(second)
    return first, second


def test_the_example_writes_the_artifacts_we_think_it_does(two_runs: tuple[Path, Path]) -> None:
    first, _ = two_runs
    written = sorted(p.name for p in first.iterdir())
    assert written == [
        "assessment.json",
        "current_sweep.csv",
        "figure_strength_duration.pdf",
        "figure_strength_duration.svg",
        "figure_summary.pdf",
        "figure_summary.svg",
        "figure_summary.tiff",
        "safety_report.pdf",
    ]


def test_every_artifact_is_byte_identical_across_two_runs(two_runs: tuple[Path, Path]) -> None:
    first, second = two_runs
    differing = [
        p.name
        for p in sorted(first.iterdir())
        if p.read_bytes() != (second / p.name).read_bytes()
    ]
    assert differing == [], f"non-reproducible artifacts: {differing}"


def test_the_pinned_date_reaches_every_artifact_that_carries_one(
    two_runs: tuple[Path, Path],
) -> None:
    """Determinism must come from pinning the date, not from deleting it.

    ``SOURCE_DATE_EPOCH=1234567890`` is 2009-02-13. If a future change makes the output
    reproducible by dropping the timestamps instead of honouring the epoch, this fails.
    """
    first, _ = two_runs

    svg = (first / "figure_summary.svg").read_text(encoding="utf-8")
    assert re.search(r"<dc:date>2009-02-13T23:31:30", svg), "SVG date not pinned to the epoch"

    for name in ("figure_summary.pdf", "safety_report.pdf"):
        blob = (first / name).read_bytes()
        assert b"D:20090213233130" in blob, f"{name} creation date not pinned to the epoch"


def test_the_visible_byline_follows_the_pinned_date(tmp_path: Path) -> None:
    """The PDF prints "Generated <stamp>" in its own body, to the minute.

    Byte-identity across two back-to-back runs is otherwise luck: the two runs land in
    the same minute almost always and in different minutes about once every few hundred
    runs, which is a flake, not a gate.
    """
    import shutil

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext (poppler) not available")

    from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
    from neurostim.io.report import build_report

    os.environ["SOURCE_DATE_EPOCH"] = PINNED_EPOCH
    try:
        calc = SafetyCalculator(DiscElectrode(200.0, "Pt"), StimProtocol(20, 200, 130, 1))
        out = build_report(calc, tmp_path / "r.pdf")
    finally:
        del os.environ["SOURCE_DATE_EPOCH"]

    text = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"], capture_output=True, text=True, check=True
    ).stdout
    assert "Generated 2009-02-13 23:31 UTC" in text


class TestBuildTimestamp:
    """``neurostim._repro`` -- the one place the wall clock is read."""

    def test_unset_means_the_wall_clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from datetime import datetime, timezone

        from neurostim import _repro

        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        assert _repro.source_date_epoch() is None
        assert _repro.is_pinned() is False
        delta = abs((_repro.build_time() - datetime.now(timezone.utc)).total_seconds())
        assert delta < 60.0

    def test_set_means_that_instant_in_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from neurostim import _repro

        monkeypatch.setenv("SOURCE_DATE_EPOCH", PINNED_EPOCH)
        assert _repro.source_date_epoch() == 1234567890
        assert _repro.is_pinned() is True
        assert _repro.build_time().strftime("%Y-%m-%d %H:%M UTC") == "2009-02-13 23:31 UTC"

    def test_blank_is_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from neurostim import _repro

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "   ")
        assert _repro.source_date_epoch() is None

    def test_a_malformed_value_is_an_error_not_a_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Silently falling back to the wall clock would make a build look reproducible."""
        from neurostim import _repro

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "yesterday")
        with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH must be an integer"):
            _repro.source_date_epoch()


def test_svg_element_ids_are_salted_deterministically(two_runs: tuple[Path, Path]) -> None:
    """The half of SVG drift that SOURCE_DATE_EPOCH does not touch.

    matplotlib salts generated element ids from a per-process ``uuid4`` unless
    ``rcParams["svg.hashsalt"]`` is set, so two runs produce files of identical length
    that differ on every ``<path id=...>`` and every ``xlink:href``.
    """
    first, second = two_runs
    pattern = re.compile(r'id="(m[0-9a-f]{10})"')
    ids_a = pattern.findall((first / "figure_summary.svg").read_text(encoding="utf-8"))
    ids_b = pattern.findall((second / "figure_summary.svg").read_text(encoding="utf-8"))
    assert ids_a, "no salted element ids found -- has the SVG structure changed?"
    assert ids_a == ids_b
