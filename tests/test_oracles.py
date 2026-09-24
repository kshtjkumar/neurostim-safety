"""Pins for ``tests/oracles`` -- the expected values every later phase will assert against.

An oracle that drifts is worse than no oracle: it makes a wrong answer look confirmed. So
each one is pinned here to a constant computed by hand, from the physics or from a
published number, never from the package.

These tests say nothing about whether the package is right. Several of them record that it
is currently wrong -- the ceiling is 20.0 uA where the package reports 141.4, and the field
model is low by exactly a factor of two. That is the point: the oracles are built and
verified before the repairs that will be judged against them, so the expected values cannot
be quietly reshaped to agree with whatever the fix happens to produce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from oracles import disc_field, drift, fail_ceiling, fd_band

# --- the worked example the plan is built around ------------------------------------
#
# RingElectrode(330, 270, "Pt") at 80 uA, 200 us, 130 Hz, compliance 10 V. The package
# reports a limiting current of 141.37166941154072 uA while two checks FAIL at 80 uA.

RING_OUTER_UM = 330.0
RING_INNER_UM = 270.0
PULSE_WIDTH_US = 200.0


# --- a calculator whose verdicts are written here, not computed ----------------------
#
# Two of the guards below are about the SHAPE of ``assess().failed`` across amplitude --
# FAIL, then PASS, then FAIL -- rather than about any package verdict. Until C1.2 they
# were driven by a real calculator at ``resting_potential_V = 0.9`` / ``0.95`` on Pt,
# which is exactly the input class C1.2 refuses at construction, for exactly this reason.
# Scripting the shape keeps the guards alive after the input that produced it is gone,
# and makes the expected ``NonMonotonePredicate`` a property of the script rather than of
# the package.
#
# The script travels in the ``electrode`` slot, so it survives ``rebuild_at``'s explicit
# forwarding like any other construction argument, and the oracle is exercised whole --
# ladder, per-check suffix invariant and all -- rather than monkeypatched out of the way.

SCRIPTED_SETTINGS = {
    # Every carried argument at a value that is NOT its constructor default, so a
    # forwarding defect shows up as a TypeError here instead of being absorbed silently
    # (the fixture rule the rebuild_at mutant earned).
    "k": 1.75,
    "material": "SIROF",
    "policy": "optimistic",
    "medium": "pbs",
    "tissue_conductivity_S_per_m": 0.27,
    "lead_resistance_ohm": 123.0,
    "compliance_V": 7.5,
    "measured_impedance_ohm": 4321.0,
    "resting_potential_V": 0.11,
    "capacitance_uF_cm2": 37.5,
    "counter_electrode": "scripted counter",
    "counter_separation_um": 2345.0,
}


@dataclass(frozen=True)
class ScriptedProtocol:
    """All of a protocol that ``rebuild_at`` touches: an amplitude it can ``replace``."""

    current_uA: float


@dataclass(frozen=True)
class ScriptedCheck:
    """All of a check that the oracle reads: its name."""

    name: str


@dataclass(frozen=True)
class ScriptedAssessment:
    """All of an assessment that the oracle reads: ``checks`` and ``failed``."""

    checks: tuple[ScriptedCheck, ...]
    failed: tuple[ScriptedCheck, ...]


class ScriptedCalculator:
    """A calculator whose failing checks come from a callable, not from any physics.

    The constructor signature is ``SafetyCalculator``'s, argument for argument, because
    ``rebuild_at`` names all fourteen and checks them against
    ``fail_ceiling.CARRIED_ARGUMENTS`` before it builds anything. Each carried value is
    asserted on arrival against :data:`SCRIPTED_SETTINGS`, so a forward that is quietly
    dropped fails the test instead of scripting the same answer anyway.
    """

    def __init__(
        self,
        electrode,
        protocol,
        k=1.5,
        *,
        material=None,
        policy="conservative",
        medium="saline",
        tissue_conductivity_S_per_m=0.35,
        lead_resistance_ohm=0.0,
        compliance_V=None,
        measured_impedance_ohm=None,
        resting_potential_V=0.0,
        capacitance_uF_cm2=None,
        counter_electrode=None,
        counter_separation_um=None,
    ) -> None:
        self.e = electrode  # the script
        self.p = protocol
        self.k = k
        self.material = material
        self.policy = policy
        self.medium = medium
        self.tissue_conductivity_S_per_m = tissue_conductivity_S_per_m
        self.lead_resistance_ohm = lead_resistance_ohm
        self.compliance_V = compliance_V
        self.measured_impedance_ohm = measured_impedance_ohm
        self.resting_potential_V = resting_potential_V
        self.capacitance_uF_cm2 = capacitance_uF_cm2
        self.counter_electrode = counter_electrode
        self.counter_separation_um = counter_separation_um
        for name, expected in SCRIPTED_SETTINGS.items():
            assert getattr(self, name) == expected, (
                f"{name} did not survive the rebuild: {getattr(self, name)!r} "
                f"against {expected!r}"
            )
        # Optional: a script may declare amplitudes outside which the calculator refuses
        # to exist, standing in for a future validation of `current_uA`. Nothing in the
        # package rejects an amplitude today, which is why it has to be scripted to be
        # tested at all -- see fail_ceiling.UNCONSTRUCTIBLE. Both ends, because a floor is
        # the likelier future validation of the two: the oracle's bracket starts at
        # 1e-12 uA specifically to dodge `StimProtocol`'s rejection of zero.
        ceiling = getattr(electrode, "rejects_above_uA", math.inf)
        if protocol.current_uA > ceiling:
            raise ValueError(
                f"current_uA must be <= {ceiling!r}, got {protocol.current_uA!r}"
            )
        floor = getattr(electrode, "rejects_below_uA", 0.0)
        if protocol.current_uA < floor:
            raise ValueError(
                f"current_uA must be >= {floor!r}, got {protocol.current_uA!r}"
            )

    def assess(self) -> ScriptedAssessment:
        failing = self.e(self.p.current_uA)
        checks = tuple(ScriptedCheck(name) for name in sorted(SCRIPTED_CHECK_NAMES))
        return ScriptedAssessment(
            checks=checks,
            failed=tuple(check for check in checks if check.name in failing),
        )


SCRIPTED_CHECK_NAMES = frozenset(
    {"Water window", "Charge injection limit", "Shannon criterion"}
)
"""The names a scripted assessment emits. Real check names, so ``names=`` still resolves."""

def scripted_calculator(
    script, monkeypatch, *, current_uA: float = 1.0
) -> ScriptedCalculator:
    """A :class:`ScriptedCalculator` whose failing checks at an amplitude are ``script``.

    ``rebuild_at`` imports ``SafetyCalculator`` from ``neurostim`` at call time and builds
    that class, which is the whole reason it can be asserted about. So the substitution is
    made where the oracle looks, for the duration of one test, rather than by teaching the
    oracle a second construction path it would then carry into production use.

    ``_assert_constructor_is_frozen`` still runs, against
    :class:`ScriptedCalculator`'s own signature -- which is why that signature repeats
    ``SafetyCalculator``'s argument for argument.
    """
    import neurostim

    monkeypatch.setattr(neurostim, "SafetyCalculator", ScriptedCalculator)
    return ScriptedCalculator(
        script, ScriptedProtocol(current_uA=current_uA), **SCRIPTED_SETTINGS
    )


@pytest.fixture
def worked_example():
    from neurostim import RingElectrode, SafetyCalculator, StimProtocol

    return SafetyCalculator(
        RingElectrode(RING_OUTER_UM, RING_INNER_UM, "Pt"),
        StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
        compliance_V=10.0,
    )


class TestFailCeiling:
    """Oracle (a): binary search over ``assess().failed``."""

    def test_the_ceiling_on_the_worked_example_is_twenty_microamps(self, worked_example) -> None:
        """Pinned to Cogan 2016's microelectrode threshold, not to the search.

        4 nC per phase over a 200 us pulse is 4e-9 C / 200e-6 s = 2e-5 A = 20 uA. The
        binding check is a published charge-per-phase threshold divided by a pulse width;
        the arithmetic is one line and does not involve the package.
        """
        from neurostim.data import cogan2016

        threshold_nC = cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE
        expected_uA = (threshold_nC * 1e-9) / (PULSE_WIDTH_US * 1e-6) * 1e6
        assert threshold_nC == 4.0
        assert expected_uA == 20.0

        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)
        assert ceiling == 20.0

    def test_the_ceiling_really_is_the_boundary(self, worked_example) -> None:
        """Passes at the ceiling and fails one ulp above it.

        A finiteness assertion would admit -21.095 uA, which is what the naive
        headroom/excursion reading of the water-window margin returns on this very case.
        """
        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)
        assert ceiling > 0.0
        assert fail_ceiling.brackets_the_ceiling(worked_example, ceiling)

    def test_the_package_headline_now_agrees_with_the_ceiling(self, worked_example) -> None:
        """What this recorded, and what it records now.

        Written in Phase 0 to record the defect while it stood: the package reported
        141.37166941154072 uA against a ceiling of 20.0, a factor of 7.0686, while
        Microelectrode charge/phase and Chronic degradation were both FAILing at 80 uA.
        Keeping that assertion after C1.6 fixed it would have pinned the defect in place.

        It still earns its keep, and for the same reason it did then: the oracle is
        written from ``assess().failed`` alone and reads no package-computed limit, so an
        agreement between the two is evidence about the package rather than a restatement
        of it. The 7.0686 is kept as the *historical* ratio, asserted against the
        superseded value rather than against anything live.
        """
        assessment = worked_example.assess()
        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)

        assert ceiling == 20.0
        assert assessment.limiting_current_uA == pytest.approx(ceiling, rel=1e-12)
        assert 141.37166941154072 / ceiling == pytest.approx(7.0686, rel=1e-4)
        # The two checks that were FAILing at 80 uA while the headline said 141 uA.
        assert {check.name for check in assessment.failed} == {
            "Microelectrode charge/phase",
            "Chronic degradation",
        }

    def test_the_oracle_reads_only_the_failed_tuple(self) -> None:
        """Structural, not behavioural: the module must not name what it is used to check."""
        text = Path(fail_ceiling.__file__ or "").read_text(encoding="utf-8")
        body = text.split('"""', 2)[-1]  # skip the module docstring, which discusses them
        for forbidden in ("limiting_current_uA", "limiting_mechanism", ".margin"):
            assert forbidden not in body, f"the oracle reads {forbidden}, which it must not"

    def test_a_non_monotone_predicate_is_reported_not_bisected(self, monkeypatch) -> None:
        """The shape the module's docstring promises to report, and used to answer 0.0 on.

        Driven by a scripted calculator rather than by a real one. The case this used to
        use -- ``resting_potential_V = 0.9 V``, already outside Pt's +0.8 V window at rest
        -- is refused at construction from C1.2 onward, precisely because it is the input
        class that makes the water-window verdict non-monotone. Leaving the test pointed
        at it would have turned this guard into dead code, and the guard has to stay live:
        C2.3 moves the DC-drift verdict onto Water window, which can legitimately
        reintroduce amplitude dependence there.

        Not tautological: the FAIL / PASS / FAIL script is written here, so the expected
        ``NonMonotonePredicate`` is a property of the script rather than of any package
        verdict. The band [9, 22] uA straddles the real case's [9.83, 19.61].
        """

        def script(current_uA: float) -> frozenset[str]:
            outside_the_window_at_rest = current_uA < 9.0 or current_uA > 22.0
            return frozenset({"Water window"}) if outside_the_window_at_rest else frozenset()

        calc = scripted_calculator(script, monkeypatch)
        # The band is real, and it does not reach the bottom of the bracket.
        assert fail_ceiling.no_check_fails(calc, 15.0)
        assert not fail_ceiling.no_check_fails(calc, 1e-12)

        with pytest.raises(fail_ceiling.NonMonotonePredicate, match="Water window"):
            fail_ceiling.fail_ceiling_uA(calc)

    def test_zero_means_no_amplitude_in_the_bracket_passes(self) -> None:
        """0.0 is the right answer for an amplitude-independent failure -- and only that.

        Ledger 84: Charge balance FAILs at every amplitude on a monophasic protocol,
        being a property of the waveform. 0.0 must therefore stay reachable, but it must
        mean "no probe anywhere in the bracket passes", not "the lower bracket failed".

        Water window joins the failing set at this amplitude after C2.3 -- 35.1 uA of net
        DC reaches the window edge in 0.256 s of a 1 s train -- and that is the distinction
        this test is about: it FAILs *here* and not at 1e-12 uA, so it is not in the
        witness, while Charge balance is.
        """
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )
        assert {check.name for check in calc.assess().failed} == {
            "Charge balance",
            "Water window",
        }
        assert fail_ceiling.fail_ceiling_uA(calc) == 0.0
        # And the answer is distinguishable from a ceiling at the call site.
        assert not fail_ceiling.brackets_the_ceiling(calc, 0.0)
        # 0.0 carries its witness: the check that FAILs at every sampled amplitude.
        assert fail_ceiling.amplitude_independent_failures(calc) == ("Charge balance",)

    def test_a_band_narrower_than_one_probe_step_is_reported(self, monkeypatch) -> None:
        """The hole a passing-probe prefix leaves open, and a per-check suffix closes.

        Scripted for the same reason as the non-monotone test above: the real case,
        ``resting_potential_V = 0.95`` on Pt, stops being constructible at C1.2. The
        script reproduces its shape exactly -- Water window FAILing below the band,
        Charge injection limit FAILing above it, and nothing failing in between.

        The band [60, 78] uA is chosen to fall between two consecutive ladder probes.
        The default ladder is ``1e-12 * 10**(n/4)``, so its neighbours here are 56.23 and
        100 uA and no probe lands inside: every probe fails, and a rule that only asked
        for the passing probes to be a prefix would conclude "no amplitude passes" when
        the ceiling is 78. What is visible at the probes is that Water window FAILs at
        56.23 uA and does NOT fail at 100 uA, which no monotone predicate may do.

        Not tautological: both thresholds and the band are literals in the script, and the
        expected ``NonMonotonePredicate`` follows from them and from the ladder's own
        geometry, neither of which the package computes.
        """

        def script(current_uA: float) -> frozenset[str]:
            failing = set()
            if current_uA < 60.0:
                failing.add("Water window")
            if current_uA > 78.0:
                failing.add("Charge injection limit")
            return frozenset(failing)

        calc = scripted_calculator(script, monkeypatch)
        assert fail_ceiling.no_check_fails(calc, 65.0)  # the band is real
        assert not fail_ceiling.no_check_fails(calc, 56.234)  # and no probe lands in it
        assert not fail_ceiling.no_check_fails(calc, 100.0)
        assert "Water window" in fail_ceiling.failing_checks(calc, 56.234)
        assert "Water window" not in fail_ceiling.failing_checks(calc, 100.0)

        with pytest.raises(fail_ceiling.NonMonotonePredicate, match="Water window"):
            fail_ceiling.fail_ceiling_uA(calc)

    def test_the_forwarded_construction_arguments_survive_the_rebuild(self) -> None:
        """rebuild_at names every argument; this asserts it also passes them.

        The signature guard catches an argument the constructor grew. It cannot catch one
        the call site stopped forwarding -- and dropping ``compliance_V`` alone moves the
        limit-bearing ceiling of a SIROF macroelectrode from 1397.01 to 2491.81 uA, a
        78 % error, with every other test still green.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(250.0, "Pt"),
            StimProtocol(37.0, 150.0, 90.0, 12.0),
            1.75,
            # Deliberately not the electrode's own material: an argument whose value
            # equals the default it would fall back to cannot detect not being passed.
            material="SIROF",
            policy="optimistic",
            medium="pbs",
            tissue_conductivity_S_per_m=0.27,
            lead_resistance_ohm=123.0,
            compliance_V=7.5,
            measured_impedance_ohm=4321.0,
            resting_potential_V=0.11,
            capacitance_uF_cm2=37.5,
        )
        rebuilt = fail_ceiling.rebuild_at(calc, 1.0)
        assert rebuilt.p.current_uA == 1.0
        for attribute in (
            "e",
            "k",
            "material",
            "policy",
            "medium",
            "tissue_conductivity_S_per_m",
            "lead_resistance_ohm",
            "compliance_V",
            "measured_impedance_ohm",
            "resting_potential_V",
            "capacitance_uF_cm2",
        ):
            assert getattr(rebuilt, attribute) == getattr(calc, attribute), attribute
        assert replace(rebuilt.p, current_uA=calc.p.current_uA) == calc.p

    def test_a_non_positive_ceiling_never_brackets(self, worked_example) -> None:
        """``brackets_the_ceiling`` must report, not raise. -21.095 is the naive margin."""
        for value in (0.0, -21.095, -math.inf, math.inf, math.nan):
            assert not fail_ceiling.brackets_the_ceiling(worked_example, value)

    def test_the_answer_is_checked_before_it_is_returned(
        self, worked_example, monkeypatch
    ) -> None:
        """The docstring's guarantee, made testable rather than asserted in prose."""
        monkeypatch.setattr(
            fail_ceiling, "brackets_the_ceiling", lambda *args, **kwargs: False
        )
        with pytest.raises(fail_ceiling.NonMonotonePredicate):
            fail_ceiling.fail_ceiling_uA(worked_example)

    def test_the_limit_bearing_names_are_the_eight_the_plan_settles_on(
        self, worked_example
    ) -> None:
        """D3 names eight since C3.11 (the counter electrode's charge injection, emitted only
        with a counter). The two it excludes impose no current ceiling."""
        assert set(fail_ceiling.LIMIT_BEARING) == {
            "Shannon criterion",
            "Charge injection limit",
            "Water window",
            "Current density",
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
            "Counter charge injection",
        }
        emitted = {check.name for check in worked_example.assess().checks}
        assert set(fail_ceiling.LIMIT_BEARING) - fail_ceiling.COUNTER_ONLY_CHECKS <= emitted
        assert emitted - set(fail_ceiling.LIMIT_BEARING) == {
            "Charge balance",
            "Validated envelope",
        }

    def test_the_limit_bearing_ceiling_is_the_quantity_d3_restates(self) -> None:
        """Ledger 84 restates D3(i) as the highest amplitude at which no LIMIT-BEARING
        check FAILs. On a monophasic protocol the qualifier changes the answer, which is
        why it is load-bearing: Charge balance FAILs at every amplitude and bears no
        limit, so the unrestricted ceiling is 0.0 while the limit-bearing one is finite.

        Pinned by hand, twice, and the pair is the point. **Shannon** is the ceiling this
        used to be: log10(D) = k - log10(Q) with D = Q/A gives Q = sqrt(10^k * A); at
        k = 1.5 and A = pi * 0.127 cm * 0.15 cm that is 1.375696 uC, which over 90 us is
        15285.51 uA. **The water window's DC drift** is the ceiling it is after C2.3, and
        it is twenty times lower: the interface holds
        ``0.6 V * 250 uF/cm^2 * A = 8.9771 uC`` before it reaches PtIr's cathodic edge --
        250 uF/cm^2 being Rose & Robblee's 150 uC/cm^2 over that 0.6 V half-window -- and
        a monophasic train spends it at ``I * 90 us * 130 Hz``, so a 1 s train is survived
        only up to ``8.9771 / (90e-6 * 130) = 767.27`` uA.

        Both are written out here, so the assertion is that the package's candidate set
        takes the smaller of two independently computed numbers rather than that it agrees
        with one of them.
        """
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )
        area_cm2 = math.pi * 0.127 * 0.15
        charge_uC = math.sqrt(10.0**1.5 * area_cm2)
        shannon_uA = charge_uC / (90.0 * 1e-6)
        assert charge_uC == pytest.approx(1.375696, abs=5e-7)
        assert shannon_uA == pytest.approx(15285.51, abs=5e-3)

        window_charge_uC = 0.6 * 250.0 * area_cm2
        expected_uA = window_charge_uC / (90.0e-6 * 130.0 * 1.0)
        assert window_charge_uC == pytest.approx(8.9771, abs=5e-5)
        assert expected_uA == pytest.approx(767.2736, abs=5e-5)
        assert shannon_uA / expected_uA == pytest.approx(130.0 * 0.1532, rel=1e-3)

        assert fail_ceiling.fail_ceiling_uA(calc) == 0.0
        ceiling = fail_ceiling.fail_ceiling_uA(calc, names=fail_ceiling.LIMIT_BEARING)
        # The boundary float sits a couple of ulps above the closed form -- D2's flooring
        # budget, not a disagreement about the physics.
        assert 0.0 <= (ceiling - expected_uA) / math.ulp(expected_uA) <= 4.0
        assert fail_ceiling.brackets_the_ceiling(
            calc, ceiling, names=fail_ceiling.LIMIT_BEARING
        )
        assert fail_ceiling.failing_checks(calc, math.nextafter(ceiling, math.inf)) == {
            "Water window",
            "Charge balance",
        }

    def test_restricting_the_predicate_changes_nothing_when_nothing_is_excluded(
        self, worked_example
    ) -> None:
        """On the biphasic worked example neither excluded check FAILs, so both agree."""
        assert fail_ceiling.fail_ceiling_uA(worked_example) == 20.0
        assert (
            fail_ceiling.fail_ceiling_uA(worked_example, names=fail_ceiling.LIMIT_BEARING)
            == 20.0
        )

    def test_a_name_the_assessment_does_not_emit_is_refused(self, worked_example) -> None:
        """A misspelled name would silently weaken the predicate to "never fails"."""
        with pytest.raises(ValueError, match="no such check"):
            fail_ceiling.fail_ceiling_uA(worked_example, names={"Shannon criteria"})

    def test_the_oracle_defines_the_limit_bearing_set_itself(self) -> None:
        """Structural: it may not import the set from the code it is used to check.

        ``LIMIT_BEARING`` is defined by the package in C1.3. An oracle that imported it
        would restate the package's own partition of the checks and could never disagree
        with it.
        """
        import re

        text = Path(fail_ceiling.__file__ or "").read_text(encoding="utf-8")
        body = text.split('"""', 2)[-1]
        assert re.search(r"^LIMIT_BEARING\b[^=]*=", body, re.MULTILINE)
        for line in body.splitlines():
            if "neurostim" in line:
                assert line.strip() == "from neurostim import SafetyCalculator", line

    def test_the_oracle_and_the_package_agree_on_the_limit_bearing_set(self) -> None:
        """Once C1.3 lands, the two definitions must not drift apart.

        Skipped until it does -- there is nothing to compare against yet. After it lands,
        a check added to or dropped from the package's set without the oracle following
        fails here, rather than leaving the oracle quietly computing a different quantity.

        The skip is tied to an observable marker rather than to the absence it is testing
        for. C1.3 also gives ``Check`` a ``kind`` field; if that has appeared and
        ``LIMIT_BEARING`` has not been found, this test has been left pointing at the
        wrong module and the seven hand-written names have silently lost their only drift
        guard -- so it fails rather than skipping on.
        """
        import dataclasses
        import importlib

        from neurostim.safety.assessment import Check

        package_set = None
        for module_name in (
            "neurostim.safety",
            "neurostim.safety.assessment",
            "neurostim.safety.limits",
            "neurostim.safety._limits",
            "neurostim.safety.checks",
        ):
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            package_set = getattr(module, "LIMIT_BEARING", None)
            if package_set is not None:
                break

        if package_set is None:
            assert "kind" not in {field.name for field in dataclasses.fields(Check)}, (
                "Check has grown `kind`, so C1.3 has landed, but LIMIT_BEARING was not "
                "found in any module this test looks in -- point it at the right one "
                "instead of letting the oracle's seven names go unguarded"
            )
            pytest.skip("C1.3 has not landed: the package exposes no LIMIT_BEARING yet")
        assert set(package_set) == set(fail_ceiling.LIMIT_BEARING)

    def test_the_per_check_ceiling_is_pinned_to_hand_constants(self) -> None:
        """Oracle (a), restricted to one check. Five values, each derived by hand.

        ``DiscElectrode(100 um, "Pt")`` at 80 uA / 200 us, area
        ``pi * (50e-4)^2 = 7.853981633974483e-5 cm^2``, so one microamp of a 200 us pulse
        is ``200e-6 / A = 2.546 uC/cm^2``:

        * **Microelectrode charge/phase** -- Cogan 2016's 4 nC/phase over 200 us is
          ``4e-9 / 200e-6 = 2e-5 A = 20 uA``.
        * **Chronic degradation** -- Pt dissolves above 50 uC/cm^2, and
          ``50 * A / 200e-6 = 19.63 uA``.
        * **Charge injection limit** -- the conservative Pt CIC is 100 uC/cm^2, twice the
          dissolution threshold, so twice that current: 39.27 uA.
        * **Water window** -- cathodic-first from 0 V, Pt's cathodic limit is -0.6 V and
          the capacitance derived from its own optimistic 150 uC/cm^2 over that same
          0.6 V is 250 uF/cm^2, so 150 uC/cm^2 reaches the edge: 58.90 uA.
        * **Current density** -- Butterwick's electroporation threshold at 200 us on a
          100 um electrode; not hand-derivable in one line, so it is pinned as measured
          and cross-checked against the ratio to the charge-injection ceiling.

        Not tautological: four of the five are a published constant divided by a pulse
        width or multiplied by an area, written out above. None reads a package limit.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
            compliance_V=10.0,
        )
        area_cm2 = math.pi * (50e-4) ** 2
        per_uA_uC_cm2 = PULSE_WIDTH_US * 1e-6 / area_cm2

        assert fail_ceiling.check_fail_ceiling_uA(
            calc, "Microelectrode charge/phase"
        ) == 4.0e-9 / (PULSE_WIDTH_US * 1e-6) * 1e6
        assert fail_ceiling.check_fail_ceiling_uA(
            calc, "Chronic degradation"
        ) == pytest.approx(50.0 / per_uA_uC_cm2, rel=1e-12)
        assert fail_ceiling.check_fail_ceiling_uA(
            calc, "Charge injection limit"
        ) == pytest.approx(100.0 / per_uA_uC_cm2, rel=1e-12)
        assert fail_ceiling.check_fail_ceiling_uA(
            calc, "Water window"
        ) == pytest.approx(150.0 / per_uA_uC_cm2, rel=1e-12)

        assert fail_ceiling.check_fail_ceiling_uA(calc, "Chronic degradation") == (
            19.634954084936204
        )
        assert fail_ceiling.check_fail_ceiling_uA(calc, "Water window") == (
            58.90486225480862
        )
        assert fail_ceiling.check_fail_ceiling_uA(calc, "Current density") == (
            86.42793360039114
        )

    def test_the_per_check_wrapper_is_the_whole_assessment_form_restricted(self) -> None:
        """One invariant in one place: the wrapper must not acquire its own answer.

        Not tautological: it asserts an identity between two call forms of the same
        module, which is exactly the property a re-implementation would break -- a second
        bisection would have its own probe ladder and its own non-monotone handling.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
            compliance_V=10.0,
        )
        for name in sorted(fail_ceiling.LIMIT_BEARING):
            assert fail_ceiling.check_fail_ceiling_uA(calc, name) == (
                fail_ceiling.fail_ceiling_uA(calc, names={name})
            )

    def test_a_per_check_ceiling_is_bracketed_or_is_not_a_ceiling(self) -> None:
        """``0.0`` and ``inf`` are answers, not boundaries, for the per-check form too.

        Not tautological: the two sentinel values are literals and the expected reply is
        ``False`` for both, while a real ceiling must reply ``True``.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
            compliance_V=10.0,
        )
        ceiling = fail_ceiling.check_fail_ceiling_uA(calc, "Chronic degradation")
        assert fail_ceiling.brackets_the_check_ceiling(
            calc, "Chronic degradation", ceiling
        )
        assert not fail_ceiling.brackets_the_check_ceiling(
            calc, "Chronic degradation", 0.0
        )
        assert not fail_ceiling.brackets_the_check_ceiling(
            calc, "Chronic degradation", math.inf
        )
        # A check that never FAILs answers inf, which is what margin = inf means.
        assert fail_ceiling.check_fail_ceiling_uA(calc, "Shannon criterion") == math.inf

    def test_an_unknown_check_name_is_an_error_not_an_empty_restriction(self) -> None:
        """Not tautological: the expected outcome is a raise, where the silent-failure
        alternative would answer ``inf`` -- "this check never fails"."""
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
            compliance_V=10.0,
        )
        with pytest.raises(ValueError, match="no such check"):
            fail_ceiling.check_fail_ceiling_uA(calc, "Chronic Degradation")

    def test_every_constructor_argument_is_carried(self) -> None:
        """The frozen set rebuild_at checks against is today's signature, exactly."""
        import inspect

        from neurostim import SafetyCalculator

        assert frozenset(
            {
                "electrode",
                "protocol",
                "k",
                "material",
                "policy",
                "medium",
                "tissue_conductivity_S_per_m",
                "lead_resistance_ohm",
                "compliance_V",
                "measured_impedance_ohm",
                "resting_potential_V",
                "capacitance_uF_cm2",
                "counter_electrode",
                "counter_separation_um",
            }
        ) == fail_ceiling.CARRIED_ARGUMENTS
        signature = inspect.signature(SafetyCalculator.__init__)
        assert set(signature.parameters) - {"self"} == set(fail_ceiling.CARRIED_ARGUMENTS)

    def test_a_new_optional_constructor_argument_is_caught(
        self, worked_example, monkeypatch
    ) -> None:
        """The protection rebuild_at documents, for the case that actually arises.

        A new REQUIRED parameter already shows up as a TypeError at the call. A new
        OPTIONAL one -- which is what Phase 1 adds -- was silently defaulted, and the
        oracle then answered about a different calculator from the one it was handed.
        """
        import inspect

        import neurostim

        real = neurostim.SafetyCalculator

        class Drifted(real):  # type: ignore[misc, valid-type]
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)

        signature = inspect.signature(real.__init__)
        Drifted.__init__.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=[
                *signature.parameters.values(),
                inspect.Parameter(
                    "counter_electrode_area_cm2",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=1.0,
                ),
            ]
        )
        monkeypatch.setattr(neurostim, "SafetyCalculator", Drifted)

        with pytest.raises(
            fail_ceiling.ConstructorDrift, match="counter_electrode_area_cm2"
        ):
            fail_ceiling.rebuild_at(worked_example, 1.0)

    def test_a_protocol_that_never_fails_reports_no_ceiling(self) -> None:
        """``inf`` is an honest answer; the bracket's upper end presented as one is not."""
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(1.0, 100.0, 10.0, 1.0)
        )
        ceiling = fail_ceiling.fail_ceiling_uA(calc, upper_uA=10.0)
        assert ceiling == math.inf


