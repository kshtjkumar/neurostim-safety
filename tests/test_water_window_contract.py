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


class TestTheDriftRunsOverTheOnTime:
    """Ledger 109 (Phase 2 review F7), user decision (a). The drift ran over the wall-clock
    train while the pulse count, the mean and RMS currents and, since C3.17, the compliance
    offset scale with ``train_duty_cycle``. Under the leak-free capacitor an off-period
    neither adds nor removes offset, so the drift runs over the on-time: the edge is reached
    within the train when ``time_to_exit < T * duty``. A real interface also relaxes in the
    off-time, so on-time is still conservative against it.
    """

    @staticmethod
    def _band():
        from neurostim import CylindricalBandElectrode

        return CylindricalBandElectrode(1270.0, 1500.0, "PtIr")

    def test_the_ledger_109_case_is_a_caution_not_a_fail(self):
        """The band, 3000 uA / 90 us / 130 Hz monophasic, 1 s at 20 % duty: 7.02 uC
        delivered against an 8.977 uC budget. It used to FAIL, 'reaches the edge in
        0.2558 s'; 0.2558 s of on-time is past the train's 0.2 s."""
        calc = SafetyCalculator(
            self._band(),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic", train_duty_cycle=0.2),
        )
        assessment = calc.assess()
        drift = assessment.water_window.drift
        assert drift.time_to_exit_s == pytest.approx(0.2557578634653229, rel=1e-12)
        assert drift.window_charge_uC == pytest.approx(8.977, abs=5e-4)
        delivered = calc.p.net_charge_per_pulse_uC * calc.p.n_pulses
        assert delivered == pytest.approx(7.02, abs=5e-3)
        assert drift.exits_during_train is False
        check = next(c for c in assessment.checks if c.name == "Water window")
        assert check.status.value == "CAUTION"
        assert "on-time" in check.summary

    def test_the_ledger_2_case_at_full_duty_is_unchanged(self):
        """At duty 1 the on-time is the wall-clock: still FAIL at 0.2558 s."""
        assessment = SafetyCalculator(
            self._band(), StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic")
        ).assess()
        assert assessment.water_window.drift.time_to_exit_s == pytest.approx(0.2558, rel=1e-3)
        check = next(c for c in assessment.checks if c.name == "Water window")
        assert check.status.value == "FAIL"

    def test_the_verdict_agrees_with_stepping_the_delivered_pulses(self):
        """Not tautological: the oracle steps the delivered pulses one by one and evaluates
        no closed form. Disagreement is allowed only within one pulse of the boundary."""
        import oracles

        compared = 0
        for duty in (0.1, 0.2, 0.5, 1.0):
            for recovery in (0.0, 0.5, 0.9, 0.99, 1.2):
                for current in (50.0, 300.0, 1000.0):
                    shape = (
                        {"waveform": "monophasic"} if recovery == 0.0
                        else {"charge_recovery_ratio": recovery}
                    )
                    calc = SafetyCalculator(
                        DiscElectrode(500.0, "Pt"),
                        StimProtocol(current, 200.0, 50.0, 2.0, train_duty_cycle=duty, **shape),
                        capacitance_uF_cm2=250.0,
                    )
                    result = calc.assess().water_window
                    if not result.passes or result.drift is None or not result.drift.drifts:
                        continue
                    drift = result.drift
                    stepped = oracles.exits_within_delivered_pulses(
                        train_duration_s=2.0, train_duty_cycle=duty, frequency_hz=50.0,
                        current_uA=current, pulse_width_us=200.0,
                        recovered_fraction=recovery, area_cm2=calc.e.area_cm2,
                        capacitance_uF_cm2=250.0, leading_window_V=0.6,
                        opposite_window_V=0.8,
                    )
                    if stepped != drift.exits_during_train:
                        assert abs(drift.time_to_exit_s - 2.0 * duty) <= 1.0 / 50.0, (
                            duty, recovery, current,
                        )
                    compared += 1
        assert compared >= 30, compared

    def test_the_ceiling_is_back_solved_over_the_on_time(self):
        """At the Water window ceiling the drift reaches the edge at the end of the on-time,
        not of the wall-clock train."""
        from dataclasses import replace as dc_replace

        protocol = StimProtocol(
            80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9, train_duty_cycle=0.25
        )
        calc = SafetyCalculator(DiscElectrode(500.0, "Pt"), protocol)
        check = next(c for c in calc.assess().checks if c.name == "Water window")
        at_ceiling = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), dc_replace(protocol, current_uA=check.ceiling_uA)
        ).assess().water_window.drift
        assert at_ceiling.time_to_exit_s == pytest.approx(0.25, rel=1e-9)
        full = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), dc_replace(protocol, train_duty_cycle=1.0)
        )
        full_ceiling = next(
            c for c in full.assess().checks if c.name == "Water window"
        ).ceiling_uA
        assert check.ceiling_uA > full_ceiling  # the relaxation, in the right direction

    def test_the_detail_says_on_time(self):
        drift = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9,
                         train_duty_cycle=0.5),
        ).assess().water_window.drift
        text = drift.describe()
        assert "(on-time)" in text
        assert "0.5 s of on-time" in text
