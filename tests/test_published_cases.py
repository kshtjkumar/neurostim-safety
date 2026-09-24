"""Reproduce published results from published inputs.

The distinction that makes this meaningful
------------------------------------------
Most numbers in this package are **stored**: a charge-injection limit read out of a
table. Feeding such a value back in and getting it out again proves nothing.

The cases below are different. Each takes inputs a paper states and checks that the
package's **computed** output matches a number that paper also states but that the
package never stores. Where the chain runs through several independent steps -- geometry,
then access resistance, then Ohm's law -- agreement is evidence the physics is right, not
evidence of bookkeeping.

Every tolerance here is the agreement actually achieved, not a target chosen to pass.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from neurostim import CylindricalBandElectrode, DiscElectrode, SphericalElectrode
from neurostim.data import butterwick2007, elwassif2006, gabriel1996, mccreery1990
from neurostim.models import field as field_mod
from neurostim.models import thermal
from neurostim.safety import current_density as jd
from neurostim.safety import shannon
from neurostim.safety.water_window import polarisation_V


class TestKuncelGrill2004:
    """Clin Neurophysiol 115:2431-41."""

    def test_their_average_current_density_is_an_assumed_impedance_not_a_resistance(self):
        """Rewritten at C3.1 (physics B3). This test used to reproduce 0.0993 A/cm^2 to 2 %
        from the equal-area *disc* access resistance at 0.35 S/m and call that agreement
        with "their finite element model". It was two errors cancelling, and the test never
        called the field model, so it could not detect the convention it was named as a
        guard for.

        What the paper says: grey matter is "around 0.2 S/m", the impedance "is estimated
        conservatively to be 500" ohm, and a 1.26 x 1.5 mm contact "set to 3 V" gives an
        average of 0.0993 A/cm^2. That average back-solves to about 509 ohm through the
        lateral area -- the assumed clinical impedance, not a spreading resistance.

        What is asserted, each from inputs written here:

        * 0.0993 A/cm^2 at 3 V over the lateral area implies 508.8 ohm, within 2 % of their
          stated 500;
        * at their own 0.2 S/m the package's equal-area sphere gives 578.8 ohm, 1.0 % above
          the converged band at that conductivity (327.6 ohm at 0.35 S/m, scaled by
          0.35/0.2 = 573.3 ohm; ledger 127 replaced an unconverged 335.1 / 586.4);
        * so the spreading resistance is about 16 % above their 500 ohm (their figure is
          14 % below it), conservative in the direction they said: a lower assumed
          impedance means a higher assumed current.
        """
        import oracles

        contact = CylindricalBandElectrode(1260.0, 1500.0, "PtIr")
        area_cm2 = math.pi * 0.126 * 0.150
        assert contact.area_cm2 == pytest.approx(area_cm2, rel=1e-12)

        implied_ohm = 3.0 / (0.0993 * area_cm2)
        assert implied_ohm == pytest.approx(508.8, abs=0.1)
        assert implied_ohm == pytest.approx(500.0, rel=0.02)

        fd_at_their_sigma = oracles.FD_BAND_REFERENCE[oracles.CLINICAL_DBS_ASPECT] * 0.35 / 0.2
        assert fd_at_their_sigma == pytest.approx(573.3, abs=0.05)
        sphere = contact.access_resistance_ohm(0.2)
        assert sphere == pytest.approx(578.8, abs=0.1)
        assert 0.0 < sphere / fd_at_their_sigma - 1.0 < 0.015
        assert 500.0 / sphere - 1.0 == pytest.approx(-0.136, abs=0.005)

    def test_thirty_uC_cm2_limit_derives_from_shannon_at_k_1_75(self):
        """'the largest charge for a contact area of 0.06 cm^2 that did not result in
        a charge density in the damaging region', which they place at k ~ 1.75."""
        assert shannon.shannon_k(30.0 * 0.06, 0.06) == pytest.approx(1.75, abs=0.03)

    def test_fraction_of_contact_above_average_current_density(self):
        """Their FEM gives 25.6 %; the analytic primary distribution gives 25 %."""
        assert pytest.approx(0.256, abs=0.01) == jd.DISC_FRACTION_ABOVE_AVERAGE