class TestDiscSurfacePotential:
    """Oracle (b): the exact half-space disc solution."""

    # A 500 um disc in grey matter at 100 uA. R = 1/(4*0.35*250e-6) = 2857.142857 ohm.
    RADIUS_M = 250e-6
    CURRENT_A = 100e-6
    SIGMA = 0.35

    def test_the_access_resistance_is_newmans(self) -> None:
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        assert resistance == pytest.approx(1.0 / (4.0 * 0.35 * 250e-6))
        assert resistance == pytest.approx(2857.142857142857)

    def test_the_rim_potential_is_exactly_current_times_resistance(self) -> None:
        """``arcsin(1) = pi/2`` cancels the ``2/pi``, so this is bit-exact, not approximate.

        This pins the arcsin normalisation of the resistance-taking primitive and nothing
        else: the identity holds for whatever R is handed in, correct or not, which is
        why it is not the pin. The pin is
        ``test_at_a_hundred_radii_only_the_half_space_factor_agrees``.
        """
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        rim = disc_field.disc_surface_potential_V(
            self.CURRENT_A, resistance, self.RADIUS_M, self.RADIUS_M
        )
        assert rim == self.CURRENT_A * resistance
        assert rim * 1e3 == pytest.approx(285.714286, abs=5e-7)

    def test_the_self_contained_form_computes_its_own_resistance(self) -> None:
        """``disc_potential_V`` takes the conductivity, so R can never be an input.

        The same closed form, with ``R = 1/(4 sigma a)`` evaluated inside instead of
        handed in. At the rim ``arcsin(1) = pi/2`` cancels the ``2/pi``, so this is the
        285.714286 mV hand constant reached without the caller supplying a resistance.
        """
        rim = disc_field.disc_potential_V(
            self.CURRENT_A, self.SIGMA, self.RADIUS_M, self.RADIUS_M
        )
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        assert rim == self.CURRENT_A * resistance
        assert rim * 1e3 == pytest.approx(285.714286, abs=5e-7)

        distance = 100.0 * self.RADIUS_M
        assert disc_field.disc_potential_V(
            self.CURRENT_A, self.SIGMA, self.RADIUS_M, distance
        ) == disc_field.disc_surface_potential_V(
            self.CURRENT_A, resistance, self.RADIUS_M, distance
        )

    def test_a_wrong_resistance_makes_todays_field_model_look_correct(self) -> None:
        """Why the pin may not take R as an input: a shared error cancels exactly.

        Feed the resistance-taking form an R that is wrong by a factor of two and a
        full-space field model scores 0.999983 against it -- the very number that is
        supposed to mean "the field model has been repaired". A C3.1 test written as
        ``disc_surface_potential_V(I, electrode.access_resistance_ohm, ...)`` would
        therefore be satisfied by a package that halved its access resistance and left
        the field alone. The self-contained form has no parameter to feed.

        The wrong field is written out here as the full-space point source rather than
        read from the package, so this keeps demonstrating the hazard after C3.1 repairs
        the package and the hazard becomes the thing being guarded against.
        """
        import inspect

        distance = 100.0 * self.RADIUS_M
        today_V = disc_field.point_source_potential_V(
            self.CURRENT_A,
            self.SIGMA,
            distance,
            geometry_factor=disc_field.FULL_SPACE_FACTOR,
        )
        half_resistance = 0.5 * disc_field.newman_disc_resistance_ohm(
            self.SIGMA, self.RADIUS_M
        )
        cancelled = disc_field.disc_surface_potential_V(
            self.CURRENT_A, half_resistance, self.RADIUS_M, distance
        )
        assert today_V / cancelled == pytest.approx(0.999983, abs=5e-7)

        parameters = inspect.signature(disc_field.disc_potential_V).parameters
        assert "access_resistance_ohm" not in parameters
        assert "conductivity_S_per_m" in parameters

    def test_the_packages_disc_access_resistance_is_newmans(self) -> None:
        """The other half of the pin, so the two errors cannot cancel.

        The field ratio is pinned through the self-contained oracle and R is pinned
        here directly against Newman 1966. A change that moves one without the other
        now breaks one of the two.
        """
        from neurostim import DiscElectrode

        electrode = DiscElectrode(2.0 * self.RADIUS_M * 1e6, "Pt")
        assert electrode.access_resistance_ohm(self.SIGMA) == pytest.approx(
            disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M), rel=1e-15
        )
        assert electrode.access_resistance_ohm(self.SIGMA) == pytest.approx(
            2857.142857142857
        )

    def test_at_a_hundred_radii_only_the_half_space_factor_agrees(self) -> None:
        """The measurement that tells the two space conventions apart.

        Far from the disc the exact solution tends to the point source, so the ratio is
        the geometry factor and nothing else. 0.5 is a factor of two; 0.999983 is the
        genuine near-field residual of a disc at a hundred radii.

        Through the self-contained form: this is the pin, and a resistance it was handed
        would make it blind to an error in that resistance.
        """
        distance = 100.0 * self.RADIUS_M
        exact = disc_field.disc_potential_V(
            self.CURRENT_A, self.SIGMA, self.RADIUS_M, distance
        )

        full_space = disc_field.point_source_potential_V(
            self.CURRENT_A, self.SIGMA, distance, geometry_factor=disc_field.FULL_SPACE_FACTOR
        )
        half_space = disc_field.point_source_potential_V(
            self.CURRENT_A, self.SIGMA, distance, geometry_factor=disc_field.HALF_SPACE_FACTOR
        )

        assert full_space / exact == pytest.approx(0.499992, abs=5e-7)
        assert half_space / exact == pytest.approx(0.999983, abs=5e-7)

    def test_the_package_field_model_is_now_the_half_space_one(self) -> None:
        """The defect this oracle was written to pin read 0.5000 until C3.1 (ledger 17).

        Now 0.999983, the far-field agreement the half-space point source has with the
        exact disc at 100a -- the same number the oracle's own half-space factor gives
        above.
        """
        from neurostim import DiscElectrode
        from neurostim.models import field

        electrode = DiscElectrode(2.0 * self.RADIUS_M * 1e6, "Pt")
        distance_um = 100.0 * self.RADIUS_M * 1e6
        exact = disc_field.disc_potential_V(
            self.CURRENT_A, self.SIGMA, self.RADIUS_M, 100.0 * self.RADIUS_M
        )

        today_V = field.potential_V(
            self.CURRENT_A * 1e6, distance_um, self.SIGMA, electrode=electrode
        )
        assert today_V / exact == pytest.approx(0.999983, abs=5e-7)

    def test_inside_the_disc_is_a_domain_error(self) -> None:
        with pytest.raises(ValueError, match="must be >= radius_m"):
            disc_field.disc_surface_potential_V(1e-4, 1000.0, 250e-6, 100e-6)

    def test_a_non_physical_geometry_is_a_domain_error(self) -> None:
        """A negative radius returned a negative resistance, silently."""
        with pytest.raises(ValueError, match="radius_m must be > 0"):
            disc_field.newman_disc_resistance_ohm(0.35, -250e-6)
        with pytest.raises(ValueError, match="conductivity_S_per_m must be > 0"):
            disc_field.newman_disc_resistance_ohm(0.0, 250e-6)
        with pytest.raises(ValueError, match="radius_m must be > 0"):
            disc_field.disc_potential_V(1e-4, 0.35, -250e-6, 1e-3)


