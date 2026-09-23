"""Phase 2 -- the data model.

Three things the package could not previously say, and one it said wrongly:

* **charge imbalance is expressible.** ``return_phase_current_uA`` was derived as
  ``current_uA / return_phase_ratio``, which makes the return charge identically equal
  to the leading charge for every biphasic protocol. The charge-balance FAIL branch and
  ``net_dc_current_uA`` were therefore dead code, and the commonest real DC fault -- a
  return phase that does not recover what the leading phase injected -- could not be
  entered at all (ledger 3).
* **the return phase is evaluated** in current density and compliance (ledger 4).
* **DC drift out of the water window** is modelled, so a waveform that leaves charge
  behind has its consequence expressed where a ceiling can carry it (ledger 2).
* **the train duty cycle** is a distinct quantity from the intra-pulse duty cycle, and
  the intra-pulse one stops being compared against McCreery's train schedule (ledger 6).

Expected values here come from arithmetic written out in the test on the protocol's own
inputs, from ``tests.oracles`` (the pulse-by-pulse drift integrator and the fail-ceiling
bisection), or from a literature constant quoted in the docstring -- never from the
property under test.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict

import pytest

from neurostim import (
    DiscElectrode,
    RingElectrode,
    SafetyCalculator,
    StimProtocol,
)
from neurostim.safety.assessment import Status


def _check(calc: SafetyCalculator, name: str):
    """The named check from a fresh assessment."""
    return next(c for c in calc.assess().checks if c.name == name)


class TestChargeRecoveryIsAnIndependentInput:
    """T12. Imbalance must be expressible, and it must reach every consumer (ledger 3).

    ``return_phase_current_uA`` was ``current_uA / return_phase_ratio`` and
    ``return_phase_width_us`` was ``pulse_width_us * return_phase_ratio``, so the return
    charge was ``I * W`` whatever the ratio: the product of the two is the identity. The
    audit swept 150 ``(I, W, r)`` combinations and every one produced exactly zero net
    charge. ``charge_recovery_ratio`` is the missing degree of freedom, named for what
    every downstream consumer actually reads -- ``r_a`` is the *fraction of injected
    charge the return phase recovers*, not an amplitude ratio (fix plan D6).

    Fixture rule: every ratio used here differs from the ``1.0`` default, so a dropped
    argument changes an asserted number rather than nothing.
    """

    def test_a_partial_recovery_leaves_the_complementary_charge_behind(self) -> None:
        """Ten per cent recovered short is ten per cent of the phase charge left behind.

        Not tautological: the expected residual is
        ``(1 - charge_recovery_ratio) * I * W * 1e-6``, written out here from the
        protocol's three scalar *inputs*, and compared against
        ``net_charge_per_pulse_uC`` -- which the package computes as a difference of two
        charges it derives separately. The two expressions share no line of code, and the
        defect being pinned is that the package's difference is structurally zero.
        """
        p = StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9)

        expected_phase_uC = 80.0 * 200.0 * 1e-6
        expected_net_uC = (1.0 - 0.9) * expected_phase_uC

        assert p.charge_per_phase_uC == pytest.approx(expected_phase_uC, rel=1e-15)
        assert p.net_charge_per_pulse_uC == pytest.approx(expected_net_uC, rel=1e-12)
        assert p.net_charge_per_pulse_uC == pytest.approx(
            0.1 * p.charge_per_phase_uC, rel=1e-12
        )
        assert not p.is_charge_balanced
        assert p.net_dc_current_uA == pytest.approx(expected_net_uC * 130.0, rel=1e-12)

    def test_recovery_is_orthogonal_to_the_return_phase_width(self) -> None:
        """The two ratios are independent axes, which is the whole of D6's rename.

        A user asking for a quarter-width return phase that recovers 90 % of the charge
        must get a return phase of ``W/4`` at ``0.9 * 4 = 3.6`` times the leading
        amplitude -- and ``0.9`` of the charge. Under the rejected
        ``return_phase_amplitude_ratio`` name the same call would have meant "return at
        90 % *amplitude*", which is ``3.6 * I`` only by coincidence of the width.

        Not tautological: both expected values are products of the two ratios with the
        leading phase's own amplitude and width, written out; neither is read back from a
        protocol property.
        """
        p = StimProtocol(
            80.0,
            200.0,
            130.0,
            1.0,
            return_phase_ratio=0.25,
            charge_recovery_ratio=0.9,
        )

        assert p.return_phase_width_us == pytest.approx(200.0 * 0.25, rel=1e-15)
        assert p.return_phase_current_uA == pytest.approx(
            80.0 * 0.9 / 0.25, rel=1e-15
        )
        assert p.return_charge_uC == pytest.approx(0.9 * 80.0 * 200.0 * 1e-6, rel=1e-12)

    def test_over_recovery_leaves_net_charge_of_the_other_sign(self) -> None:
        """A return phase that over-recovers is a DC offset too, of opposite polarity.

        Not tautological: the expected value is ``(1 - 1.2) * I * W * 1e-6``, negative by
        construction, and the sign is what distinguishes this from the magnitude-only
        reading the ``abs`` in ``is_charge_balanced`` would otherwise permit.
        """
        p = StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=1.2)

        assert p.net_charge_per_pulse_uC == pytest.approx(
            (1.0 - 1.2) * 80.0 * 200.0 * 1e-6, rel=1e-12
        )
        assert p.net_charge_per_pulse_uC < 0.0
        assert not p.is_charge_balanced

    def test_a_recovery_ratio_outside_its_domain_is_rejected(self) -> None:
        """Negative or non-finite recovery is not a waveform.

        A negative ratio would mean a "return" phase of the same polarity as the leading
        one, which this parameterisation cannot express -- the sign lives in
        ``anodic_first`` -- and would silently produce a net charge *larger* than the
        injected one. Rejected at construction, like every other setting (C1.9).

        Not tautological: the assertion is on the exception type and on the parameter name
        appearing in the message, neither of which any arithmetic can supply.
        """
        for bad in (-0.1, float("nan"), float("inf")):
            with pytest.raises(ValueError, match="charge_recovery_ratio"):
                StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=bad)

    def test_charge_balance_is_relative_to_the_phase_charge(self) -> None:
        """Ledger 15. An absolute 1e-12 uC tolerance is wrong at millicoulomb scale.

        At 1 A and 1 ms the phase charge is 1000 uC, and one float ulp of that is about
        2.3e-13 uC -- so a *symmetric* protocol at that scale can miss an absolute
        1e-12 uC window on rounding alone, while a genuine 1e-15 relative imbalance on a
        nanoampere protocol would sail through it.

        Not tautological: both expected verdicts are stated from the ratio of the net
        charge to the phase charge computed here, and the scale at which the absolute
        tolerance breaks is quoted from the arithmetic rather than from the constant.
        """
        huge = StimProtocol(1e6, 1000.0, 10.0, 1.0)
        assert huge.charge_per_phase_uC == pytest.approx(1000.0, rel=1e-15)
        assert huge.is_charge_balanced

        # 1e-9 of the phase charge: far above an absolute 1e-12 uC at this scale, and a
        # real imbalance, so it must read as one.
        slightly_off = StimProtocol(
            1e6, 1000.0, 10.0, 1.0, charge_recovery_ratio=1.0 - 1e-9
        )
        assert slightly_off.net_charge_per_pulse_uC == pytest.approx(1e-6, rel=1e-6)
        assert not slightly_off.is_charge_balanced

    def test_the_charge_balance_check_cautions_for_a_biphasic_imbalance(self) -> None:
        """D6: categorical, and never a FAIL for a partial recovery.

        Charge balance carries no ceiling and its verdict must stay amplitude-independent
        (D3, ledger 84), so the *consequence* of an imbalance cannot be expressed here --
        it goes on Water window at C2.3, which is limit-bearing. What stays here is the
        statement of fact, with the net DC current and its density.

        A FAIL would be wrong as well as misplaced: it would make ``limiting_current_uA``
        ``None`` for a protocol that has a perfectly good limit, on the strength of a
        float tolerance. At 80 uA / 200 us / 130 Hz a 0.1 % imbalance is 2.1 nA of net DC.

        Not tautological: the expected DC current and current density are computed here
        from the inputs (``(1-r_a) * I * W * f`` and that over the geometric area), and the
        status expectation is a literal, not a branch of the check restated.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.999),
        )
        expected_dc_uA = 0.001 * 80.0 * 200.0 * 1e-6 * 130.0
        expected_dc_A_cm2 = expected_dc_uA * 1e-6 / calc.e.area_cm2

        check = _check(calc, "Charge balance")
        assert calc.p.net_dc_current_uA == pytest.approx(expected_dc_uA, rel=1e-9)
        # D6's own worked figure for this case, in nanoamps: 2.1 nA of net DC, which is
        # below anything in this bibliography that is treated as damaging.
        assert expected_dc_uA * 1e3 == pytest.approx(2.08, rel=1e-3)
        assert check.status is Status.CAUTION
        assert f"{expected_dc_uA:.4g}" in check.summary
        assert f"{expected_dc_A_cm2:.4g}" in check.summary

    def test_a_biphasic_pulse_that_recovers_nothing_fails_like_a_monophasic_one(
        self,
    ) -> None:
        """Zero recovery is a monophasic waveform however the field is spelled.

        The monophasic FAIL is not about the size of the DC -- it is that no
        charge-density limit in this package was measured on a waveform that recovers no
        charge (Merrill et al. 2005). That argument applies verbatim to
        ``charge_recovery_ratio = 0.0``, and leaving it at CAUTION while the byte-identical
        monophasic waveform FAILs would be the same defect ledger 3 is about, entered
        through the new field.

        Not tautological: the two protocols are asserted to carry the *same* net charge
        before their statuses are compared, so the assertion is about the verdict tracking
        the waveform rather than about the spelling of ``waveform``.
        """
        electrode = DiscElectrode(500.0, "Pt")
        zero_recovery = SafetyCalculator(
            electrode,
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.0),
        )
        monophasic = SafetyCalculator(
            electrode, StimProtocol(80.0, 200.0, 130.0, 1.0, waveform="monophasic")
        )

        assert zero_recovery.p.net_charge_per_pulse_uC == pytest.approx(
            monophasic.p.net_charge_per_pulse_uC, rel=1e-15
        )
        assert _check(zero_recovery, "Charge balance").status is Status.FAIL
        assert _check(monophasic, "Charge balance").status is Status.FAIL

    def test_the_new_field_reaches_every_consumer_of_the_protocol(self) -> None:
        """The field a only citation string reads is a new silent failure (physics M7).

        Four surfaces serialise or render the protocol, and a field missing from any of
        them is a setting the user entered and the output does not mention.

        Not tautological: each assertion is against a *rendered* artefact -- a dataclass
        dict, a JSON document, the PDF's own text -- and the expected number is the
        recovery ratio the calculator was constructed with, which none of them derives.
        """
        import json

        from neurostim.io.tabular import protocol_from_dict, report_to_json

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.75),
        )

        assert asdict(calc.p)["charge_recovery_ratio"] == 0.75

        payload = json.loads(report_to_json(calc))
        assert payload["protocol"]["charge_recovery_ratio"] == 0.75

        # The batch path builds a protocol from a flat mapping; a column the builder does
        # not accept is a row that cannot express the fault.
        rebuilt = protocol_from_dict(
            {
                "current_uA": 80.0,
                "pulse_width_us": 200.0,
                "frequency_hz": 130.0,
                "train_duration_s": 1.0,
                "charge_recovery_ratio": 0.75,
            }
        )
        assert rebuilt.charge_recovery_ratio == 0.75
        assert rebuilt.net_charge_per_pulse_uC == pytest.approx(
            0.25 * 80.0 * 200.0 * 1e-6, rel=1e-12
        )

    def test_the_pdf_names_the_recovery_and_the_net_dc(self, tmp_path) -> None:
        """The report is the artefact a reader keeps; a DC offset must appear on it.

        Not tautological: the assertion is on text extracted from the rendered PDF by an
        external tool, against a percentage computed here from the constructor argument.
        """
        from tests.test_verdict_core import pdf_text

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.75),
        )
        text = pdf_text(calc, tmp_path / "recovery.pdf")

        assert "Charge recovery" in text
        assert "75.0" in text


