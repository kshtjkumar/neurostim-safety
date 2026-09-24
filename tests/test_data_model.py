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
        from test_verdict_core import pdf_text

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

    ``required_compliance_V`` was moved by C3.9 (ledger 131: ring 0.8286922987786409 ->
    1.0550459956204477, Pt disc 1.957730451487647 -> 2.7726037601181512, SIROF disc
    1.4300993160251108 -> 1.4306086118430048), and C3.12 restored it (ledger 135). C3.9 gave
    the return phase's fictitious full excursion the opposite polarity's C_eff; a balanced
    return phase only discharges the leading branch and never needs more than ``I_ret R``.
    All keys are the aaf3c85 values again.
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

    BAND_SYMMETRIC_REQUIRED_V = 0.3354767487193873
    """``required_V`` for the band at 1000 uA / 90 us.

    A pre-change literal for C2.2, measured at ``9e87b85`` as 0.5235321306516268: that
    commit had to leave it exactly where it was for the symmetric protocol. C3.1 then moved
    it by moving the band's access resistance from the half-space equal-area disc
    (517.5 ohm) to the equal-area sphere (329.5 ohm), booked in section 6. Re-measured
    there.
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

        Not tautological: the expected requirement is Ohm's law for the *return* phase's
        own amplitude, ``I_ret * R``, a quantity the package computed nowhere before C2.2.
        ``R`` is read from the result rather than written as a literal because it is the
        geometry's answer, not the compliance model's, and C3.1 moves it.

        C2.2 wrote the expectation as ``I_ret R + (I_ret W_ret / A) / C``: the return phase's
        own full excursion from rest. C3.12 (ledger 135) removed that term. A return phase
        recovering no more than the leading charge only discharges the leading branch, and
        its interface voltage opposes the drive.
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
        expected = 5000e-6 * resistance
        assert asymmetric.required_V == pytest.approx(expected, rel=1e-12)
        assert area > 0.0
        # 2.59 V / 4.954x at the half-space disc's 517.5 ohm (C2.2); 1.653 V / 4.928x at the
        # sphere's 329.5 ohm (C3.1); 1.647 V / 4.910x without the fictitious return
        # excursion (C3.12).
        assert asymmetric.required_V == pytest.approx(1.6473, rel=1e-4)
        assert asymmetric.required_V / symmetric.required_V == pytest.approx(
            4.910, rel=1e-3
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
        import oracles

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
    """The closed-form drift inverse -- the seed. Two ulps below the reported ceiling."""
    PLAN_CASE_FLOORED_CEILING_uA = 767.2735903959689
    """The ceiling the package reports: the seed walked onto its predicate's boundary."""
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
        import oracles

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
        """Section 6's C2.3 row: 99745.56675147594 -> 767.2735903959689 uA.

        767.2735903959687 is the closed form, which floors two ulps up onto the boundary of
        the check's own comparison. Section 6 booked the closed form (ledger 106(e)); the
        ceiling is asserted here to the bit.

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
        assert ceiling == self.PLAN_CASE_FLOORED_CEILING_uA
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

        import oracles

        from neurostim.safety.assessment import LIMIT_BEARING

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
        # Half the charge left behind would double the ceiling if the offset had the whole
        # budget. The recovered half of each pulse rides on the offset (ledger 105), so it
        # is 2 * f*T / (f*T + 1) with f*T = 130 pulses over the 1 s train: 260/131, not 2.
        assert ceilings[0] == pytest.approx(260.0 / 131.0 * monophasic, rel=1e-9)


class TestTheHeadlineRefusesWheneverNoAmplitudeIsSafe:
    """Ledger 99, and the classification trap beside it.

    ``limiting_current_uA`` documented "``None`` exactly when the protocol is unsafe at any
    amplitude" and did not keep it. Two separate holes:

    **A ceiling of exactly zero was printed as a number.** ``unsafe_at_any_amplitude``
    collected only FAILs outside ``LIMIT_BEARING``, so a limit-bearing check permitting no
    current at all returned ``0.0`` and every surface printed
    ``Limiting current: 0 uA (Water window)`` -- an amplitude ``StimProtocol`` itself
    rejects, so the package named as a limit a value no user can set. 12 240 of 299 520
    swept configurations produce one. C2.3 widened the population: a continuous train with
    any unrecovered charge drives the drift ceiling to exactly zero, and Charge balance is
    only a CAUTION for a partial recovery, so nothing else refuses.

    **"Not limit-bearing" was standing in for "failure means no amplitude is safe".** Two
    checks sit outside ``LIMIT_BEARING`` and only one of them means that. ``Validated
    envelope`` has no FAIL state today -- 60 CAUTION, 12 PASS, 0 FAIL over 72 swept
    configurations -- which is the only reason the coupling is invisible. C2.5 rewrites
    that check, and the first time it FAILs a protocol whose only sin is sitting outside
    McCreery's fit envelope would be announced as having no safe amplitude at all. The
    property is now named rather than inferred.
    """

    def _zero_by_resting_potential(self) -> SafetyCalculator:
        """Ledger 99's own case: a Pt interface resting exactly on its cathodic edge.

        Accepted deliberately -- ``validate_resting_potential_V`` is inclusive at both
        ends, so the rejection cannot disagree with ``WaterWindow.contains`` about the
        boundary itself.
        """
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            resting_potential_V=-0.6,
        )

    def _zero_by_continuous_drift(self) -> SafetyCalculator:
        """The door C2.3 opened: an unrecovered offset with no end to the train."""
        return SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(
                80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=0.9
            ),
        )

    @pytest.mark.parametrize(
        "case", ["_zero_by_resting_potential", "_zero_by_continuous_drift"]
    )
    def test_a_zero_ceiling_refuses_rather_than_naming_an_unusable_amplitude(
        self, case: str
    ) -> None:
        """Not tautological: the raw ceiling is asserted to still *be* 0.0 -- the value is
        not being hidden, it is being refused -- and the refusal is checked against
        ``StimProtocol``'s own rejection of that amplitude, which is what makes printing it
        wrong rather than merely ugly.
        """
        calc = getattr(self, case)()
        assessment = calc.assess()

        assert assessment.limit_bearing_ceiling_uA == 0.0
        with pytest.raises(ValueError, match="current_uA"):
            StimProtocol(0.0, 200.0, 130.0, 1.0)

        assert assessment.limiting_current_uA is None
        assert calc.report()["limiting_current_uA"] is None

    def test_the_refusal_names_the_check_that_permits_no_current(self) -> None:
        """"No amplitude is safe" without saying which check makes it so is unactionable.

        Not tautological: the named check is read from the tuple of zero-ceiling checks and
        compared with the sentence, and the sentence is additionally required to differ
        from the amplitude-independent wording -- the two reasons carry different
        instructions to the reader and must not collapse into one string.
        """
        calc = self._zero_by_continuous_drift()
        assessment = calc.assess()

        assert [c.name for c in assessment.permits_no_current] == ["Water window"]
        note = assessment.no_safe_amplitude_note()
        assert "Water window" in note
        assert "no amplitude is safe" in note
        assert "at every amplitude" not in note

    @pytest.mark.parametrize(
        "case", ["_zero_by_resting_potential", "_zero_by_continuous_drift"]
    )
    def test_no_surface_prints_an_amplitude_for_a_zero_ceiling(
        self, case: str, tmp_path
    ) -> None:
        """All six render surfaces, since a refusal honoured by five of them is ledger 84.

        Not tautological: each assertion is on a *rendered* string -- ``describe()``, the
        batch dict, the JSON document, the PDF's extracted text, the GUI headline free
        function -- and what is asserted is the absence of a number beside the word
        "Limiting", which no arithmetic in the package can produce.
        """
        import json

        from test_verdict_core import pdf_text

        from neurostim.gui.app import headline_text
        from neurostim.io.tabular import report_to_json

        calc = getattr(self, case)()
        assessment = calc.assess()

        text = assessment.describe()
        assert "Limiting current: none" in text
        assert "Limiting current: 0 uA" not in text

        assert "no amplitude is safe" in calc.report()["limiting_mechanism"]

        payload = json.loads(report_to_json(calc))
        assert payload["results"]["limiting_current_uA"] is None
        assert payload["permits_no_current"] == ["Water window"]

        assert "0 uA" not in headline_text(assessment)
        assert "no amplitude is safe" in headline_text(assessment)

        pdf = pdf_text(calc, tmp_path / f"{case}.pdf")
        assert "no amplitude is safe" in pdf

    def test_sensitivity_refuses_for_a_zero_ceiling_too(self) -> None:
        """``analyse`` renders the limit nine times; a zero would be nine unusable numbers.

        Not tautological: the exception type and the named check are asserted, and
        ``describe`` is separately required to contain no amplitude -- the two paths are
        different code.
        """
        from neurostim import sensitivity

        calc = self._zero_by_continuous_drift()
        with pytest.raises(sensitivity.UnsafeAtAnyAmplitude, match="Water window"):
            sensitivity.analyse(calc)
        text = sensitivity.describe(calc)
        assert "none --" in text
        assert "baseline:" not in text

    def test_the_no_safe_amplitude_set_is_named_rather_than_inferred(self) -> None:
        """Decision (d). "Not limit-bearing" is a classification, not this property.

        Not tautological: the set is compared with the *complement* of ``LIMIT_BEARING``
        over the checks an assessment actually emits, and the assertion is that it is a
        strict subset -- which is the whole finding. A test asserting only the membership
        of Charge balance would pass under the old inferred definition too.
        """
        from neurostim.safety.assessment import LIMIT_BEARING, NO_SAFE_AMPLITUDE

        emitted = {
            c.name
            for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
            ).assess().checks
        }
        not_limit_bearing = emitted - LIMIT_BEARING

        assert not_limit_bearing == {"Charge balance", "Validated envelope"}
        assert frozenset({"Charge balance"}) == NO_SAFE_AMPLITUDE
        assert not_limit_bearing > NO_SAFE_AMPLITUDE

    def test_a_failing_validated_envelope_does_not_refuse_the_headline(self) -> None:
        """The trap C2.5 would have sprung. Scripted, because the check has no FAIL today.

        ``Validated envelope`` returns CAUTION or PASS for every protocol the package can
        build -- 60 and 12 of 72 swept, 0 FAIL -- so no real configuration exercises this.
        The FAIL is substituted into an otherwise real assessment, which is the same device
        C1.2 uses for the two ``NonMonotonePredicate`` guards: the scripted verdict is
        written here, so the expected outcome is a property of the script rather than of
        any package verdict.

        Not tautological: the substituted check is asserted to be a FAIL and to sit outside
        ``LIMIT_BEARING`` before the headline is read, so the test cannot pass by the
        substitution silently failing to take.
        """
        from dataclasses import replace

        from neurostim.safety.assessment import LIMIT_BEARING
        from neurostim.safety.assessment import Status as S

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
        )
        real = calc.assess()
        assert real.limiting_current_uA is not None

        scripted = replace(
            real,
            checks=tuple(
                replace(c, status=S.FAIL)
                if c.name == "Validated envelope"
                else c
                for c in real.checks
            ),
        )
        envelope = next(
            c for c in scripted.checks if c.name == "Validated envelope"
        )
        assert envelope.status is S.FAIL
        assert envelope.name not in LIMIT_BEARING

        assert scripted.unsafe_at_any_amplitude == ()
        assert scripted.no_safe_amplitude_note() == ""
        assert scripted.limiting_current_uA == real.limiting_current_uA
        assert scripted.status is S.FAIL


class TestMonophasicProtocolsStopInheritingBiphasicLimits:
    """T4. Ledger 2, and the regression a naive repair would have shipped.

    Every charge-injection capacity in the material database was measured with a
    charge-balanced biphasic waveform (Merrill et al. 2005). Applying one to a monophasic
    protocol asserts more than the measurement supports, so the check reports
    NOT_EVALUATED and ``limits_incomplete`` says the candidate set is short one member.

    **Removing a candidate from a minimum can only raise it**, which is why that repair
    cannot stand alone: a strictly worse waveform would earn a strictly higher limit. Two
    things close it. The DC-drift ceiling (C2.3) puts a *new*, much lower candidate into
    the monophasic set -- it is the binding one for most materials -- and a monotonicity
    cap holds the rest at the biphasic value. Measured over 216 configurations: after the
    NOT_EVALUATED alone, 4 invert, every one of them Ta2O5, the single shipped material
    with no water window on record and therefore no drift ceiling. The cap closes those
    four by construction, and they are the only ones it has to.

    Fixture rule: the sweep spans every material rather than a chosen one, so no assertion
    can rest on a value a default would supply.
    """

    DIAMETERS_UM = (40.0, 100.0, 150.0, 500.0, 1000.0, 2000.0)
    PULSE_WIDTHS_US = (50.0, 100.0, 200.0, 400.0)

    def _pair(self, key: str, diameter_um: float, pulse_width_us: float):
        electrode = DiscElectrode(diameter_um, key)
        mono = SafetyCalculator(
            electrode,
            StimProtocol(80.0, pulse_width_us, 130.0, 1.0, waveform="monophasic"),
        ).assess()
        bi = SafetyCalculator(
            electrode, StimProtocol(80.0, pulse_width_us, 130.0, 1.0)
        ).assess()
        return mono, bi

    def _sweep(self):
        from neurostim.materials import list_materials

        for material in list_materials():
            for diameter_um in self.DIAMETERS_UM:
                for pulse_width_us in self.PULSE_WIDTHS_US:
                    yield (
                        material.key,
                        diameter_um,
                        pulse_width_us,
                        *self._pair(material.key, diameter_um, pulse_width_us),
                    )

    def test_a_strictly_worse_waveform_never_earns_a_higher_limit(self) -> None:
        """T4(a), the monotonicity property, over every material and size.

        Not tautological: the two ceilings come from two independent assessments of two
        different protocols, and the comparison is between them -- no expected value is
        written down, so the assertion cannot be satisfied by reproducing an expression.
        Verified to fail without the repair: the NOT_EVALUATED alone inverts 4 of these 216
        pairs.
        """
        inverted = [
            (key, d, w, mono.limit_bearing_ceiling_uA, bi.limit_bearing_ceiling_uA)
            for key, d, w, mono, bi in self._sweep()
            if mono.limit_bearing_ceiling_uA > bi.limit_bearing_ceiling_uA
        ]
        assert inverted == []

    def test_the_drift_ceiling_is_what_makes_the_inequality_strict(self) -> None:
        """T4(a), the half the cap alone cannot deliver.

        The cap can only produce ``<=``; equality is all it ever gives. Wherever the
        monophasic protocol is bound by Water window it must be *strictly* lower, and the
        value must be the drift closed form -- so this clause fails if the drift model is
        not wired into the candidate set.

        Not tautological: the expected ceiling is
        ``headroom * C * A / (W * f * T)`` recomputed here from the assessment's own
        published window and interfacial capacitance, and the strictness is a comparison
        against a separate assessment of a separate protocol.
        """
        strict = 0
        for key, d, w, mono, bi in self._sweep():
            binding = min(
                (c for c in mono.checks if c.name in _limit_bearing_names()),
                key=lambda c: c.ceiling_uA,
            )
            if binding.name != "Water window":
                continue
            strict += 1
            assert mono.limit_bearing_ceiling_uA < bi.limit_bearing_ceiling_uA, (key, d, w)

            drift = mono.water_window.drift
            assert drift is not None
            expected = drift.window_charge_uC / (w * 1e-6 * 130.0 * 1.0)
            assert mono.limit_bearing_ceiling_uA == pytest.approx(expected, rel=1e-9), (
                key,
                d,
                w,
            )
        assert strict > 100

    def test_the_monophasic_case_fails_overall(self) -> None:
        """T4(b). Ledger 2's own configuration.

        Not tautological: the FAILing checks are named, so the assertion is about *which*
        failures produce the status rather than about the status alone -- a FAIL from some
        unrelated check would satisfy a bare ``status is FAIL``.
        """
        from neurostim import CylindricalBandElectrode

        assessment = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            capacitance_uF_cm2=250.0,
        ).assess()

        assert assessment.status is Status.FAIL
        assert {c.name for c in assessment.failed} == {"Charge balance", "Water window"}

    def test_charge_injection_is_not_evaluated_and_the_limit_says_so(self) -> None:
        """T4(c). Every stored CIC was measured biphasic; none validates monophasic.

        Not tautological: the check's *summary* is required to name the measurement
        condition, and ``limits_incomplete`` is asserted alongside -- the flag exists so a
        limit over a knowingly short candidate set cannot be read as a complete one, and a
        status assertion alone would not catch the flag being forgotten.
        """
        for key in ("Pt", "Ta2O5", "SIROF"):
            calc = SafetyCalculator(
                DiscElectrode(40.0, key),
                StimProtocol(80.0, 200.0, 130.0, 1.0, waveform="monophasic"),
            )
            assessment = calc.assess()
            check = next(
                c for c in assessment.checks if c.name == "Charge injection limit"
            )
            assert check.status is Status.NOT_EVALUATED, key
            assert "biphasic" in check.summary, key
            assert check.ceiling_uA == math.inf, key
            assert "Charge injection limit" in [
                c.name for c in assessment.not_evaluated
            ], key
            assert assessment.limits_incomplete is True, key
            assert "Charge injection limit" in assessment.limits_incomplete_note(), key

    def test_the_cap_closes_the_material_with_no_window_on_record(self) -> None:
        """T4(c)'s Ta2O5 half, and the only population the cap has to carry.

        Ta2O5 is the one shipped material with no water window in the database, so there
        is no drift ceiling for it and the NOT_EVALUATED has nothing to replace the
        candidate it removes. Equality -- not strict inequality -- is the correct answer:
        the cap says a worse waveform cannot earn a *higher* limit, not that it must earn
        a lower one.

        Not tautological: the biphasic ceiling is a separate assessment's answer, and the
        absence of a water window is read from the material database rather than assumed.
        """
        from neurostim import get_material

        assert get_material("Ta2O5").water_window is None

        capped = [
            (d, w)
            for d in self.DIAMETERS_UM
            for w in self.PULSE_WIDTHS_US
            if self._pair("Ta2O5", d, w)[0].monotonicity_capped
        ]
        assert capped, "the cap must bind somewhere on Ta2O5 or it is untested"

        for d, w in capped:
            mono, bi = self._pair("Ta2O5", d, w)
            assert mono.limit_bearing_ceiling_uA == bi.limit_bearing_ceiling_uA, (d, w)
            assert mono.limiting_mechanism == bi.limiting_mechanism, (d, w)
            assert mono.limits_incomplete is True

    def test_the_drift_time_matches_the_integrator_to_one_per_cent(self) -> None:
        """T4(d). The ledger-2 number, against an oracle that shares no code with it.

        Not tautological: ``tests/oracles/drift.drift_time_s`` is a pulse-by-pulse
        accumulation loop that imports no part of ``neurostim`` and evaluates no closed
        form.
        """
        import oracles

        from neurostim import CylindricalBandElectrode

        electrode = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        assessment = SafetyCalculator(
            electrode,
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            capacitance_uF_cm2=250.0,
        ).assess()
        drift = assessment.water_window.drift
        assert drift is not None

        integrated = oracles.drift_time_s(
            current_uA=3000.0,
            pulse_width_us=90.0,
            frequency_hz=130.0,
            area_cm2=electrode.area_cm2,
            capacitance_uF_cm2=250.0,
            window_V=0.6,
        )
        assert drift.time_to_exit_s == pytest.approx(0.2558, rel=1e-2)
        assert integrated == pytest.approx(drift.time_to_exit_s, rel=3e-2)

    def test_a_biphasic_protocol_carries_no_cap(self) -> None:
        """The cap must not cost a biphasic assessment anything, or it recurses.

        Not tautological: the absence of a cap is asserted as ``inf`` and as the flag being
        False, and the biphasic ceiling is separately asserted to equal the plain minimum
        over the seven checks -- so a cap that silently applied itself would be visible.
        """
        assessment = SafetyCalculator(
            DiscElectrode(500.0, "SIROF"), StimProtocol(500.0, 50.0, 130.0, 1.0)
        ).assess()

        assert assessment.biphasic_ceiling_uA == math.inf
        assert assessment.monotonicity_capped is False
        assert assessment.limit_bearing_ceiling_uA == min(
            c.ceiling_uA
            for c in assessment.checks
            if c.name in _limit_bearing_names()
        )

    def test_a_protocol_whose_biphasic_twin_cannot_exist_is_left_uncapped(self) -> None:
        """A return phase that does not fit the period has no biphasic counterpart.

        ``StimProtocol`` rejects a pulse whose active duration exceeds its period, and
        adding a return phase doubles that duration. There is then no biphasic limit to cap
        against, and the honest answer is no cap rather than a fabricated one.

        Not tautological: the counterpart's unconstructibility is asserted directly, by
        building it and catching the package's own ``ValueError``, before the absence of a
        cap is read.
        """
        protocol = StimProtocol(80.0, 400.0, 2000.0, 1.0, waveform="monophasic")
        with pytest.raises(ValueError, match="does not fit in its period"):
            StimProtocol(80.0, 400.0, 2000.0, 1.0)

        assessment = SafetyCalculator(DiscElectrode(500.0, "Pt"), protocol).assess()
        assert assessment.biphasic_ceiling_uA == math.inf
        assert assessment.monotonicity_capped is False


def _limit_bearing_names() -> frozenset[str]:
    """The seven, written out rather than imported.

    The package defines its own set; a test that imported it could not disagree with the
    package about which checks bear a limit, and this module's sweeps use the partition as
    an expected value.
    """
    return frozenset(
        {
            "Shannon criterion",
            "Charge injection limit",
            "Water window",
            "Current density",
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        }
    )


class TestTheTrainDutyCycleReplacesThePulseDuty:
    """T14. Ledger 6 and 67(a): a category error, and the dead branch it produced.

    McCreery et al. (2010) varied a **train** schedule -- one second on, one second off --
    and measured the damage radius shrinking from at least 150 um to about 60 um at
    identical charge per phase. The package compared that against the *intra-pulse*
    current-flowing fraction, which for any pulsed protocol is a few per cent. McCreery's
    own fit protocol, 400 us at 50 Hz for 7 h, therefore reported a duty fold of 25 and
    ``inside = False``: the envelope's inside-PASS branch was unreachable for every pulsed
    protocol in a 300 000-protocol sweep, while a passing test certified it.

    **The pulse-duty excursion is deleted rather than rescaled**, and the reason is
    arithmetic. For a symmetric biphasic pulse ``duty = 2 * PW * f * 1e-6``, so
    ``duty_fold`` is identically ``pw_fold * freq_fold`` -- the product of two excursions
    already reported with their own sourced directions. Verified: 100 us at 200 Hz is 4x
    outside on both real axes and gives a duty fold of exactly 1.000, while 600 us at 75 Hz
    is inside on both and gives 2.250, which would have fabricated a Shannon CAUTION out of
    two parameters the sources do not object to.

    ``train_duty_cycle`` is the quantity McCreery actually varied, and it is wired into the
    three models that claim to consume it rather than read only by the citation string.

    Fixture rule: every duty used here differs from the 1.0 default, and the default's own
    behaviour is pinned separately as an absence.
    """

    FIT_PROTOCOL = (50.0, 400.0, 50.0, 7 * 3600.0)
    """McCreery's own conditions: the protocol the Shannon fit was derived at."""

    def _excursions(self, protocol: StimProtocol, area_cm2: float | None = None):
        from neurostim.safety import envelope

        return envelope.evaluate(protocol, area_cm2)

    def test_the_fit_protocol_is_inside_its_own_envelope(self) -> None:
        """The dead branch, brought back to life (ledger 67(a)).

        Not tautological: the protocol is McCreery's published conditions, written out --
        400 us, 50 Hz, 7 h, on a 0.1 cm^2 electrode inside the 0.01-0.5 cm^2 range of the
        platinum discs the fit was derived from -- so ``inside`` is being asserted for the
        one protocol for which it is true by construction of the source, not by
        construction of the code.
        """
        result = self._excursions(StimProtocol(*self.FIT_PROTOCOL), area_cm2=0.1)

        assert result.inside is True
        assert result.outside == ()
        assert result.supports_unqualified_pass

    def test_no_excursion_compares_the_intra_pulse_duty_against_a_train_schedule(
        self,
    ) -> None:
        """The deletion, pinned as an absence -- a re-referenced excursion fails here.

        Not tautological: the first clause could be satisfied by any repair; only the
        absence assertion distinguishes deleting the excursion from rescaling it, and the
        identity below shows why rescaling is not available. ``duty_fold`` for a symmetric
        biphasic pulse is exactly ``pw_fold * freq_fold``, recomputed here from the
        protocol's own inputs.
        """
        protocol = StimProtocol(100.0, 100.0, 200.0, 1.0)
        result = self._excursions(protocol)

        names = [e.parameter for e in result.excursions]
        assert "duty cycle" not in names
        assert "train duty cycle" in names

        # Two separate faults, and both are why the excursion is deleted rather than
        # repaired. The reference it compared against was 100 % -- a continuous train --
        # where the fit protocol's own intra-pulse duty is 2 * 400 us * 50 Hz = 4 %, which
        # is what made McCreery's own conditions read 25x outside their own envelope.
        fit_duty = 2 * 400e-6 * 50.0
        assert fit_duty == pytest.approx(0.04)
        assert max(1.0 / fit_duty, fit_duty) == pytest.approx(25.0)

        # And against the *right* reference the quantity is redundant: for a symmetric
        # biphasic pulse duty = 2 * PW * f, so the fold is identically pw_fold * f_fold,
        # both of which are already reported above with their own sourced directions.
        pw_fold = 400.0 / 100.0
        freq_fold = 200.0 / 50.0
        duty_fold = protocol.duty_cycle / fit_duty
        assert pw_fold == pytest.approx(4.0)
        assert freq_fold == pytest.approx(4.0)
        assert duty_fold == pytest.approx(1.0, rel=1e-12)
        assert duty_fold == pytest.approx(
            (100.0 / 400.0) * (200.0 / 50.0), rel=1e-12
        )

    def test_the_fabrication_case_produces_no_concerning_excursion(self) -> None:
        """600 us at 75 Hz: inside on both real axes, 2.25x on the deleted one.

        The case v1's repair would have manufactured a Shannon CAUTION from. Both
        parameters are within the 2x tolerance the module applies to every axis, so nothing
        here reduces margin.

        Not tautological: the two folds are computed here from the protocol's inputs
        against the module's published reference conditions, and the assertion is that
        neither crosses the tolerance -- so a reintroduced duty excursion fails on a number
        this test derives rather than on a name.
        """
        protocol = StimProtocol(50.0, 600.0, 75.0, 3600.0)
        result = self._excursions(protocol)

        pulse_width_fold = protocol.pulse_width_us / 400.0
        frequency_fold = protocol.frequency_hz / 50.0
        assert pulse_width_fold == pytest.approx(1.5, rel=1e-12)
        assert frequency_fold == pytest.approx(1.5, rel=1e-12)
        # The fold a reintroduced pulse-duty excursion would report: 1.5 * 1.5 = 2.25,
        # over the 2x tolerance, so it alone would have produced the CAUTION.
        assert pulse_width_fold * frequency_fold == pytest.approx(2.25, rel=1e-12)
        assert protocol.duty_cycle / (2 * 400e-6 * 50.0) == pytest.approx(
            2.25, rel=1e-12
        )
        assert result.concerning == ()
        assert result.supports_unqualified_pass

    def test_the_train_duty_excursion_cites_the_measurement_it_comes_from(self) -> None:
        """McCreery's contrast is 150 um against 60 um; the note must carry both.

        Not tautological: the two radii are the source's own numbers and are asserted to
        appear in the rationale, which is the only thing that distinguishes a sourced
        excursion from an invented one. The direction is asserted separately, because a
        lower train duty is the *safer* direction and must not read as a concern.
        """
        result = self._excursions(
            StimProtocol(50.0, 400.0, 50.0, 3600.0, train_duty_cycle=0.5)
        )
        excursion = next(
            e for e in result.excursions if e.parameter == "train duty cycle"
        )

        assert excursion.value == pytest.approx(50.0)
        assert excursion.reference == pytest.approx(100.0)
        assert excursion.direction == "conservative"
        assert "60" in excursion.rationale and "150" in excursion.rationale
        assert not excursion.concerning

    def test_the_default_train_duty_keeps_the_envelope_reachable(self) -> None:
        """A continuous train is McCreery's own condition, so the fold is exactly 1.

        Not tautological: the assertion is that a *default* protocol produces an excursion
        whose fold is 1.0 and whose direction is ``inside``, which is what keeps
        ``EnvelopeResult.inside`` reachable at all. A default that produced any other fold
        would leave the branch dead in a new way.
        """
        result = self._excursions(StimProtocol(*self.FIT_PROTOCOL))
        excursion = next(
            e for e in result.excursions if e.parameter == "train duty cycle"
        )

        assert excursion.value == pytest.approx(100.0)
        assert excursion.fold == pytest.approx(1.0)
        assert excursion.direction == "inside"
        assert not excursion.outside

    def test_the_train_duty_is_wired_into_the_models_that_claim_to_consume_it(
        self,
    ) -> None:
        """Physics M7: a field only the citation string reads is a new silent failure.

        ``StimProtocol``'s own docstring says duty cycle "governs average power
        dissipation, which is what the thermal model integrates". Three quantities feed
        that, and each scales differently: the pulse count linearly, the mean current
        linearly, and the RMS current as the square root, because heating goes as the
        square of the current and the off time contributes none.

        Not tautological: every expected value is the same quantity read from the
        ``train_duty_cycle = 1.0`` protocol and scaled by the factor written here, so the
        assertion is about the *scaling law* rather than about any absolute number the
        package computes.
        """
        full = StimProtocol(80.0, 200.0, 130.0, 10.0)
        half = StimProtocol(80.0, 200.0, 130.0, 10.0, train_duty_cycle=0.5)

        assert half.n_pulses == pytest.approx(0.5 * full.n_pulses, rel=1e-12)
        assert half.average_current_uA == pytest.approx(
            0.5 * full.average_current_uA, rel=1e-12
        )
        assert half.rms_current_uA == pytest.approx(
            full.rms_current_uA / math.sqrt(2.0), rel=1e-12
        )
        assert half.total_charge_per_train_uC == pytest.approx(
            0.5 * full.total_charge_per_train_uC, rel=1e-12
        )

    def test_a_train_duty_outside_its_domain_is_rejected(self) -> None:
        """A fraction of time is in (0, 1]; zero would be no stimulation at all.

        Not tautological: the assertion is on the exception type and on the parameter name
        in the message, which no arithmetic supplies.
        """
        for bad in (0.0, -0.1, 1.5, float("nan"), float("inf")):
            with pytest.raises(ValueError, match="train_duty_cycle"):
                StimProtocol(80.0, 200.0, 130.0, 1.0, train_duty_cycle=bad)

    def test_the_intra_pulse_duty_is_still_reported_and_unchanged(self) -> None:
        """Section 6: ``report()["duty_cycle"]`` does not move (0.052).

        The intra-pulse duty is a real quantity -- the fraction of time current flows --
        and it is still what the protocol summary and the PDF print. What changed is only
        that no source is asked a question it cannot answer about it.

        Not tautological: 0.052 is ``2 * 200 us * 130 Hz`` written out, and it is asserted
        against both the protocol property and the batch dict, which are different code
        paths.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, train_duty_cycle=0.5),
        )
        expected_duty = 2 * calc.p.pulse_width_us * 1e-6 * calc.p.frequency_hz
        assert expected_duty == pytest.approx(0.052, rel=1e-12)
        assert calc.p.duty_cycle == pytest.approx(0.052, rel=1e-12)
        assert calc.report()["duty_cycle"] == pytest.approx(0.052, rel=1e-12)

    def test_the_new_field_reaches_the_serialised_protocol(self) -> None:
        """Section 6 books the protocol block growing; this is the second of its two keys.

        Not tautological: the assertion is against a JSON document and a dataclass dict,
        and the expected value is the constructor argument, which neither derives.
        """
        import json

        from neurostim.io.tabular import protocol_from_dict, report_to_json

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, train_duty_cycle=0.25),
        )
        assert asdict(calc.p)["train_duty_cycle"] == 0.25
        payload = json.loads(report_to_json(calc))
        assert payload["protocol"]["train_duty_cycle"] == 0.25
        assert set(payload["protocol"]) == {
            "current_uA",
            "pulse_width_us",
            "frequency_hz",
            "train_duration_s",
            "waveform",
            "interphase_gap_us",
            "anodic_first",
            "return_phase_ratio",
            "charge_recovery_ratio",
            "train_duty_cycle",
        }
        assert protocol_from_dict(
            {
                "current_uA": 80.0,
                "pulse_width_us": 200.0,
                "frequency_hz": 130.0,
                "train_duration_s": 1.0,
                "train_duty_cycle": 0.25,
            }
        ).train_duty_cycle == 0.25


class TestTheRefusalContractHoldsInBothDirections:
    """The equivalence the type now promises, asserted as an equivalence.

    ``limiting_current_uA`` is ``None`` **if and only if** either a check in
    :data:`NO_SAFE_AMPLITUDE` FAILs, or no positive amplitude clears every limit-bearing
    check. A one-directional test would let the attribute refuse too often and still pass,
    which is the mirror image of ledger 99 and just as wrong: a refusal where a limit
    exists hides a usable number behind a sentence.

    The sweep spans the shapes that reach each branch and the ordinary ones that reach
    neither -- balanced and unbalanced, biphasic and monophasic, finite and continuous
    trains, a resting potential on the window edge and one in the middle of it.
    """

    def _sweep(self):
        """Every configuration and a short label, built once."""
        cases = []
        for material in ("Pt", "SIROF", "Ta2O5"):
            for diameter_um in (100.0, 500.0, 2000.0):
                electrode = DiscElectrode(diameter_um, material)
                base = (80.0, 200.0, 130.0, 1.0)
                cases += [
                    (f"{material}/{diameter_um:g}/balanced", electrode, StimProtocol(*base), {}),
                    (
                        f"{material}/{diameter_um:g}/monophasic",
                        electrode,
                        StimProtocol(*base, waveform="monophasic"),
                        {},
                    ),
                    (
                        f"{material}/{diameter_um:g}/partial-recovery",
                        electrode,
                        StimProtocol(*base, charge_recovery_ratio=0.9),
                        {},
                    ),
                    (
                        f"{material}/{diameter_um:g}/continuous-unbalanced",
                        electrode,
                        StimProtocol(
                            80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=0.9
                        ),
                        {},
                    ),
                ]
        # A resting potential exactly on the window edge, and one comfortably inside it.
        disc = DiscElectrode(100.0, "Pt")
        cases += [
            ("Pt/edge-resting", disc, StimProtocol(80.0, 200.0, 130.0, 1.0),
             {"resting_potential_V": -0.6}),
            ("Pt/mid-resting", disc, StimProtocol(80.0, 200.0, 130.0, 1.0),
             {"resting_potential_V": -0.2}),
        ]
        # Ledger 140: an uncapped train offset makes the compliance ceiling zero on its own
        # -- the counter, whose window is not assessed, and Ta2O5, which has none -- beside
        # a capped one that leaves a positive ceiling.
        continuous = StimProtocol(80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=0.9)
        counter = {"counter_electrode": DiscElectrode(900.0, "Pt"),
                   "counter_separation_um": 20000.0}
        cases += [
            ("Ta2O5/continuous-unbalanced/compliance", DiscElectrode(500.0, "Ta2O5"),
             continuous, {"compliance_V": 10.0}),
            ("Pt/continuous-unbalanced/counter/compliance", DiscElectrode(500.0, "Pt"),
             continuous, {"compliance_V": 10.0, **counter}),
            ("Pt/partial-recovery/counter/compliance", DiscElectrode(500.0, "Pt"),
             StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9),
             {"compliance_V": 10.0, **counter}),
            ("Pt/partial-recovery/compliance", DiscElectrode(500.0, "Pt"),
             StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9),
             {"compliance_V": 10.0}),
        ]
        return cases

    def test_none_exactly_when_no_amplitude_is_safe(self) -> None:
        """Both directions, over the sweep.

        Not tautological: the right-hand side is built from the *checks* -- a FAIL whose
        name is in the named set, and a ceiling that admits no positive amplitude -- while
        the left-hand side is the attribute. The attribute could satisfy either half alone
        and fail the equivalence; it is the ``==`` between two independently formed
        booleans that carries the contract, and ``limit_bearing_ceiling_uA`` is asserted to
        be unchanged either way so the refusal cannot be implemented by hiding the number.
        """
        from neurostim.safety.assessment import NO_SAFE_AMPLITUDE

        for label, electrode, protocol, settings in self._sweep():
            assessment = SafetyCalculator(electrode, protocol, **settings).assess()

            waveform_fails = any(
                c.status is Status.FAIL and c.name in NO_SAFE_AMPLITUDE
                for c in assessment.checks
            )
            no_positive_amplitude = assessment.limit_bearing_ceiling_uA <= 0.0
            expected_none = waveform_fails or no_positive_amplitude

            assert (assessment.limiting_current_uA is None) is expected_none, label
            assert math.isfinite(assessment.limit_bearing_ceiling_uA) or math.isinf(
                assessment.limit_bearing_ceiling_uA
            ), label
            if expected_none:
                assert assessment.no_safe_amplitude_note() != "", label
            else:
                assert assessment.no_safe_amplitude_note() == "", label
                assert assessment.limiting_current_uA == (
                    assessment.limit_bearing_ceiling_uA
                ), label

    def test_the_reported_limit_is_always_an_amplitude_a_protocol_can_carry(
        self,
    ) -> None:
        """The invariant that makes the zero question dissolve rather than need an answer.

        ``StimProtocol`` accepts exactly the amplitudes strictly above zero. After this
        phase, ``limiting_current_uA`` is either ``None`` or one of those -- so its domain
        is the constructor's domain, and no render site can ever be handed a value a user
        cannot programme. That is why ``format_limit(0.0)`` is left alone: the question of
        whether it should print ``'0'`` or ``'0.000'`` cannot arise on a limit.

        Not tautological: the positivity is checked by *constructing a protocol at the
        reported limit*, which is the package's own domain test and not a comparison this
        test invents.
        """
        from dataclasses import replace

        for label, electrode, protocol, settings in self._sweep():
            limit = SafetyCalculator(
                electrode, protocol, **settings
            ).assess().limiting_current_uA
            if limit is None:
                continue
            assert limit > 0.0, label
            # Constructible: the package's own domain test for an amplitude.
            replace(protocol, current_uA=limit)

    def test_format_limit_still_renders_zero_as_a_bare_zero(self) -> None:
        """Left unchanged deliberately, and this records why that is safe.

        ``format_limit(0.0)`` returns ``'0'``, not the ``'0.000'`` its four-significant-digit
        promise would suggest. It is not repaired because no limit render can reach it: a
        non-positive limit-bearing ceiling is refused by name before any formatting
        happens. If a future change lets a zero through to a render site, the test above
        fails first and names the configuration.

        Not tautological: the two assertions are about different functions -- the
        formatter's own output, and the refusal that keeps it from being called -- and the
        second is what makes the first acceptable.
        """
        from neurostim.safety._limits import format_limit

        assert format_limit(0.0) == "0"
        assert format_limit(20.0) == "20.00"

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            resting_potential_V=-0.6,
        )
        assessment = calc.assess()
        assert assessment.limit_bearing_ceiling_uA == 0.0
        assert assessment.limiting_current_uA is None

        # Scoped to the render site itself: "0 uA" also occurs inside "80 uA" in the
        # protocol echo, and an assertion that matched that would pass for the wrong
        # reason.
        headline = next(
            line
            for line in assessment.describe().splitlines()
            if line.startswith("Limiting current:")
        )
        assert headline.startswith("Limiting current: none --")
        assert "Water window" in headline

    def test_the_independent_bisection_agrees_that_no_amplitude_clears_the_checks(
        self,
    ) -> None:
        """The right-hand side of the equivalence, from an oracle instead of a ceiling.

        The sweep above reads ``limit_bearing_ceiling_uA``, which is the package's own
        minimum. This asks the same question by binary search over ``assess().failed``,
        reading one bit per probe and no ceiling, margin or limit at all -- and it carries a
        witness, the name of the check that FAILs at every one of the 73 ladder probes.

        Not tautological: ``tests/oracles/fail_ceiling`` writes out its own
        ``LIMIT_BEARING`` rather than importing the package's, so the two partitions are
        independent statements; and 0.0 from that search means "no probe anywhere in an
        eighteen-decade bracket passes", which no expression in the package produces.
        """
        import oracles

        for label, settings in (
            ("edge resting potential", {"resting_potential_V": -0.6}),
        ):
            calc = SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80.0, 200.0, 130.0, 1.0),
                **settings,
            )
            assert oracles.fail_ceiling_uA(calc, names=oracles.LIMIT_BEARING) == 0.0, label
            assert oracles.amplitude_independent_failures(
                calc, names=oracles.LIMIT_BEARING
            ) == ("Water window",), label
            assert calc.assess().limiting_current_uA is None, label
            assert "Water window" in calc.assess().no_safe_amplitude_note(), label

        continuous = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=0.9),
        )
        assert oracles.fail_ceiling_uA(continuous, names=oracles.LIMIT_BEARING) == 0.0
        assert oracles.amplitude_independent_failures(
            continuous, names=oracles.LIMIT_BEARING
        ) == ("Water window",)
        assert continuous.assess().limiting_current_uA is None

        # Ledger 140: with no water window the drift clause cannot refuse, and the uncapped
        # train offset in the compliance budget is what admits no amplitude.
        no_window = SafetyCalculator(
            DiscElectrode(500.0, "Ta2O5"),
            StimProtocol(80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=0.9),
            compliance_V=10.0,
        )
        assert oracles.fail_ceiling_uA(no_window, names=oracles.LIMIT_BEARING) == 0.0
        assert oracles.amplitude_independent_failures(
            no_window, names=oracles.LIMIT_BEARING
        ) == ("Compliance voltage",)
        assert no_window.assess().limiting_current_uA is None
        assert "Compliance voltage" in no_window.assess().no_safe_amplitude_note()


class TestAnOverRecoveryDriftChargesTheOppositeBranch:
    """Ledger 141. An over-recovering waveform drifts toward the edge opposite the leading
    phase, so its offset is stored on the opposite polarity's branch, whose C_eff differs
    for most materials (Pt: 125 anodic against 250 cathodic). The drift clause budgeted it
    at the leading one, so for a cathodic-first Pt pulse the time to the edge was twice the
    model's. A measured capacitance is one value and is unchanged.
    """

    @staticmethod
    def _oracle_time(calc, *, branched=True):
        import oracles

        from neurostim.materials import get_material
        from neurostim.safety.water_window import effective_capacitance_uF_cm2

        p = calc.p
        material = get_material(calc.e.material)
        window = material.water_window
        rest = calc.resting_potential_V
        cathodic, anodic = rest - window.cathodic_V, window.anodic_V - rest
        lead, opposite = (anodic, cathodic) if p.anodic_first else (cathodic, anodic)
        return oracles.partial_recovery_exit_time_s(
            current_uA=p.current_uA,
            pulse_width_us=p.pulse_width_us,
            recovered_fraction=p.charge_recovery_ratio,
            frequency_hz=p.frequency_hz,
            area_cm2=calc.e.area_cm2,
            capacitance_uF_cm2=effective_capacitance_uF_cm2(material, anodic_first=p.anodic_first),
            leading_window_V=lead,
            opposite_window_V=opposite,
            opposite_capacitance_uF_cm2=(
                effective_capacitance_uF_cm2(material, anodic_first=not p.anodic_first)
                if branched else None
            ),
        )

    def _population(self):
        for material, anodic_first, recovery, current, rest in itertools.product(
            ("Pt", "TiN", "SIROF"), (False, True), (1.05, 1.2, 1.5),
            (50.0, 300.0, 1000.0), (0.0, -0.2),
        ):
            yield SafetyCalculator(
                DiscElectrode(500.0, material),
                StimProtocol(
                    current, 200.0, 50.0, 1e4, anodic_first=anodic_first,
                    charge_recovery_ratio=recovery,
                ),
                resting_potential_V=rest,
            )

    def test_the_drift_time_is_the_branched_circuits_to_one_pulse(self) -> None:
        """Pt cathodic- and anodic-first, TiN (equal branches) and SIROF (the opposite
        branch larger when cathodic-first). Not tautological: the oracle follows the charge
        through both phases of every pulse and converts it with whichever branch holds it."""
        compared = 0
        for calc in self._population():
            assessment = calc.assess()
            drift = assessment.water_window.drift
            if not assessment.water_window.passes:  # the peak clause, not the drift
                continue
            exit_s = self._oracle_time(calc)
            one_pulse = (1.0 / calc.p.frequency_hz) * (1.0 + 1e-9)
            assert abs(drift.time_to_exit_s - exit_s) <= one_pulse, (
                calc.p, calc.e.material, drift.time_to_exit_s, exit_s,
            )
            compared += 1
        assert compared >= 100, compared

    def test_the_reviewers_case_is_half_as_long(self) -> None:
        """The ledger's measurement: Pt 500 um, cathodic-first, r_a = 1.3, 300 uA. The anodic
        branch holds 0.1963495408493621 uC to the 0.8 V edge, not 0.3926990816987242."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(300.0, 200.0, 130.0, 1.0, charge_recovery_ratio=1.3),
        )
        drift = calc.assess().water_window.drift
        assert drift.window_headroom_V == 0.8
        assert drift.window_charge_uC == pytest.approx(0.1963495408493621, rel=1e-15)
        assert drift.time_to_exit_s == pytest.approx(0.16782012038407015 / 2.0, rel=1e-12)

    def test_a_measured_capacitance_is_one_value(self) -> None:
        """The override is unchanged: one measurement, not split by polarity."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(300.0, 200.0, 130.0, 1.0, charge_recovery_ratio=1.3),
            capacitance_uF_cm2=250.0,
        )
        drift = calc.assess().water_window.drift
        assert drift.window_charge_uC == pytest.approx(0.8 * 250.0 * calc.e.area_cm2, rel=1e-15)

    def test_a_capped_compliance_offset_means_the_window_fails(self) -> None:
        """Ledger 140's cap stated that an offset reaching the headroom has made Water
        window FAIL. Over-recovery broke it for every material whose opposite branch is the
        smaller; it now holds in both directions. The sweep spans the materials, both
        polarities, under- and over-recovery, trains and resting potentials."""
        import math

        capped = 0
        for material, anodic_first, recovery, current, train, rest in itertools.product(
            ("Pt", "PtIr", "AIROF", "SIROF", "TIROF", "TiN", "PEDOT", "SS316LVM"),
            (False, True), (0.8, 0.95, 1.05, 1.3, 1.5), (20.0, 300.0),
            (0.05, 1.0, math.inf), (0.0, -0.2),
        ):
            assessment = SafetyCalculator(
                DiscElectrode(100.0, material),
                StimProtocol(
                    current, 200.0, 130.0, train, anodic_first=anodic_first,
                    charge_recovery_ratio=recovery,
                ),
                compliance_V=10.0, resting_potential_V=rest,
            ).assess()
            result = assessment.compliance
            if not (math.isfinite(result.offset_cap_V) and result.offset_V == result.offset_cap_V):
                continue
            window = next(c for c in assessment.checks if c.name == "Water window")
            assert window.status is Status.FAIL, (material, anodic_first, recovery, current, train)
            capped += 1
        assert capped >= 300, capped


class TestTheUnrecoveredChargeIsExactlyLinear:
    """Ledger 103, 104 and 112 (Phase 2 review F1, F2, F10): one expression for the residue.

    The unrecovered charge was ``charge_uC(I, W) - charge_uC(I * r_a / r, W * r)``: two
    products in different associations, subtracted. For a *balanced* asymmetric pulse that
    left a few ulps of residue, which the drift clause read as DC. It crashed ``assess()``
    with a ``ZeroDivisionError``, FAILed Water window beside a Charge balance PASS, and
    reported a limit above amplitudes that FAIL. For a partial recovery the residue's noise
    made the drift clause flicker across consecutive floats, so ``floor_to_pass`` raised.
    It is now ``charge_uC(I, W) * (1 - r_a)``: exactly zero at ``r_a = 1``, and exactly
    monotone in ``I``.
    """

    @staticmethod
    def _balanced_asymmetric():
        """The reviewer's residual-net population. Every protocol here is balanced."""
        amplitudes = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0, 20.0, 33.0, 100.0, 393.0,
                      1000.0, 2222.0)
        for ratio, width, current, train in itertools.product(
            (0.3, 0.7, 3.0), (50.0, 90.0, 200.0), amplitudes, (1.0, 3600.0, math.inf)
        ):
            if width * (1.0 + ratio) >= 1e6 / 50.0:
                continue
            yield SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(current, width, 50.0, train, return_phase_ratio=ratio),
            )

    def test_a_balanced_pulse_leaves_exactly_nothing_behind(self) -> None:
        """Not tautological: the expected residue is the literal 0.0, and the premise --
        these are the ratios whose subtraction left a residue -- is the reviewer's measured
        population, not a property of the new expression."""
        count = 0
        for calc in self._balanced_asymmetric():
            p = calc.p
            assert p.net_charge_per_pulse_uC == 0.0, (p.current_uA, p.return_phase_ratio)
            assert p.net_dc_current_uA == 0.0
            assert p.is_charge_balanced
            count += 1
        assert count == 3 * 3 * 14 * 3

    def test_a_balanced_pulse_never_drifts_or_crashes(self) -> None:
        """No ZeroDivisionError, and no Water window FAIL that Charge balance contradicts.

        Not tautological: before the fix 140 finite-train cases of this shape raised and
        74 infinite-train cases FAILed on drift beside a Charge balance PASS.
        """
        for calc in self._balanced_asymmetric():
            assessment = calc.assess()
            window = next(c for c in assessment.checks if c.name == "Water window")
            balance = next(c for c in assessment.checks if c.name == "Charge balance")
            drift = assessment.water_window.drift
            assert drift is None or not drift.drifts, (calc.p, drift)
            assert "net DC" not in window.summary, window.summary
            assert balance.status is Status.PASS

    def test_the_reported_limit_is_the_independent_bisection_of_the_failing_set(self) -> None:
        """The D3 contract on the reviewer's own cases: no reported limit sits above an
        amplitude that FAILs.

        Not tautological: the expected value is ``oracles.fail_ceiling_uA``, a bisection over
        ``assess().failed`` that reads one bit per probe and raises
        ``NonMonotonePredicate`` on the flicker this fix removes.
        """
        import oracles

        for current, train in ((5.0, math.inf), (7.0, math.inf), (7.0, 3600.0), (7.0, 1.0)):
            calc = SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(current, 90.0, 50.0, train, return_phase_ratio=0.3),
            )
            assessment = calc.assess()
            expected = oracles.fail_ceiling_uA(calc, names=oracles.LIMIT_BEARING)
            assert assessment.limit_bearing_ceiling_uA == pytest.approx(expected, rel=1e-9)
            assert not assessment.failed, [c.name for c in assessment.failed]

    @staticmethod
    def _partial_recovery():
        """The r_a population the review asked for, over ordinary geometries."""
        from neurostim.materials import MATERIALS

        for material, diameter, width, recovery, train, current in itertools.product(
            sorted(MATERIALS),
            (40.0, 100.0, 500.0, 2000.0),
            (50.0, 200.0),
            (0.9, 0.95, 0.99, 0.999, 1.0 - 1e-6),
            (1.0, 60.0, 3600.0),
            (10.0, 500.0),
        ):
            yield SafetyCalculator(
                DiscElectrode(diameter, material),
                StimProtocol(current, width, 130.0, train, charge_recovery_ratio=recovery),
            )

    def test_partial_recovery_assesses_everywhere(self) -> None:
        """Zero raises over 2160 partial-recovery protocols, each water-window ceiling on
        its own boundary.

        Not tautological: before the fix ``DiscElectrode(500, "Pt")`` at 10 uA, 50 us,
        130 Hz, 1 s, r_a = 0.99 raised ``LimitDidNotSettle``, and so did 576 of the
        reviewer's 16 200. The boundary is checked by rebuilding the protocol at the ceiling
        and at the next float up, which is IEEE's definition and not the package's.
        """
        from oracles.fail_ceiling import rebuild_at

        count = 0
        for calc in self._partial_recovery():
            assessment = calc.assess()
            window = next(c for c in assessment.checks if c.name == "Water window")
            ceiling = window.ceiling_uA
            if 0.0 < ceiling < math.inf and window.status is not Status.NOT_EVALUATED:
                at = rebuild_at(calc, ceiling).assess()
                above = rebuild_at(calc, math.nextafter(ceiling, math.inf)).assess()
                assert "Water window" not in {c.name for c in at.failed}, calc.p
                assert "Water window" in {c.name for c in above.failed}, calc.p
            count += 1
        assert count == 9 * 4 * 2 * 5 * 3 * 2

    def test_partial_recovery_agrees_with_the_independent_bisection(self) -> None:
        """A sample of the population above against ``fail_ceiling_uA``.

        Not tautological: see the balanced-pulse bisection test; the sample is every
        fiftieth protocol, so each recovery ratio, train and size is represented.
        """
        import oracles

        for calc in list(self._partial_recovery())[::50]:
            expected = oracles.fail_ceiling_uA(calc, names=oracles.LIMIT_BEARING)
            assert calc.assess().limit_bearing_ceiling_uA == pytest.approx(
                expected, rel=1e-9
            ), calc.p

    def test_the_balance_verdict_does_not_move_with_amplitude_at_its_tolerance(self) -> None:
        """Ledger 112 (F10): within ~1e-12 of full recovery the verdict used to flip with
        amplitude, because a rounded difference was compared against a tolerance scaled by
        the charge.

        Not tautological: the premise, a recovery ratio at the tolerance edge, is written
        out, and the assertion is that one verdict holds across eighteen decades.
        """
        for recovery in (1.0 - 2e-12, 1.0 - 1e-12, 1.0 - 5e-13, 1.0 + 5e-13, 1.0 + 1e-12):
            for ratio in (0.3, 1.0, 3.0):
                verdicts = {
                    StimProtocol(
                        10.0**e, 50.0, 50.0, 1.0,
                        return_phase_ratio=ratio, charge_recovery_ratio=recovery,
                    ).is_charge_balanced
                    for e in range(-12, 7)
                }
                assert len(verdicts) == 1, (recovery, ratio, verdicts)

    def test_drift_and_charge_balance_read_the_same_test(self) -> None:
        """A recovery inside the balance tolerance is balanced for both checks.

        Not tautological: at ``r_a = 1 - 5e-13`` the residue is a real non-zero product, so
        only the shared gate keeps the drift clause from reading it as DC while Charge
        balance prints PASS -- the disagreement ledger 103 records.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=1.0 - 5e-13),
        )
        assert calc.p.net_charge_per_pulse_uC != 0.0  # the premise
        assessment = calc.assess()
        balance = next(c for c in assessment.checks if c.name == "Charge balance")
        assert balance.status is Status.PASS
        assert not assessment.water_window.drift.drifts
        assert assessment.limiting_current_uA is not None

    def test_the_seed_refuses_a_drift_it_cannot_invert(self) -> None:
        """The nan route: a drifting result whose protocol carries no DC per microamp.

        ``min([peak, nan])`` returned the peak term silently. A drift the seed cannot
        invert is now an error naming the check, not a number.

        Not tautological: the drift and the protocol are made to disagree on purpose here,
        which no assessment produces after this fix; the assertion is that the seed does not
        answer.
        """
        from dataclasses import replace

        from neurostim.safety import assessment as assessment_mod

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9),
        )
        result = calc.assess().water_window
        balanced = replace(calc.p, charge_recovery_ratio=1.0)
        with pytest.raises(ArithmeticError, match="Water window"):
            assessment_mod._water_window_seed_uA(result, balanced, calc.e.area_cm2)


class TestTheDriftBudgetCarriesThePulseRidingOnIt:
    """Ledger 105 (Phase 2 review F3) and the drift half of 110 (F8).

    Under the package's own capacitive model the leading phase of pulse ``n`` peaks at
    ``rest + offset + excursion``, so the interface leaves the window when the offset has
    used up the headroom *minus* what the pulse itself adds. The drift clause spent the
    whole headroom on the offset. For monophasic delivery the two agree, because each pulse
    is all offset, and the only drift oracle was monophasic. For a partial recovery the
    clause was anti-conservative: CAUTION "after the 1 s train" for an interface the
    model's own physics takes out of the window at 0.42 s.
    """

    PT_CATHODIC_V = 0.6
    PT_ANODIC_V = 0.8

    @staticmethod
    def _oracle_time(calc):
        import oracles

        p = calc.p
        lead, opposite = (
            (0.8, 0.6) if p.anodic_first else (0.6, 0.8)
        )
        return oracles.partial_recovery_exit_time_s(
            current_uA=p.current_uA,
            pulse_width_us=p.pulse_width_us,
            recovered_fraction=0.0 if p.waveform == "monophasic" else p.charge_recovery_ratio,
            frequency_hz=p.frequency_hz,
            area_cm2=calc.e.area_cm2,
            capacitance_uF_cm2=250.0,
            leading_window_V=lead,
            opposite_window_V=opposite,
        )

    def test_the_reviewers_case_fails_inside_the_train(self) -> None:
        """Not tautological: the expected exit, pulse 22 at 50 Hz (0.44 s, inside the 1 s
        train), comes from the pulse-by-pulse oracle, which follows both phases of every
        pulse on the same capacitor and evaluates no closed form."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(1227.184630308513, 200.0, 50.0, 1.0, charge_recovery_ratio=0.99),
            capacitance_uF_cm2=250.0,
        )
        exit_s = self._oracle_time(calc)
        assert exit_s == pytest.approx(0.44)
        assessment = calc.assess()
        window = next(c for c in assessment.checks if c.name == "Water window")
        assert window.status is Status.FAIL, window.summary
        # One pulse, with a float of slack: 0.42 s against the oracle's pulse-22 0.44 s.
        assert abs(assessment.water_window.drift.time_to_exit_s - exit_s) <= (1.0 / 50.0) * (
            1.0 + 1e-9
        )
        assert window.ceiling_uA < 1227.184630308513

    def _population(self, train_duration_s: float = 1e4):
        for recovery, current, anodic_first, width in itertools.product(
            (0.0, 0.5, 0.9, 0.99, 1.2, 1.5),
            (50.0, 300.0, 1000.0, 1300.0),
            (False, True),
            (100.0, 200.0),
        ):
            yield SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(
                    current, width, 50.0, train_duration_s,
                    anodic_first=anodic_first, charge_recovery_ratio=recovery,
                ),
                capacitance_uF_cm2=250.0,
            )

    def test_the_drift_time_agrees_with_the_oracle_to_one_pulse_for_every_recovery(self) -> None:
        """Under-recovery, zero recovery and over-recovery, in both polarities.

        Not tautological: see the reviewer's-case test. Over-recovery drifts toward the
        opposite edge, where the leading phase moves *away*; the oracle checks that edge
        after each return phase, so a closed form that rode the wrong excursion on the
        offset, or headed for the wrong edge, disagrees by more than one pulse.
        """
        compared = 0
        for calc in self._population():
            assessment = calc.assess()
            drift = assessment.water_window.drift
            if not assessment.water_window.passes or not drift.drifts:
                continue
            exit_s = self._oracle_time(calc)
            one_pulse = (1.0 / calc.p.frequency_hz) * (1.0 + 1e-9)
            assert abs(drift.time_to_exit_s - exit_s) <= one_pulse, (
                calc.p, drift.time_to_exit_s, exit_s,
            )
            compared += 1
        assert compared >= 60, compared

    def test_the_ceiling_does_not_exit_before_the_train_ends(self) -> None:
        """At the reported water-window ceiling the oracle keeps the interface inside the
        window for the whole train, to within one pulse.

        Not tautological: the ceiling is the package's; the exit time at it is the oracle's.
        """
        from oracles.fail_ceiling import rebuild_at

        checked = 0
        for calc in self._population(train_duration_s=1.0):
            window = next(c for c in calc.assess().checks if c.name == "Water window")
            if calc.p.is_charge_balanced or not 0.0 < window.ceiling_uA < math.inf:
                continue
            at = rebuild_at(calc, window.ceiling_uA)
            assert self._oracle_time(at) >= 1.0 - 1.0 / 50.0, (calc.p, window.ceiling_uA)
            checked += 1
        assert checked >= 60, checked

    def test_exits_during_train_is_strict_at_its_boundary(self) -> None:
        """F8's surviving mutant, ``<`` -> ``<=``: a train that ends exactly as the edge is
        reached is not a failure; one a float longer is.

        Not tautological: the drift is built from literals, so the time to the edge is
        exactly 1.0 s by IEEE arithmetic.
        """
        from neurostim.safety.water_window import DcDrift

        at_edge = DcDrift(
            net_dc_current_uA=2.0, window_headroom_V=0.5, window_charge_uC=2.0,
            train_duration_s=1.0,
        )
        assert at_edge.time_to_exit_s == 1.0
        assert not at_edge.exits_during_train
        longer = DcDrift(
            net_dc_current_uA=2.0, window_headroom_V=0.5, window_charge_uC=2.0,
            train_duration_s=math.nextafter(1.0, math.inf),
        )
        assert longer.exits_during_train

    def test_over_recovery_heads_for_the_opposite_edge(self) -> None:
        """F8's other survivor: ignoring the net's sign. A cathodic-first pulse whose return
        phase recovers 120 % leaves an anodic offset, so the budget is the 0.8 V to Pt's
        anodic edge, and no leading excursion rides on it.

        Not tautological: 0.8 V is Pt's published anodic limit at a resting potential of 0,
        and the direction is the sign of ``1 - 1.2``.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(300.0, 200.0, 50.0, 1.0, charge_recovery_ratio=1.2),
            capacitance_uF_cm2=250.0,
        )
        drift = calc.assess().water_window.drift
        assert drift.net_dc_current_uA < 0.0
        assert drift.window_headroom_V == pytest.approx(self.PT_ANODIC_V, rel=1e-15)
        assert drift.window_charge_uC == pytest.approx(0.8 * 250.0 * calc.e.area_cm2)
        assert drift.time_to_exit_s == pytest.approx(
            drift.window_charge_uC / abs(drift.net_dc_current_uA), rel=1e-15
        )



class TestTheWaterWindowDetailAgreesWithItsVerdict:
    """Ledger 108 (Phase 2 review F6). A FAIL whose detail line said "-> PASS".

    ``WaterWindowResult.describe()`` took its verdict from the peak alone. So on ledger 2's
    own case the check FAILed on drift while its detail, in ``describe()`` and in the PDF,
    printed "-> PASS" above "headroom +0.582 V". That is the text ledger 2 complained
    about, now sitting under the FAIL.
    """

    @staticmethod
    def _band_calc(**protocol_kw):
        from neurostim import CylindricalBandElectrode

        return SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, **protocol_kw),
            capacitance_uF_cm2=250.0,
        )

    def test_a_drift_fail_does_not_print_pass(self) -> None:
        """Not tautological: the premise, a FAIL whose peak is inside the window, is
        asserted from the assessment first; then the detail text is searched."""
        assessment = self._band_calc(waveform="monophasic").assess()
        check = next(c for c in assessment.checks if c.name == "Water window")
        assert check.status is Status.FAIL
        assert assessment.water_window.passes  # the peak alone is inside

        header = check.detail.splitlines()[0]
        assert "-> PASS" not in check.detail, header
        assert "EXCEEDS" in header, header
        assert "drift" in header, header
        # The headroom that remains is the peak's, and says so.
        assert "peak headroom" in check.detail
        assert "\n  headroom " not in check.detail

    def test_a_drift_caution_says_the_drift_lands_after_the_train(self) -> None:
        """A drift that reaches the edge after the train is not an exceedance, and the
        header must not call the check clean either."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(10.0, 50.0, 130.0, 1.0, charge_recovery_ratio=0.99),
        )
        assessment = calc.assess()
        check = next(c for c in assessment.checks if c.name == "Water window")
        assert check.status is Status.CAUTION, check.summary
        header = check.detail.splitlines()[0]
        assert "EXCEEDS" not in header, header
        assert "after the train" in header, header

    def test_a_balanced_protocol_is_unchanged(self) -> None:
        """No drift, no change: the header is exactly what it was."""
        assessment = self._band_calc().assess()
        header = next(
            c for c in assessment.checks if c.name == "Water window"
        ).detail.splitlines()[0]
        assert header == "Water window (PtIr, cathodic phase) -> PASS"
        assert "\n  headroom      +" in assessment.water_window.describe()