class TestDriftTime:
    """Oracle (c): pulse-by-pulse DC accumulation."""

    # The audit's case: CylindricalBandElectrode(1270, 1500, 'PtIr') driven monophasically
    # at 3000 uA, 90 us, 130 Hz. Area = pi * d * h = pi * 0.127 cm * 0.15 cm.
    CURRENT_UA = 3000.0
    PULSE_WIDTH_US = 90.0
    FREQUENCY_HZ = 130.0
    AREA_CM2 = math.pi * 0.127 * 0.15
    CAPACITANCE_UF_CM2 = 250.0
    WINDOW_V = 0.6

    def _kwargs(self) -> dict[str, float]:
        return {
            "current_uA": self.CURRENT_UA,
            "pulse_width_us": self.PULSE_WIDTH_US,
            "frequency_hz": self.FREQUENCY_HZ,
            "area_cm2": self.AREA_CM2,
            "capacitance_uF_cm2": self.CAPACITANCE_UF_CM2,
            "window_V": self.WINDOW_V,
        }

    def test_the_net_dc_current_is_the_duty_cycle_times_the_amplitude(self) -> None:
        # 90 us at 130 Hz is a duty of 0.0117; 3000 uA * 0.0117 = 35.1 uA.
        duty = 90e-6 * 130.0
        assert duty == pytest.approx(0.0117)
        assert drift.net_dc_current_uA(3000.0, 90.0, 130.0) == pytest.approx(35.1)

    def test_the_geometry_matches_the_audits_area(self) -> None:
        assert abs(self.AREA_CM2 - 0.05985) < 5e-6

    def test_the_closed_form_is_a_quarter_of_a_second(self) -> None:
        """35.1 uA over 0.05985 cm^2 is 586.5 uA/cm^2; at 250 uF/cm^2 that is 2.346 V/s."""
        dc_density = 35.1 / self.AREA_CM2
        assert dc_density == pytest.approx(586.5, abs=0.1)
        volts_per_second = (dc_density * 1e-6) / (self.CAPACITANCE_UF_CM2 * 1e-6)
        assert volts_per_second == pytest.approx(2.346, abs=5e-4)
        assert self.WINDOW_V / volts_per_second == pytest.approx(0.2558, abs=5e-5)

        assert drift.drift_time_s_closed_form(**self._kwargs()) == pytest.approx(0.2558, abs=5e-5)

    def test_the_pulse_loop_agrees_with_the_closed_form_to_within_one_pulse(self) -> None:
        """The strongest statement available: a pulse train cannot resolve time finer."""
        stepped = drift.drift_time_s(**self._kwargs())
        continuous = drift.drift_time_s_closed_form(**self._kwargs())
        one_pulse = 1.0 / self.FREQUENCY_HZ

        assert stepped == pytest.approx(34.0 / 130.0)  # the 34th pulse crosses 0.6 V
        assert 0.0 < stepped - continuous < one_pulse

    def test_the_loop_never_evaluates_the_closed_form(self) -> None:
        text = Path(drift.__file__ or "").read_text(encoding="utf-8")
        body = text.split("def drift_time_s(", 1)[1].split("def drift_time_s_closed_form", 1)[0]
        assert "closed_form" not in body

    def test_an_unreachable_window_reports_infinity(self) -> None:
        assert drift.drift_time_s(**{**self._kwargs(), "max_pulses": 3}) == math.inf

    def test_the_package_now_fails_here_within_one_pulse_of_the_oracle(self) -> None:
        """The defect this oracle was written to record, and its repair (C2.3).

        Until C2.3 the check reported PASS with 0.58 V of headroom while this loop said
        the interface leaves the window in a quarter of a second. The assertion is now
        that the package agrees with the loop to within one pulse -- the finest a pulse
        train resolves -- which is a stronger statement than the FAIL alone.
        """
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )
        assessment = calc.assess()
        water_window = next(c for c in assessment.checks if c.name == "Water window")
        assert water_window.status.value == "FAIL"

        stepped = drift.drift_time_s(**self._kwargs())
        assert stepped < 1.0
        reported = assessment.water_window.drift
        assert reported is not None
        assert abs(reported.time_to_exit_s - stepped) < 1.0 / self.FREQUENCY_HZ