class TestCogan2008:
    """Annu Rev Biomed Eng 10:275-309."""

    def test_dbs_contact_area(self):
        """Table 1 footnote b quotes 0.06 cm^2 for clinical DBS electrodes."""
        assert CylindricalBandElectrode(1270.0, 1500.0).area_cm2 == pytest.approx(
            0.06, abs=0.001
        )


class TestCogan2016:
    """J Neural Eng 13:021001. Their own worked example."""

    def test_their_k_1_25_example(self):
        """'charge densities up to 60 uC/cm^2 (k ~ 1.25 for a 0.005 cm^2 electrode)'."""
        assert shannon.shannon_k(60.0 * 0.005, 0.005) == pytest.approx(1.25, abs=0.01)


class TestElwassif2006:
    """Proc IEEE EMBS 2006:3580-3. Table I, one parameter varied at a time."""

    def test_peak_rise_linear_in_electrical_conductivity(self):
        ratios = [
            p.rise_K_3389 / p.sigma_S_per_m for p in elwassif2006.conductivity_block()
        ]
        assert max(ratios) / min(ratios) - 1 < 0.02

    def test_peak_rise_inverse_in_thermal_conductivity(self):
        products = [
            p.rise_K_3389 * p.thermal_conductivity_W_per_mK
            for p in elwassif2006.thermal_conductivity_block()
        ]
        assert max(products) / min(products) - 1 < 0.02

    def test_perfusion_attenuation_matches_the_analytic_form(self):
        """Analytic 1/(1 + a/L) against their FEM sweep; achieved agreement 8 %."""
        contact = CylindricalBandElectrode(
            elwassif2006.LEAD_3389_CONTACT_DIAMETER_UM,
            elwassif2006.LEAD_3389_CONTACT_HEIGHT_UM,
        )
        a = contact.equivalent_radius_um * 1e-6
        block = elwassif2006.perfusion_block()
        for point in block[1:]:
            tissue = thermal.TissueThermalProperties(
                thermal_conductivity_W_per_mK=point.thermal_conductivity_W_per_mK,
                perfusion_rate_per_s=point.perfusion_per_s,
                blood_density_kg_per_m3=elwassif2006.BLOOD_DENSITY_KG_PER_M3,
                blood_specific_heat_J_per_kgK=elwassif2006.BLOOD_SPECIFIC_HEAT_J_PER_KGK,
                verified_fields=(),
                uncertainty={},
            )
            predicted = 1.0 / (1.0 + a / tissue.thermal_penetration_depth_m)
            reported = point.rise_K_3389 / block[0].rise_K_3389
            assert predicted == pytest.approx(reported, rel=0.10)

    def test_peak_rise_reproduced_from_their_implied_power(self):
        """Feed the analytic model the power their 0.82 K implies and it returns 0.82 K."""
        contact = CylindricalBandElectrode(
            elwassif2006.LEAD_3389_CONTACT_DIAMETER_UM,
            elwassif2006.LEAD_3389_CONTACT_HEIGHT_UM,
        )
        unperfused = thermal.TissueThermalProperties(
            thermal_conductivity_W_per_mK=0.527,
            perfusion_rate_per_s=0.0,
            verified_fields=(),
            uncertainty={},
        )
        rise = thermal.peak_temperature_rise_K(
            elwassif2006.implied_power_W(), contact.equivalent_radius_um, unperfused
        )
        assert rise == pytest.approx(elwassif2006.PEAK_RISE_K, rel=0.02)


class TestMcCreery1990:
    """IEEE TBME 37:996-1001, Table I."""

    def test_every_row_is_internally_consistent(self):
        """Q/A must equal the tabulated charge density for all twelve conditions."""
        for point in mccreery1990.TABLE_I:
            assert point.charge_per_phase_uC / point.area_cm2 == pytest.approx(
                point.charge_density_uC_cm2, rel=0.05
            )

    def test_their_stated_thresholds_bracket_correctly(self):
        """'when the charge per phase is 1 uC/ph, the threshold lies between 50 and
        100 uC/cm^2. When the charge per phase is 5 uC/ph, between 10 and 12.'"""
        at_1uC = [p for p in mccreery1990.TABLE_I if p.charge_per_phase_uC == 1.0]
        safe = [p for p in at_1uC if p.outcome == "none"]
        harmed = [p for p in at_1uC if p.outcome != "none"]
        assert max(p.charge_density_uC_cm2 for p in safe) <= 50.0
        assert min(p.charge_density_uC_cm2 for p in harmed) >= 50.0

    def test_local_charge_density_worked_example(self):
        """Their eq. (1) at 60 um below a 45 um facet pulsed at 800 uC/cm^2."""
        assert mccreery1990.local_charge_density_uC_cm2(800.0, 60.0, 45.0) == (
            pytest.approx(160.0)
        )