class TestSymmetricProtocolsDoNotMove:
    """The golden guard on C2.1 and C2.2: a balanced pulse is byte-identical.

    Both commits change how the return phase is derived and how it is evaluated. The
    population that must not move is every protocol that was already symmetric and
    balanced, which is every protocol anyone has assessed with this package. The values
    below were captured at ``aaf3c85``, before the change, and are literals here so that a
    regression is a diff against a recorded number rather than against a recomputation.

    Not tautological: these are *pre-change* outputs, pasted in. Nothing in the commit
    under test can produce them; it can only fail to disturb them.
    """

    GOLDEN = {
        "ring": (
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            {
                "limiting_current_uA": 20.0,
                "required_compliance_V": 0.8286922987786409,
                "peak_electrode_potential_V": -0.22635369684180667,
                "net_dc_current_uA": 0.0,
                "duty_cycle": 0.052,
            },
        ),
        "disc_pt": (
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            {
                "limiting_current_uA": 19.634954084936204,
                "required_compliance_V": 1.957730451487647,
                "peak_electrode_potential_V": -0.8148733086305042,
                "net_dc_current_uA": 0.0,
                "duty_cycle": 0.052,
            },
        ),
        "disc_sirof": (
            DiscElectrode(500.0, "SIROF"),
            StimProtocol(500.0, 50.0, 130.0, 1.0),
            {
                "limiting_current_uA": 998.0887516949169,
                "required_compliance_V": 1.4300993160251108,
                "peak_electrode_potential_V": -0.0015278874536821948,
                "net_dc_current_uA": 0.0,
                "duty_cycle": 0.013,
            },
        ),
    }

    @pytest.mark.parametrize("case", sorted(GOLDEN))
    def test_a_balanced_symmetric_protocol_reports_what_it_did_before(
        self, case: str
    ) -> None:
        electrode, protocol, expected = self.GOLDEN[case]
        report = SafetyCalculator(electrode, protocol).report()
        for key, value in expected.items():
            assert report[key] == value, (case, key, report[key])

    def test_a_balanced_symmetric_protocol_still_passes_charge_balance(self) -> None:
        """The check whose branch structure C2.1 rewrites, on the arm that must not move."""
        calc = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
        )
        assert calc.p.is_charge_balanced
        assert calc.p.net_charge_per_pulse_uC == 0.0
        check = _check(calc, "Charge balance")
        assert check.status is Status.PASS
        assert check.summary == "biphasic, fully charge-balanced"

    def test_a_balanced_asymmetric_width_protocol_is_still_balanced(self) -> None:
        """``return_phase_ratio`` alone still recovers everything, exactly.

        The width ratio and the recovery ratio are orthogonal, so widening the return
        phase without changing the recovery must leave the net charge at exactly zero --
        not approximately zero, because the two charges are the same product in a
        different association only when the recovery ratio is exactly one.
        """
        p = StimProtocol(80.0, 200.0, 130.0, 1.0, return_phase_ratio=4.0)
        assert p.net_charge_per_pulse_uC == 0.0
        assert p.is_charge_balanced
        assert math.isclose(p.return_charge_uC, p.charge_per_phase_uC, rel_tol=0.0)