class TestPartialRecoveryExitTime:
    """Oracle (c'): the pulse-by-pulse loop that follows the return phase too (ledger 105)."""

    def test_it_reduces_to_the_monophasic_loop_when_nothing_is_recovered(self) -> None:
        """With no return phase the two loops step the same charges, so they agree exactly
        on the audit's band case: the 34th pulse, 34/130 s."""
        kwargs = TestDriftTime()._kwargs()
        window = kwargs.pop("window_V")
        assert drift.partial_recovery_exit_time_s(
            **kwargs, recovered_fraction=0.0, leading_window_V=window,
            opposite_window_V=0.8,
        ) == pytest.approx(34.0 / 130.0)

    def test_the_reviewers_partial_recovery_case_by_hand(self) -> None:
        """A 500 um disc (0.0019635 cm^2) at 250 uF/cm^2 is 4.9087e-7 F. 1227.1846 uA for
        200 us is 2.4544e-7 C, so e = 0.5 V, and 99 % recovery leaves 0.005 V per pulse.
        Pulse n peaks at (n - 1) * 0.005 + 0.5, which first exceeds 0.6 V at n = 22:
        22/50 = 0.44 s."""
        area = math.pi * 0.025**2
        assert drift.partial_recovery_exit_time_s(
            current_uA=1227.184630308513,
            pulse_width_us=200.0,
            recovered_fraction=0.99,
            frequency_hz=50.0,
            area_cm2=area,
            capacitance_uF_cm2=250.0,
            leading_window_V=0.6,
            opposite_window_V=0.8,
        ) == pytest.approx(0.44)

    def test_over_recovery_leaves_by_the_opposite_edge(self) -> None:
        """e = 0.5 V recovered at 120 % moves the potential 0.1 V the other way per pulse;
        the opposite edge at 0.8 V is passed after the return phase of pulse 9
        (-0.9 V): 9/50 s. The leading edge is never reached, because the leading phase
        starts ever further from it."""
        area = math.pi * 0.025**2
        assert drift.partial_recovery_exit_time_s(
            current_uA=1227.184630308513,
            pulse_width_us=200.0,
            recovered_fraction=1.2,
            frequency_hz=50.0,
            area_cm2=area,
            capacitance_uF_cm2=250.0,
            leading_window_V=0.6,
            opposite_window_V=0.8,
        ) == pytest.approx(9.0 / 50.0)

    def test_the_loop_never_evaluates_a_closed_form(self) -> None:
        text = Path(drift.__file__ or "").read_text(encoding="utf-8")
        body = text.split("def partial_recovery_exit_time_s(", 1)[1]
        assert "closed_form" not in body