class TestMerrill2005:
    """J Neurosci Methods 141:171-98."""

    def test_footnote_2_double_layer_arithmetic(self):
        """'A 1 V potential excursion applied to a double layer capacitance of
        20 uF/cm^2 yields 20 uC/cm^2 stored charge.'"""
        assert polarisation_V(20.0, 20.0) == pytest.approx(1.0)

    def test_equation_5_1_identity(self):
        """log(Q/A) = k - log(Q) for arbitrary inputs."""
        for charge, area in ((0.016, 2.8e-4), (1.0, 1e-2), (18.0, 0.5)):
            k = shannon.shannon_k(charge, area)
            assert math.log10(charge / area) == pytest.approx(k - math.log10(charge))


class TestNewman1966:
    """J Electrochem Soc 113:501-2."""

    @pytest.mark.parametrize("diameter_um", [50.0, 500.0, 5000.0])
    def test_disc_access_resistance(self, diameter_um):
        """R = 1/(4 kappa a) for the primary current distribution."""
        disc = DiscElectrode(diameter_um)
        assert disc.access_resistance_ohm(0.35) == pytest.approx(
            1.0 / (4.0 * 0.35 * diameter_um / 2.0 * 1e-6)
        )

    def test_sphere_potential_equals_current_times_access_resistance(self):
        """Two independent derivations of the same quantity."""
        sphere = SphericalElectrode(500.0)
        assert field_mod.potential_V(100.0, sphere.radius_um, 0.35) == pytest.approx(
            100e-6 * sphere.access_resistance_ohm(0.35)
        )


class TestButterwick2007:
    """IEEE TBME 54:2261-7."""

    def test_both_retina_anchors_reproduce(self):
        assert butterwick2007.threshold_A_per_cm2(6000.0) == pytest.approx(0.061, rel=1e-6)
        assert butterwick2007.threshold_A_per_cm2(6.0) == pytest.approx(1.3, rel=1e-6)

    def test_their_thermal_estimate_agrees_with_the_pennes_model(self):
        """They compute a rise of order millikelvin for a 1 mm electrode and conclude
        'no hyperthermia can be expected as a result of chronic stimulation'."""
        sphere = SphericalElectrode(1000.0)
        power = thermal.ohmic_power_W(100.0, sphere.access_resistance_ohm(0.35))
        rise = thermal.peak_temperature_rise_K(power, sphere.radius_um)
        assert rise < 1e-2


class TestGabriel1996:
    """Phys Med Biol 41:2271-93, Table 1."""

    def test_blood_low_frequency_conductivity_is_its_ionic_term(self):
        """Blood has no low-frequency dispersions in Table 1, so sigma -> sigma_i."""
        assert gabriel1996.BLOOD.conductivity_S_per_m(100.0) == pytest.approx(
            gabriel1996.BLOOD.sigma_i_S_per_m, rel=1e-3
        )

    def test_grey_matter_low_frequency_conductivity_is_about_0_1(self):
        """The well-known Gabriel figure for brain at kilohertz frequencies."""
        assert gabriel1996.GREY_MATTER.conductivity_S_per_m(1000.0) == pytest.approx(
            0.10, abs=0.02
        )


class TestInternalConsistency:
    """Closed form against an independently written numerical solve."""

    def test_pennes_analytic_equals_classical_unperfused_limit(self):
        tissue = thermal.TissueThermalProperties(
            perfusion_rate_per_s=0.0, verified_fields=(), uncertainty={}
        )
        expected = 1e-3 / (
            4 * math.pi * tissue.thermal_conductivity_W_per_mK * 500e-6
        )
        assert thermal.peak_temperature_rise_K(1e-3, 500.0, tissue) == pytest.approx(
            expected, rel=1e-12
        )

    def test_pennes_analytic_equals_finite_difference_solve(self):
        analytic = thermal.peak_temperature_rise_K(1e-3, 500.0, thermal.BRAIN)
        numeric = thermal.pennes_transient_sphere(
            1e-3, 500.0, np.array([20000.0]), thermal.BRAIN
        )[0]
        assert numeric == pytest.approx(analytic, rel=1e-4)


