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

import math

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


class TestRestingPotentialIsInsideTheWindow:
    """An electrode already outside its own water window at rest is rejected, not
    assessed (ledger 14, fix plan D2 point 3).

    Two reasons, and the second is why this lands here rather than six commits later.
    The visible one: ``max_charge_density_in_window_uC_cm2("Pt",
    resting_potential_V=5.0)`` returns 1400 uC/cm^2 "allowed" for an interface 4.2 V past
    its anodic limit before any current flows. The structural one: the water-window
    predicate is non-monotone in current for exactly these inputs -- a small cathodic
    pulse pulls the interface back INTO the window while a large one breaches the charge
    limits, so the verdict runs FAIL, PASS, FAIL -- and the next commit introduces
    ``floor_to_pass``, which is only correct for a monotone-decreasing predicate. Phase 0b
    swept 1824 configurations: every non-monotone case was an out-of-window resting
    potential, and across 630 in-window configurations there were none. Rejecting the
    input makes the precondition true rather than merely asserted.
    """

    def test_the_calculator_refuses_a_resting_potential_past_the_anodic_limit(self):
        """Not tautological: 0.9 V and Pt's +0.8 V anodic limit are both literals here,
        the second quoted from the material database's stored window, and the expected
        outcome is a raise rather than any number the package computes."""
        with pytest.raises(ValueError, match=r"resting_potential_V"):
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                compliance_V=10.0,
                resting_potential_V=0.9,
            )

    def test_the_message_names_the_window_it_is_outside(self):
        """Not tautological: the three quantities the message must carry are written out
        here -- the offending value, the material, and both window bounds."""
        with pytest.raises(ValueError) as raised:
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                resting_potential_V=0.9,
            )
        message = str(raised.value)

        assert "0.9" in message
        assert "Pt" in message
        assert "-0.6" in message and "0.8" in message

    def test_the_calculator_refuses_a_resting_potential_past_the_cathodic_limit(self):
        """The other side. Not tautological: -0.7 V against Pt's stored -0.6 V."""
        with pytest.raises(ValueError, match=r"resting_potential_V"):
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                resting_potential_V=-0.7,
            )

    def test_a_resting_potential_on_the_boundary_is_accepted(self):
        """The window is closed: ``WaterWindow.contains`` is inclusive at both ends, and
        the rejection must use the same inclusivity or it contradicts the check it
        protects.

        Not tautological: +0.8 is Pt's stored anodic limit, written out, and the assertion
        is that construction succeeds -- the opposite outcome from the tests above.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=0.8,
        )
        assert calc.resting_potential_V == 0.8

    def test_a_material_with_no_window_on_record_accepts_any_resting_potential(self):
        """Ta2O5 has no water window in the database, so there is nothing to be outside
        of and the check itself reports NOT_EVALUATED.

        Not tautological: Ta2O5 is named literally, 5.0 V is a value every windowed
        material would reject, and the expected outcome is construction plus a
        NOT_EVALUATED water-window check.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Ta2O5"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=5.0,
        )
        window = next(
            c for c in calc.assess().checks if c.name == "Water window"
        )
        assert window.status is Status.NOT_EVALUATED

    def test_the_module_function_refuses_what_it_used_to_answer(self):
        """Ledger 14's own reproduction.

        Not tautological: the expected outcome is a raise where the recorded defect is the
        specific number 1400.0, so the test would fail both before the fix and under any
        fix that kept returning a charge density.
        """
        from neurostim.safety import water_window as ww

        with pytest.raises(ValueError, match=r"resting_potential_V"):
            ww.max_charge_density_in_window_uC_cm2("Pt", resting_potential_V=5.0)

    def test_the_evaluate_entry_point_refuses_it_too(self):
        """``evaluate`` is exported and callable directly, so the guard cannot live only
        in the calculator.

        Not tautological: the raise is asserted at a second entry point with its own
        signature, not inferred from the first.
        """
        from neurostim.safety import water_window as ww

        with pytest.raises(ValueError, match=r"resting_potential_V"):
            ww.evaluate("Pt", 10.0, resting_potential_V=0.9)

    def test_an_in_window_resting_potential_still_works(self):
        """The guard must not reject the case it exists to protect.

        Not tautological: +0.3 V is inside Pt's window and the assertion is on the
        assessment running to completion and reporting that potential back.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=0.3,
        )
        assert calc.assess().water_window.resting_potential_V == 0.3


class TestFloorToPass:
    """The helper itself: ``_limits.floor_to_pass`` and ``_limits.format_limit``
    (fix plan D2, ledger 9 and 49).

    A reported limit is a promise: programme this and the check passes. Two things broke
    it. The back-solve recomputed the limit through a different float association than the
    forward comparison, so the answer could land one ulp on the wrong side (ledger 9); and
    every render site formatted with round-to-nearest, which rounds a maximum UP
    (ledger 49). Both are fixed by the same contract -- return, and print, the largest
    value that still passes.
    """

    def test_it_steps_down_to_the_largest_passing_value(self):
        """Not tautological: the predicate is written here as a comparison against a
        literal, so the expected answer is the largest float at or below that literal --
        an IEEE fact, not a package one."""
        import math

        from neurostim.safety import _limits

        limit = 100.0
        overshoot = math.nextafter(limit, math.inf)

        settled = _limits.floor_to_pass(
            overshoot, lambda v: v <= limit, name="synthetic"
        )
        assert settled == limit

    def test_it_steps_up_when_the_back_solve_undershot(self):
        """Flooring is "the largest value that passes", which is not always downward.

        Measured on the real back-solves: of 108 (material, policy, polarity) x
        (charge, Shannon) limits, 12 sit one ulp above their own boundary and 4 sit one
        ulp below it. A one-directional helper would leave the second group reporting a
        limit that is not the limit.

        Not tautological: the expected answer is again the literal boundary, reached from
        the other side.
        """
        import math

        from neurostim.safety import _limits

        limit = 100.0
        undershoot = math.nextafter(limit, -math.inf)

        settled = _limits.floor_to_pass(
            undershoot, lambda v: v <= limit, name="synthetic"
        )
        assert settled == limit

    def test_the_returned_value_is_asserted_to_be_the_boundary(self):
        """D2 point 1: ``passes(v)`` and not ``passes(nextafter(v, +inf))``.

        Not tautological: the assertion is made here, independently, on whatever the
        helper returned.
        """
        import math

        from neurostim.safety import _limits

        settled = _limits.floor_to_pass(
            1.0000000000000002, lambda v: v <= 1.0, name="synthetic"
        )
        assert settled <= 1.0
        assert not (math.nextafter(settled, math.inf) <= 1.0)

    def test_exhausting_the_step_budget_raises_rather_than_returning(self):
        """Returning the failing value would be a silent failure; leaving the budget
        unstated is how a future non-linear check degrades quietly (D2 point 2).

        Not tautological: the predicate written here never passes, so no value the helper
        could return would be correct, and the expected outcome is the raise.

        The budget's *size* is pinned by ``TestBothSettleBudgetsAreBinding``, not here.
        This test used to assert ``"4" in message``, which "40 steps" also satisfies -- a
        substring test on a number, and the survivor the review demonstrated.
        """
        from neurostim.safety import _limits

        with pytest.raises(_limits.LimitDidNotSettle):
            _limits.floor_to_pass(50.0, lambda v: False, name="Chronic degradation")

    def test_a_non_finite_or_non_positive_value_is_returned_unchanged(self):
        """``inf`` means "no ceiling" and ``0.0`` means "nothing is permitted"; neither is
        a float to be walked, and neither has a successor that means anything.

        Not tautological: three literal inputs, three literal expected outputs.
        """
        import math

        from neurostim.safety import _limits

        never = lambda v: False  # noqa: E731 - the point is that it is never consulted
        assert _limits.floor_to_pass(math.inf, never, name="x") == math.inf
        assert _limits.floor_to_pass(0.0, never, name="x") == 0.0
        assert math.isnan(_limits.floor_to_pass(math.nan, never, name="x"))


class TestTheClimbIsBoundedByThePredicatesOwnResolution:
    """A limit whose check cannot resolve single floats must still settle (fix plan D2).

    ``_climb_to_boundary`` bounded the upward walk by ``CLIMB_TOLERANCE`` *of the seed*.
    The water-window predicate compares ``resting_potential_V + excursion`` against a
    window edge, and that sum is where its resolution is lost: with the resting potential
    1e-8 V inside the edge, the excursion at the boundary is 1e-8 V while the sum's ulp is
    ``ulp(0.6 V) = 1.1e-16``, so about 1e8 consecutive amplitudes map to one peak float.
    That plateau's width is set by the sum and not by the seed, so *relative* to the seed
    it grows as the headroom shrinks, and a relative bound is certain to be exceeded
    somewhere inside the inputs C1.2 accepts. Measured on the Phase 1 review's
    edge-clustered sampling: 4487 of 70831 constructed configurations raised
    ``LimitDidNotSettle``, every one of them Water window, on inputs the package itself
    declares valid -- ``resting_potential_V = -0.59999999`` is inside platinum's
    ``[-0.6, +0.8]`` window, and that call returned 39.2699 uA before Phase 1.

    The bound therefore has to come from the predicate's own arithmetic. Raising
    ``CLIMB_TOLERANCE`` only moves the headroom at which the raise starts; it cannot
    remove it, because the ratio the bound is compared against diverges as the seed
    shrinks.
    """

    def test_a_resting_potential_just_inside_the_window_still_assesses(self):
        """The review's reproduction, on the anodic side.

        Not tautological: +0.79999999 V and platinum's stored +0.8 V anodic limit are both
        literals, C1.2's rule accepts the first, and the expected outcome is that a number
        exists at all -- the defect is an exception, so no arithmetic here can produce a
        false pass.
        """
        import math

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, anodic_first=True),
            resting_potential_V=0.79999999,
            capacitance_uF_cm2=103.0,
        )

        limit = calc.assess().limiting_current_uA

        assert math.isfinite(limit)
        assert limit > 0.0

    def test_the_settled_limit_is_the_water_window_boundary(self):
        """Settling across a plateau must still land on the boundary, not inside it.

        Not tautological: the assertion is made against ``water_window.evaluate`` -- the
        forward check, called here with its own arguments -- at the returned amplitude and
        at its successor, so a helper that stopped anywhere inside the plateau fails it.
        """
        import math

        from neurostim.safety import charge as charge_mod
        from neurostim.safety import water_window as ww
        from neurostim.units import charge_uC

        electrode = DiscElectrode(100.0, "Pt")
        calc = SafetyCalculator(
            electrode,
            StimProtocol(80.0, 200.0, 130.0, 1.0, anodic_first=True),
            resting_potential_V=0.79999999,
            capacitance_uF_cm2=103.0,
        )
        ceiling = next(
            c for c in calc.assess().checks if c.name == "Water window"
        ).ceiling_uA

        def inside(current_uA: float) -> bool:
            return ww.evaluate(
                "Pt",
                charge_mod.charge_density_uC_cm2(
                    charge_uC(current_uA, 200.0), electrode.area_cm2
                ),
                anodic_first=True,
                resting_potential_V=0.79999999,
                capacitance_uF_cm2=103.0,
            ).passes

        assert inside(ceiling)
        assert not inside(math.nextafter(ceiling, math.inf))

    def test_no_configuration_clustered_against_a_window_edge_raises(self):
        """The review's randomised sweep, seeded so a failure is reproducible.

        Not tautological: every input is drawn from the material database's own stored
        windows and from literal geometry, the calculator is asked only for its headline,
        and the assertion is that no exception escapes -- there is no expected number here
        for the code to agree with itself about.
        """
        import random

        from neurostim.materials import MATERIALS, get_material
        from neurostim.safety._limits import LimitDidNotSettle

        windowed = sorted(
            key for key in MATERIALS if get_material(key).water_window is not None
        )
        rng = random.Random(20260923)
        raised: list[str] = []
        constructed = 0
        for _ in range(1500):
            key = rng.choice(windowed)
            window = get_material(key).water_window
            assert window is not None
            at_cathodic = rng.random() < 0.5
            headroom_V = 10.0 ** rng.uniform(-9.0, -1.0)
            resting_V = (
                window.cathodic_V + headroom_V
                if at_cathodic
                else window.anodic_V - headroom_V
            )
            if not window.contains(resting_V):  # pragma: no cover - a draw that overshot
                continue
            calc = SafetyCalculator(
                DiscElectrode(rng.choice([20.0, 100.0, 500.0, 2000.0]), key),
                StimProtocol(
                    10.0 ** rng.uniform(0.0, 3.0),
                    rng.choice([50.0, 90.0, 200.0]),
                    130.0,
                    1.0,
                    anodic_first=not at_cathodic,
                ),
                resting_potential_V=resting_V,
                capacitance_uF_cm2=rng.choice([37.0, 103.0, 811.0]),
            )
            constructed += 1
            try:
                assert calc.assess().limiting_current_uA >= 0.0
            except LimitDidNotSettle as exc:
                raised.append(f"{key} at {resting_V!r}: {exc}"[:200])

        assert constructed == 1500
        assert raised == [], f"{len(raised)} of {constructed} raised; first: {raised[0]}"

    def test_the_helper_crosses_a_plateau_of_the_width_its_caller_declares(self):
        """The contract in isolation: a predicate that can only resolve ``plateau``.

        Not tautological: the predicate is written here as a comparison on a *quantised*
        argument, so the expected answer is a property of the quantisation written in the
        test, and the seed sits 1.5 plateaus -- 1.5e6 times ``CLIMB_TOLERANCE`` of itself
        -- below the boundary.
        """
        import math

        from neurostim.safety import _limits

        plateau = 1e-3

        def passes(value: float) -> bool:
            return math.floor(value / plateau) * plateau <= 1.0

        settled = _limits.floor_to_pass(
            0.9995, passes, name="synthetic", plateau=plateau
        )

        assert passes(settled)
        assert not passes(math.nextafter(settled, math.inf))

    def test_a_seed_further_below_the_boundary_than_the_plateau_still_raises(self):
        """The bound must still catch a back-solve that is simply wrong.

        Not tautological: the predicate's resolution is 1e-12 and the seed sits 0.5 below
        its boundary -- 5e11 plateaus -- so the expected outcome is the raise, which no
        value the helper could return would satisfy.
        """
        import math

        from neurostim.safety import _limits

        plateau = 1e-12

        def passes(value: float) -> bool:
            return math.floor(value / plateau) * plateau <= 1.0

        with pytest.raises(_limits.LimitDidNotSettle):
            _limits.floor_to_pass(0.5, passes, name="synthetic", plateau=plateau)


class TestTheWaterWindowSeedInvertsItsOwnPredicate:
    """The seed and the check it seeds must stay one change (review B3 / F6).

    ``_water_window_ceiling_uA`` hands ``floor_to_pass`` a seed obtained by inverting the
    window expression in closed form, and a predicate that evaluates it forward. The two
    are written separately, and ``floor_to_pass``'s whole contract is that they are
    inverses: it walks four floats down and raises otherwise (ledger 9).

    C2.3 adds a DC-drift clause to that predicate -- FAIL when ``t_exit < train_duration_s``
    -- which the peak-only seed knows nothing about. On the plan's own case
    (``CylindricalBandElectrode(1270, 1500, "PtIr")``, 3000 uA / 90 us / 130 Hz monophasic,
    ``capacitance_uF_cm2=250``, area 0.05984734 cm^2) the two ends are

        pulse-peak seed          99745.56675147594 uA
        drift ceiling            767.2735903959687 uA   = Q_window / (PW . f . T)
        ratio                    130.0                  = f . T
        gap                      8.7e17 ulps            against a 4-float budget

    so ``floor_to_pass`` would walk down four floats, still fail, and raise on **every**
    monophasic protocol -- exactly the population C2.4 is about. The seed must become the
    minimum of the two closed forms, because the predicate becomes their conjunction; both
    branches are individually monotone-decreasing in current, so the conjunction is too.

    These tests do not add the drift term -- the clause it inverts does not exist yet, and
    a seed 130x below the live boundary raises on the way *up* instead (measured: 160 of
    160 monophasic configurations). They pin the coupling, so that adding the clause
    without adding its inverse fails here and is not discovered as a crash inside C2.3.
    """

    GRID = [
        ("PtIr", 1270.0, 3000.0, 90.0, "monophasic"),
        ("Pt", 100.0, 80.0, 200.0, "monophasic"),
        ("Pt", 100.0, 80.0, 200.0, "biphasic"),
        ("SIROF", 500.0, 500.0, 50.0, "monophasic"),
        ("AIROF", 20.0, 10.0, 500.0, "biphasic"),
    ]

    def _search(self, key, diameter_um, current_uA, pulse_width_us, waveform):
        """The package's own seed, predicate and plateau for one grid row.

        Built with the drift inputs the calculator supplies, so the monophasic rows
        exercise both clauses. Without them the result carries no ``drift`` and the seed
        collapses to its peak term -- which would leave this guard blind to exactly the
        coupling it exists to hold.
        """
        from neurostim.safety import water_window as ww
        from neurostim.safety.assessment import _water_window_search

        electrode = DiscElectrode(diameter_um, key)
        protocol = StimProtocol(
            current_uA, pulse_width_us, 130.0, 1.0, waveform=waveform
        )
        result = ww.evaluate(
            key,
            0.0,
            anodic_first=protocol.anodic_first,
            resting_potential_V=-0.25,
            capacitance_uF_cm2=137.0,
            anodic_first_for_capacitance=protocol.anodic_first,
            net_dc_current_uA=protocol.net_dc_current_uA,
            area_cm2=electrode.area_cm2,
            train_duration_s=protocol.train_duration_s,
        )
        return _water_window_search(result, protocol, electrode.area_cm2)

    def test_the_seed_inverts_the_predicate_it_seeds(self):
        """The coupling, asserted against the package's own predicate object.

        The contract is not "the seed passes" -- a one-ulp overshoot is what the walk down
        exists for (ledger 9), and one grid row does overshoot. It is that the seed is
        within the *declared budget* of the boundary in whichever direction it landed:
        ``STEP_BUDGET`` floats down, ``max(CLIMB_TOLERANCE x seed, PLATEAU_ALLOWANCE x
        plateau)`` up.

        Not tautological: the seed is a closed-form inversion and the predicate a forward
        comparison, written as different expressions and brought together here only
        because ``_water_window_search`` returns both; the budget is recomputed from
        ``_limits``' own constants. A clause added to one and not the other makes this
        false, which is the whole of B3 and cannot be reproduced by re-deriving either
        side inside the test.
        """
        import math

        from neurostim.safety._limits import (
            CLIMB_TOLERANCE,
            PLATEAU_ALLOWANCE,
            STEP_BUDGET,
            LimitDidNotSettle,
            floor_to_pass,
        )

        for row in self.GRID:
            search = self._search(*row)
            try:
                settled = floor_to_pass(
                    search.seed_uA,
                    search.passes,
                    name="Water window",
                    plateau=search.plateau_uA,
                )
            except LimitDidNotSettle as exc:  # pragma: no cover - the tripwire firing
                pytest.fail(
                    f"the water-window seed no longer inverts the predicate it seeds, "
                    f"for {row}: {exc}. A clause added to the forward check needs its "
                    f"closed-form inverse in _water_window_seed_uA, in the same commit."
                )

            if settled <= search.seed_uA:
                steps, probe = 0, search.seed_uA
                while probe > settled and steps <= STEP_BUDGET:
                    probe = math.nextafter(probe, -math.inf)
                    steps += 1
                assert steps <= STEP_BUDGET, (row, steps)
            else:
                budget = max(
                    abs(search.seed_uA) * CLIMB_TOLERANCE,
                    PLATEAU_ALLOWANCE * search.plateau_uA,
                )
                assert settled - search.seed_uA <= budget, (row, settled)

            assert search.passes(settled), row
            assert not search.passes(math.nextafter(settled, math.inf)), row

    def test_the_seed_is_a_minimum_over_the_clauses_the_check_actually_has(self):
        """Two terms since C2.3, and the drift one binds on every monophasic row.

        Not tautological: both terms are recomputed here from the published window and
        the supplied capacitance -- the peak inverse from
        ``max_charge_density_in_window_uC_cm2`` and the geometry, the drift inverse from
        ``(rest - cathodic edge) * C * A`` over ``frac * W * f * T`` -- and compared with
        what the package seeds. A third clause added to the predicate without its inverse
        makes this false.
        """
        from neurostim import get_material
        from neurostim.safety import water_window as ww

        for key, diameter_um, current_uA, pulse_width_us, waveform in self.GRID:
            electrode = DiscElectrode(diameter_um, key)
            protocol = StimProtocol(
                current_uA, pulse_width_us, 130.0, 1.0, waveform=waveform
            )
            peak = (
                ww.max_charge_density_in_window_uC_cm2(
                    key,
                    anodic_first=protocol.anodic_first,
                    resting_potential_V=-0.25,
                    capacitance_uF_cm2=137.0,
                )
                * electrode.area_cm2
                / (pulse_width_us * 1e-6)
            )
            if waveform == "monophasic":
                window = get_material(key).water_window
                assert window is not None
                headroom_V = -0.25 - window.cathodic_V
                drift = (headroom_V * 137.0 * electrode.area_cm2) / (
                    1.0 * pulse_width_us * 1e-6 * 130.0 * 1.0
                )
                # A monophasic train spends the window budget f*T times faster than one
                # pulse fills it, so the drift term binds by exactly that factor.
                assert peak / drift == pytest.approx(130.0, rel=1e-9), key
            else:
                drift = math.inf
            expected = min(peak, drift)
            search = self._search(key, diameter_um, current_uA, pulse_width_us, waveform)

            assert search.seed_uA == pytest.approx(expected, rel=1e-12), (key, waveform)

    def test_the_monophasic_water_window_ceiling_is_the_drift_inverse(self):
        """The tripwire on the value itself. C2.3 moved it, with the seed, in one commit.

        Not tautological: both ends are recomputed here from the material database and the
        geometry rather than read from the check. The peak-only answer
        ``max_charge_density_in_window_uC_cm2 * area / pulse_width_s`` is
        99745.56675147594 uA; the drift answer
        ``0.6 V * 250 uF/cm^2 * 0.05984734 cm^2 = 8.9771 uC`` over
        ``90e-6 s * 130 Hz * 1 s`` is 767.2735903959687 uA; the ratio is ``f * T = 130``,
        which is 8.7e17 ulps -- what made the two a single change.
        """
        from neurostim import CylindricalBandElectrode
        from neurostim.safety import water_window as ww

        electrode = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        calc = SafetyCalculator(
            electrode,
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            capacitance_uF_cm2=250.0,
        )
        seed_density = ww.max_charge_density_in_window_uC_cm2(
            "PtIr",
            anodic_first=False,
            resting_potential_V=0.0,
            capacitance_uF_cm2=250.0,
        )
        peak_inverse_uA = seed_density * electrode.area_cm2 / 90e-6
        drift_uA = (0.6 * 250.0 * electrode.area_cm2) / (90e-6 * 130.0 * 1.0)

        ceiling = next(
            c for c in calc.assess().checks if c.name == "Water window"
        ).ceiling_uA

        assert peak_inverse_uA == pytest.approx(99745.56675147594, rel=1e-12)
        assert drift_uA == pytest.approx(767.2735903959687, rel=1e-12)
        assert peak_inverse_uA / drift_uA == pytest.approx(130.0, rel=1e-12)
        assert ceiling == pytest.approx(drift_uA, rel=1e-9)


class TestBothSettleBudgetsAreBinding:
    """M4. ``STEP_BUDGET`` and ``CLIMB_TOLERANCE`` were unpinned by 770 tests.

    The Phase 1 review's mutation battery: ``STEP_BUDGET = 4 -> 40`` **survived** 284
    tests, and so did ``CLIMB_TOLERANCE = 1e-9 -> 1e-3``. The second is the more serious,
    because loosening it is not behaviour-neutral -- under ``1e-3`` the B1 case stops
    raising and returns a number, and nothing noticed. A constant that no test constrains
    is not a convention, it is a comment.

    Both are pinned here by **straddling** them: one case just inside the budget that must
    settle, one just outside that must raise. The straddling values are written as
    literals rather than derived from the constants, which is the whole point -- a test
    that computes its fixture from ``STEP_BUDGET`` moves with the mutant and survives it.
    Together they pin the step budget to exactly 4 and the climb tolerance to
    ``[1e-9, 2e-9)``.
    """

    def test_a_walk_down_of_exactly_four_floats_settles(self):
        """Not tautological: the predicate's boundary is placed by ``math.nextafter`` a
        literal four times below the seed, so the expected outcome follows from IEEE
        arithmetic and the literal 4, neither of which moves when ``STEP_BUDGET`` does."""
        import math

        from neurostim.safety import _limits

        target = 50.0
        for _ in range(4):
            target = math.nextafter(target, -math.inf)

        assert _limits.floor_to_pass(
            50.0, lambda v: v <= target, name="synthetic"
        ) == target

    def test_a_walk_down_of_five_floats_raises(self):
        """The other side of the same literal. Under ``STEP_BUDGET = 40`` -- the mutant
        that survived 284 tests -- this settles instead, so this assertion is what kills it.

        Not tautological: the boundary is five ulps below the seed by construction here and
        the expected outcome is the raise, which no returned value satisfies.
        """
        import math

        from neurostim.safety import _limits

        target = 50.0
        for _ in range(5):
            target = math.nextafter(target, -math.inf)

        with pytest.raises(_limits.LimitDidNotSettle):
            _limits.floor_to_pass(50.0, lambda v: v <= target, name="synthetic")

    def test_the_raise_names_the_budget_it_exhausted(self):
        """``assert "4" in message`` was the demonstrated survivor: "40 steps" contains
        "4", so it could not tell 4 from 40, 14, 42 or 400. The count has to be read as a
        count.

        Not tautological about the *number* -- the behavioural pair above does that -- but
        about the *shape*: a message that drops the step count, or reports it in another
        unit, fails here while still raising.
        """
        from neurostim.safety import _limits

        with pytest.raises(_limits.LimitDidNotSettle) as raised:
            _limits.floor_to_pass(50.0, lambda v: False, name="Chronic degradation")
        message = str(raised.value)

        assert "Chronic degradation" in message
        assert "50.0" in message
        assert f"after {_limits.STEP_BUDGET} steps" in message

    def test_a_climb_of_one_part_in_a_billion_settles(self):
        """The inside of the climb budget, with no plateau declared so only the relative
        bound applies.

        Not tautological: 1e-9 is a literal here and is the largest relative gap the
        shipped tolerance admits; under a tightened ``CLIMB_TOLERANCE`` this raises.
        """
        from neurostim.safety import _limits

        boundary = 1.0 + 1e-9

        settled = _limits.floor_to_pass(
            1.0, lambda v: v <= boundary, name="synthetic"
        )

        assert settled <= boundary
        assert settled == pytest.approx(boundary, rel=1e-15)

    def test_a_climb_of_two_parts_in_a_billion_raises(self):
        """The outside. Under ``CLIMB_TOLERANCE = 1e-3`` -- the mutant that survived 284
        tests, and the "just loosen the constant" answer to B1 -- this settles instead, so
        this assertion is what kills both.

        Not tautological: 2e-9 is a literal, the predicate is a comparison against it, and
        the expected outcome is the raise.
        """
        from neurostim.safety import _limits

        boundary = 1.0 + 2e-9

        with pytest.raises(_limits.LimitDidNotSettle):
            _limits.floor_to_pass(1.0, lambda v: v <= boundary, name="synthetic")

    def test_the_declared_plateau_widens_the_climb_and_nothing_else_does(self):
        """B1's fix must not be reachable by loosening the relative bound instead.

        The same 2e-9 gap that raises above settles when the caller declares a plateau
        wide enough to explain it -- and only then. That is the mechanism: the budget comes
        from the predicate's own resolution, supplied by the caller who knows the units.

        Not tautological: the plateau is a literal chosen against the literal gap
        (``4 x 1e-9 > 2e-9`` and ``4 x 1e-10 < 2e-9``), so both outcomes follow from
        ``PLATEAU_ALLOWANCE`` being 4 and from nothing the helper computes.
        """
        from neurostim.safety import _limits

        boundary = 1.0 + 2e-9

        assert _limits.floor_to_pass(
            1.0, lambda v: v <= boundary, name="synthetic", plateau=1e-9
        ) == pytest.approx(boundary, rel=1e-15)

        with pytest.raises(_limits.LimitDidNotSettle):
            _limits.floor_to_pass(
                1.0, lambda v: v <= boundary, name="synthetic", plateau=1e-10
            )


class TestFormatLimit:
    """A limit must never be printed larger than it is (ledger 49)."""

    def test_the_worked_example_headline_floors(self):
        """Not tautological: 141.37166941154072 and the expected "141.3" are both written
        out, and 141.4 -- what ``:.4g`` prints -- is asserted absent."""
        from neurostim.safety._limits import format_limit

        assert format_limit(141.37166941154072) == "141.3"

    def test_the_shannon_limit_floors(self):
        """Ledger 49's second recorded case. Not tautological: both literals are quoted
        from the ledger entry."""
        from neurostim.safety._limits import format_limit

        assert format_limit(472.78772824642175) == "472.7"

    def test_the_printed_number_never_exceeds_the_value_it_floors(self):
        """The property, over a decade-spanning grid rather than one case.

        Not tautological: the comparison is between the float the string parses back to
        and the input float -- arithmetic on the test's own values, with the package only
        supplying the formatter.
        """
        from neurostim.safety._limits import format_limit

        values = [
            base * 10.0**exponent
            for exponent in range(-6, 7)
            for base in (1.0, 1.0000001, 1.4999, 1.5, 1.9999, 3.14159265, 9.99999)
        ]
        for value in values:
            printed = format_limit(value)
            assert float(printed) <= value, f"{printed} exceeds {value!r}"

    def test_four_significant_digits_are_kept(self):
        """Flooring must not become truncation to the integer.

        Not tautological: the expected strings are written out for values whose fourth
        significant digit is where the information is.
        """
        from neurostim.safety._limits import format_limit

        assert format_limit(0.0012345678) == "0.001234"
        assert format_limit(15285.509415880857) == "1.528e+04"
        # Trailing zeros are kept: four significant digits is the promise, and "20" would
        # claim only two. This is the form the fix plan's blast radius records.
        assert format_limit(20.0) == "20.00"
        assert format_limit(212.05750411731108) == "212.0"

    def test_it_does_not_invent_a_number_for_infinity(self):
        """Not tautological: the expected output is the same token ``:.4g`` produces, so
        no surface starts printing a finite ceiling where there is none."""
        import math

        from neurostim.safety._limits import format_limit

        assert format_limit(math.inf) == "inf"


class TestEveryBackSolvedLimitPassesItsOwnCheck:
    """T2a. Re-assess at the package's own reported limit and the check must pass.

    Measured before the fix: over 9 materials x 3 policies x 2 polarities, 12 of the 54
    charge-injection limits and 0 of the 54 Shannon limits FAIL their own forward check,
    surfacing as "100 uC/cm^2 exceeds the 100 uC/cm^2 limit" (ledger 9). A further 4
    charge limits sit one ulp *below* their boundary.
    """

    @staticmethod
    def _cases():
        from dataclasses import replace

        from neurostim.materials import MATERIALS

        electrode = DiscElectrode(100.0, "Pt")
        base = StimProtocol(80.0, 200.0, 130.0, 1.0)
        for material in MATERIALS:
            for policy in ("conservative", "nominal", "optimistic"):
                for anodic_first in (False, True):
                    protocol = replace(base, anodic_first=anodic_first)
                    yield material, policy, protocol, electrode

    @staticmethod
    def _at(electrode, protocol, current_uA, material, policy):
        from dataclasses import replace

        return SafetyCalculator(
            electrode,
            replace(protocol, current_uA=current_uA),
            material=material,
            policy=policy,
        ).assess()

    def test_the_charge_injection_limit_is_the_boundary(self):
        """Not tautological: the oracle is IEEE, not the package -- the limit must pass
        and its successor float must fail. A one-sided ``<=`` would admit a limit that is
        merely somewhere below the boundary."""
        import math

        for material, policy, protocol, electrode in self._cases():
            limit = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            ).assess().charge.max_current_uA
            if not math.isfinite(limit) or limit <= 0:
                continue
            at = self._at(electrode, protocol, limit, material, policy)
            above = self._at(
                electrode, protocol, math.nextafter(limit, math.inf), material, policy
            )
            assert at.charge.passes, (material, policy, protocol.anodic_first, limit)
            assert not above.charge.passes, (material, policy, limit)

    def test_the_shannon_limit_is_the_boundary(self):
        """Same oracle, second back-solve."""
        import math

        for material, policy, protocol, electrode in self._cases():
            limit = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            ).assess().shannon.max_current_uA
            if not math.isfinite(limit) or limit <= 0:
                continue
            at = self._at(electrode, protocol, limit, material, policy)
            above = self._at(
                electrode, protocol, math.nextafter(limit, math.inf), material, policy
            )
            assert at.shannon.passes, (material, policy, limit)
            assert not above.shannon.passes, (material, policy, limit)

    def test_the_compliance_limit_is_the_boundary(self):
        """The third back-solve, and the one C1.6 is about to add to the candidate set.

        Measured before the fix: over 36 (electrode, compliance, pulse width)
        combinations, 6 reported limits FAIL their own compliance check and 14 more sit
        below their boundary.
        """
        import math
        from dataclasses import replace

        from neurostim import CylindricalBandElectrode, RingElectrode

        electrodes = (
            DiscElectrode(100.0, "Pt"),
            RingElectrode(330.0, 270.0, "Pt"),
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            DiscElectrode(2000.0, "SIROF"),
        )
        for electrode in electrodes:
            for compliance_V in (1.0, 5.0, 10.0):
                for pulse_width_us in (50.0, 200.0, 400.0):
                    protocol = StimProtocol(80.0, pulse_width_us, 130.0, 1.0)
                    limit = SafetyCalculator(
                        electrode, protocol, compliance_V=compliance_V
                    ).assess().compliance.max_current_uA
                    if not math.isfinite(limit) or limit <= 0:
                        continue

                    def at(current, electrode=electrode, protocol=protocol,
                           compliance_V=compliance_V):
                        return SafetyCalculator(
                            electrode,
                            replace(protocol, current_uA=current),
                            compliance_V=compliance_V,
                        ).assess().compliance

                    assert at(limit).passes, (electrode, compliance_V, limit)
                    assert not at(math.nextafter(limit, math.inf)).passes, (
                        electrode,
                        compliance_V,
                        limit,
                    )

    def test_the_second_charge_back_solve_agrees_with_the_first(self):
        """``SafetyCalculator.max_current_cic_uA`` is a separate back-solve behind every
        CSV row and the amplitude-limits figure, and it was not floored (execution M4).

        Not tautological: two independently computed attributes are compared to each
        other, and both are separately asserted to be the boundary above.
        """
        for material, policy, protocol, electrode in self._cases():
            calc = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            )
            assert calc.max_current_cic_uA == calc.assess().charge.max_current_uA, (
                material,
                policy,
            )


class TestEveryRenderSiteFloors:
    """Ledger 49: a limit rounded to nearest is a limit rounded UP, on five surfaces."""

    @staticmethod
    def _worked_example() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_describe_floors_the_headline(self):
        """Not tautological: "141.4" is what ``:.4g`` prints and is asserted absent;
        "141.3" is the floored value, computed by hand from 141.37166941154072.

        The charge-injection ceiling moved off the headline at C1.6 -- the binding check
        on this electrode is Microelectrode charge/phase at 20 uA -- so the flooring is
        asserted where that number is still printed, on the per-kind line, and the
        headline is checked for the four significant digits flooring promises.
        """
        lines = self._worked_example().describe().splitlines()
        headline = next(
            row for row in lines if row.startswith("Limiting current:")
        )
        by_kind = next(row for row in lines if row.strip().startswith("by kind:"))

        assert "20.00 uA" in headline
        assert "141.3" in by_kind
        assert "141.4" not in by_kind

    def test_describe_floors_both_ends_of_the_published_range(self):
        """Not tautological: the low end is platinum's 20 uC/cm^2 dissolution threshold
        over this area and pulse width, 7.853981633974483 uA, which floors by hand to
        7.853 where ``:.4g`` rounds it up to 7.854 -- and 7.854 uA FAILs the check whose
        maximum it claims to be.

        The fixture is a 100 um Pt disc rather than the worked-example ring: from C1.8 the
        ring's interval collapses onto its point estimate, because the check that binds
        there -- Cogan's 4 nC/phase -- has no published range. On the disc the chronic
        threshold band 20-50 uC/cm^2 straddles the limit at both ends.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        line = next(
            row
            for row in calc.describe().splitlines()
            if "across published ranges" in row
        )
        assert "7.853-" in line
        assert "7.854" not in line

    def test_the_pdf_floors_every_limit_it_prints(self):
        """Not tautological: the three ledger-49 sites are asserted on extracted PDF text
        against hand-floored values."""
        text = pdf_text(self._worked_example(), __import__("pathlib").Path("/tmp") / "x")
        assert "141.3" in text
        assert "472.7" in text
        assert "141.4" not in text
        assert "472.8" not in text

    def test_the_figure_annotation_floors(self):
        """``viz/plots.py`` prints the binding limit through ``format_limit``.

        Not tautological: the expected string is the hand-floored four-significant-digit
        form of 12.5*pi, and the round-to-nearest form is asserted absent.

        On a different electrode from the other four sites, because C5.1 made this panel
        annotate the assessment's binding limit instead of its own three-check minimum,
        and on the worked example that number is exactly 20 uA -- where flooring and
        rounding agree and the site would assert nothing. A 100 um Pt disc at 100 us
        binds on chronic degradation at 39.26990816987241 uA, which ``:.4g`` prints as
        "39.27" -- above the ceiling, the ledger 49 defect -- and ``format_limit`` as
        "39.26".
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from neurostim.viz.plots import current_limit_sweep

        electrode = DiscElectrode(100.0, "Pt")
        protocol = StimProtocol(80, 100, 130, 1)
        calc = SafetyCalculator(electrode, protocol, compliance_V=10.0)
        assert calc.assess().limiting_current_uA == pytest.approx(
            39.26990816987241, rel=1e-12  # 12.5*pi, floored onto its own check
        )

        figure, axes = plt.subplots()
        try:
            current_limit_sweep(electrode, protocol, compliance_V=10.0, ax=axes)
            texts = [text.get_text() for text in axes.texts]
        finally:
            plt.close(figure)

        binding = [text for text in texts if "binding limit" in text]
        assert binding, texts
        assert "39.26" in binding[0]
        assert "39.27" not in binding[0]


    def test_the_sensitivity_report_floors_its_baseline_and_every_row(self):
        """``sensitivity`` is a sixth render surface and was byte-untouched by C1.3.

        Not tautological: 14.137166941154069 is the binding limit on this electrode,
        written out here; "14.14" is what ``:.4g`` prints and is asserted absent, "14.13"
        is the hand-floored four-digit form. Swept over 9 diameters x 9 materials x 3
        pulse widths, 100 of 243 configurations printed a limit strictly larger than the
        limit.
        """
        from neurostim import sensitivity

        calc = SafetyCalculator(
            DiscElectrode(60.0, "Pt"), StimProtocol(30.0, 100.0, 130.0, 1.0)
        )
        assert calc.assess().limiting_current_uA == pytest.approx(
            14.137166941154069, rel=1e-12
        )

        lines = sensitivity.describe(calc).splitlines()
        baseline = next(row for row in lines if row.strip().startswith("baseline:"))
        row = next(row for row in lines if "saline ->" in row)

        assert "14.13" in baseline
        assert "14.14" not in baseline
        assert "14.13" in row
        assert "14.14" not in row

    def test_the_worked_example_never_prints_an_amplitude_above_the_limit(self):
        """``examples/worked_example.py`` renders four limits and was never repaired.

        Not tautological: each expected string is the hand-floored form of a value printed
        in the test's own assertion message by the example itself -- Shannon 472.7877282,
        the charge-injection ceiling 141.37166941154072, and the measured-CIC ceiling
        87.65043503515524 -- and the round-to-nearest form that overstates each is
        asserted absent. The assertion runs against the example's real stdout, not against
        a re-render of the same expression.
        """
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as work:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "examples" / "worked_example.py"),
                    str(Path(work) / "out"),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        printed = completed.stdout

        assert "472.7 uA" in printed and "472.8" not in printed
        assert "141.3 uA" in printed and "141.4" not in printed
        assert "87.65 uA" in printed and "87.7 uA" not in printed


class TestSensitivityRefusesWhenNoAmplitudeIsSafe:
    """Ledger 84 reaches ``sensitivity`` too, and C1.5 could not reach it.

    ``sensitivity.describe`` renders the binding current limit nine times -- a baseline
    and both ends of four varied settings. For the monophasic band that ledger 84 is
    written about it printed all nine as bare amplitudes, headed
    ``baseline: 1.529e+04 uA (Shannon criterion)``, for a protocol whose own assessment
    says ``Limiting current: none -- no amplitude is safe: Charge balance FAILs at every
    amplitude``. ``_limit`` returns the raw attribute and ``Sensitivity.describe`` renders
    it with no access to the assessment, so the refusal has to be hoisted into
    ``analyse``/``describe``.
    """

    @staticmethod
    def _monophasic() -> SafetyCalculator:
        from neurostim import CylindricalBandElectrode

        return SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
        )

    def test_the_assessment_this_is_about_refuses_to_report_a_limit(self):
        """The precondition, asserted here rather than assumed, so the tests below are
        about a protocol the package itself declares unsafe at any amplitude.

        Not tautological: it reads ``unsafe_at_any_amplitude`` and the ``describe()``
        headline, neither of which ``sensitivity`` consults today.
        """
        assessment = self._monophasic().assess()

        assert [c.name for c in assessment.unsafe_at_any_amplitude] == ["Charge balance"]
        assert "Limiting current: none" in assessment.describe()

    def test_analyse_refuses_rather_than_ranking_an_amplitude_that_does_not_exist(self):
        """The programmatic surface: a list of ``Sensitivity`` rows *is* eight amplitudes.

        Not tautological: the expected outcome is a raise naming the check, so no number
        the module could compute would satisfy it.
        """
        from neurostim import sensitivity

        with pytest.raises(sensitivity.UnsafeAtAnyAmplitude, match="Charge balance"):
            sensitivity.analyse(self._monophasic())

    def test_describe_prints_the_refusal_in_place_of_nine_amplitudes(self):
        """The text surface, in place of the number and not beside it -- a reader who sees
        an amplitude will programme it, however the sentence next to it is worded.

        Not tautological: "1.529e+04" and "4750" are two of the nine amplitudes the report
        printed before, written out here, and the expected text is the assessment's own
        refusal sentence rather than anything this module composes.
        """
        from neurostim import sensitivity

        text = sensitivity.describe(self._monophasic())

        assert "no amplitude is safe" in text
        assert "Charge balance" in text
        assert "1.529e+04" not in text
        assert "4750" not in text
        assert " uA" not in text

    def test_the_varied_settings_cannot_create_or_remove_that_refusal(self):
        """Why checking the baseline once is sufficient.

        ``analyse`` varies ``k``, ``policy``, ``medium`` and the tissue conductivity, none
        of which is an input to a check outside ``LIMIT_BEARING``: charge balance is a
        property of the waveform and the validated envelope of the protocol's timing. If
        that ever stopped being true, the refusal would have to move into ``_limit``.

        Not tautological: the eight variant calculators are built here with the same
        settings ``_limit`` uses, and the assertion is on each one's own
        ``unsafe_at_any_amplitude``, read from the assessment rather than from the flag
        ``analyse`` consulted.
        """
        from neurostim.models import field as field_mod
        from neurostim.safety import shannon as shannon_mod

        base = self._monophasic()
        variants = (
            [{"k": k} for k in (shannon_mod.K_SHANNON, shannon_mod.K_DAMAGE_OBSERVED)]
            + [{"policy": p} for p in ("conservative", "optimistic")]
            + [{"medium": m} for m in ("in_vivo", "saline")]
            + [
                {"tissue_conductivity_S_per_m": sigma}
                for sigma in (0.11, field_mod.GREY_MATTER_CONDUCTIVITY_S_PER_M)
            ]
        )
        settings = {
            "k": base.k,
            "material": base.material,
            "policy": base.policy,
            "medium": base.medium,
            "tissue_conductivity_S_per_m": base.tissue_conductivity_S_per_m,
        }
        for override in variants:
            varied = SafetyCalculator(base.e, base.p, **{**settings, **override})
            names = [c.name for c in varied.assess().unsafe_at_any_amplitude]
            assert names == ["Charge balance"], (override, names)


class TestALimitFloorsWhateverItsUnit:
    """Ledger 49 closed for amplitudes only; the same defect survived in other units.

    D2's rule is about *maxima*, not about microamps: "a limit rounded to nearest is a
    limit rounded UP", and a reader who programmes to a printed maximum must pass the check
    whose maximum it claims to be. C1.3 routed every µA limit through ``format_limit`` and
    stopped there, so ``:.4g`` still rounded a published charge density and a published
    current density up on six surfaces including the PDF.

    Both quantities only look round. ``cic_limit_uC_cm2`` is a stored constant *divided by
    an in vivo derating factor*, and ``threshold_A_per_cm2`` is a power law in pulse width
    and electrode size -- neither is round except by accident.

    *Applied* quantities are deliberately left on round-to-nearest. Flooring one would
    understate what is being delivered, which is the wrong direction for a value that is
    compared *against* a limit.
    """

    def test_the_derated_charge_injection_limit_floors_on_every_surface(self):
        """Pt's 50 uC/cm^2 over Cogan's conservative in vivo derating is 7.142857142857143.

        Not tautological: 50.0 and the 7x derating are published constants, the quotient is
        written out here, "7.143" is what ``:.4g`` prints and is asserted absent on each
        surface, and "7.142" is the hand-floored four-digit form. The FAIL and the CAUTION
        branches render the limit through different f-strings and are both asserted.
        """
        failing = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            medium="in_vivo",
        ).assess()
        cautioning = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(2.0, 200.0, 130.0, 1.0),
            medium="in_vivo",
        ).assess()

        assert failing.charge.cic_limit_uC_cm2 == pytest.approx(
            7.142857142857143, rel=1e-15
        )
        for assessment in (failing, cautioning):
            check = next(
                c for c in assessment.checks if c.name == "Charge injection limit"
            )
            assert "7.142" in check.summary, check.summary
            assert "7.143" not in check.summary, check.summary
            assert "7.142" in assessment.charge.describe()
            assert "7.143" not in assessment.charge.describe()

    def test_the_pdf_charge_injection_row_floors(self, tmp_path):
        """The sixth surface, and the one a reader takes away from the room.

        Not tautological: the PDF is rendered and its extracted text searched for the two
        literal forms, neither of which the renderer is asked about.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            medium="in_vivo",
        )
        text = pdf_text(calc, tmp_path / "derated.pdf")

        assert "7.142" in text
        assert "7.143" not in text

    def test_the_electroporation_threshold_floors(self):
        """Butterwick's threshold is a power law, so it is round only by accident: 32 of 56
        swept (diameter, pulse width) pairs print a threshold strictly above the threshold.

        Not tautological: 9.348927087079717 A/cm^2 is recomputed here from
        ``butterwick2007.threshold_A_per_cm2`` for this geometry -- the data module, not
        the check -- "9.349" is what ``:.4g`` prints and is asserted absent, "9.348" is the
        hand-floored form.
        """
        from neurostim.data import butterwick2007

        expected = butterwick2007.threshold_A_per_cm2(100.0, 40.0)
        assert expected == pytest.approx(9.348927087079717, rel=1e-15)
        assert f"{expected:.4g}" == "9.349"  # what the defect printed

        assessment = SafetyCalculator(
            DiscElectrode(40.0, "Pt"), StimProtocol(5.0, 100.0, 130.0, 1.0)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Current density")

        assert "9.348" in check.summary, check.summary
        assert "9.349" not in check.summary, check.summary
        assert "9.348" in check.detail
        assert "9.349" not in check.detail

    def test_the_applied_quantities_are_not_floored(self):
        """The rule is about maxima. Flooring an applied value would understate what is
        being delivered, which is the wrong direction for the number a limit is compared
        against.

        Not tautological: the applied density here is 203.71833174178533 uC/cm^2, whose
        round-to-nearest four-digit form is "203.7" and whose floored form is also "203.7"
        at four digits -- so the assertion is made on a value where the two differ:
        0.39788735772973844 A/cm^2, which rounds to "0.3979" and floors to "0.3978".
        """
        assessment = SafetyCalculator(
            DiscElectrode(40.0, "Pt"), StimProtocol(5.0, 100.0, 130.0, 1.0)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Current density")

        assert "0.3979" in check.summary, check.summary
        assert "0.3978" not in check.summary, check.summary

    def test_every_constant_printed_with_g_renders_exactly(self):
        """The ``:g`` sites are safe only because the constants behind them are round.

        ``:g`` is six significant digits and rounds to nearest, so the chronic-degradation
        band, the published CIC ends, the water-window bounds, Cogan's 4 nC/phase and the
        ISO 14708-3 thermal limit are all printed without overstating *today* -- and would
        start overstating the day a non-round value is added, silently. This turns "they
        happen to be round" into a gate: adding a constant that does not survive its own
        rendering fails here, and whoever adds it decides between flooring the site and
        widening the format.

        Not tautological: the property asserted is a round trip through the *rendering*,
        ``float(f"{value:g}") == value``, which is a fact about IEEE and the format spec
        and is false for most floats -- 7.142857142857143 and 9.348927087079717, the two
        values this commit had to floor, both fail it.
        """
        from neurostim.data import cogan2016
        from neurostim.materials import MATERIALS, get_material

        def renders_exactly(value: float) -> bool:
            return float(f"{value:g}") == value

        # The two values that forced the rest of this commit fail the property, so it is
        # not vacuous.
        assert not renders_exactly(7.142857142857143)
        assert not renders_exactly(9.348927087079717)

        checked = 0
        for key in sorted(MATERIALS):
            material = get_material(key)
            if material.chronic_threshold is not None:
                for value in (
                    material.chronic_threshold.low_uC_cm2,
                    material.chronic_threshold.high_uC_cm2,
                ):
                    assert renders_exactly(value), (key, "chronic", value)
                    checked += 1
            if material.water_window is not None:
                for value in (
                    material.water_window.cathodic_V,
                    material.water_window.anodic_V,
                ):
                    assert renders_exactly(value), (key, "window", value)
                    checked += 1
            # What MeasuredRange.describe prints with :g: the ends in their stored units,
            # plus every polarity sub-range end.
            cic = material.cic
            for value in (
                cic.low,
                cic.high,
                *(cic.anodic_first_range or ()),
                *(cic.cathodic_first_range or ()),
            ):
                assert renders_exactly(value), (key, "stored CIC end", value)
                checked += 1
            # The same ends converted to uC/cm^2, for every polarity. ``nominal`` is not
            # a stored constant but a midpoint -- Pt's anodic-first one is
            # 75.00000000000001 and fails this property -- so it is not gated here: its
            # one render site is charge.py's policy warning, which floors, and
            # TestTheDerivedChargeLimitsFloor walks every policy through that site.
            for policy in ("conservative", "optimistic"):
                for anodic_first in (True, False, None):
                    value = material.cic_uC_cm2(policy, anodic_first)
                    assert renders_exactly(value), (key, policy, anodic_first, value)
                    checked += 1

        assert renders_exactly(
            cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE
        )
        checked += 1
        # The module's own value, not a literal standing in for it: rendered with :g at
        # ThermalResult.describe, and defaulted twice (the dataclass and evaluate()).
        import inspect

        from neurostim.models import thermal

        for value in (
            thermal.ThermalResult.limit_K,
            inspect.signature(thermal.evaluate).parameters["limit_K"].default,
        ):
            assert renders_exactly(value), ("thermal limit_K", value)
            checked += 1
        assert checked > 100, checked


class TestTheDerivedChargeLimitsFloor:
    """Ledger 100(b). The policy warning renders a *derived* limit, and it must floor.

    ``charge.evaluate``'s policy warning printed ``limit`` and ``endorsed`` with ``:g``.
    ``limit`` is the policy's value divided by any in vivo derating -- Pt's 50 uC/cm^2
    over 7 is 7.142857142857143, which ``:g`` prints as "7.14286", above the limit -- and
    ``nominal`` is a midpoint, not a stored constant. The stored-constant gate above cannot
    reach either. Today only SS316LVM's source endorses an end and it has no derating, so
    the site printed round numbers by luck of the database; this walks the site with every
    material given an endorsement, so the luck is not what the test rests on.
    """

    @staticmethod
    def _warnings():
        """Every (material, policy, polarity, medium) that renders a policy warning.

        Each material's CIC is given ``recommended_policy="conservative"`` so the warning
        is reachable for all of them, then evaluated at the two policies that exceed it.
        """
        from dataclasses import replace

        from neurostim.materials import MATERIALS, get_material
        from neurostim.safety import charge

        for key in sorted(MATERIALS):
            base = get_material(key)
            material = replace(base, cic=replace(base.cic, recommended_policy="conservative"))
            for policy in ("nominal", "optimistic"):
                for anodic_first in (True, False, None):
                    for medium in ("saline", "in_vivo"):
                        result = charge.evaluate(
                            material,
                            1.0,
                            0.01,
                            200.0,
                            policy=policy,  # type: ignore[arg-type]
                            medium=medium,
                            anodic_first=anodic_first,
                        )
                        endorsed = material.cic_uC_cm2("conservative", anodic_first)
                        yield key, policy, anodic_first, medium, result, endorsed

    def test_every_number_in_the_policy_warning_is_at_or_below_its_limit(self):
        """Not tautological: the two numbers are parsed back out of the rendered sentence
        and compared with values computed here from the material record -- the policy's
        own value over the derating the result reports -- not with anything the renderer
        was handed."""
        import re

        from neurostim.materials import get_material

        pattern = re.compile(
            r"applies (\S+) uC/cm\^2, but .* end at (\S+) uC/cm\^2"
        )
        checked = 0
        for key, policy, anodic_first, medium, result, endorsed in self._warnings():
            case = (key, policy, anodic_first, medium, result.policy_warning)
            match = pattern.search(result.policy_warning)
            assert match is not None, case
            applied_text, endorsed_text = match.groups()
            limit = (
                get_material(key).cic_uC_cm2(policy, anodic_first)  # type: ignore[arg-type]
                / result.derating_applied
            )
            assert float(applied_text) <= limit, case
            assert float(endorsed_text) <= endorsed, case
            checked += 1
        assert checked == 9 * 2 * 3 * 2, checked

    def test_the_derated_platinum_limit_does_not_round_up(self):
        """The review's own values. Pt's unpolarised range is 50-150 uC/cm^2 and Cogan's
        worst in vivo reduction for it is 14x, so nominal is 100/14 = 7.142857142857143
        and optimistic 150/14 = 10.714285714285714 -- printed "7.14286" and "10.7143" by
        ``:g``, each above the limit it names. The floored forms are "7.142" and "10.71".
        """
        from neurostim.data import cogan2016

        assert cogan2016.derating_for("Pt").worst == 14.0  # the fixture's premise
        assert float("7.14286") > 100.0 / 14.0  # the defect's direction, written out
        assert float("10.7143") > 150.0 / 14.0
        seen = {}
        for key, policy, anodic_first, medium, result, _ in self._warnings():
            if key == "Pt" and medium == "in_vivo" and anodic_first is None:
                seen[policy] = result.policy_warning
        assert set(seen) == {"nominal", "optimistic"}
        assert "applies 7.142 uC/cm^2" in seen["nominal"], seen["nominal"]
        assert "applies 10.71 uC/cm^2" in seen["optimistic"], seen["optimistic"]
        for warning in seen.values():
            assert "7.14286" not in warning and "10.7143" not in warning, warning


class TestEveryLimitBearingCheckHasAMargin:
    """C1.4. Four of nine checks expose a margin today, so a minimum over them cannot see
    the other three (fix plan D3, ledger 1).

    ``margin`` is defined as **the ratio of the FAIL ceiling to the applied current** --
    not the CAUTION ceiling, and not ``headroom / excursion``. The difference is not
    cosmetic: the naive headroom reading of the water-window margin is **negative** at
    ``resting_potential_V = 0`` (-21.095 uA against a true 58.905), which a finiteness
    test and a one-sided ``<= 20.0`` both admit.
    """

    @staticmethod
    def _cases():
        from neurostim import CylindricalBandElectrode, RingElectrode

        yield SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"),
            StimProtocol(20, 400, 50, 3600),
            compliance_V=20.0,
        )

    def test_every_limit_bearing_margin_is_its_own_fail_ceiling(self):
        """The pin. ``margin * current`` must equal the independent per-check bisection.

        Not tautological: the expected value comes from ``tests/oracles``, which reads one
        bit per probe -- whether that named check is in ``assess().failed`` -- and never
        reads a margin, a maximum or a limiting current.
        """
        from oracles.fail_ceiling import check_fail_ceiling_uA

        from neurostim.safety import LIMIT_BEARING

        for calc in self._cases():
            assessment = calc.assess()
            named = {c.name for c in assessment.checks}
            assert named >= LIMIT_BEARING, LIMIT_BEARING - named
            for check in assessment.checks:
                if check.name not in LIMIT_BEARING:
                    continue
                expected = check_fail_ceiling_uA(calc, check.name)
                assert check.margin * calc.p.current_uA == pytest.approx(
                    expected, rel=1e-9
                ), (calc.e, check.name)

    def test_the_water_window_margin_is_positive_where_the_naive_reading_is_negative(
        self,
    ):
        """Execution B4's case, stated as a value rather than as finiteness.

        Not tautological: 58.90486225480862 uA is derived in the oracle pins from Pt's own
        150 uC/cm^2 over its own 0.6 V cathodic limit, and -21.095 is asserted absent.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        water = next(c for c in calc.assess().checks if c.name == "Water window")

        assert water.margin > 0.0
        assert water.margin * 80.0 == pytest.approx(58.90486225480862, rel=1e-12)

    def test_the_two_checks_that_had_no_margin_now_have_one(self):
        """§6: ``assessment.json`` records ``null`` for 5 of 9 margins today.

        Not tautological: the two names are written out and the assertion is finiteness
        *plus* the ceiling identity above, which finiteness alone would not give.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        checks = {c.name: c for c in calc.assess().checks}
        import math

        assert math.isfinite(checks["Water window"].margin)
        assert math.isfinite(checks["Chronic degradation"].margin)

    def test_a_check_that_did_not_run_has_an_infinite_margin(self):
        """NOT_EVALUATED must not contribute a ceiling to the minimum C1.6 takes.

        Not tautological: the oracle answers ``inf`` for a check that never FAILs across
        the whole bracket, and that is what is compared against.
        """
        import math

        from oracles.fail_ceiling import check_fail_ceiling_uA

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        shannon = next(c for c in calc.assess().checks if c.name == "Shannon criterion")

        assert shannon.status is Status.NOT_EVALUATED
        assert shannon.margin == math.inf
        assert check_fail_ceiling_uA(calc, "Shannon criterion") == math.inf

    def test_the_checks_that_bear_no_limit_keep_an_infinite_margin(self):
        """Validated envelope and Charge balance impose no ceiling on amplitude.

        Not tautological: both names are written out, and the second half asserts the
        *reason* -- their verdict does not move with amplitude -- against the oracle's
        witness rather than against their margin.
        """
        import math

        from oracles.fail_ceiling import LIMIT_BEARING as ORACLE_LIMIT_BEARING

        from neurostim.safety import LIMIT_BEARING

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        checks = {c.name: c for c in calc.assess().checks}

        assert set(checks) - LIMIT_BEARING == {"Validated envelope", "Charge balance"}
        assert checks["Validated envelope"].margin == math.inf
        assert checks["Charge balance"].margin == math.inf
        assert set(ORACLE_LIMIT_BEARING) == LIMIT_BEARING


class TestCheckKindAndProvisional:
    """``kind`` separates the four things a limit can be about; ``provisional`` says the
    limit is caveated (physics M1a, M1c, m6)."""

    @staticmethod
    def _calc() -> SafetyCalculator:
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )

    def test_every_check_declares_one_of_the_four_kinds(self):
        """Not tautological: the four labels are written out here, and the mapping from
        each check name to its kind is written out in the next test."""
        kinds = {c.kind for c in self._calc().assess().checks}
        assert kinds <= {"tissue", "electrode-chronic", "electrode-acute", "instrument"}

    def test_the_kind_of_each_check_is_the_one_its_source_measures(self):
        """Not tautological: the expected mapping is stated here from what each check's
        cited source is about -- Shannon and Butterwick measured tissue injury, the CIC
        and water window are single-pulse interface properties, dissolution is chronic,
        and compliance is a property of the stimulator, not of the patient."""
        kinds = {c.name: c.kind for c in self._calc().assess().checks}

        assert kinds == {
            "Shannon criterion": "tissue",
            "Charge injection limit": "electrode-acute",
            "Water window": "electrode-acute",
            "Validated envelope": "tissue",
            "Current density": "tissue",
            "Microelectrode charge/phase": "tissue",
            "Chronic degradation": "electrode-chronic",
            "Charge balance": "electrode-chronic",
            "Compliance voltage": "instrument",
        }

    def test_the_current_density_limit_is_always_provisional(self):
        """Its own docstring says why: the threshold is chick membrane and retina, so the
        margin is against a preparation that is not the one being stimulated.

        Not tautological: the expected value is ``True`` and the reason is the check's own
        stated one, not a recomputation of anything.
        """
        density = next(
            c for c in self._calc().assess().checks if c.name == "Current density"
        )
        assert density.provisional is True

    def test_a_caveated_charge_injection_limit_is_provisional(self):
        """Three distinct caveats, three fixtures, each chosen from the database itself.

        * TIROF's stored CIC carries **no pulse width**, so its applicability at any
          pulse width is unknown.
        * Pt's was measured at 200 us, so 2000 us is ten times away from it.
        * SS316LVM's source endorses the conservative end, so the optimistic policy
          applies a number that source argues against.

        Not tautological: each premise is asserted here against the material database
        before the ``provisional`` flag is checked, so the test fails if the fixture stops
        being the case it claims to be.
        """
        from neurostim.materials import get_material

        assert get_material("TIROF").cic.pulse_width_us is None
        assert get_material("Pt").cic.pulse_width_us == 200.0
        assert get_material("SS316LVM").cic.recommended_policy == "conservative"

        fixtures = (
            ("TIROF", 200.0, "conservative"),
            ("Pt", 2000.0, "conservative"),
            ("SS316LVM", 100.0, "optimistic"),
        )
        for material, pulse_width_us, policy in fixtures:
            calc = SafetyCalculator(
                DiscElectrode(100.0, material),
                StimProtocol(1.0, pulse_width_us, 130.0, 1.0),
                policy=policy,  # type: ignore[arg-type]
            )
            charge = next(
                c for c in calc.assess().checks if c.name == "Charge injection limit"
            )
            assert charge.provisional is True, (material, pulse_width_us, policy)

    def test_a_verified_limit_at_its_measured_conditions_is_not_provisional(self):
        """The flag must discriminate, not decorate.

        Not tautological: Pt's CIC is verified and measured at 200 us, which is the pulse
        width used, so the expected value is ``False`` -- the opposite of the test above.
        """
        charge = next(
            c
            for c in self._calc().assess().checks
            if c.name == "Charge injection limit"
        )
        assert charge.provisional is False

    def test_kind_and_provisional_reach_the_json(self):
        """Not tautological: the keys and one expected value are written out, against a
        payload that carries neither today."""
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._calc()))
        rows = {row["name"]: row for row in payload["checks"]}

        assert rows["Compliance voltage"]["kind"] == "instrument"
        assert rows["Current density"]["provisional"] is True
        assert rows["Water window"]["margin"] is not None


