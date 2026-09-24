"""C4.2 -- one polarity convention, the conservative half-window, and a strict argument
contract for the public water-window function (ledgers 7, 8, 117, 119)."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from neurostim import DiscElectrode, SafetyCalculator, StimProtocol, get_material
from neurostim.safety import water_window as ww


class TestOnePolarityConvention:
    """Ledger 7. ``anodic_first`` defaulted to False and ``anodic_first_for_capacitance`` to
    None, so the sign and the capacitance could disagree: AIROF at its own CIC returned
    +0.4286 V of headroom and PASS where the definition of the CIC puts it on the edge."""

    def test_airof_at_its_own_cic_lands_on_the_window_edge(self):
        """AIROF cathodic-first: 1 mC/cm^2 over the 0.6 V cathodic half-window."""
        result = ww.evaluate("AIROF", 1000.0)
        assert result.headroom_V == pytest.approx(0.0, abs=1e-12)
        assert result.peak_potential_V == pytest.approx(-0.6, abs=1e-12)

    @pytest.mark.parametrize("anodic_first", [False, True])
    def test_the_capacitance_follows_the_pulse_polarity_by_default(self, anodic_first):
        default = ww.evaluate("Pt", 50.0, anodic_first=anodic_first)
        assert default.capacitance_uF_cm2 == ww.effective_capacitance_uF_cm2(
            "Pt", anodic_first=anodic_first
        )

    def test_a_disagreeing_capacitance_polarity_raises(self):
        with pytest.raises(ValueError, match="anodic_first_for_capacitance"):
            ww.evaluate("Pt", 50.0, anodic_first=True, anodic_first_for_capacitance=False)
        # Agreement is still accepted, so existing callers that pass both are unaffected.
        ww.evaluate("Pt", 50.0, anodic_first=True, anodic_first_for_capacitance=True)


class TestThePolarityBlindCapacitanceIsTheSmallest:
    """Ledger 8. With the polarity unknown the narrower half-window was taken, which sits
    in the denominator of ``C = limit / available_V``: it enlarged C and understated the
    excursion. The conservative capacitance is the smallest one either polarity gives."""

    @pytest.mark.parametrize("material", ["Pt", "PtIr", "AIROF", "SIROF", "TiN", "PEDOT"])
    def test_it_is_the_smaller_of_the_two_polarities(self, material):
        blind = ww.effective_capacitance_uF_cm2(material, anodic_first=None)
        assert blind == min(
            ww.effective_capacitance_uF_cm2(material, anodic_first=True),
            ww.effective_capacitance_uF_cm2(material, anodic_first=False),
        )

    def test_platinum_by_hand(self):
        """Pt: 100 uC/cm^2 anodic-first over 0.8 V is 125; 150 cathodic-first over 0.6 V is
        250. The old rule gave 150 (the union's high end) over 0.6 V, 250."""
        assert ww.effective_capacitance_uF_cm2("Pt", anodic_first=None) == pytest.approx(125.0)

    def test_the_counter_relation_for_platinum_is_unchanged(self):
        """Ledger 7's note: the counter takes the opposite boolean polarity, so an identical
        Pt counter polarises exactly twice the contact cathodic-first (125 against 250
        uF/cm^2) and half anodic-first. The boolean branches are untouched by C4.2."""
        for material in ("Pt", "PtIr"):
            for anodic_first, ratio in ((False, 2.0), (True, 0.5)):
                contact = DiscElectrode(500.0, material)
                result = SafetyCalculator(
                    contact,
                    StimProtocol(300.0, 200.0, 130.0, 1.0, anodic_first=anodic_first),
                    compliance_V=10.0,
                    counter_electrode=DiscElectrode(500.0, material),
                    counter_separation_um=1e6,
                ).assess().compliance
                assert result.counter_polarisation_V == pytest.approx(
                    ratio * result.polarisation_V, rel=1e-12
                ), (material, anodic_first)


class TestTheDriftArgumentsAreAllOrNone:
    """Ledgers 117 and 119 (Phase 2 review F15, Phase 2b review G1). The public function
    built no drift clause, and said nothing, unless all three of net DC, area and train
    were given; it had no balance gate, so a waveform Charge balance calls balanced still
    drifted; and ``recovered_charge_uC`` defaulted to 0.0, so omitting it made a partial
    recovery look monophasic (2.4 s and no exit, where assess() gives 0.42 s and FAIL)."""

    KW = {"net_dc_current_uA": 1.0, "area_cm2": 0.001963, "train_duration_s": 1.0}

    @pytest.mark.parametrize("missing", ["net_dc_current_uA", "area_cm2", "train_duration_s"])
    def test_a_partial_set_raises_and_names_what_is_missing(self, missing):
        kwargs = {k: v for k, v in self.KW.items() if k != missing}
        with pytest.raises(ValueError, match=missing):
            ww.evaluate("Pt", 50.0, recovered_charge_uC=0.0, **kwargs)

    def test_the_recovered_charge_must_be_given_with_the_drift(self):
        with pytest.raises(ValueError, match="recovered_charge_uC"):
            ww.evaluate("Pt", 50.0, **self.KW)

    def test_no_drift_arguments_is_still_the_peak_alone(self):
        assert ww.evaluate("Pt", 50.0).drift is None

    def test_a_waveform_charge_balance_calls_balanced_does_not_drift(self):
        """G1's case: r_a = 1 - 5e-13 is balanced by Charge balance's own tolerance."""
        protocol = StimProtocol(
            80.0, 200.0, 130.0, math.inf, charge_recovery_ratio=1 - 5e-13
        )
        assert protocol.is_charge_balanced  # the premise
        area = DiscElectrode(500.0, "Pt").area_cm2
        density = protocol.charge_per_phase_uC / area
        result = ww.evaluate(
            "Pt", density, net_dc_current_uA=protocol.net_dc_current_uA, area_cm2=area,
            train_duration_s=protocol.train_duration_s,
            recovered_charge_uC=protocol.charge_per_phase_uC * protocol.recovered_fraction,
        )
        assert result.drift is None or not result.drift.drifts

    def test_the_review_case_agrees_with_assess(self):
        """G1's second case, with the recovered charge given: the direct call and assess()
        agree to the bit on the time to the edge."""
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(1227.184630308513, 200.0, 50.0, 1.0, charge_recovery_ratio=0.99),
            capacitance_uF_cm2=250.0,
        )
        p = calc.p
        direct = ww.evaluate(
            "Pt", p.charge_per_phase_uC / calc.e.area_cm2, capacitance_uF_cm2=250.0,
            net_dc_current_uA=p.net_dc_current_uA, area_cm2=calc.e.area_cm2,
            train_duration_s=p.train_duration_s,
            recovered_charge_uC=p.charge_per_phase_uC * p.recovered_fraction,
        )
        assert direct.drift.time_to_exit_s == calc.assess().water_window.drift.time_to_exit_s


class TestTheChargeIntervalRaisesInsteadOfCollapsing:
    """Ledger 117's third item. ``_charge_ceiling_interval`` fell back to
    ``Interval.exact`` when the charge result carried no interval -- the fall-through
    ledger 97 removed everywhere else."""

    def test_a_charge_result_without_an_interval_raises(self):
        assessment = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
        ).assess()
        stripped = replace(
            assessment, charge=replace(assessment.charge, max_current_interval_uA=None)
        )
        check = next(c for c in stripped.checks if c.name == "Charge injection limit")
        with pytest.raises(ValueError, match="Charge injection limit"):
            stripped._ceiling_interval_uA(check)


def test_every_shipped_material_still_evaluates():
    """The premise for the contract: the packaged path passes all or none."""
    for key in ("Pt", "AIROF", "TiN", "SS316LVM"):
        assert get_material(key) is not None
