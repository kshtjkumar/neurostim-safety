"""C5.1 -- the figure is a render surface, and it must render what the report states.

Pulled forward from Phase 5 because leaving it parked ships a self-contradicting artifact
set: ``safety_summary`` and ``build_report`` are the two outputs a user puts in the same
manuscript, and after Phase 1 they disagree about the binding amplitude by 7.07x, with the
figure the permissive one.

Three separate defects meet in one panel, and each has its own test here:

* **the candidate set** (ledger 48, fix plan B2). ``viz.current_limit_sweep`` computed its
  own ``min(shannon, cic, compliance)`` -- the three-check minimum C1.6 replaced -- so the
  artist annotated ``binding limit 141.3 uA`` beside a headline of ``20.00``.
* **the settings** (ledger 48 proper). ``safety_summary`` forwarded neither ``k``, nor
  ``policy``, nor ``tissue_conductivity_S_per_m``, so every curve was recomputed at library
  defaults while the suptitle carried the user's verdict.
* **the refusal** (ledger 84, C1.5). A protocol unsafe at *any* amplitude still got a bare
  number on the figure, because ``viz`` computed its own minimum and C1.5 could not reach
  it.

Where the expected values come from
-----------------------------------
Never from ``viz``. Two independent sources, and where they overlap they are asserted to
agree:

* ``tests/oracles/fail_ceiling`` -- a binary search over ``assess().failed`` that reads one
  bit per probe and no package-computed number;
* hand arithmetic quoted in each test: 4 nC/phase / 200 us = 20 uA (Cogan et al. 2016),
  and ``sqrt(A * 10**k) / W`` for the Shannon ceiling.

Fixtures are deliberately off-default. ``k = 1.2`` and
``tissue_conductivity_S_per_m = 0.10`` are neither the library defaults (1.5 and 0.35) nor
anything the code falls back to, because a fixture at the default is exactly what the
forwarding defect would survive: at ``k = 1.5`` the un-forwarded panel draws the right
number for the wrong reason.
"""

from __future__ import annotations

import math

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from neurostim import (
    DiscElectrode,
    RingElectrode,
    SafetyCalculator,
    StimProtocol,
)
from neurostim.geometry import CylindricalBandElectrode
from neurostim.safety.assessment import LIMIT_BEARING, Status
from neurostim.viz.plots import current_limit_sweep, safety_summary
from neurostim.viz.style import PALETTE

BINDING_PREFIX = "binding limit"
"""How the sweep panel opens its annotation of the amplitude that binds."""


def texts(ax) -> list[str]:
    """Every annotation on ``ax``, whitespace collapsed so wrapping is not asserted."""
    return [" ".join(artist.get_text().split()) for artist in ax.texts]


def binding_annotation(ax) -> str:
    """The one annotation that names the binding amplitude, or the refusal in its place."""
    found = [text for text in texts(ax) if text.startswith(BINDING_PREFIX)]
    assert len(found) <= 1, f"more than one binding annotation: {found}"
    return found[0] if found else ""


def binding_rules(ax) -> list[float]:
    """The levels of every fail-coloured horizontal rule -- the "programme below me" line.

    Distinguished from the per-check ceiling curves by colour, because they are different
    claims: a ceiling curve says *this check permits up to here* and carries the check's
    own name; the rule says *this is the amplitude*, which is the one thing a protocol
    unsafe at every amplitude must not be given.
    """
    return [
        float(line.get_ydata()[0])
        for line in ax.lines
        if _is_flat(line) and line.get_color() == PALETTE["fail"]
    ]


def drawn_levels(ax) -> dict[str, float]:
    """Label -> the constant level of each horizontal line drawn on ``ax``.

    A limit-bearing check's ceiling does not move with the requested amplitude -- that is
    what makes it a ceiling -- so each candidate is a flat line across the sweep. Verified
    over 25 amplitudes spanning 1e-2 to 1e4 uA on four configurations: every one of the
    seven ceilings is constant to the last bit.
    """
    levels: dict[str, float] = {}
    for line in ax.get_lines():
        y = line.get_ydata()
        if len(y) and len(set(map(float, y))) == 1:
            levels[str(line.get_label())] = float(y[0])
    return levels


def sweep(calc: SafetyCalculator):
    """Render ``current_limit_sweep`` for ``calc``'s own settings and return the axes.

    The settings are named here rather than left to default, so this helper cannot
    reintroduce the defect the tests below are about.
    """
    figure, ax = plt.subplots()
    try:
        current_limit_sweep(
            calc.e,
            calc.p,
            ax=ax,
            k=calc.k,
            policy=calc.policy,
            tissue_conductivity_S_per_m=calc.tissue_conductivity_S_per_m,
            compliance_V=calc.compliance_V,
        )
        return ax, (texts(ax), drawn_levels(ax))
    finally:
        plt.close(figure)