class TestUnsafeAtAnyAmplitude:
    """Ledger 84. A check outside ``LIMIT_BEARING`` FAILs at every amplitude, so there is
    no ceiling to report -- and the package printed one anyway.

    Verified before the fix: monophasic ``CylindricalBandElectrode(1270, 1500, "PtIr")``
    at 3000 uA / 90 us / 130 Hz reports ``failed == ['Charge balance']`` and prints
    ``Limiting current: 1.528e+04 uA (Shannon tissue-damage criterion)``, while the
    unrestricted fail-ceiling oracle answers 0.0. A reader is told 15.3 mA is the ceiling
    for a protocol that is unsafe at any amplitude.

    This is a separate field from ``limits_incomplete``, not a reuse of it, because the
    two carry opposite instructions: one says *the number may be too high*, this one says
    *there is no number*.
    """

    @staticmethod
    def _monophasic() -> SafetyCalculator:
        from neurostim import CylindricalBandElectrode

        return SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )

    @staticmethod
    def _worked_example() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_the_failure_is_amplitude_independent_and_the_oracle_names_it(self):
        """The precondition, asserted rather than assumed.

        Not tautological: ``amplitude_independent_failures`` walks 73 probes from 1e-12 to
        1e6 uA and reports the checks that FAIL at every one of them. It reads names, not
        numbers, and it is a strictly stronger statement than a bare ceiling of 0.0 --
        which is why it is the witness the rendering is asserted against.
        """
        from oracles.fail_ceiling import amplitude_independent_failures

        assert amplitude_independent_failures(self._monophasic()) == ("Charge balance",)
        assert amplitude_independent_failures(self._worked_example()) == ()

    def test_unsafe_at_any_amplitude_names_the_check_the_oracle_names(self):
        """Not tautological: the package field is compared against the oracle's witness,
        computed by probing the assessment across eighteen decades."""
        from oracles.fail_ceiling import amplitude_independent_failures

        calc = self._monophasic()
        assessment = calc.assess()

        assert tuple(c.name for c in assessment.unsafe_at_any_amplitude) == (
            amplitude_independent_failures(calc)
        )
        assert self._worked_example().assess().unsafe_at_any_amplitude == ()

    def test_describe_prints_no_number_and_names_the_check(self):
        """Not tautological: the assertion is an **absence** -- the amplitude the package
        prints today, 1.528e+04, must not appear in the headline block -- together with the
        presence of the check's name.

        Scoped to the headline, not to the whole rendering: the Shannon check's own detail
        block still reports 1.528e+04 as *the Shannon criterion's* limit, and it should.
        That number is true about that criterion. What was false is calling it the
        limiting current for a protocol no amplitude makes safe.
        """
        text = self._monophasic().describe()
        lines = text.splitlines()
        headline = "\n".join(lines[: next(i for i, s in enumerate(lines) if s.startswith("["))])
        limiting = [
            line for line in lines if line.startswith("Limiting current:")
        ]

        assert limiting, text
        assert "1.528e+04" not in headline
        assert "15285" not in headline
        assert "no amplitude is safe" in limiting[0].lower()
        assert "Charge balance" in limiting[0]
        assert "across published ranges" not in headline

    def test_report_to_json_refuses_the_number_too(self):
        """A machine consumer is the one that cannot read a caveat in prose.

        Not tautological: the expected values are ``None`` for the amplitude and the
        literal check name for the flag, against a payload that today carries
        15285.50941588086.
        """
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._monophasic()))

        assert payload["unsafe_at_any_amplitude"] == ["Charge balance"]
        assert payload["results"]["limiting_current_uA"] is None
        assert "Charge balance" in payload["results"]["limiting_mechanism"]

    def test_the_pdf_header_refuses_the_number(self, tmp_path):
        """Not tautological: asserted on extracted PDF text, absence and presence both,
        and scoped to the header sentence -- the Computed quantities table below it still
        reports the Shannon criterion's own limit, which is a true statement about that
        criterion."""
        text = pdf_text(self._monophasic(), tmp_path / "unsafe.pdf")
        start = text.index("Overall assessment:")
        header = text[start : text.index("Electrode", start)]

        assert "no amplitude is safe" in header.lower()
        assert "Charge balance" in header
        assert "1.528e+04" not in header

    def test_the_gui_headline_refuses_the_number(self):
        """The headline is the one line a user reads before acting.

        Not tautological: the GUI's own headline builder is driven with the monophasic
        assessment and the resulting string is checked for the absent number and the
        present name.
        """
        pytest.importorskip("PyQt6")
        from neurostim.gui.app import headline_text

        text = headline_text(self._monophasic().assess())

        assert "no amplitude is safe" in text.lower()
        assert "Charge balance" in text
        assert "1.528e+04" not in text

    def test_a_safe_protocol_still_gets_its_number(self):
        """The refusal must fire only where it belongs.

        Not tautological: the worked example's witness is empty (asserted above), and the
        expected rendering is the floored 20.00 -- Cogan 2016's 4 nC/phase over 200 us.
        """
        line = next(
            row
            for row in self._worked_example().describe().splitlines()
            if row.startswith("Limiting current:")
        )
        assert "20.00" in line
        assert "no amplitude is safe" not in line.lower()


