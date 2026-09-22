"""Phase 1 -- the verdict core.

Everything the package says about *how much current is safe* is settled here: the
status ordering, the flooring of every reported limit, the per-check margin, the
refusal to report a limit at all when no amplitude is safe, and the minimum that
produces the headline.

Expected values in this file come from one of three places, never from the code path
under test:

* ``tests.oracles`` -- an independently written binary search over ``assess().failed``,
  which reads one bit per probe and no package-computed number;
* IEEE float semantics (``math.nextafter``), which is the definition of "floors";
* a literature constant quoted in the test, back-solved by hand in the docstring.
"""

from __future__ import annotations

import pytest

from neurostim import (
    DiscElectrode,
    SafetyCalculator,
    StimProtocol,
)
from neurostim.safety.assessment import Status


def pdf_text(calc: SafetyCalculator, path) -> str:
    """Render the PDF report and return its extracted text, whitespace collapsed.

    ``pdftotext`` rather than a Python PDF reader because that is what the rest of the
    suite uses and what is installed; the point of extracting at all is that the assertion
    lands on what reaches the page, not on the string the renderer assembled.
    """
    import re
    import shutil
    import subprocess

    from neurostim.io import build_report

    if shutil.which("pdftotext") is None:  # pragma: no cover - environment dependent
        pytest.skip("pdftotext (poppler) not available")
    out = build_report(calc, path)
    raw = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return re.sub(r"\s+", " ", raw)


class TestStatusRank:
    """NOT_EVALUATED must sit below PASS (ledger 11, fix plan D1).

    Today ``PASS.rank == 0`` and ``NOT_EVALUATED.rank == 1``, so ``_worst`` -- a max over
    ranks -- makes an overall PASS unreachable for any macroelectrode: three of the nine
    checks do not apply above the macro/micro boundary and their NOT_EVALUATED outranks
    every PASS beside them.
    """

    def test_rank_order_is_not_evaluated_pass_caution_fail(self):
        """Four explicit inequalities, written out rather than derived from the mapping.

        Not tautological: each side is a literal member of the enum and the expected
        ordering is stated here, so a mapping that reorders any pair fails this.
        """
        assert Status.NOT_EVALUATED.rank < Status.PASS.rank
        assert Status.PASS.rank < Status.CAUTION.rank
        assert Status.CAUTION.rank < Status.FAIL.rank
        assert Status.NOT_EVALUATED.rank < Status.FAIL.rank

    def test_a_macroelectrode_within_every_applicable_limit_reports_pass(self):
        """T17. A 2 mm SIROF disc at 20 uA / 400 us / 50 Hz passes everything that ran.

        Not tautological: the expected status is named literally (``Status.PASS``) and the
        case is one where three checks are genuinely NOT_EVALUATED -- Microelectrode
        charge/phase and Chronic degradation do not apply, and no compliance voltage was
        supplied -- so it is exactly the configuration today's ordering makes unreachable.
        """
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )
        assessment = calc.assess()

        assert {c.status for c in assessment.checks} == {
            Status.PASS,
            Status.NOT_EVALUATED,
        }
        assert assessment.status is Status.PASS

    def test_a_check_that_did_not_run_cannot_be_the_overall_verdict(self):
        """The same case, stated as the property rather than the instance.

        Not tautological: it compares the overall status against the worst status among
        the checks that *ran*, computed here from the check list, not from
        ``assessment.status``.
        """
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )
        assessment = calc.assess()
        ran = [c for c in assessment.checks if c.status is not Status.NOT_EVALUATED]

        assert ran
        assert assessment.status is max(
            (c.status for c in ran), key=lambda s: s.rank
        )


class TestUnevaluatedChecksAreDisclosed:
    """A bare ``PASS`` over a knowingly incomplete check set is less informative than
    today's ``NOT_EVALUATED``. Every headline surface must name what did not run
    (fix plan D1, execution M9).
    """

    @staticmethod
    def _macro_calc() -> SafetyCalculator:
        return SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )

    def test_not_evaluated_collects_the_checks_that_did_not_run(self):
        """Not tautological: the expected names are written out, and the count is the
        literal 3, neither read from the assessment."""
        assessment = self._macro_calc().assess()

        assert [c.name for c in assessment.not_evaluated] == [
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        ]

    def test_describe_names_the_checks_that_did_not_run(self):
        """Not tautological: the expected substring is a literal, and the assertion that
        the overall line carries it rules out a disclosure printed somewhere a reader of
        the headline would not see."""
        text = self._macro_calc().describe()
        overall = next(
            line for line in text.splitlines() if line.startswith("Overall:")
        )

        assert "PASS" in overall
        assert "3 checks not evaluated" in overall
        assert "Compliance voltage" in overall

    def test_report_to_json_discloses_the_checks_that_did_not_run(self):
        """Not tautological: the expected list is written out, against a payload key that
        does not exist today.

        Top-level rather than inside ``results``: ``results`` is ``calc.report()``, whose
        keys become columns of ``current_sweep.csv``, and a list does not belong in a CSV
        cell.
        """
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._macro_calc()))

        assert payload["not_evaluated"] == [
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        ]

    def test_the_pdf_header_discloses_the_checks_that_did_not_run(self, tmp_path):
        """Not tautological: the PDF is rendered and its text extracted with pdftotext, so
        the assertion is on what a reader sees, not on the string the code assembled."""
        text = pdf_text(self._macro_calc(), tmp_path / "report.pdf")

        assert "3 checks not evaluated" in text
        assert "Compliance voltage" in text

    def test_an_assessment_with_every_check_run_says_nothing_about_unevaluated(self):
        """The disclosure must not fire when there is nothing to disclose.

        Not tautological: the fixture is a distinct configuration -- a 250 um Pt disc in
        the macro/micro transition band with a compliance voltage supplied, so all nine
        checks run -- and the assertion is that the parenthetical is absent.
        """
        calc = SafetyCalculator(
            DiscElectrode(250.0, "Pt"),
            StimProtocol(5, 200, 130, 1),
            compliance_V=10.0,
        )
        assessment = calc.assess()

        assert assessment.not_evaluated == ()
        overall = next(
            line
            for line in assessment.describe().splitlines()
            if line.startswith("Overall:")
        )
        assert "not evaluated" not in overall