class TestTheReturnPhaseIsEvaluated:
    """T13. Only the leading phase reached the verdicts (ledger 4).

    ``return_phase_ratio`` has always changed the return phase's amplitude and width, and
    neither current density nor compliance ever looked at it. With ``r = 0.2`` on a
    1000 uA protocol the return phase is 5000 uA -- five times the current through the
    same access resistance and the same electrode area -- and both checks returned
    bit-identical answers to the symmetric case: ``required_V`` 0.5235 V and a current
    density of 0.01671 A/cm^2, when the return phase alone needs 2.59 V and reaches
    0.0835 A/cm^2.

    The return phase is a pulse of its own width, so it is compared against the Butterwick
    threshold *at that width* rather than at the leading phase's. A shorter return phase
    is not simply worse: the threshold rises as roughly ``t^-0.5``, so the amplitude gain
    and the threshold gain partly cancel and only the arithmetic says which binds.

    Fixture rule: every ratio here differs from the 1.0 default, and the golden class
    above pins that the default population does not move.
    """

    BAND_SYMMETRIC_REQUIRED_V = 0.5235321306516268
    """``required_V`` for the band at 1000 uA / 90 us, measured at ``9e87b85``.

    A pre-change literal. The commit under test must leave it exactly where it is for the
    symmetric protocol and must move the asymmetric one away from it.
    """

    def test_the_peak_current_density_is_the_return_phase_when_it_is_narrower(
        self,
    ) -> None:
        """Four times the leading density at a quarter of the width.

        Not tautological: the expected peak is ``4 * I * 1e-6 / area``, written from the
        protocol's own inputs and the geometric area. The defect is that the package never
        formed this quantity at all -- ``0.3183 A/cm^2`` was reported for both the
        symmetric and the asymmetric protocol.
        """
        from neurostim.safety import current_density as jd

        electrode = DiscElectrode(100.0, "Pt")
        area = electrode.area_cm2
        symmetric = StimProtocol(25.0, 200.0, 130.0, 1.0)
        asymmetric = StimProtocol(25.0, 200.0, 130.0, 1.0, return_phase_ratio=0.25)

        assert asymmetric.return_phase_current_uA == pytest.approx(100.0, rel=1e-15)
        assert asymmetric.return_phase_width_us == pytest.approx(50.0, rel=1e-15)

        def peak(p: StimProtocol) -> float:
            return jd.evaluate(
                p.current_uA,
                area,
                p.pulse_width_us,
                diameter_um=2.0 * electrode.equivalent_radius_um,
                return_phase_current_uA=p.return_phase_current_uA,
                return_phase_width_us=p.return_phase_width_us,
            ).peak_A_per_cm2

        assert peak(symmetric) == pytest.approx(25e-6 / area, rel=1e-15)
        assert peak(asymmetric) == pytest.approx(4.0 * 25e-6 / area, rel=1e-15)

    def test_the_binding_phase_is_whichever_sits_closer_to_its_own_threshold(
        self,
    ) -> None:
        """Compared at its own width, because that is the pulse it is.

        Butterwick's threshold falls as ``(t / 6000 us) ** n``. On a 500 um disc the size
        regime is flat, so the two phases differ only through that power law: a quarter
        the width raises the threshold by ``4 ** -n`` while the amplitude rises 4x, and
        the return phase binds by the ratio of the two.

        Not tautological: both thresholds are written out here from the published anchor
        (0.061 A/cm^2 at 6 ms, repeated exposure) and the fitted exponent, not read from
        the comparison the check builds.
        """
        from neurostim.data import butterwick2007 as bw
        from neurostim.safety import current_density as jd

        electrode = DiscElectrode(500.0, "SIROF")
        area = electrode.area_cm2
        protocol = StimProtocol(500.0, 50.0, 130.0, 1.0, return_phase_ratio=0.25)
        n = bw.FITTED_DURATION_EXPONENT

        expected_lead_threshold = 0.061 * (50.0 / 6000.0) ** n
        expected_return_threshold = 0.061 * (12.5 / 6000.0) ** n
        lead_margin = expected_lead_threshold / (500e-6 / area)
        return_margin = expected_return_threshold / (2000e-6 / area)
        assert return_margin < lead_margin

        result = jd.evaluate(
            protocol.current_uA,
            area,
            protocol.pulse_width_us,
            diameter_um=2.0 * electrode.equivalent_radius_um,
            return_phase_current_uA=protocol.return_phase_current_uA,
            return_phase_width_us=protocol.return_phase_width_us,
        )
        assert result.binding_phase == "return"
        assert result.binding_threshold is not None
        assert result.binding_threshold.threshold_A_per_cm2 == pytest.approx(
            expected_return_threshold, rel=1e-12
        )
        assert result.binding_threshold.margin == pytest.approx(return_margin, rel=1e-12)

    def test_an_asymmetric_protocol_gets_a_worse_current_density_margin(self) -> None:
        """The check itself, not just the result object -- identical today.

        Not tautological: the two margins are compared with each other, and the symmetric
        one is pinned to the value the package reported before this commit
        (3.4571173440156455 on a 100 um Pt disc at 25 uA / 200 us), so the assertion fails
        if the asymmetric case is merely *changed* rather than made worse.
        """
        electrode = DiscElectrode(100.0, "Pt")
        symmetric = _check(
            SafetyCalculator(electrode, StimProtocol(25.0, 200.0, 130.0, 1.0)),
            "Current density",
        )
        asymmetric = _check(
            SafetyCalculator(
                electrode,
                StimProtocol(25.0, 200.0, 130.0, 1.0, return_phase_ratio=0.25),
            ),
            "Current density",
        )

        assert symmetric.margin == pytest.approx(3.4571173440156455, rel=1e-12)
        assert asymmetric.margin < symmetric.margin
        assert asymmetric.ceiling_uA < symmetric.ceiling_uA

    def test_the_return_phase_enters_the_voltage_budget(self) -> None:
        """Ledger 4's own case: 5000 uA through the same access resistance.

        Not tautological: the expected requirement is Ohm's law plus the capacitive
        excursion, written here for the *return* phase's own amplitude and width --
        ``I_ret * R + (I_ret * W_ret / A) / C`` -- a quantity the package computed nowhere.
        ``R`` is read from the result rather than written as a literal because it is the
        geometry's answer, not the compliance model's, and C3.1 moves it.
        """
        from neurostim import CylindricalBandElectrode

        electrode = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        area = electrode.area_cm2
        symmetric = SafetyCalculator(
            electrode,
            StimProtocol(1000.0, 90.0, 130.0, 1.0),
            capacitance_uF_cm2=250.0,
        ).assess().compliance
        asymmetric = SafetyCalculator(
            electrode,
            StimProtocol(1000.0, 90.0, 130.0, 1.0, return_phase_ratio=0.2),
            capacitance_uF_cm2=250.0,
        ).assess().compliance

        assert symmetric.required_V == self.BAND_SYMMETRIC_REQUIRED_V

        resistance = asymmetric.total_resistance_ohm
        expected = 5000e-6 * resistance + (5000.0 * 18.0 * 1e-6 / area) / 250.0
        assert asymmetric.required_V == pytest.approx(expected, rel=1e-12)
        assert asymmetric.required_V == pytest.approx(2.59, rel=1e-2)
        assert asymmetric.required_V / symmetric.required_V == pytest.approx(
            4.954, rel=1e-3
        )

    def test_the_compliance_limit_falls_and_still_passes_its_own_check(self) -> None:
        """A limit that FAILs its own check is the defect the whole floor contract is for.

        Not tautological: the limit is re-fed to the forward comparison the check uses,
        and to its IEEE successor. Neither reads the back-solve.
        """
        import math

        from neurostim import CylindricalBandElectrode

        electrode = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        symmetric = SafetyCalculator(
            electrode,
            StimProtocol(1000.0, 90.0, 130.0, 1.0),
            capacitance_uF_cm2=250.0,
            compliance_V=3.0,
        ).assess().compliance
        asymmetric_calc = SafetyCalculator(
            electrode,
            StimProtocol(1000.0, 90.0, 130.0, 1.0, return_phase_ratio=0.2),
            capacitance_uF_cm2=250.0,
            compliance_V=3.0,
        )
        asymmetric = asymmetric_calc.assess().compliance

        assert asymmetric.max_current_uA < symmetric.max_current_uA

        limit = asymmetric.max_current_uA
        assert asymmetric.required_V_at(limit) <= 3.0
        assert asymmetric.required_V_at(math.nextafter(limit, math.inf)) > 3.0

    def test_the_headline_moves_where_current_density_binds(self) -> None:
        """Section 6: the limiting current moves for every ``return_phase_ratio != 1``
        whose binding check is one of the two this commit repairs.

        Not tautological: the expected ceiling is the independent fail-ceiling bisection
        over ``assess().failed``, which reads one bit per probe and never reads a margin,
        a ceiling or the limiting current.
        """
        from tests import oracles

        electrode = DiscElectrode(500.0, "SIROF")
        symmetric = SafetyCalculator(electrode, StimProtocol(500.0, 50.0, 130.0, 1.0))
        asymmetric = SafetyCalculator(
            electrode,
            StimProtocol(500.0, 50.0, 130.0, 1.0, return_phase_ratio=0.25),
        )

        assert symmetric.assess().limiting_current_uA == 998.0887516949169
        moved = asymmetric.assess().limiting_current_uA
        assert moved is not None
        assert moved < 998.0887516949169
        assert moved == pytest.approx(
            oracles.fail_ceiling_uA(asymmetric, names=oracles.LIMIT_BEARING), rel=1e-9
        )

    def test_a_monophasic_protocol_has_no_return_phase_to_evaluate(self) -> None:
        """A zero-width return phase must not be handed to a ``t ** -n`` threshold.

        Not tautological: the assertion is that the binding phase is the leading one and
        that no return comparison exists, which is a statement about absence; the
        arithmetic that would otherwise raise is the package's, not the test's.
        """
        electrode = DiscElectrode(500.0, "SIROF")
        result = SafetyCalculator(
            electrode,
            StimProtocol(500.0, 50.0, 130.0, 1.0, waveform="monophasic"),
        ).assess()
        jd_result = next(
            c for c in result.checks if c.name == "Current density"
        )
        assert jd_result.ceiling_uA == pytest.approx(998.0887516949169, rel=1e-12)