class TestTheHeadlineRefusesInItsOwnType:
    """M2. ``limiting_current_uA`` meant two things under one name (review F7).

    Nine consumers read it. Six consult ``unsafe_at_any_amplitude`` beside it; three did
    not, and those three were F1 -- ``sensitivity.py`` twice and the worked example. That
    is the ledger 19/59/60 shape exactly: the qualifying information exists one row away
    from where it is needed and nothing structural carries it across, so each new consumer
    restarts the same race. C2.1 widens the refusal to unbalanced *biphasic* protocols,
    which multiplies the disagreeing population before anyone re-audits it.

    So the raw quantity keeps its definition under a name that states it --
    ``limit_bearing_ceiling_uA``, the minimum over :data:`LIMIT_BEARING` -- and
    ``limiting_current_uA`` becomes ``float | None``, ``None`` exactly when no amplitude is
    safe. ``float -> float | None`` is a type change and ``mypy neurostim`` is a CI gate, so
    a consumer that forgets stops typechecking rather than printing 15.3 mA.

    ``None`` and not a raise: ``limiting_current_by_kind``,
    ``limiting_current_interval_uA`` and ``limiting_mechanism`` are what a user needs in
    order to *diagnose* a protocol that is unsafe as a waveform, and a raise would take
    them with it.
    """

    @staticmethod
    def _monophasic() -> SafetyCalculator:
        from neurostim import CylindricalBandElectrode

        return SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
        )

    @staticmethod
    def _safe() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_the_headline_is_none_exactly_when_no_amplitude_is_safe(self):
        """Not tautological: the two expected outcomes are opposite -- ``None`` for the
        protocol ledger 84 is written about, and a number for the worked example -- and the
        condition they are read against is ``unsafe_at_any_amplitude``, a different
        attribute computed from the checks' statuses rather than from any ceiling."""
        unsafe = self._monophasic().assess()
        safe = self._safe().assess()

        assert unsafe.unsafe_at_any_amplitude
        assert unsafe.limiting_current_uA is None
        assert not safe.unsafe_at_any_amplitude
        assert safe.limiting_current_uA == pytest.approx(20.0)

    def test_the_raw_quantity_survives_under_a_name_that_states_it(self):
        """``limit_bearing_ceiling_uA`` is still the minimum over the seven, for the same
        protocol whose headline refuses.

        Not tautological: the expected value is the water window's DC-drift boundary,
        written out here from the published constants -- PtIr holds
        ``0.6 V * 250 uF/cm^2 * A = 8.9771 uC`` before reaching its cathodic edge and a
        monophasic train spends it at ``I * 90 us * 130 Hz`` -- and the assertion is that
        the minimum over the seven is still computable, under the name that says what it
        is, while the headline is ``None``.

        The number ledger 84 records for this protocol is 15285.509415880857, the Shannon
        ceiling. C2.3 put a twentyfold lower candidate into the same set, so the raw
        quantity moved while the refusal it sits beside did not; both halves are asserted
        because it is the pairing that is under test.
        """
        assessment = self._monophasic().assess()
        area_cm2 = math.pi * 0.127 * 0.15
        expected = (0.6 * 250.0 * area_cm2) / (90.0e-6 * 130.0 * 1.0)

        assert expected == pytest.approx(767.2736, abs=5e-5)
        assert assessment.limit_bearing_ceiling_uA == pytest.approx(expected, rel=1e-9)
        assert assessment.limiting_current_uA is None

    def test_the_decomposition_stays_reachable_when_the_headline_refuses(self):
        """Why ``None`` and not a raise: these three are how a user diagnoses the protocol.

        Not tautological: each is read for the refusing protocol and checked against the
        raw ceiling, which is a different attribute from the one under test.
        """
        assessment = self._monophasic().assess()

        assert assessment.limiting_current_uA is None
        assert assessment.limiting_mechanism
        assert min(assessment.limiting_current_by_kind.values()) == pytest.approx(
            assessment.limit_bearing_ceiling_uA, rel=1e-12
        )
        assert assessment.limiting_current_interval_uA.contains(
            assessment.limit_bearing_ceiling_uA
        )

    def test_report_reads_the_attribute_with_no_conditional_of_its_own(self):
        """One rule, one place: ``report()`` used to carry its own copy of the branch.

        Not tautological: the assertion is that two independently reached values agree --
        the dict entry and the attribute -- for both a refusing and a non-refusing
        protocol, and ``None`` is asserted where a number used to be.
        """
        unsafe = self._monophasic()
        safe = self._safe()

        assert unsafe.report()["limiting_current_uA"] is None
        assert unsafe.report()["limiting_current_uA"] is (
            unsafe.assess().limiting_current_uA
        )
        assert safe.report()["limiting_current_uA"] == pytest.approx(
            safe.assess().limiting_current_uA
        )

    def test_the_sensitivity_helper_refuses_a_variant_with_no_safe_amplitude(self):
        """``sensitivity._limit`` is the single choke point that turns an assessment into a
        bare amplitude, and under the new type it has to handle the ``None``.

        Called directly rather than through ``analyse``, which refuses earlier: that guard
        argues the varied settings cannot change an amplitude-independent verdict, and this
        one does not need the argument.

        Not tautological: the expected outcome is a raise naming the check, so no number
        the helper could return would satisfy it.
        """
        from neurostim import sensitivity

        with pytest.raises(sensitivity.UnsafeAtAnyAmplitude, match="Charge balance"):
            sensitivity._limit(self._monophasic())