class TestWaterWindowConsistency:
    """The water-window model must agree with the CIC measurement, not contradict it.

    Before 0.10.0 the interface was modelled as a bare 20 uF/cm^2 double layer, which
    predicted platinum leaves the window at 12 uC/cm^2 while Rose & Robblee measured it
    staying inside up to 100-150. That tenfold contradiction lived inside this package
    and fired a false alarm on nearly every realistic protocol.
    """

    @pytest.mark.parametrize("key", ["Pt", "PtIr", "AIROF", "SIROF", "TiN"])
    @pytest.mark.parametrize("anodic_first", [True, False])
    def test_injecting_the_cic_reaches_the_window_edge_and_no_further(
        self, key, anodic_first
    ):
        """This is what the charge-injection limit means, so it must hold by design --
        and it must hold separately for each polarity, since Rose & Robblee measured a
        different limit for each against the same window."""
        from neurostim import get_material
        from neurostim.safety import water_window as ww

        material = get_material(key)
        reached = ww.max_charge_density_in_window_uC_cm2(
            material, anodic_first=anodic_first
        )
        assert reached == pytest.approx(
            material.cic_uC_cm2("optimistic", anodic_first), rel=0.01
        )

    def test_platinum_effective_capacitance_reflects_pseudocapacitance(self):
        """20 uF/cm^2 is double-layer only; Pt stores an order of magnitude more."""
        from neurostim.safety import water_window as ww

        c_eff = ww.effective_capacitance_uF_cm2("Pt")
        assert c_eff > 10 * ww.DOUBLE_LAYER_CAPACITANCE_uF_cm2

    def test_a_protocol_inside_its_cic_no_longer_fails_the_window(self):
        """The false alarm the old model produced."""
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        checks = {
            c.name: c
            for c in SafetyCalculator(
                RingElectrode(330, 270, "Pt"), StimProtocol(20, 200, 130, 1)
            ).assess().checks
        }
        assert checks["Charge injection limit"].status is Status.PASS
        assert checks["Water window"].status is Status.PASS

    def test_polarisation_can_never_exceed_the_window_within_the_cic(self):
        """A polarisation larger than the whole window is physically impossible for an
        electrode operating inside its measured charge-injection limit."""
        from neurostim import get_material
        from neurostim.safety import water_window as ww

        for key in ("Pt", "AIROF", "SIROF", "TiN"):
            material = get_material(key)
            excursion = ww.polarisation_V(
                material.cic_uC_cm2("optimistic"),
                ww.effective_capacitance_uF_cm2(material),
            )
            assert excursion <= material.water_window.width_V


class TestTehovnik2006:
    """J Neurophysiol 96:512-21."""

    def test_mt_excitability_constant_reproduces(self):
        """'The average excitability constant of the activated elements in MT is
        therefore estimated to be 2,000 uA/mm^2 [K = 20 uA/(0.1 mm)^2].'"""
        from neurostim.models import vta

        assert pytest.approx(vta.MT_BEHAVIOURAL_K_uA_PER_MM2) == 20.0 / (0.1**2)

    def test_stoney_curve_reproduces_at_one_millimetre(self):
        """'an element having a constant of 1,292 uA/mm^2 would require a 1,292-uA
        current to be activated 1 mm away 50% of the time.'"""
        from neurostim.models import vta

        model = vta.CurrentDistanceModel()
        assert model.threshold_uA(1000.0) == pytest.approx(1292.0)
        assert model.activation_radius_um(1292.0) == pytest.approx(1000.0)

    def test_chronaxie_tau_relation_spans_the_reported_pyramidal_range(self):
        """Tehovnik report pyramidal tract chronaxies of 0.1-0.4 ms; the Lapicque
        relation t_c = tau ln2 must round-trip across that whole range."""
        from neurostim.models import strength_duration as sd
        from neurostim.models import vta

        for chronaxie_ms in vta.PYRAMIDAL_CHRONAXIE_RANGE_MS:
            tau = sd.tau_from_chronaxie_us(chronaxie_ms * 1000.0)
            assert sd.chronaxie_from_tau_us(tau) == pytest.approx(
                chronaxie_ms * 1000.0
            )