class TestPlanarBounds:
    """Oracle (e): exact elliptic disc and the thin-ring asymptote (ledger 10)."""

    def test_k_of_zero_recovers_newman(self) -> None:
        """K(0) = pi/2, so R = (pi/2)/(2 pi sigma a) = 1/(4 sigma a)."""
        from oracles import planar_bounds

        assert planar_bounds.complete_elliptic_k(0.0) == pytest.approx(math.pi / 2, rel=1e-15)
        assert planar_bounds.elliptic_disc_resistance_ohm(0.35, 100e-6, 100e-6) == pytest.approx(
            1.0 / (4.0 * 0.35 * 100e-6), rel=1e-14
        )

    def test_the_geometry_audits_elliptic_table(self) -> None:
        """audit_geometry.md: an ellipse of the area of a 100 um disc at sigma 0.35, by
        aspect -- 6934.1, 6133.6, 5314.2 and 3407.5 ohm at 2, 5, 10 and 50."""
        from oracles import planar_bounds

        for aspect, expected in ((2, 6934.1), (5, 6133.6), (10, 5314.2), (50, 3407.5)):
            a = 100e-6 * math.sqrt(aspect)
            b = 100e-6 / math.sqrt(aspect)
            assert planar_bounds.elliptic_disc_resistance_ohm(0.35, a, b) == pytest.approx(
                expected, abs=0.05
            )

    def test_the_geometry_audits_thin_ring(self) -> None:
        """audit_geometry.md: 200 um diameter, 1 um strip: about 11 682 ohm."""
        from oracles import planar_bounds

        assert planar_bounds.thin_ring_resistance_ohm(0.35, 200e-6, 1e-6) == pytest.approx(
            11682.2, abs=0.1
        )

    def test_the_oracle_imports_nothing_from_the_package(self) -> None:
        from oracles import planar_bounds

        text = Path(planar_bounds.__file__ or "").read_text(encoding="utf-8")
        assert "neurostim" not in text.split('"""', 2)[2]