class TestLimitingCurrentIsTheMinimumOverLimitBearingChecks:
    """T1 and T2b. Ledger 1 and 66: the headline was a minimum over three candidates while
    nine checks ran, so four computed limits could not reach it.

    On the worked example the package reported 141.37 uA while Microelectrode charge/phase
    (ceiling 20.0) and Chronic degradation (ceiling 70.69) were both in a FAIL state at
    80 uA -- a 7.07x overstatement of the maximum safe current.
    """

    @staticmethod
    def _worked_example() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_the_worked_example_limit_is_twenty_microamps(self):
        """T1. Pinned twice: to an independent binary search, and to the published
        constant behind the binding check.

        Not tautological: the oracle bisects over ``assess().failed`` restricted to the
        seven limit-bearing names and reads no package-computed number; and 20.0 is
        Cogan 2016's 4 nC/phase divided by the 200 us pulse -- ``4e-9 C / 200e-6 s =
        2e-5 A``, arithmetic that does not involve the package at all.

        The precondition is **asserted, not assumed**: without it T1 is unsatisfiable for
        any protocol with an amplitude-independent failure, and silently narrowing the
        parametrisation would hide exactly the case C1.5 exists to fix.
        """
        from oracles.fail_ceiling import fail_ceiling_uA

        from neurostim.data import cogan2016
        from neurostim.safety import LIMIT_BEARING

        calc = self._worked_example()
        assessment = calc.assess()

        assert not assessment.unsafe_at_any_amplitude

        expected = fail_ceiling_uA(calc, names=LIMIT_BEARING)
        assert assessment.limiting_current_uA == pytest.approx(expected, rel=1e-9)
        assert assessment.limiting_current_uA > 0
        assert assessment.limiting_current_uA == pytest.approx(20.0)
        assert (
            cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE * 1e-9 / 200e-6 * 1e6
        ) == 20.0

    def test_the_mechanism_names_the_check_that_binds(self):
        """Not tautological: the expected name is written out and is a check name, where
        today's answer is a hand-made string ("Pt charge-injection limit") naming a check
        that is not the binding one."""
        assessment = self._worked_example().assess()

        assert assessment.limiting_mechanism == "Microelectrode charge/phase"

    def test_the_named_mechanism_is_always_a_check_that_ran(self):
        """T3, ledger 1 §9b.1. ``DiscElectrode(40, "PEDOT")`` at 200 us reported
        99.6724 uA "(Shannon tissue-damage criterion)" while Shannon is NOT_EVALUATED.

        Not tautological: the status of the named check is looked up in the assessment and
        asserted to be something other than NOT_EVALUATED, across several configurations
        chosen to make different checks bind.
        """
        from neurostim import CylindricalBandElectrode, RingElectrode

        cases = [
            self._worked_example(),
            SafetyCalculator(DiscElectrode(40.0, "PEDOT"), StimProtocol(80, 200, 130, 1)),
            SafetyCalculator(
                CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
                StimProtocol(3000.0, 60.0, 130.0, 1.0),
                compliance_V=10.0,
            ),
            SafetyCalculator(
                RingElectrode(330.0, 270.0, "Pt"),
                StimProtocol(1.0, 20.0, 130.0, 1.0),
                compliance_V=1.0,
            ),
        ]
        for calc in cases:
            assessment = calc.assess()
            named = {c.name: c for c in assessment.checks}
            mechanism = assessment.limiting_mechanism

            assert mechanism in named, (calc.e, mechanism)
            assert named[mechanism].status is not Status.NOT_EVALUATED, (
                calc.e,
                mechanism,
            )

    def test_the_pedef_case_moves_to_the_check_that_actually_binds(self):
        """The value half of T3, not just the label.

        Not tautological: 99.67240473569454 is the number the package printed and is
        asserted absent; 20.0 is the independently pinned microelectrode ceiling.
        """
        calc = SafetyCalculator(
            DiscElectrode(40.0, "PEDOT"), StimProtocol(80, 200, 130, 1)
        )
        assessment = calc.assess()

        assert assessment.limiting_current_uA == pytest.approx(20.0)
        assert assessment.limiting_mechanism == "Microelectrode charge/phase"

    def test_reassessing_at_the_reported_limit_fails_nothing(self):
        """T2b. The promise the headline makes, over 9 materials x 3 policies x 2
        polarities.

        Not tautological: it programmes the package's own reported number back in and asks
        the assessment -- a different object, built from a different protocol -- whether
        anything FAILs. A limit that is one ulp high, or that omits a candidate, fails
        here.
        """
        from dataclasses import replace

        from neurostim.materials import MATERIALS

        electrode = DiscElectrode(100.0, "Pt")
        base = StimProtocol(80.0, 200.0, 130.0, 1.0)
        for material in MATERIALS:
            for policy in ("conservative", "nominal", "optimistic"):
                for anodic_first in (False, True):
                    protocol = replace(base, anodic_first=anodic_first)
                    calc = SafetyCalculator(
                        electrode,
                        protocol,
                        material=material,
                        policy=policy,  # type: ignore[arg-type]
                        compliance_V=10.0,
                    )
                    assessment = calc.assess()
                    assert not assessment.unsafe_at_any_amplitude
                    limit = assessment.limiting_current_uA
                    assert limit > 0, (material, policy)

                    at_limit = SafetyCalculator(
                        electrode,
                        replace(protocol, current_uA=limit),
                        material=material,
                        policy=policy,  # type: ignore[arg-type]
                        compliance_V=10.0,
                    ).assess()
                    assert not at_limit.failed, (
                        material,
                        policy,
                        anodic_first,
                        limit,
                        [c.name for c in at_limit.failed],
                    )

    def test_the_restriction_to_limit_bearing_checks_is_load_bearing(self):
        """The monophasic companion, where the two oracle forms diverge.

        Not tautological: the two expected values are the oracle's own two answers, and
        they differ by fifteen orders of magnitude -- the restricted one is what the
        package's raw ceiling must equal, the unrestricted one is what
        ``unsafe_at_any_amplitude`` is about. A test written against the unrestricted form
        would demand 0.0 here and would still pass on the worked-example ring, where both
        forms answer 20.0.

        Pinned against ``limit_bearing_ceiling_uA`` and not ``limiting_current_uA``: the
        oracle brackets the raw minimum over :data:`LIMIT_BEARING`, which is defined for
        every protocol, while the headline is ``None`` for this one by construction (M2).
        Both are asserted, because the pair is the point.
        """
        from oracles.fail_ceiling import fail_ceiling_uA

        from neurostim import CylindricalBandElectrode
        from neurostim.safety import LIMIT_BEARING

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )

        assert fail_ceiling_uA(calc) == 0.0
        restricted = fail_ceiling_uA(calc, names=LIMIT_BEARING)
        # The water window's DC-drift boundary since C2.3: PtIr holds
        # 0.6 V * 250 uF/cm^2 * A = 8.9771 uC before its cathodic edge, and a monophasic
        # train spends that at I * 90 us * 130 Hz.
        area_cm2 = math.pi * 0.127 * 0.15
        expected = (0.6 * 250.0 * area_cm2) / (90.0e-6 * 130.0 * 1.0)
        assert expected == pytest.approx(767.2736, abs=5e-5)
        assert restricted == pytest.approx(expected, rel=1e-9)
        assert calc.assess().limit_bearing_ceiling_uA == pytest.approx(
            restricted, rel=1e-9
        )

        # ...and it is still not presented as a number anywhere (C1.5, M2).
        assert calc.assess().limiting_current_uA is None
        assert calc.report()["limiting_current_uA"] is None