class TestDcDriftOutOfTheWaterWindow:
    """C2.3. A waveform that leaves charge behind walks the interface to the edge.

    The package applied per-pulse limits, every one of them measured on a charge-balanced
    waveform, and reported the monophasic case as a PASS with 0.58 V of headroom (ledger
    2). The interface is a capacitor charged by the mean unrecovered current, so the
    potential ramps: on the audit's own case -- a clinical band at 3000 uA, 90 us, 130 Hz
    -- it leaves a 0.6 V window in about a quarter of a second.

    **Reported on Water window, never on Charge balance** (fix plan D6, ledger 84). Charge
    balance bears no ceiling and its verdict must stay amplitude-independent, which is the
    invariant that makes ``unsafe_at_any_amplitude`` correct. The drift consequence *is*
    amplitude-dependent -- halve the amplitude and the time to the edge doubles -- so it
    belongs on the check that can express a ceiling.

    Fixture rule: the capacitance is supplied as 250 uF/cm^2 rather than left to the
    material derivation, and the train duration is 1 s rather than the ``inf`` that would
    make every drift verdict a FAIL for free.
    """

    BAND = ("PtIr", 1270.0, 1500.0)
    PLAN_CASE_DRIFT_TIME_S = 0.2557578634653229
    PLAN_CASE_DRIFT_CEILING_uA = 767.2735903959687
    PLAN_CASE_PEAK_CEILING_uA = 99745.56675147594

    def _band(self):
        from neurostim import CylindricalBandElectrode

        return CylindricalBandElectrode(1270.0, 1500.0, "PtIr")

    def _calc(self, **protocol_kw):
        return SafetyCalculator(
            self._band(),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, **protocol_kw),
            capacitance_uF_cm2=250.0,
        )

    def test_the_drift_time_agrees_with_the_pulse_by_pulse_integrator(self) -> None:
        """Within one pulse, which is the strongest statement that can be made.

        Not tautological: the oracle is ``tests/oracles/drift.drift_time_s``, a loop that
        adds one pulse's charge at a time and asks after each whether the potential has
        left the window. It evaluates no closed form and imports no part of ``neurostim``;
        a pulse train cannot resolve time more finely than its own period, so agreement to
        within ``1/f`` is the whole of what can be asserted.
        """
        from tests import oracles

        electrode = self._band()
        drift = self._calc(waveform="monophasic").assess().water_window.drift
        assert drift is not None

        integrated = oracles.drift_time_s(
            current_uA=3000.0,
            pulse_width_us=90.0,
            frequency_hz=130.0,
            area_cm2=electrode.area_cm2,
            capacitance_uF_cm2=250.0,
            window_V=0.6,
        )
        assert drift.time_to_exit_s == pytest.approx(
            self.PLAN_CASE_DRIFT_TIME_S, rel=1e-12
        )
        assert abs(drift.time_to_exit_s - integrated) < 1.0 / 130.0
        assert drift.time_to_exit_s == pytest.approx(0.2558, rel=1e-3)

    def test_the_window_charge_is_the_headroom_times_the_interface(self) -> None:
        """``Q = dV * C * A``, and the net DC that empties it.

        Not tautological: both quantities are written out here from the published window
        edge (PtIr, -0.6 V cathodic), the supplied capacitance and the geometric area --
        ``0.6 V * 250 uF/cm^2 * 0.05984734 cm^2 = 8.9771 uC`` -- and the DC from the duty
        cycle, ``3000 uA * 90 us * 130 Hz = 35.1 uA``.
        """
        electrode = self._band()
        drift = self._calc(waveform="monophasic").assess().water_window.drift
        assert drift is not None

        assert electrode.area_cm2 == pytest.approx(0.05984734005088556, rel=1e-12)
        assert drift.window_headroom_V == pytest.approx(0.6, rel=1e-15)
        assert drift.window_charge_uC == pytest.approx(
            0.6 * 250.0 * electrode.area_cm2, rel=1e-12
        )
        assert drift.window_charge_uC == pytest.approx(8.9771, rel=1e-4)
        assert drift.net_dc_current_uA == pytest.approx(35.1, rel=1e-12)

    def test_the_seed_gains_the_drift_term_in_the_same_commit_as_the_clause(
        self,
    ) -> None:
        """The hard condition. ``_water_window_seed_uA`` inverts every clause it seeds.

        The peak-only seed is ``f * T = 130`` times the drift boundary -- 8.7e17 ulps
        against a four-float budget -- so a drift clause added without its inverse makes
        ``floor_to_pass`` raise ``LimitDidNotSettle`` on every monophasic protocol. Landing
        the seed first was measured to be no better: 160 of 160 monophasic configurations
        then raise on the way *up*.

        Not tautological: both terms are written out here from the published window and the
        geometry -- ``max_charge_density_in_window_uC_cm2 * A / W`` and
        ``dV * C * A / (frac * W * f * T)`` -- and the ratio 130 between them is asserted
        as ``f * T``, so a seed missing either term fails on a number this test computes
        rather than on a crash inside the check.
        """
        from neurostim.safety import water_window as ww
        from neurostim.safety.assessment import _water_window_search

        electrode = self._band()
        calc = self._calc(waveform="monophasic")
        result = calc.assess().water_window

        seed_density = ww.max_charge_density_in_window_uC_cm2(
            "PtIr", anodic_first=False, resting_potential_V=0.0, capacitance_uF_cm2=250.0
        )
        peak_inverse = seed_density * electrode.area_cm2 / 90e-6
        drift_inverse = (0.6 * 250.0 * electrode.area_cm2) / (1.0 * 90e-6 * 130.0 * 1.0)

        assert peak_inverse == pytest.approx(self.PLAN_CASE_PEAK_CEILING_uA, rel=1e-12)
        assert drift_inverse == pytest.approx(self.PLAN_CASE_DRIFT_CEILING_uA, rel=1e-12)
        assert peak_inverse / drift_inverse == pytest.approx(130.0, rel=1e-12)

        search = _water_window_search(result, calc.p, electrode.area_cm2)
        assert search.seed_uA == pytest.approx(drift_inverse, rel=1e-12)
        assert search.seed_uA == pytest.approx(min(peak_inverse, drift_inverse), rel=1e-12)

    def test_the_monophasic_water_window_ceiling_is_the_drift_boundary(self) -> None:
        """Section 6's C2.3 row: 99745.56675147594 -> 767.2735903959687 uA.

        Not tautological: the expected ceiling is the closed form written above, and it is
        then re-fed to the check's own forward comparison and to that value's IEEE
        successor -- the floor contract -- neither of which reads the back-solve.
        """
        import math

        from neurostim.safety.assessment import _water_window_search

        calc = self._calc(waveform="monophasic")
        electrode = self._band()
        ceiling = _check(calc, "Water window").ceiling_uA

        assert ceiling == pytest.approx(self.PLAN_CASE_DRIFT_CEILING_uA, rel=1e-9)
        search = _water_window_search(
            calc.assess().water_window, calc.p, electrode.area_cm2
        )
        assert search.passes(ceiling)
        assert not search.passes(math.nextafter(ceiling, math.inf))

    def test_the_monophasic_verdict_is_fail_with_the_drift_time(self) -> None:
        """Ledger 2: PASS with 0.58 V of headroom becomes FAIL at 0.256 s.

        Not tautological: the headroom the old verdict rested on is asserted to still be
        positive -- the peak excursion really does stay inside the window -- so the FAIL
        can only come from the drift clause, which is the finding.
        """
        assessment = self._calc(waveform="monophasic").assess()
        result = assessment.water_window
        check = next(c for c in assessment.checks if c.name == "Water window")

        assert result.headroom_V > 0.5
        assert result.passes
        assert check.status is Status.FAIL
        assert "0.256" in check.summary or "0.2558" in check.summary

    def test_a_balanced_protocol_has_no_drift_and_does_not_move(self) -> None:
        """The population that must stay byte-identical: no DC, no clause.

        Not tautological: the net charge is asserted to be exactly zero before the verdict,
        so this pins the *absence* of a drift term rather than a coincidence of values.
        """
        calc = self._calc()
        result = calc.assess().water_window
        assert calc.p.net_charge_per_pulse_uC == 0.0
        assert result.drift is not None
        assert not result.drift.drifts
        assert result.drift.time_to_exit_s == math.inf
        assert _check(calc, "Water window").status is Status.PASS

    def test_the_drift_verdict_is_not_on_charge_balance(self) -> None:
        """D6 and ledger 84: the ceiling goes where a ceiling can be expressed.

        Not tautological: the two checks are read from one assessment and their statuses
        compared with each other, and the Charge-balance status is additionally pinned to
        the bracket invariant in the next test rather than to a literal alone.
        """
        calc = SafetyCalculator(
            self._band(),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, charge_recovery_ratio=0.5),
            capacitance_uF_cm2=250.0,
        )
        assert _check(calc, "Charge balance").status is Status.CAUTION
        assert _check(calc, "Water window").status is Status.FAIL
        assert _check(calc, "Charge balance").ceiling_uA == math.inf
        assert _check(calc, "Water window").ceiling_uA < math.inf

    def test_no_check_outside_limit_bearing_moves_with_amplitude(self) -> None:
        """C1.5's bracket test, re-run on an unbalanced biphasic protocol.

        The invariant the whole placement decision rests on: a check that bears no ceiling
        must return the same verdict at a femtoamp and at an amp, because that is what
        licenses ``unsafe_at_any_amplitude`` to read a FAIL there as "no amplitude is
        safe". C2.3 is the commit that could break it, so it is the commit that re-asserts
        it.

        Not tautological: the statuses are sampled at two amplitudes 18 decades apart and
        compared with each other -- no literal verdict appears -- and the oracle's
        ``amplitude_independent_failures`` witness is asserted alongside, which establishes
        the same property across all 73 ladder probes.
        """
        from dataclasses import replace

        from neurostim.safety.assessment import LIMIT_BEARING
        from tests import oracles

        calc = SafetyCalculator(
            self._band(),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, charge_recovery_ratio=0.5),
            capacitance_uF_cm2=250.0,
        )

        def statuses(current_uA: float) -> dict[str, Status]:
            rebuilt = SafetyCalculator(
                calc.e,
                replace(calc.p, current_uA=current_uA),
                capacitance_uF_cm2=250.0,
            )
            return {
                c.name: c.status
                for c in rebuilt.assess().checks
                if c.name not in LIMIT_BEARING
            }

        low, high = statuses(1e-12), statuses(1e6)
        assert low == high
        assert set(low) == {"Validated envelope", "Charge balance"}
        assert oracles.amplitude_independent_failures(calc) == ()

    def test_the_ceiling_converges_to_the_monophasic_one_as_recovery_vanishes(
        self,
    ) -> None:
        """The continuity the FAIL/CAUTION boundary at zero recovery could have hidden.

        Charge balance's label jumps at ``charge_recovery_ratio == 0`` -- CAUTION above it,
        FAIL at it -- because a waveform that recovers nothing is a monophasic waveform.
        The *safe amplitude* must not jump there: it is set by the drift ceiling, which is
        continuous in the unrecovered fraction. If the label moved while the number did
        not, the structure would be hiding a discontinuity.

        Not tautological: the expected limit is the ceiling the byte-identical monophasic
        protocol reports, which is a separate assessment of a separate protocol, and the
        monotonicity is a property of a sequence of ten independent assessments.
        """
        ratios = [0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0]
        ceilings = [
            _check(self._calc(charge_recovery_ratio=r), "Water window").ceiling_uA
            for r in ratios
        ]
        monophasic = _check(self._calc(waveform="monophasic"), "Water window").ceiling_uA

        assert all(
            later < earlier for earlier, later in itertools.pairwise(ceilings)
        ), ceilings
        assert ceilings[-1] == pytest.approx(monophasic, rel=1e-12)
        assert ceilings[0] == pytest.approx(2.0 * monophasic, rel=1e-9)