def worked_example() -> SafetyCalculator:
    """The plan's worked example: 330/270 um Pt ring, 80 uA, 200 us, 130 Hz, 10 V."""
    return SafetyCalculator(
        RingElectrode(330.0, 270.0, "Pt"),
        StimProtocol(80, 200, 130, 1),
        compliance_V=10.0,
    )


def off_default_band() -> SafetyCalculator:
    """A clinical DBS band at ``k = 1.2`` and ``sigma = 0.10`` -- both off-default."""
    return SafetyCalculator(
        CylindricalBandElectrode(1270.0, 1500.0, material="Pt"),
        StimProtocol(3000.0, 200.0, 130.0, 1.0),
        k=1.2,
        tissue_conductivity_S_per_m=0.10,
        compliance_V=10.0,
    )


def monophasic_band() -> SafetyCalculator:
    """Ledger 84's case: monophasic, so Charge balance FAILs at every amplitude."""
    return SafetyCalculator(
        CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
        StimProtocol(3000, 90, 130, 1, waveform="monophasic"),
        compliance_V=10.0,
    )


class TestTheFigureAnnotatesTheAssessmentsLimit:
    """The number on the figure is the number in the report, or there is no number.

    ``viz/plots.py`` rebuilt ``binding`` as ``min(shannon, cic, compliance)`` from the
    0.1.0-compat properties, which is the three-check candidate set C1.6 replaced with the
    minimum over all seven of ``LIMIT_BEARING``. The figure is the one surface the C1
    commits could not reach.
    """

    def test_the_annotation_is_the_assessments_limiting_current(self):
        """Worked example: the report says 20.00 uA, so the figure must not say 141.3.

        Not tautological: 20.0 uA is Cogan et al. (2016)'s 4 nC/phase microelectrode
        damage threshold divided by the 200 us pulse -- arithmetic done here -- and the
        binary-search oracle returns the same number without reading any package limit.
        """
        calc = worked_example()
        ceiling_uA = 4.0e-3 / 200e-6 * 1e3 / 1e3  # 4 nC / 200 us, in uA
        assert ceiling_uA == pytest.approx(20.0)

        from oracles.fail_ceiling import LIMIT_BEARING as ORACLE_LIMIT_BEARING
        from oracles.fail_ceiling import fail_ceiling_uA

        oracle_uA = fail_ceiling_uA(calc, names=ORACLE_LIMIT_BEARING)
        assert oracle_uA == pytest.approx(20.0, rel=1e-9)
        assert calc.assess().limiting_current_uA == pytest.approx(oracle_uA, rel=1e-12)

        _ax, (_annotations, _levels) = sweep(calc)
        annotation = binding_annotation(_ax)
        assert annotation == "binding limit 20.00 µA (Microelectrode charge/phase)"

    def test_the_annotation_names_the_mechanism_the_report_names(self):
        """The mechanism beside the number is the assessment's, not a re-derived one.

        Not tautological: the expected name is the check the independent oracle's own
        ceiling belongs to -- ``Microelectrode charge/phase`` is the only limit-bearing
        check whose ceiling equals the oracle's 20.0 -- and the name is read off the
        checks, not off ``limiting_mechanism``.
        """
        calc = worked_example()
        assessment = calc.assess()
        from oracles.fail_ceiling import LIMIT_BEARING as ORACLE_LIMIT_BEARING
        from oracles.fail_ceiling import fail_ceiling_uA

        oracle_uA = fail_ceiling_uA(calc, names=ORACLE_LIMIT_BEARING)
        at_the_ceiling = [
            check.name
            for check in assessment.checks
            if check.name in LIMIT_BEARING
            and check.ceiling_uA == pytest.approx(oracle_uA, rel=1e-12)
        ]
        assert at_the_ceiling == ["Microelectrode charge/phase"]

        _ax, _ = sweep(calc)
        assert "Microelectrode charge/phase" in binding_annotation(_ax)

    def test_the_binding_rule_is_drawn_at_the_assessments_limit(self):
        """The red rule, not just its label, sits at the reported amplitude.

        Not tautological: the expected level is the oracle's binary-searched ceiling, and
        the superseded three-check minimum (141.37 uA) is asserted absent from the rule.
        """
        calc = worked_example()
        from oracles.fail_ceiling import LIMIT_BEARING as ORACLE_LIMIT_BEARING
        from oracles.fail_ceiling import fail_ceiling_uA

        oracle_uA = fail_ceiling_uA(calc, names=ORACLE_LIMIT_BEARING)
        _ax, _ = sweep(calc)

        assert binding_rules(_ax) == [pytest.approx(oracle_uA, rel=1e-12)]
        assert not any(
            value == pytest.approx(141.37166941154072, rel=1e-9)
            for value in binding_rules(_ax)
        )

    def test_the_annotation_still_floors(self):
        """Ledger 49 at the figure site, on a case where flooring changes the digits.

        Not tautological: 39.26990816987241 uA is 12.5*pi floored onto its own check, its
        round-to-nearest 4-significant-digit form is ``39.27`` and its floored form
        ``39.26``; the expected string is the hand-floored one and the rounded one is
        asserted absent.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80, 100, 130, 1), compliance_V=10.0
        )
        assert calc.assess().limiting_current_uA == pytest.approx(12.5 * math.pi, rel=1e-12)

        _ax, _ = sweep(calc)
        annotation = binding_annotation(_ax)
        assert "39.26" in annotation
        assert "39.27" not in annotation


class TestEveryPanelUsesTheCalculatorsSettings:
    """Ledger 48. ``safety_summary`` drew panel (b) at library defaults.

    Separated from the candidate-set tests above on purpose: this class asserts on the
    *per-check* curves, which are wrong under the settings defect alone and right under it
    alone, so a green here is evidence about forwarding and nothing else.
    """

    def test_each_drawn_ceiling_is_the_checks_own_ceiling(self):
        """Every limit-bearing check with a finite ceiling is drawn at that ceiling.

        Not tautological: the Shannon level is pinned to ``sqrt(A * 10**1.2) / 200 us``
        computed here from the electrode's area, and the library-default ``k = 1.5`` value
        the panel draws today (6878.479 uA) is asserted absent.
        """
        calc = off_default_band()
        assessment = calc.assess()

        area_cm2 = calc.e.area_cm2
        hand_shannon_uA = math.sqrt(area_cm2 * 10**1.2) / 200.0 * 1e6
        assert hand_shannon_uA == pytest.approx(4869.590378911605, rel=1e-12)

        _ax, (_annotations, levels) = sweep(calc)
        for check in assessment.checks:
            if check.name not in LIMIT_BEARING or not math.isfinite(check.ceiling_uA):
                continue
            assert check.name in levels, (check.name, sorted(levels))
            assert levels[check.name] == pytest.approx(check.ceiling_uA, rel=1e-12)

        assert levels["Shannon criterion"] == pytest.approx(hand_shannon_uA, rel=1e-12)
        assert not any(
            value == pytest.approx(6878.479237146387, rel=1e-9)
            for value in levels.values()
        ), levels

    def test_summary_panel_b_carries_the_calculators_k_and_conductivity(self):
        """The ledger 48 headline, end to end through ``safety_summary``.

        Not tautological: the expected annotation is the hand-computed Shannon ceiling at
        the user's own ``k``, floored -- 4869 -- and the string the panel prints today
        under library defaults (6878) is asserted absent.
        """
        calc = off_default_band()
        figure, axes = safety_summary(calc)
        try:
            panel_b = axes[0][1]
            annotation = binding_annotation(panel_b)
            levels = drawn_levels(panel_b)
        finally:
            plt.close(figure)

        # G12 (C4.3, ledger 128): at k = 1.2, below Shannon's own 1.5, the binding Shannon
        # check is provisional, and the figure now says so as every headline surface does.
        assert annotation == "binding limit 4869 µA (Shannon criterion), provisional"
        assert "6878" not in annotation
        assert levels["Compliance voltage"] == pytest.approx(
            calc.assess().compliance.max_current_uA, rel=1e-12
        )

    def test_summary_panel_d_carries_the_calculators_conductivity(self):
        """Panel (d)'s field profile is drawn at sigma, not at the library's 0.35 S/m.

        Not tautological: the expected ratio is the point-source law ``V = I/(4 pi sigma
        r)``, so halving the conductivity doubles the potential everywhere; 0.35/0.10 =
        3.5 is arithmetic on the two settings, and the panel currently draws both at 0.35
        and so returns 1.0.
        """
        sigmas = (0.35, 0.10)
        profiles = []
        for sigma in sigmas:
            calc = SafetyCalculator(
                RingElectrode(330.0, 270.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                compliance_V=10.0,
                tissue_conductivity_S_per_m=sigma,
            )
            figure, axes = safety_summary(calc)
            try:
                profiles.append(axes[1][1].get_lines()[0].get_ydata())
            finally:
                plt.close(figure)

        ratio = profiles[1] / profiles[0]
        assert ratio == pytest.approx(sigmas[0] / sigmas[1], rel=1e-9)


class TestNoBareNumberWhenNoAmplitudeIsSafe:
    """Ledger 84 reaches the figure. C1.5 fixed four surfaces; this is the fifth.

    ``describe()``, ``report_to_json``, the PDF header and the GUI headline already refuse
    to print an amplitude for a protocol that is unsafe as a waveform. The figure did not,
    because it computed its own minimum and never consulted the assessment.
    """

    def test_the_figure_prints_no_amplitude_and_names_the_check(self):
        """Monophasic: no number anywhere near the binding annotation, and a named reason.

        Not tautological: the witness is the oracle's ``amplitude_independent_failures``,
        which establishes across 73 ladder probes that ``Charge balance`` FAILs at every
        one -- an absence asserted against a named check, not against a bare zero.
        """
        calc = monophasic_band()
        from oracles.fail_ceiling import amplitude_independent_failures

        assert amplitude_independent_failures(calc) == ("Charge balance",)

        _ax, (annotations, _levels) = sweep(calc)
        assert binding_annotation(_ax) == ""
        refusal = [text for text in annotations if "no amplitude is safe" in text]
        assert refusal == ["no amplitude is safe: Charge balance FAILs at every amplitude"]
        assert not any("1.528e+04" in text or "15285" in text for text in annotations)

    def test_no_binding_rule_is_drawn_when_no_amplitude_is_safe(self):
        """The refusal is in place of the amplitude, not beside it.

        Not tautological: the same scrape is asserted in both directions in one test --
        the worked example, which has a safe amplitude, must carry exactly one rule, and
        the monophasic protocol, which has none, must carry zero. A panel that simply
        stopped drawing rules would fail the first half.
        """
        assert len(binding_rules(sweep(worked_example())[0])) == 1

        calc = monophasic_band()
        assessment = calc.assess()
        assert assessment.unsafe_at_any_amplitude

        _ax, _ = sweep(calc)
        assert binding_rules(_ax) == []

    def test_the_drawn_candidate_set_is_the_assessments_candidate_set(self):
        """Every limit-bearing check that ran is drawn, and nothing else is.

        Not tautological: the expected set is built from the assessment's own checks --
        which today's panel does not consult at all, drawing three hand-named curves
        (``Shannon limit``, ``charge-injection limit``, ``compliance limit``) whatever the
        candidate set is. A NOT_EVALUATED ceiling is ``inf`` and must not reach a log
        axis, so it is excluded by the same rule rather than by a special case.
        """
        calc = monophasic_band()
        assessment = calc.assess()
        expected = {
            check.name
            for check in assessment.checks
            if check.name in LIMIT_BEARING and math.isfinite(check.ceiling_uA)
        }
        skipped = {
            check.name
            for check in assessment.checks
            if check.status is Status.NOT_EVALUATED
        }
        assert "Microelectrode charge/phase" in skipped and skipped.isdisjoint(expected)

        _ax, (_annotations, levels) = sweep(calc)
        assert expected <= set(levels), sorted(set(levels))
        assert all(math.isfinite(value) for value in levels.values()), levels


def _is_flat(line) -> bool:
    """Whether a drawn line is horizontal, so its single level can be compared."""
    y = line.get_ydata()
    return bool(len(y)) and len(set(map(float, y))) == 1


class TestTheSeparatrixThatDecidedTheVerdictIsDrawn:
    """Ledger 55 (io-gui H6), C5.2. The Shannon panel drew separatrices at the module
    constants 1.5/1.7/2.0 and never at ``calc.k``, while the operating point's colour came
    from ``calc.k``: at calc.k = 2.0 a point sat above the solid k = 1.5 line coloured
    green, at calc.k = 1.2 below it coloured red. The line that decided is not on the chart."""

    @staticmethod
    def _separatrix(ax, k):
        """The drawn lines of slope -1 at ``k``: Q * (Q/A) == 10**k along every point."""
        found = []
        for line in ax.get_lines():
            x, y = (list(map(float, v)) for v in (line.get_xdata(), line.get_ydata()))
            if len(x) > 2 and all(
                math.isclose(xi * yi, 10.0**k, rel_tol=1e-9) for xi, yi in zip(x, y, strict=True)
            ):
                found.append(line)
        return found

    @pytest.mark.parametrize("k", [1.2, 1.5, 1.75, 2.0])
    def test_the_assessments_k_is_drawn_and_named(self, k):
        from neurostim.viz.plots import shannon_safe_operating_area

        calc = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1), k=k)
        ax = shannon_safe_operating_area(calc)
        lines = self._separatrix(ax, k)
        assert len(lines) == 1, (k, [line.get_label() for line in lines])
        assert "this assessment" in str(lines[0].get_label())
        others = [
            line for line in ax.get_lines()
            if line is not lines[0] and "this assessment" in str(line.get_label())
        ]
        assert not others
        plt.close("all")

    def test_without_a_calculator_nothing_is_named(self):
        from neurostim.viz.plots import shannon_safe_operating_area

        ax = shannon_safe_operating_area()
        assert not [line for line in ax.get_lines() if "this assessment" in str(line.get_label())]
        assert len(self._separatrix(ax, 1.5)) == 1
        plt.close("all")


class TestPassAndFailDifferInMoreThanColour:
    """Ledger 56 (io-gui H7), C5.3. Pass and fail were carried by colour alone: the Shannon
    operating point was marker 'o', size 5, either way; material_comparison's bars had no
    hatch; McCreery's "no damage" and "some damage" were both 'o'. #1a7f37 and #b62324 have
    near-identical luminance, so greyscale and deuteranopic readers lose all three."""

    @staticmethod
    def _protocol_point(ax):
        [line] = [line for line in ax.get_lines() if line.get_label() == "protocol"]
        return line

    def test_the_operating_point_changes_shape(self):
        from neurostim.viz.plots import shannon_safe_operating_area

        passing = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1))
        failing = SafetyCalculator(DiscElectrode(1000, "Pt"), StimProtocol(8000, 500, 50, 1))
        assert passing.assess().shannon.passes and not failing.assess().shannon.passes
        a = self._protocol_point(shannon_safe_operating_area(passing))
        b = self._protocol_point(shannon_safe_operating_area(failing))
        assert a.get_marker() != b.get_marker()
        plt.close("all")

    def test_the_mccreery_groups_have_three_shapes(self):
        from neurostim.viz.plots import shannon_safe_operating_area

        ax = shannon_safe_operating_area()
        markers = {
            str(line.get_label()): line.get_marker()
            for line in ax.get_lines()
            if line.get_label() in ("no damage", "some damage", "damage")
        }
        assert len(markers) == 3 and len(set(markers.values())) == 3, markers
        plt.close("all")

    def test_material_bars_that_fail_are_hatched(self):
        from neurostim.viz.plots import material_comparison

        electrode, protocol = DiscElectrode(500, "Pt"), StimProtocol(300, 200, 130, 1)
        applied = protocol.charge_per_phase_uC / electrode.area_cm2
        ax = material_comparison(electrode, protocol)
        bars = ax.patches
        widths = [bar.get_width() for bar in bars]
        assert any(w >= applied for w in widths) and any(w < applied for w in widths)
        for bar in bars:
            hatched = bool(bar.get_hatch())
            assert hatched == (bar.get_width() < applied), (bar.get_width(), bar.get_hatch())
        plt.close("all")


class TestSavePublicationKeepsDecimalNames:
    """Ledger 58 (io-gui H9), C5.4. save_publication stripped whatever followed the last
    dot, so "shannon_k1.5" and "shannon_k1.8" both wrote shannon_k1.svg and the second
    destroyed the first."""

    def test_two_decimal_names_do_not_collide(self, tmp_path):
        from neurostim.viz.style import save_publication, subplots

        written = []
        for k in ("1.5", "1.8"):
            fig, _ = subplots()
            written += save_publication(fig, tmp_path / f"shannon_k{k}", formats=("svg",), close=True)
        assert [p.name for p in written] == ["shannon_k1.5.svg", "shannon_k1.8.svg"]
        assert all(p.exists() for p in written)

    def test_a_format_extension_is_still_replaced(self, tmp_path):
        from neurostim.viz.style import save_publication, subplots

        fig, _ = subplots()
        written = save_publication(fig, tmp_path / "fig.svg", formats=("svg", "pdf"), close=True)
        assert [p.name for p in written] == ["fig.svg", "fig.pdf"]
        fig, _ = subplots()
        written = save_publication(fig, tmp_path / "k1.5.TIFF", formats=("svg",), close=True)
        assert [p.name for p in written] == ["k1.5.svg"]