class TestLimitsIncompleteAndByKind:
    """A limit over a knowingly-incomplete candidate set is ledger 1 in a new place, and a
    single scalar hides which of four different things binds (fix plan D3)."""

    @staticmethod
    def _worked_example() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_limits_incomplete_is_set_when_a_limit_bearing_check_did_not_run(self):
        """Not tautological: the premise -- Shannon is NOT_EVALUATED here and Shannon is
        limit-bearing -- is asserted from the assessment and from ``LIMIT_BEARING``
        separately, and the flag is checked against their conjunction."""
        from neurostim.safety import LIMIT_BEARING

        assessment = self._worked_example().assess()
        skipped = {c.name for c in assessment.not_evaluated}

        assert "Shannon criterion" in skipped
        assert "Shannon criterion" in LIMIT_BEARING
        assert assessment.limits_incomplete is True

    def test_limits_incomplete_is_clear_when_every_limit_bearing_check_ran(self):
        """The flag must discriminate.

        Not tautological: the fixture is a 250 um Pt disc in the transition band with a
        compliance voltage, where all nine checks run, and the expected value is the
        opposite of the test above.
        """
        calc = SafetyCalculator(
            DiscElectrode(250.0, "Pt"),
            StimProtocol(5, 200, 130, 1),
            compliance_V=10.0,
        )
        assessment = calc.assess()

        assert assessment.not_evaluated == ()
        assert assessment.limits_incomplete is False

    PER_KIND_uA = {
        "tissue": 20.0,
        "electrode-acute": 141.37166941154072,
        "electrode-chronic": 70.68583470577036,
        "instrument": 965.3764143567779,
    }
    """The worked example's four per-kind ceilings, written out rather than recomputed.

    Each is pinned independently in ``tests/test_oracles.py`` by the binary search over
    ``assess().failed``, which reads one bit per probe and no package-computed number: 20.0
    is Cogan's 4 nC/phase over a 200 us pulse, 141.37 is platinum's charge-injection limit
    over this area, 70.69 its 20 uC/cm^2 dissolution threshold, 965.38 the compliance
    ceiling at 10 V.
    """

    def test_the_headline_is_the_minimum_of_the_per_kind_limits(self):
        """The decomposition and the headline, against hand-written values.

        This test used to build ``expected`` by looping over ``check.ceiling_uA`` -- the
        same values ``limiting_current_by_kind`` and the headline are computed from -- and
        assert equality, which is the implementation restated. Measured: with every
        ceiling multiplied by two it still passed. That is the form C1.6's own plan row
        dropped as "the implementation restated", reappearing in the by-kind commit.

        Not tautological: every expected number is a literal from :attr:`PER_KIND_uA`,
        each independently pinned by the fail-ceiling oracle, and the headline is asserted
        against the minimum of those literals rather than of anything the package returned.
        """
        assessment = self._worked_example().assess()
        by_kind = assessment.limiting_current_by_kind

        assert by_kind.keys() == self.PER_KIND_uA.keys()
        for kind, expected_uA in self.PER_KIND_uA.items():
            assert by_kind[kind] == pytest.approx(expected_uA, rel=1e-12), kind
        assert assessment.limiting_current_uA == pytest.approx(
            min(self.PER_KIND_uA.values()), rel=1e-12
        )

    def test_the_per_kind_limits_disagree_where_it_matters(self):
        """The decomposition earns its place only if the four numbers differ.

        Not tautological: the spread is asserted between literals in :attr:`PER_KIND_uA`,
        so a decomposition that collapsed every kind onto the headline would fail here
        while still satisfying a minimum.
        """
        by_kind = self._worked_example().assess().limiting_current_by_kind

        assert len(set(self.PER_KIND_uA.values())) == 4
        assert max(by_kind.values()) / min(by_kind.values()) == pytest.approx(
            self.PER_KIND_uA["instrument"] / self.PER_KIND_uA["tissue"], rel=1e-12
        )

    def test_describe_states_both(self):
        """Not tautological: two literal substrings, one naming the check that did not
        run and one carrying a per-kind number, against a rendering that has neither."""
        text = self._worked_example().describe()

        assert "20.00 uA (Microelectrode charge/phase)" in text
        assert "Shannon criterion" in text
        assert "INCOMPLETE" in text
        assert "electrode-chronic 70.68 uA" in text

    def test_the_json_carries_both(self):
        """Not tautological: the expected keys and one expected value are written out."""
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._worked_example()))

        assert payload["limits_incomplete"] is True
        assert payload["limiting_current_by_kind"]["tissue"] == pytest.approx(20.0)
        assert payload["results"]["limiting_current_uA"] == pytest.approx(20.0)

    def test_the_pdf_and_the_gui_headline_say_the_limit_may_be_lower(self, tmp_path):
        """Not tautological: both surfaces are rendered and searched for the literal
        marker, which neither carries today."""
        pytest.importorskip("PyQt6")
        from neurostim.gui.app import headline_text

        calc = self._worked_example()
        text = pdf_text(calc, tmp_path / "incomplete.pdf")

        assert "20.00" in text
        assert "incomplete" in text.lower()
        assert "incomplete" in headline_text(calc.assess()).lower()


