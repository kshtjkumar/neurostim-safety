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