class TestActivationAgainstDamageRadius:
    """Two independent measurements, 42 years apart, that ought to agree."""

    def test_stoney_activation_radius_matches_mccreery_damage_radius(self):
        """Stoney et al. (1968) measured a current-distance constant by single-cell
        recording in cat motor cortex. McCreery et al. (2010) measured a *damage* radius
        by chronic histology in cat sensorimotor cortex at 4 nC/phase.

        If damage follows the activated volume -- the mass-action mechanism McCreery
        proposes -- the two radii should be comparable. At 100 us per phase, 4 nC/phase
        is 40 uA, and Stoney's constant puts the activation radius at 176 um against
        McCreery's observed loss to at least 150 um. Agreement within about 20 %, from
        unrelated experiments and methods.
        """
        from neurostim.data import mccreery2010
        from neurostim.models import vta

        current_uA = mccreery2010.DAMAGE_NC_PER_PHASE / (100.0 * 1e-3)
        radius = vta.CurrentDistanceModel().activation_radius_um(current_uA)
        observed = mccreery2010.DAMAGE_RADIUS_CONTINUOUS_UM
        assert radius == pytest.approx(observed, rel=0.25)

    def test_activation_radius_is_in_the_far_field(self):
        """The point-source assumption behind the current-distance rule requires it."""
        from neurostim.data import cogan2016
        from neurostim.models import vta

        radius = vta.CurrentDistanceModel().activation_radius_um(20.0)
        assert radius > cogan2016.MICROELECTRODE_POINT_SOURCE_DISTANCE_UM


class TestStrengthDurationFormsDiverge:
    """Weiss and Lapicque are different fits, not two names for one curve."""

    def test_they_agree_exactly_at_chronaxie(self):
        from neurostim.models import strength_duration as sd

        rheobase, chronaxie = 20.0, 150.0
        weiss = sd.weiss_threshold_uA(chronaxie, rheobase, chronaxie)
        lapicque = sd.lapicque_threshold_uA(
            chronaxie, rheobase, sd.tau_from_chronaxie_us(chronaxie)
        )
        assert weiss == pytest.approx(2 * rheobase)
        assert lapicque == pytest.approx(weiss)

    def test_they_diverge_either_side_of_chronaxie(self):
        """Weiss reads lower for short pulses and higher for long ones, by up to 17 %."""
        from neurostim.models import strength_duration as sd

        rheobase, chronaxie = 20.0, 150.0
        tau = sd.tau_from_chronaxie_us(chronaxie)
        short = sd.weiss_threshold_uA(50.0, rheobase, chronaxie) / (
            sd.lapicque_threshold_uA(50.0, rheobase, tau)
        )
        long = sd.weiss_threshold_uA(1000.0, rheobase, chronaxie) / (
            sd.lapicque_threshold_uA(1000.0, rheobase, tau)
        )
        assert short < 0.9
        assert long > 1.1


class TestComplianceConsistency:
    """The polarisation term must not contradict the water window."""

    @pytest.mark.parametrize("key", ["Pt", "AIROF", "SIROF", "TiN"])
    def test_polarisation_at_the_cic_equals_the_half_window(self, key):
        """Compliance and the water-window check share one interfacial capacitance, so
        injecting the CIC must land exactly on the window edge in both."""
        from neurostim import get_material
        from neurostim.safety import water_window as ww

        material = get_material(key)
        excursion = ww.polarisation_V(
            material.cic_uC_cm2("optimistic", anodic_first=False),
            ww.effective_capacitance_uF_cm2(material, anodic_first=False),
        )
        assert excursion == pytest.approx(abs(material.water_window.cathodic_V))

    def test_required_voltage_is_ohmic_plus_polarisation(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        result = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1), compliance_V=10.0
        ).assess().compliance
        assert result.required_V == pytest.approx(
            result.ohmic_drop_V + result.polarisation_V
        )