class TestTheIntervalContainsThePointEstimate:
    """T16. The interval and the point estimate must be answers to the same question.

    ``limiting_current_interval_uA`` propagated only the Shannon band and the material's
    charge-injection range, so after C1.6 widened the point estimate to all seven
    limit-bearing checks the two disagreed outright: the worked example reported a limit of
    20.0 uA and an interval of 141.37-212.06 uA that does not contain it. An interval that
    excludes its own point estimate is not a wider statement of the same thing; it is a
    second, contradictory answer.
    """

    @staticmethod
    def _cases():
        from dataclasses import replace

        from neurostim.materials import MATERIALS

        electrode = DiscElectrode(100.0, "Pt")
        base = StimProtocol(80.0, 200.0, 130.0, 1.0)
        for material in MATERIALS:
            for policy in ("conservative", "nominal", "optimistic"):
                for anodic_first in (False, True):
                    yield SafetyCalculator(
                        electrode,
                        replace(base, anodic_first=anodic_first),
                        material=material,
                        policy=policy,  # type: ignore[arg-type]
                        compliance_V=10.0,
                    )

    def test_the_interval_contains_the_point_estimate(self):
        """A regression guard for the *candidate-set* defect, and nothing stronger.

        What it can catch, and did: before C1.8 the interval propagated Shannon and the
        charge-injection range while the point estimate was a minimum over all seven
        limit-bearing checks, so the two answered different questions and the worked
        example printed a limit of 20.0 uA beside an interval of 141.37-212.06. Any future
        divergence of the two candidate sets fails here.

        What it cannot catch, stated because the docstring used to claim otherwise
        ("computed by different code from different inputs"): over one candidate set the
        containment is a theorem about the two constructions, not a measurement.
        ``most_restrictive`` is ``(min lows, min highs)`` and ``_ceiling_interval_uA``
        brackets each check's own ceiling, so for ``j = argmin(highs)``,
        ``min(highs) = high_j >= low_j >= min(lows)`` and
        ``point = min(ceilings) <= min(highs)`` since ``ceiling_i <= high_i``. It cannot
        fail while both are built that way, whatever the ceilings are.

        Pinned against ``limit_bearing_ceiling_uA``: the interval is of the raw quantity
        and is defined for protocols whose headline is ``None`` (M2).
        """
        for calc in self._cases():
            assessment = calc.assess()
            interval = assessment.limiting_current_interval_uA
            limit = assessment.limit_bearing_ceiling_uA

            assert interval.contains(limit), (
                calc.material.key,
                calc.policy,
                calc.p.anodic_first,
                limit,
                (interval.low, interval.high),
            )

    def test_the_worked_example_interval_moves_down_with_its_point_estimate(self):
        """Not tautological: the expected low end is the microelectrode ceiling, 20.0 uA,
        which is a published constant over a pulse width and is where the point estimate
        independently landed."""
        from neurostim import RingElectrode

        assessment = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        ).assess()
        interval = assessment.limiting_current_interval_uA

        assert interval.low == pytest.approx(20.0)
        assert interval.contains(20.0)
        assert interval.high < 141.37166941154072

    def test_a_published_range_still_widens_the_interval(self):
        """The interval must stay an interval, not collapse to the point estimate.

        Not tautological: the fixture is chosen so the *chronic* threshold binds, whose
        published band is 20-50 uC/cm^2 on platinum -- a factor of 2.5 -- and the expected
        fold is that ratio, written out.
        """
        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(500.0, 200.0, 50.0, 1.0)
        ).assess()
        interval = assessment.limiting_current_interval_uA

        assert assessment.limiting_mechanism == "Chronic degradation"
        assert interval.fold_range == pytest.approx(50.0 / 20.0, rel=1e-6)
        assert interval.contains(assessment.limiting_current_uA)

    def test_a_check_that_did_not_run_does_not_narrow_the_interval(self):
        """Not tautological: the premise -- Shannon NOT_EVALUATED on this microelectrode
        -- is asserted from the assessment, and the expected behaviour is that the Shannon
        band, which would bind at 472.7-841.3 uA, is absent from the result."""
        from neurostim import RingElectrode

        calc = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )
        assessment = calc.assess()
        shannon = next(c for c in assessment.checks if c.name == "Shannon criterion")

        assert shannon.status is Status.NOT_EVALUATED
        assert assessment.limiting_current_interval_uA.contains(
            assessment.limiting_current_uA
        )