class TestFdBandReference:
    """Oracle (d): the converged Laplace solve for a band on an insulating shaft.

    Regenerated at ledger 127. The first table was under-resolved at the band edge and read
    335.1 ohm at the clinical aspect; these pins now carry the converged values.
    """

    def test_the_clinical_contact_is_three_hundred_and_twenty_eight_ohms(self) -> None:
        assert fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT] == 327.6

    def test_the_equal_area_sphere_is_just_above_it_at_the_clinical_aspect(self) -> None:
        """329.5 ohm, computed here from the geometry: +0.6 %, high, not -1.7 %."""
        diameter_cm = fd_band.SHAFT_DIAMETER_UM * 1e-4
        height_cm = fd_band.CLINICAL_DBS_ASPECT * diameter_cm
        area_cm2 = math.pi * diameter_cm * height_cm
        radius_m = math.sqrt((area_cm2 * 1e-4) / (4.0 * math.pi))
        sphere_ohm = 1.0 / (4.0 * math.pi * fd_band.CONDUCTIVITY_S_PER_M * radius_m)

        assert sphere_ohm == pytest.approx(329.5, abs=0.05)
        reference = fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT]
        assert (sphere_ohm - reference) / reference == pytest.approx(0.006, abs=5e-4)

    def test_the_equal_area_disc_used_before_c3_1_is_high_by_more_than_half(self) -> None:
        diameter_cm = fd_band.SHAFT_DIAMETER_UM * 1e-4
        height_cm = fd_band.CLINICAL_DBS_ASPECT * diameter_cm
        area_cm2 = math.pi * diameter_cm * height_cm
        radius_m = math.sqrt((area_cm2 * 1e-4) / math.pi)
        disc_ohm = 1.0 / (4.0 * fd_band.CONDUCTIVITY_S_PER_M * radius_m)

        assert disc_ohm == pytest.approx(517.5, abs=0.05)
        reference = fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT]
        assert disc_ohm / reference == pytest.approx(1.580, abs=5e-3)

    def test_resistance_falls_monotonically_with_band_height(self) -> None:
        values = [fd_band.FD_BAND_REFERENCE[a] for a in sorted(fd_band.FD_BAND_REFERENCE)]
        assert values == sorted(values, reverse=True)

    def test_the_rejected_log_form_is_negative_at_small_aspect(self) -> None:
        """``ln(2L/r)/(2 pi sigma L)`` below aspect 0.25, written out here."""
        shaft_radius_m = fd_band.SHAFT_DIAMETER_UM * 1e-6 / 2.0
        height_m = 0.2 * fd_band.SHAFT_DIAMETER_UM * 1e-6
        log_form = math.log(2.0 * height_m / shaft_radius_m) / (
            2.0 * math.pi * fd_band.CONDUCTIVITY_S_PER_M * height_m
        )
        assert log_form < 0.0
        assert log_form == pytest.approx(-399.5, abs=0.5)
        assert fd_band.FD_BAND_REFERENCE[0.200] == 653.4

    def test_the_table_agrees_with_an_independent_solve(self) -> None:
        """The Phase 3 reviewer's separately written axisymmetric FV solver (review_p3.md,
        H1), validated to 0.05 % on Newman's disc: 653.7, 520.6, 473.9, 353.9, 327.8,
        252.5, 171.9 and 96.7 ohm. Agreement within 0.3 % at every aspect."""
        independent = {
            0.200: 653.7, 0.390: 520.6, 0.500: 473.9, 1.000: 353.9,
            1.181: 327.8, 2.000: 252.5, 4.000: 171.9, 10.000: 96.7,
        }
        for aspect, value in independent.items():
            assert fd_band.FD_BAND_REFERENCE[aspect] == pytest.approx(value, rel=3e-3), aspect

    @staticmethod
    def _generator():
        import importlib.util
        import sys
        from pathlib import Path

        generator_path = Path(__file__).resolve().parents[1] / "scripts" / "fd_band_reference.py"
        spec = importlib.util.spec_from_file_location("fd_band_reference", generator_path)
        assert spec is not None and spec.loader is not None
        generator = importlib.util.module_from_spec(spec)
        sys.modules["fd_band_reference"] = generator
        spec.loader.exec_module(generator)
        return generator

    def test_the_generator_reproduces_newmans_disc(self) -> None:
        """The same solver on a flush disc, whose resistance is exact: within 0.05 % after
        extrapolation. This is what licenses trusting it on the band."""
        generator = self._generator()
        result = generator.converge(
            lambda **kw: generator.disc_resistance_ohm(250e-6, **kw)
        )
        exact = 1.0 / (4.0 * generator.SIGMA_S_PER_M * 250e-6)
        assert result.richardson_ohm == pytest.approx(exact, rel=5e-4)

    def test_the_generator_reproduces_the_table(self) -> None:
        """A frozen table nothing can re-derive is a magic number. The full convergence at
        the clinical aspect: within 0.05 % of the table, with an observed order between
        1 and 2, as expected at a re-entrant edge."""
        generator = self._generator()
        height = fd_band.CLINICAL_DBS_ASPECT * generator.SHAFT_DIAMETER_M
        result = generator.converge(
            lambda **kw: generator.band_resistance_ohm(
                generator.SHAFT_DIAMETER_M / 2.0, height, **kw
            )
        )
        assert result.richardson_ohm == pytest.approx(
            fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT], rel=5e-4
        )
        assert 1.0 < result.order < 2.0
        assert result.uncertainty_ohm <= fd_band.CONVERGENCE_SPREAD_OHM