class TestRose1985Ta2O5:
    """Rose, Kelliher & Robblee (1985), the Ta2O5 capacitor-electrode review.

    A capacitor electrode is the one material here whose behaviour is fully predicted
    by a closed-form model, ``Q/A = C x 0.8 V_f`` with ``C = k eps0 A_e / d``. That
    makes the paper's own numbers a genuine end-to-end check rather than a lookup.
    """

    def test_smooth_tantalum_charge_storage(self):
        """22 nF/mm^2 at 5 V forming gives 0.088 uC/mm^2 at 80 % of forming."""
        from neurostim.data import ta2o5_capacitor as ta

        assert ta.charge_storage_uC_mm2(0.022, 5.0) == pytest.approx(0.088)

    def test_etched_tantalum_roughness_factor(self):
        """0.13-0.33 uF/mm^2 on a 10 V film is an enhancement of "12 to 30".

        Only reproducible if the smooth baseline is thickness-corrected from 5 V to
        10 V first. Against the uncorrected 22 nF/mm^2 it would come out 6 to 15.
        """
        from neurostim.data import ta2o5_capacitor as ta

        assert ta.roughness_factor(0.13, 10.0) == pytest.approx(12.0, abs=0.3)
        assert ta.roughness_factor(0.33, 10.0) == pytest.approx(30.0, abs=0.3)

    def test_etched_tantalum_dc_charge_storage_brackets_the_pulsed_value(self):
        """DC storage is 1.04-2.64 uC/mm^2; pulsed at 0.1 ms it is 0.88-1.4.

        The gap is pore resistance, which Rose et al. put at up to 80 % of the DC
        capacitance for short pulses.
        """
        from neurostim.data import ta2o5_capacitor as ta

        low = ta.charge_storage_uC_mm2(0.13, 10.0)
        high = ta.charge_storage_uC_mm2(0.33, 10.0)
        assert low == pytest.approx(1.04, abs=0.01)
        assert high == pytest.approx(2.64, abs=0.01)
        assert low > 0.88
        assert high > 1.4
        assert (1.0 - 1.4 / high) < ta.PORE_RESISTANCE_MAX_REDUCTION

    def test_barium_titanate_worked_example(self):
        """"a 10 nm BaTiO3 film ... pulsed to 4 V would store only 2.4 nC"."""
        from neurostim.data import ta2o5_capacitor as ta

        capacitance_F = ta.parallel_plate_capacitance_F(7000.0, 1e-10, 1e-8)
        assert capacitance_F * 4.0 * 1e9 == pytest.approx(2.4, abs=0.1)

    @pytest.mark.parametrize(
        ("label", "expected_nC"),
        [("etched Ta, best", 0.26), ("etched Ti, best", 0.63), ("BaTiO3", 0.007)],
    )
    def test_table_iii_microelectrode_extrapolation(self, label, expected_nC):
        """Table III's last column: storage density x 1e-4 mm^2, in nC."""
        from neurostim.data import ta2o5_capacitor as ta

        design = next(d for d in ta.DESIGNS if label in d.label)
        assert design.scaled_to_microelectrode_nC() == pytest.approx(
            expected_nC, rel=0.02
        )

    def test_no_capacitor_design_reaches_the_intracortical_target(self):
        """The paper's conclusion: none of them delivers 5 nC on 1e-4 mm^2."""
        from neurostim.data import ta2o5_capacitor as ta

        assert not any(ta.meets_intracortical_target(d) for d in ta.DESIGNS)

    def test_package_limit_does_not_exceed_the_best_measured_microelectrode(self):
        """Cogan's ~0.5 mC/cm^2 is above every Ta2O5 microelectrode Rose et al. report.

        It is *below* their sintered porous surface disc at 0.7 mC/cm^2, which is the
        likely origin of the number -- and is a macroelectrode for surface stimulation,
        not an intracortical electrode. Quoting it for a microelectrode overstates the
        limit by about twofold; the package's 0.26 mC/cm^2 ceiling does not.
        """
        from neurostim import get_material
        from neurostim.data import ta2o5_capacitor as ta

        micro = [
            d
            for d in ta.DESIGNS
            if d.dielectric == "Ta2O5"
            and d.geometric_area_mm2 is not None
            and d.geometric_area_mm2 < 1.0
        ]
        best_micro = max(d.charge_storage_uC_cm2 for d in micro)
        assert best_micro == pytest.approx(260.0)
        assert get_material("Ta2O5").cic_uC_cm2("optimistic") <= best_micro
        assert best_micro < 500.0  # Cogan's row, above every microelectrode measured

        surface_disc = next(d for d in ta.DESIGNS if "Guyton" in d.label)
        assert surface_disc.charge_storage_uC_cm2 == pytest.approx(700.0)