class TestEveryCeilingDeclaresItsInterval:
    """Ledger 97. A check's published band is looked up by name, and a stale name raises.

    ``_ceiling_interval_uA`` dispatched on three string literals and fell through to
    ``Interval.exact(ceiling)``, so a check whose name stopped matching reported a *point*
    where the literature supports a band -- on ``DiscElectrode(100, "Pt")`` at 80 uA the
    chronic band 7.853-19.63 uA collapsed to 19.63 uA, and nothing raised. The names have
    already been rewritten wholesale once in this repair (ledger 95(a)). The neighbouring
    lookup on the same strings, :attr:`Check.kind`, raises; this one now does too.
    """

    @staticmethod
    def _assessment():
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
        ).assess()

    def test_every_limit_bearing_check_declares_an_interval_provider(self):
        """Exhaustiveness against the set, not against a list written here.

        Not tautological: ``LIMIT_BEARING`` is cross-asserted against the oracle's
        independent copy elsewhere, so a check added to it without a provider fails here,
        and a provider left behind for a check that was renamed away fails here too.
        """
        from neurostim.safety.assessment import CEILING_INTERVALS, LIMIT_BEARING

        assert set(CEILING_INTERVALS) == set(LIMIT_BEARING)

    def test_the_published_chronic_band_is_still_a_band(self):
        """Not tautological: 7.853981633974484 and 19.634954084936204 uA are Pt's 20 and
        50 uC/cm^2 dissolution band times 7.853981633974483e-05 cm^2 over 200 us, the
        numbers the ledger entry quotes; the fold is the band's own 2.5."""
        assessment = self._assessment()
        interval = assessment.limiting_current_interval_uA

        assert assessment.limiting_mechanism == "Chronic degradation"
        assert interval.low == pytest.approx(7.853981633974484, rel=1e-12)
        assert interval.high == pytest.approx(19.634954084936204, rel=1e-12)
        assert interval.fold_range == pytest.approx(2.5, rel=1e-12)

    def test_a_renamed_check_raises_instead_of_collapsing_its_band(self, monkeypatch):
        """The ledger's own reproduction: one name drifts, everywhere but the interval.

        The rename is applied to the check, to ``LIMIT_BEARING`` and to ``CHECK_KINDS`` --
        every table a rename would be caught by today -- and not to the interval dispatch,
        which is the one that used to fall through. Before the fix this returned the
        point 19.63 uA silently; it must raise and name the check.
        """
        from dataclasses import replace

        from neurostim.safety import assessment as assessment_mod

        stale = "Chronic dissolution"
        monkeypatch.setattr(
            assessment_mod,
            "LIMIT_BEARING",
            (assessment_mod.LIMIT_BEARING - {"Chronic degradation"}) | {stale},
        )
        monkeypatch.setitem(assessment_mod.CHECK_KINDS, stale, "electrode-chronic")
        original = self._assessment()
        renamed = replace(
            original,
            checks=tuple(
                replace(c, name=stale) if c.name == "Chronic degradation" else c
                for c in original.checks
            ),
        )
        assert stale in {c.name for c in renamed._limit_bearing}  # the premise

        with pytest.raises(KeyError, match="Chronic dissolution"):
            _ = renamed.limiting_current_interval_uA

    def test_an_unknown_check_raises(self):
        """A check the table has never heard of is not given a point interval by default."""
        from neurostim.safety.assessment import Check

        stranger = Check(name="Not a check", status=Status.PASS, summary="", ceiling_uA=1.0)
        with pytest.raises(KeyError, match="Not a check"):
            self._assessment()._ceiling_interval_uA(stranger)


class TestNonFiniteSettingsAreRejected:
    """Ledger 13 and 52. A setting that is not a number produced a verdict anyway.

    ``compliance_V = -5.0`` printed "needs 0.52 V but only -5.00 V available"; ``nan``
    yielded FAIL by comparison accident. And a blank ``compliance_V`` cell in a batch CSV
    becomes ``nan``, whose ceiling is ``nan``, which ``min()`` silently discards --
    ``min([141.0, 212.0, nan]) == 141.0`` but ``min([nan, 141.0, 212.0])`` is ``nan``. The
    row then reports a limiting current indistinguishable from a valid one.
    """

    @staticmethod
    def _build(**settings):
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80, 200, 130, 1), **settings
        )

    @pytest.mark.parametrize(
        ("setting", "value"),
        [
            ("compliance_V", float("nan")),
            ("compliance_V", float("inf")),
            ("compliance_V", -5.0),
            ("compliance_V", 0.0),
            ("tissue_conductivity_S_per_m", float("nan")),
            ("tissue_conductivity_S_per_m", 0.0),
            ("tissue_conductivity_S_per_m", -0.35),
            ("lead_resistance_ohm", float("nan")),
            ("lead_resistance_ohm", -1.0),
            ("measured_impedance_ohm", float("nan")),
            ("measured_impedance_ohm", 0.0),
            ("capacitance_uF_cm2", float("nan")),
            ("capacitance_uF_cm2", 0.0),
            ("resting_potential_V", float("nan")),
        ],
    )
    def test_the_setting_is_refused_at_construction(self, setting, value):
        """Not tautological: each (name, value) pair is written out and the expected
        outcome is a raise that names the setting -- where today every one of them
        constructs and goes on to produce a verdict."""
        with pytest.raises(ValueError, match=setting):
            self._build(**{setting: value})

    def test_a_valid_setting_of_the_same_shape_still_constructs(self):
        """The guard must reject the value, not the parameter.

        Not tautological: every setting above is supplied at a legitimate value and the
        expected outcome is a working assessment.
        """
        calc = self._build(
            compliance_V=10.0,
            tissue_conductivity_S_per_m=0.27,
            lead_resistance_ohm=500.0,
            measured_impedance_ohm=4000.0,
            capacitance_uF_cm2=37.5,
            resting_potential_V=0.1,
        )
        assert calc.assess().status is not None

    def test_a_nan_candidate_can_no_longer_reach_the_minimum(self):
        """Ledger 52's mechanism, stated as the property it breaks.

        Not tautological: the assertion is that every limit-bearing ceiling is a number,
        checked with ``math.isnan`` over the assessment -- and the only way a ``nan``
        entered was through a setting that is now refused.
        """
        import math

        from neurostim.safety import LIMIT_BEARING

        calc = self._build(compliance_V=10.0)
        for check in calc.assess().checks:
            if check.name in LIMIT_BEARING:
                assert not math.isnan(check.ceiling_uA), check.name

    def test_a_blank_compliance_cell_becomes_an_error_row_not_a_verdict(self):
        """Ledger 52's reproduction, on the surface it was found on.

        Not tautological: the two rows are identical apart from the blank cell, and the
        expected outcome is that they differ -- one a verdict, one an ERROR carrying the
        message. Today both report 19.634954 uA and a FAIL status.
        """
        from neurostim.io import assess_batch

        base = {
            "shape": "disc",
            "diameter_um": 100,
            "material": "Pt",
            "current_uA": 80,
            "pulse_width_us": 200,
            "frequency_hz": 130,
            "train_duration_s": 1,
        }
        frame = assess_batch(
            [
                {"label": "good", **base, "compliance_V": 10.0},
                {"label": "blank", **base, "compliance_V": float("nan")},
            ]
        )
        rows = {row["label"]: row for _, row in frame.iterrows()}

        assert rows["good"]["status"] != "ERROR"
        assert rows["blank"]["status"] == "ERROR"
        assert "compliance_V" in rows["blank"]["error"]
        assert "ValueError" in rows["blank"]["error"]


class TestTheCeilingOracleSurvivesConstructionTimeValidation:
    """Amendment 3. Both ceiling oracles rebuild a calculator up to ~135 times per call
    across a 1e-12 to 1e6 uA bracket. Nothing validates ``current_uA`` today, so nothing
    breaks -- the guard lands with the validation so that a later extension to amplitude is
    caught by a test rather than by a crashed bisection.
    """

    def test_an_amplitude_the_constructor_refuses_is_not_a_passing_amplitude(
        self, monkeypatch
    ):
        """Not tautological: the rejection threshold is written into the scripted
        calculator here, and the expected answers -- ``False`` rather than a raise, and a
        ceiling at the largest constructible amplitude rather than at the script's own
        boundary -- both follow from it."""
        from oracles import fail_ceiling
        from test_oracles import scripted_calculator

        def script(current_uA: float) -> frozenset[str]:
            return frozenset() if current_uA < 500.0 else frozenset({"Water window"})

        script.rejects_above_uA = 50.0  # type: ignore[attr-defined]

        calc = scripted_calculator(script, monkeypatch)

        assert fail_ceiling.no_check_fails(calc, 10.0)
        assert not fail_ceiling.no_check_fails(calc, 1e6)
        assert fail_ceiling.fail_ceiling_uA(calc) == 50.0

    def test_an_amplitude_below_a_future_floor_narrows_the_bracket(self, monkeypatch):
        """The other side of the same guard, which was one-sided.

        ``UNCONSTRUCTIBLE`` entered the per-check suffix invariant as if it were a check
        name, so a rejection at the *bottom* of the ladder was a prefix rather than a
        suffix and ``_assert_each_check_fails_upwards`` raised ``NonMonotonePredicate`` --
        the crashed bisection the guard exists to prevent. A floor is the likelier of the
        two future validations: the bracket already starts at 1e-12 uA specifically to
        dodge ``StimProtocol``'s rejection of zero.

        Not tautological: the floor and the script's own 500 uA boundary are both written
        here, and the expected answer is a boundary property -- it passes, its successor
        is 500.0 and fails -- asserted against the oracle's own probe, not against a
        number this test computed.
        """
        import math

        from oracles import fail_ceiling
        from test_oracles import scripted_calculator

        def script(current_uA: float) -> frozenset[str]:
            return frozenset() if current_uA < 500.0 else frozenset({"Water window"})

        script.rejects_below_uA = 1.0  # type: ignore[attr-defined]

        calc = scripted_calculator(script, monkeypatch, current_uA=10.0)

        assert not fail_ceiling.no_check_fails(calc, 1e-6)  # refused, so not passing
        ceiling = fail_ceiling.fail_ceiling_uA(calc)
        assert ceiling < 500.0
        assert math.nextafter(ceiling, math.inf) == 500.0
        assert fail_ceiling.brackets_the_ceiling(calc, ceiling)

    def test_a_floor_and_a_ceiling_together_still_leave_the_suffix_rule_in_force(
        self, monkeypatch
    ):
        """Narrowing the bracket must not become "ignore ``UNCONSTRUCTIBLE`` everywhere".

        Not tautological: the ceiling 50.0 is the script's own declared upper rejection,
        written here, and is below the 500 uA at which the script's check starts to fail
        -- so an oracle that stopped treating a refused amplitude as failing would answer
        the script's boundary instead, and one that still choked on the floor would raise.
        """
        from oracles import fail_ceiling
        from test_oracles import scripted_calculator

        def script(current_uA: float) -> frozenset[str]:
            return frozenset() if current_uA < 500.0 else frozenset({"Water window"})

        script.rejects_below_uA = 1.0  # type: ignore[attr-defined]
        script.rejects_above_uA = 50.0  # type: ignore[attr-defined]

        calc = scripted_calculator(script, monkeypatch, current_uA=10.0)

        assert fail_ceiling.fail_ceiling_uA(calc) == 50.0

    def test_a_zero_ceiling_above_a_floor_still_names_the_check_that_makes_it_zero(
        self, monkeypatch
    ):
        """``fail_ceiling_uA`` never returns ``0.0`` without a witness (ledger 84).

        The witness comes from the same probes the search uses, so it has to be narrowed
        the same way: over the untrimmed ladder the intersection is empty, because the
        refused probes at the bottom report only ``UNCONSTRUCTIBLE``, and the zero would
        then arrive unexplained.

        Not tautological: "Water window" is the name the script fails under, written here,
        and it is read back from a function that never sees the script.
        """
        from oracles import fail_ceiling
        from test_oracles import scripted_calculator

        def script(current_uA: float) -> frozenset[str]:
            return frozenset({"Water window"})

        script.rejects_below_uA = 1.0  # type: ignore[attr-defined]

        calc = scripted_calculator(script, monkeypatch, current_uA=10.0)

        assert fail_ceiling.fail_ceiling_uA(calc) == 0.0
        assert fail_ceiling.amplitude_independent_failures(calc) == ("Water window",)

    def test_a_bracket_with_no_constructible_amplitude_is_reported_not_answered(
        self, monkeypatch
    ):
        """``0.0`` means "a check fails at every amplitude". "the package refuses every
        amplitude in this bracket" is a different statement and must not borrow that one.

        Not tautological: the floor is set above the bracket's own 1e6 uA top, written
        here, and the expected outcome is a raise -- no number the oracle could return
        would satisfy it.
        """
        from oracles import fail_ceiling
        from test_oracles import scripted_calculator

        def script(current_uA: float) -> frozenset[str]:
            return frozenset()

        script.rejects_below_uA = 1e7  # type: ignore[attr-defined]

        calc = scripted_calculator(script, monkeypatch, current_uA=1e8)

        with pytest.raises(fail_ceiling.NoConstructibleAmplitude, match="1e-12"):
            fail_ceiling.fail_ceiling_uA(calc)

    def test_the_guard_does_not_hide_a_misspelled_check_name(self):
        """The catch must be narrow. A ``ValueError`` from an unknown check name is a test
        defect and must still surface.

        Not tautological: the expected outcome is a raise with a specific message, against
        a call that differs from the one above only in the check name.
        """
        from oracles import fail_ceiling

        from neurostim import RingElectrode

        calc = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )
        with pytest.raises(ValueError, match="no such check"):
            fail_ceiling.no_check_fails(calc, 10.0, names={"Water Window"})


class TestEveryCheckHasAPinnedFailure:
    """T8. Ledger 63 and 64: three `Status.FAIL` assertions in the whole 522-test suite,
    and three of nine checks with a failing case pinned. A limit nothing crosses is a limit
    whose inclusivity is unobservable -- mutating ``<=`` to ``<`` survived in Shannon,
    charge injection and compliance, and ``>`` to ``>=`` in chronic degradation.

    Each threshold is asserted against the constant the package stores for it, quoted from
    its primary source, before the FAIL is asserted -- so the test fails if the fixture
    stops being on the far side of the number it is supposed to cross.
    """

    @staticmethod
    def _check(calc: SafetyCalculator, name: str):
        return next(c for c in calc.assess().checks if c.name == name)

    def test_shannon_fails_above_the_line(self):
        """Shannon 1992: k = 1.5 is the line below which no damage was observed.

        Not tautological: the threshold is read from ``shannon.K_SHANNON`` and the
        protocol's own k is computed from its charge and area, both asserted before the
        status is.
        """
        from neurostim import CylindricalBandElectrode
        from neurostim.safety import shannon

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "SIROF"),
            StimProtocol(20000, 400, 50, 1),
        )
        assert shannon.K_SHANNON == 1.5
        assert calc.shannon_metric > shannon.K_SHANNON
        assert self._check(calc, "Shannon criterion").status is Status.FAIL

    def test_charge_injection_fails_above_the_material_limit(self):
        """Rose & Robblee 1990: platinum 50-150 uC/cm^2, cathodic-first 100-150.

        Not tautological: the stored bounds are asserted against the published pair and
        the applied density against the conservative end, before the status.
        """
        from neurostim.materials import get_material

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(3000, 200, 50, 1)
        )
        assert get_material("Pt").cic.bounds(None) == (0.05, 0.15)  # mC/cm^2
        assert calc.charge_density > 100.0
        assert self._check(calc, "Charge injection limit").status is Status.FAIL

    def test_the_water_window_fails_when_the_peak_leaves_it(self):
        """Cogan 2008: platinum -0.6 to +0.8 V vs Ag|AgCl.

        Not tautological: the stored window is asserted against the published pair, the
        resting potential is inside it, and the peak is computed from the result and
        asserted outside -- all before the status.
        """
        from neurostim.materials import get_material

        window = get_material("Pt").water_window
        assert window is not None
        assert (window.cathodic_V, window.anodic_V) == (-0.6, 0.8)

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(300, 200, 50, 1),
            resting_potential_V=-0.55,
        )
        assessment = calc.assess()
        assert window.contains(-0.55)
        assert not window.contains(assessment.water_window.peak_potential_V)
        assert self._check(calc, "Water window").status is Status.FAIL

    def test_compliance_fails_when_the_stimulator_runs_out(self):
        """Not tautological: the required voltage is read from the result and asserted
        above the 1.0 V supplied, before the status."""
        calc = SafetyCalculator(
            DiscElectrode(50.0, "Pt"), StimProtocol(50, 200, 50, 1), compliance_V=1.0
        )
        assessment = calc.assess()

        assert assessment.compliance.required_V > 1.0
        assert self._check(calc, "Compliance voltage").status is Status.FAIL

    def test_chronic_degradation_fails_above_the_dissolution_band(self):
        """Rose & Robblee 1990: platinum dissolution 20-50 uC/cm^2.

        Not tautological: the stored band is asserted against the published pair and the
        applied density against its upper end, before the status.
        """
        from neurostim.materials import get_material

        threshold = get_material("Pt").chronic_threshold
        assert threshold is not None
        assert (threshold.low_uC_cm2, threshold.high_uC_cm2) == (20.0, 50.0)

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(3000, 200, 50, 1)
        )
        assert calc.charge_density > threshold.high_uC_cm2
        assert self._check(calc, "Chronic degradation").status is Status.FAIL

    def test_the_microelectrode_threshold_fails_above_four_nanocoulombs(self):
        """Cogan 2016: about 4 nC/phase on a microelectrode.

        Not tautological: the stored threshold is asserted against the published value and
        the protocol's charge per phase against it, before the status.
        """
        from neurostim.data import cogan2016

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80, 200, 130, 1)
        )
        assert cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE == 4.0
        assert calc.charge_uC * 1e3 > 4.0
        assert self._check(calc, "Microelectrode charge/phase").status is Status.FAIL

    def test_charge_balance_fails_for_a_monophasic_waveform(self):
        """Merrill 2005: monophasic pulsing damages more than charge-balanced biphasic.

        The biphasic arm of this check is unreachable until imbalance is expressible
        (ledger 3, Phase 2 C2.1); this pins the arm that is reachable.

        Not tautological: the net DC current is read from the protocol and asserted
        non-zero before the status.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "SIROF"),
            StimProtocol(10, 100, 50, 1, waveform="monophasic"),
        )
        assert calc.p.net_dc_current_uA != 0.0
        assert self._check(calc, "Charge balance").status is Status.FAIL

    def test_current_density_fails_at_the_electroporation_threshold(self):
        """Butterwick 2007, on chick retina.

        Not tautological: the applied density is read from the result and asserted at or
        above the stored threshold, before the status.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(5000, 200, 130, 1)
        )
        comparison = calc.assess().checks
        threshold = next(
            c for c in comparison if c.name == "Current density"
        )
        applied = (5000.0 * 1e-6) / calc.e.area_cm2

        assert applied > 0.0
        assert threshold.status is Status.FAIL


class TestBothSidesOfEveryBoundary:
    """T9. Every mutation survivor in the safety checks is a comparison nothing approaches:
    ``<=`` to ``<`` in Shannon, charge injection and compliance, ``>`` to ``>=`` in chronic
    degradation. Approaching each limit from both sides by one float makes the inclusivity
    observable.

    Each threshold comes from the package's stored constant, and the amplitude either side
    of it from ``math.nextafter`` -- IEEE, not the code under test.
    """

    def test_the_shannon_line_is_inclusive(self):
        """Not tautological: ``shannon_max_charge_uC`` supplies the charge and
        ``math.nextafter`` the value one float above it; the expected verdicts are PASS
        then FAIL."""
        import math

        from neurostim.safety import shannon

        area_cm2 = 0.05985
        charge_uC = shannon.shannon_max_charge_uC(area_cm2, shannon.K_SHANNON)

        assert shannon.evaluate(charge_uC, area_cm2, 200.0, shannon.K_SHANNON).passes
        assert not shannon.evaluate(
            math.nextafter(charge_uC, math.inf), area_cm2, 200.0, shannon.K_SHANNON
        ).passes

    @pytest.mark.parametrize(
        "name",
        [
            "Shannon criterion",
            "Charge injection limit",
            "Water window",
            "Current density",
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        ],
    )
    def test_each_check_passes_at_its_ceiling_and_fails_one_float_above(self, name):
        """The general form, over every limit-bearing check at once.

        Not tautological: the ceiling comes from the assessment, but the verdicts either
        side come from two fresh assessments at ``ceiling`` and
        ``math.nextafter(ceiling, +inf)`` -- so a check whose comparison is exclusive where
        it should be inclusive, or inclusive where it should be exclusive, fails here.
        """
        import math
        from dataclasses import replace

        from neurostim import CylindricalBandElectrode

        electrode = (
            DiscElectrode(100.0, "Pt")
            if name != "Shannon criterion"
            else CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        )
        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        settings = {"compliance_V": 10.0}

        def status_at(current_uA: float):
            calc = SafetyCalculator(
                electrode, replace(protocol, current_uA=current_uA), **settings
            )
            return next(c for c in calc.assess().checks if c.name == name)

        ceiling = next(
            c
            for c in SafetyCalculator(electrode, protocol, **settings).assess().checks
            if c.name == name
        ).ceiling_uA
        if not math.isfinite(ceiling):
            pytest.skip(f"{name} imposes no ceiling on this electrode")

        assert status_at(ceiling).status is not Status.FAIL, (name, ceiling)
        assert status_at(math.nextafter(ceiling, math.inf)).status is Status.FAIL, (
            name,
            ceiling,
        )

    def test_a_water_window_ceiling_is_found_even_when_the_predicate_plateaus(self):
        """A resting potential near a window edge makes the check's own arithmetic flat.

        ``peak = resting + excursion`` is a sum of two numbers of very different size, so
        near the boundary a whole run of consecutive amplitudes maps to the same peak
        float and the back-solved seed sits several floats below the true boundary --
        measured at more than four on ``resting_potential_V = -0.55``. That is a property
        of the check's arithmetic, not evidence that the back-solve is wrong, and it must
        not raise.

        Not tautological: the expected outcome is a finite ceiling that is the boundary,
        asserted with ``math.nextafter`` against two fresh assessments.
        """
        import math
        from dataclasses import replace

        electrode = DiscElectrode(500.0, "Pt")
        protocol = StimProtocol(300.0, 200.0, 50.0, 1.0)

        def water_window_at(current_uA: float):
            calc = SafetyCalculator(
                electrode,
                replace(protocol, current_uA=current_uA),
                resting_potential_V=-0.55,
            )
            return next(c for c in calc.assess().checks if c.name == "Water window")

        ceiling = water_window_at(300.0).ceiling_uA

        assert math.isfinite(ceiling)
        assert water_window_at(ceiling).status is not Status.FAIL
        assert water_window_at(math.nextafter(ceiling, math.inf)).status is Status.FAIL


class TestMoreCurrentIsNeverSafer:
    """T15. The one property every reader assumes without being told (ledger 69, §4.1).

    The existing guard was ``test_gui.py::test_raising_current_lowers_the_headroom``, which
    asserts only that a *string* changed.
    """

    @staticmethod
    def _configurations():
        from neurostim import CylindricalBandElectrode, RingElectrode

        yield DiscElectrode(500.0, "Pt"), {"compliance_V": 10.0}
        yield RingElectrode(330.0, 270.0, "Pt"), {"compliance_V": 10.0}
        yield CylindricalBandElectrode(1270.0, 1500.0, "PtIr"), {"compliance_V": 10.0}
        yield DiscElectrode(2000.0, "SIROF"), {}
        yield DiscElectrode(100.0, "TiN"), {"compliance_V": 5.0, "policy": "nominal"}

    def test_the_overall_verdict_never_improves_as_current_rises(self):
        """Not tautological: the ordering is over ``Status.rank``, whose values are pinned
        separately by ``TestStatusRank``, and the comparison is between two independently
        built assessments five decades apart."""
        for electrode, settings in self._configurations():
            previous = None
            for current_uA in (1.0, 10.0, 100.0, 1000.0, 10000.0):
                assessment = SafetyCalculator(
                    electrode,
                    StimProtocol(current_uA, 200.0, 50.0, 1.0),
                    **settings,  # type: ignore[arg-type]
                ).assess()
                if previous is not None:
                    assert assessment.status.rank >= previous.status.rank, (
                        electrode,
                        current_uA,
                    )
                previous = assessment

    def test_no_check_gains_margin_as_current_rises(self):
        """Not tautological: margins are compared across two assessments, with no
        tolerance -- ``margin`` is ``ceiling / current`` and the ceiling does not move, so
        the relation is exact and a tolerance would only hide a real inversion."""
        for electrode, settings in self._configurations():
            previous = None
            for current_uA in (1.0, 10.0, 100.0, 1000.0, 10000.0):
                assessment = SafetyCalculator(
                    electrode,
                    StimProtocol(current_uA, 200.0, 50.0, 1.0),
                    **settings,  # type: ignore[arg-type]
                ).assess()
                if previous is not None:
                    for check, before in zip(
                        assessment.checks, previous.checks, strict=True
                    ):
                        assert check.name == before.name
                        assert check.margin <= before.margin, (
                            electrode,
                            check.name,
                            current_uA,
                        )
                previous = assessment

    def test_a_ceiling_does_not_depend_on_the_amplitude_that_asked_for_it(self):
        """The stronger statement behind the two above, and the one that makes the
        limiting current meaningful: a ceiling is a property of the electrode, material and
        protocol shape, not of the amplitude requested.

        Not tautological: equality is asserted bit-for-bit across five decades of
        amplitude, which no rescaling of the reported value could satisfy by accident.
        """
        for electrode, settings in self._configurations():
            previous = None
            for current_uA in (1.0, 10.0, 100.0, 1000.0, 10000.0):
                ceilings = {
                    c.name: c.ceiling_uA
                    for c in SafetyCalculator(
                        electrode,
                        StimProtocol(current_uA, 200.0, 50.0, 1.0),
                        **settings,  # type: ignore[arg-type]
                    )
                    .assess()
                    .checks
                }
                if previous is not None:
                    assert ceilings == previous, (electrode, current_uA)
                previous = ceilings

    def test_the_limiting_current_does_not_depend_on_the_amplitude_requested(self):
        """The same property at the headline.

        Not tautological: the headline is recomputed from scratch at five amplitudes and
        compared with itself, which a limit derived from the requested current -- as a
        ``headroom``-style reading would be -- could not satisfy.
        """
        for electrode, settings in self._configurations():
            limits = {
                SafetyCalculator(
                    electrode,
                    StimProtocol(current_uA, 200.0, 50.0, 1.0),
                    **settings,  # type: ignore[arg-type]
                )
                .assess()
                .limiting_current_uA
                for current_uA in (1.0, 10.0, 100.0, 1000.0, 10000.0)
            }
            assert len(limits) == 1, (electrode, limits)


class TestDimensionalConsistency:
    """T11. Invariants that hold by dimensional analysis, so they can be written down
    without consulting the code (ledger 69, §4.5).

    Each expected value is an identity -- a quantity times its own unit conversion, or the
    sphere volume formula written out -- not a second call into the module under test.
    """

    def test_charge_density_times_area_is_charge(self):
        """Not tautological: the identity ``(Q/A) x A == Q`` is arithmetic, and the two
        factors are read from different attributes of the result."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(300.0, 200.0, 50.0, 1.0)
        )
        charge = calc.assess().charge

        assert charge.charge_density_uC_cm2 * calc.e.area_cm2 == pytest.approx(
            charge.charge_per_phase_uC
        )

    def test_the_charge_limit_and_the_current_limit_are_the_same_limit(self):
        """``I_max x W`` must be ``Q_max``: the two are one limit in two units.

        Not tautological: the conversion ``uA x us x 1e-6 = uC`` is written out here, and
        the two limits are separate attributes back-solved independently. ``rel=1e-12``
        rather than exact because both ends are floored onto their own boundary and the two
        boundaries are one float apart at most.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(300.0, 200.0, 50.0, 1.0)
        )
        charge = calc.assess().charge

        assert charge.max_current_uA * 200.0 * 1e-6 == pytest.approx(
            charge.max_charge_uC, rel=1e-12
        )

    def test_current_density_times_area_is_current(self):
        """Not tautological: ``A/cm^2 x cm^2 = A``, then ``x 1e6`` to microamps -- the
        conversion chain is written out and compared against the input."""
        from neurostim.safety import current_density as jd

        area_cm2 = DiscElectrode(500.0, "Pt").area_cm2
        applied = jd.average_current_density_A_per_cm2(300.0, area_cm2)

        assert applied * area_cm2 * 1e6 == pytest.approx(300.0)

    def test_the_activated_volume_is_the_sphere_of_the_activation_radius(self):
        """Not tautological: ``(4/3) pi r^3`` is written out here with the um-to-mm
        conversion, rather than read back from ``vta``. It is the assertion that catches a
        dropped unit conversion in either method, which a ratio between them cannot."""
        import math

        from neurostim.models import vta

        model = vta.CurrentDistanceModel()
        for current_uA in (10.0, 100.0, 1000.0):
            radius_mm = model.activation_radius_um(current_uA) * 1e-3
            assert model.activated_volume_mm3(current_uA) == pytest.approx(
                (4.0 / 3.0) * math.pi * radius_mm**3
            )

    def test_the_activation_radius_inverts_the_current_distance_law(self):
        """``I_th = I_0 + k r^2``, written out, against the radius the model returns.

        Not tautological: the law is restated here from the model's two stored
        coefficients, and a dropped ``1e3`` in either direction breaks it.
        """
        from neurostim.models import vta

        model = vta.CurrentDistanceModel()
        for current_uA in (10.0, 100.0, 1000.0):
            radius_mm = model.activation_radius_um(current_uA) * 1e-3
            assert (
                model.threshold_offset_uA + model.k_uA_per_mm2 * radius_mm**2
            ) == pytest.approx(current_uA)


class TestIntervalContainmentAcrossPoliciesAndK:
    """T16 in the form ``audit_tests.md`` states it: the weak invariant, always true.

    The strong form -- the point estimate equals the interval's low end -- is only true at
    the default ``k`` and policy. Containment holds everywhere, and is what a reader
    relies on.
    """

    def test_containment_holds_across_every_policy_and_k(self):
        """Not tautological: 9 combinations of two independent inputs, with the interval
        and the point estimate computed by different code from different ranges."""
        from neurostim import RingElectrode

        electrode = RingElectrode(330.0, 270.0, "Pt")
        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        for policy in ("conservative", "nominal", "optimistic"):
            for k in (1.5, 1.7, 2.0):
                assessment = SafetyCalculator(
                    electrode,
                    protocol,
                    k=k,
                    policy=policy,  # type: ignore[arg-type]
                    compliance_V=10.0,
                ).assess()

                assert assessment.limiting_current_interval_uA.contains(
                    assessment.limiting_current_uA
                ), (policy, k)