class TestRiedyWalter1996:
    """316LVM stainless steel, one year of continuous pulsing."""

    def test_protein_study_current(self):
        """40 uC/cm^2 on 5 mm of 0.17 mm wire at 100 us -> 11.2 mA."""
        from neurostim.data import riedy_walter1996 as rw

        assert rw.current_for_charge_density_mA(40.0, 5.0) == pytest.approx(
            rw.PROTEIN_STUDY_CURRENT_MA, rel=0.06
        )

    def test_chronic_study_current(self):
        """20 uC/cm^2 on 3 mm -> 3.8 mA, to within the tip-area ambiguity."""
        from neurostim.data import riedy_walter1996 as rw

        assert rw.current_for_charge_density_mA(20.0, 3.0) == pytest.approx(
            rw.CHRONIC_CURRENT_MA, rel=0.16
        )

    def test_every_table_i_final_polarisation_exceeds_the_reversible_limit(self):
        """At 40 uC/cm^2 the 1.2 V limit is exceeded in all three baths."""
        from neurostim.data import riedy_walter1996 as rw

        finals = [r for r in rw.TABLE_I if r.parameter == "E_max"]
        assert len(finals) == 3
        assert all(rw.exceeds_reversible_limit(r.final_V) for r in finals)

    def test_protein_does_not_change_the_transients(self):
        """Albumin at 0.4 and 4.0 g/L left E_max within the no-protein spread."""
        from neurostim.data import riedy_walter1996 as rw

        by_bath = {r.bath: r for r in rw.TABLE_I if r.parameter == "E_max"}
        reference = by_bath["no protein"]
        for bath, row in by_bath.items():
            if bath == "no protein":
                continue
            assert abs(row.final_V - reference.final_V) < 3 * reference.final_sd_V
        assert rw.PROTEIN_AFFECTS_CORROSION is False

    def test_package_conservative_limit_is_the_authors_recommendation(self):
        """20 uC/cm^2, not the 40 the older literature recommends."""
        from neurostim import get_material
        from neurostim.data import riedy_walter1996 as rw

        ss = get_material("SS316LVM")
        assert ss.cic_uC_cm2("conservative") == pytest.approx(
            rw.NONFARADAIC_LIMIT_UC_CM2
        )
        assert ss.cic_uC_cm2("optimistic") == pytest.approx(
            rw.RECOMMENDED_LIMIT_UC_CM2
        )


class TestAsanuma1976:
    """Strength-duration parameters for cortical cell bodies and axons."""

    def test_threshold_is_twice_rheobase_at_chronaxie(self):
        """The defining property, and the one point where Weiss and Lapicque agree."""
        from neurostim.data import asanuma1976 as az
        from neurostim.models import strength_duration as sd

        for row in az.CHRONAXIES:
            weiss = sd.weiss_threshold_uA(row.median_us, 3.0, row.median_us)
            lapicque = sd.lapicque_threshold_uA(
                row.median_us, 3.0, sd.tau_from_chronaxie_us(row.median_us)
            )
            assert weiss == pytest.approx(6.0)
            assert lapicque == pytest.approx(6.0)
            assert az.threshold_ratio_at(row.median_us, row.median_us) == 2.0

    def test_axons_have_shorter_chronaxies_than_cell_bodies(self):
        """Mann-Whitney p < 0.012, and the ranges only partly overlap."""
        from neurostim.data import asanuma1976 as az

        soma = az.chronaxie_for("cell bodies")
        axon = az.chronaxie_for("axons")
        assert axon.median_us < soma.median_us
        assert axon.low_us < soma.low_us
        assert axon.high_us < soma.high_us

    def test_paired_measurement_on_one_neuron_agrees_with_the_population(self):
        """The same cell gave 0.13 ms at the soma and 0.10 ms at its fibre."""
        from neurostim.data import asanuma1976 as az

        paired = az.PAIRED_SAME_NEURON_MS
        assert paired["cell_body"] > paired["fibre"]
        assert az.chronaxie_for("cell bodies").contains(paired["cell_body"] * 1e3)
        assert az.chronaxie_for("axons").contains(paired["fibre"] * 1e3)

    def test_a_weiss_fit_to_the_measured_chronaxie_round_trips(self):
        """Generate a curve from a published chronaxie; the fit must recover it."""
        import numpy as np

        from neurostim.data import asanuma1976 as az
        from neurostim.models import strength_duration as sd

        soma = az.chronaxie_for("cell bodies")
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = sd.weiss_threshold_uA(widths, 2.0, soma.median_us)
        fit = sd.fit_weiss(widths, thresholds)
        assert fit.rheobase_uA == pytest.approx(2.0)
        assert fit.chronaxie_us == pytest.approx(soma.median_us)
        assert az.plausible_cortical_chronaxie(fit.chronaxie_us)

    def test_implausible_chronaxie_is_flagged(self):
        """A 3 ms chronaxie is nothing this paper measured in cortex."""
        from neurostim.data import asanuma1976 as az

        assert not az.plausible_cortical_chronaxie(3000.0)
        assert not az.plausible_cortical_chronaxie(10.0)

    def test_functional_depression_sits_far_below_any_charge_density_limit(self):
        """80 uA at 0.2 ms is 16 nC/phase and depressed volleys in 5 of 7 trials.

        McCreery's smallest damaging charge per phase was 1 uC. Reversible functional
        depression is two orders of magnitude below anything the Shannon criterion or
        the charge-injection limits are built to catch, which is the point of storing
        it: it is a real ceiling that this package's checks cannot see.
        """
        from neurostim.data import asanuma1976 as az

        charge_nC = az.NOXIOUS_CURRENT_UA * az.PULSE_WIDTH_US * 1e-3
        assert charge_nC == pytest.approx(16.0)
        assert charge_nC * 1e-3 < 1.0  # uC/phase, vs McCreery's 1 uC threshold
        assert az.NOXIOUS_TRIALS_AFFECTED == (5, 7)


class TestSourceEndorsedPolicy:
    """A limit the cited work argues against must not return an unqualified PASS."""

    def test_stainless_steel_high_end_is_disputed_by_its_own_source(self):
        from neurostim import get_material

        cic = get_material("SS316LVM").cic
        assert cic.recommended_policy == "conservative"
        assert not cic.exceeds_recommendation("conservative")
        assert cic.exceeds_recommendation("nominal")
        assert cic.exceeds_recommendation("optimistic")

    @pytest.mark.parametrize("policy", ["nominal", "optimistic"])
    def test_permissive_policy_cannot_pass_unqualified(self, policy):
        """Before this, 'optimistic' turned CAUTION into PASS at 40 uC/cm^2.

        Forty is the number Riedy & Walter wrote their paper to dispute, so selecting it
        made the verdict better by applying a limit the evidence is worse for.
        """
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        calc = SafetyCalculator(
            RingElectrode(330.0, 215.0, "SS316LVM"),
            StimProtocol(40.0, 200.0, 130.0, 1.54),
            k=1.0,
            policy=policy,
        )
        result = calc.assess()
        check = next(c for c in result.checks if c.name == "Charge injection limit")
        assert check.status is Status.CAUTION
        assert result.charge.policy_warning
        assert "20 uC/cm^2" in result.charge.policy_warning

    def test_conservative_policy_carries_no_policy_warning(self):
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            RingElectrode(330.0, 215.0, "SS316LVM"),
            StimProtocol(40.0, 200.0, 130.0, 1.54),
            k=1.0,
            policy="conservative",
        )
        assert calc.assess().charge.policy_warning == ""

    def test_materials_without_a_stated_preference_are_unaffected(self):
        """Most sources report a range without arguing for an end; do not invent one."""
        from neurostim import get_material
        from neurostim.materials import list_materials

        assert get_material("Pt").cic.recommended_policy is None
        opinionated = [
            m.key for m in list_materials() if m.cic.recommended_policy is not None
        ]
        assert opinionated == ["SS316LVM"]

    def test_ta2o5_high_end_excludes_the_slow_charge_figure(self):
        """260 uC/cm^2 is a DC value and must not cap a 100 us pulsed limit."""
        from neurostim import get_material
        from neurostim.data import ta2o5_capacitor as ta

        material = get_material("Ta2O5")
        assert material.cic.pulse_width_us == 100.0
        assert material.cic_uC_cm2("optimistic") == pytest.approx(150.0)

        best_reported = next(d for d in ta.DESIGNS if "best reported" in d.label)
        assert best_reported.charge_storage_uC_cm2 == pytest.approx(260.0)
        assert material.cic_uC_cm2("optimistic") < best_reported.charge_storage_uC_cm2
