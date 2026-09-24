"""Phase 3 -- one half-space/full-space convention per geometry (fix plan D4, C3.1).

The field model gave every electrode but the hemisphere a full-space point source,
``V = I / (4 pi sigma r)``, while the access resistance of the planar geometries was
Newman's *half*-space disc. The same disc was therefore half-space in the compliance budget
and full-space in the field, so its far field was exactly half the true value (ledger 17).
Immersed geometries -- the clinical band and the microwire -- took the half-space disc
formula for a body with tissue on every side, high by a factor that the FV solve below
measures at 58-92 % (ledger 20; ledger 127 corrected an earlier, unconverged 40-70 %).

Expected values here come from ``tests.oracles``: the exact half-space disc solution
``V(r) = (2/pi) I R arcsin(a/r)`` with Newman's ``R = 1/(4 sigma a)`` derived inside the
oracle, and a converged finite-difference Laplace solve of the band. Neither calls the
package. The sphere and the hemisphere are pinned against their own exact surface
identity at their *physical* radius, which is what makes the assignment per geometry:
a uniform 4 pi breaks the hemisphere by 2, and a uniform 2 pi breaks the sphere by 2.
"""

from __future__ import annotations

import math

import pytest

from neurostim import (
    CylindricalBandElectrode,
    DiscElectrode,
    HemisphericalElectrode,
    MicrowireElectrode,
    RectangularElectrode,
    RingElectrode,
    SphericalElectrode,
)
from neurostim.models import field

SIGMA = 0.35
CURRENT_UA = 100.0


def _planar():
    return (
        DiscElectrode(1000.0, "Pt"),
        RingElectrode(1000.0, 600.0, "Pt"),
        RectangularElectrode(700.0, 900.0, "Pt"),
    )


class TestPinAPlanarFarFieldIsTheHalfSpaceDisc:
    """The exact flush-disc potential against the package's field model, at 100a and 10a.

    Only one of the four combinations of field factor (2 pi, 4 pi) and access resistance
    (Newman, ``1/(2 pi sigma a)``) passes. So this cannot be made green by the 57 % error in
    the access resistance that v1's false invariant would have forced.
    """

    @pytest.mark.parametrize("electrode", _planar(), ids=lambda e: e.shape_name)
    @pytest.mark.parametrize(("multiple", "rel"), [(100.0, 1e-4), (10.0, 1e-2)])
    def test_the_far_field_matches_the_exact_disc(self, electrode, multiple, rel):
        import oracles

        a_um = electrode.equivalent_radius_um
        expected = oracles.disc_potential_V(
            CURRENT_UA * 1e-6, SIGMA, a_um * 1e-6, multiple * a_um * 1e-6
        )
        got = field.potential_V(CURRENT_UA, multiple * a_um, SIGMA, electrode=electrode)
        assert got == pytest.approx(expected, rel=rel)

    def test_the_disc_access_resistance_is_still_newman(self):
        """The pin is not satisfied by moving R: the disc keeps ``1/(4 sigma a)``."""
        from oracles.disc_field import newman_disc_resistance_ohm

        disc = DiscElectrode(1000.0, "Pt")
        assert disc.access_resistance_ohm(SIGMA) == pytest.approx(
            newman_disc_resistance_ohm(SIGMA, 500e-6), rel=1e-15
        )


class TestPinBSurfaceIdentityAtThePhysicalRadius:
    """``V(a) == I * R_access`` exactly, for the two geometries where both are exact."""

    @pytest.mark.parametrize(
        "electrode",
        [SphericalElectrode(400.0, "Pt"), HemisphericalElectrode(400.0, "Pt")],
        ids=lambda e: e.shape_name,
    )
    def test_the_surface_potential_is_i_times_r(self, electrode):
        radius = electrode.radius_um
        surface = field.potential_V(CURRENT_UA, radius, SIGMA, electrode=electrode)
        assert surface == pytest.approx(
            CURRENT_UA * 1e-6 * electrode.access_resistance_ohm(SIGMA), rel=1e-12
        )

    def test_the_assignment_is_per_geometry(self):
        """The sphere is full-space and the hemisphere half-space, by default."""
        assert SphericalElectrode(400.0).environment == "full_space"
        assert HemisphericalElectrode(400.0).environment == "half_space"


class TestPinCImmersedGeometriesUseTheEqualAreaSphere:
    """The band against a converged FV Laplace solve (``tests/oracles/fd_band``).

    Re-pinned at ledger 127. The first table was unconverged and certified "within 5 %"
    from aspect 0.39 to 2.0; against the converged table the sphere is +10.2 % at 0.39. The
    pins now state the accuracy the package documents, band by band, and that the sphere
    errs *high* -- toward a larger compliance requirement -- at every aspect solved.
    """

    @pytest.mark.parametrize(
        ("aspect", "bound"),
        [
            (1.0, 0.015), (1.181, 0.015), (2.0, 0.015),
            (0.39, 0.11), (0.5, 0.11), (4.0, 0.05),
            (0.2, 0.25), (10.0, 0.25),
        ],
    )
    def test_high_and_within_the_documented_bound(self, aspect, bound):
        import oracles

        band = CylindricalBandElectrode(1270.0, 1270.0 * aspect, "PtIr")
        fd = oracles.FD_BAND_REFERENCE[aspect]
        excess = band.access_resistance_ohm(0.35) / fd - 1.0
        assert 0.0 < excess < bound, (aspect, excess)

    def test_the_clinical_contact_is_the_equal_area_sphere(self):
        """``1/(4 pi sigma a)`` with ``4 pi a^2 = A``: 329.5 ohm, against 517.5 before.

        Not tautological: the expected value is the sphere formula written out here on the
        band's lateral area, and the converged solve puts the truth at 327.6 ohm (+0.6 %).
        """
        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        area_m2 = math.pi * 1270e-6 * 1500e-6
        a_m = math.sqrt(area_m2 / (4.0 * math.pi))
        assert band.access_resistance_ohm(0.35) == pytest.approx(
            1.0 / (4.0 * math.pi * 0.35 * a_m), rel=1e-12
        )
        assert band.access_resistance_ohm(0.35) == pytest.approx(329.5, abs=0.05)
        assert band.environment == "full_space"
        assert band.access_resistance_is_exact is False

    def test_the_microwire_is_immersed_too(self):
        wire = MicrowireElectrode(50.0, 200.0, "flat")
        area_m2 = wire.area_um2 * 1e-12
        a_m = math.sqrt(area_m2 / (4.0 * math.pi))
        assert wire.environment == "full_space"
        assert wire.access_resistance_ohm(0.35) == pytest.approx(
            1.0 / (4.0 * math.pi * 0.35 * a_m), rel=1e-12
        )

    def test_the_field_of_an_immersed_geometry_is_full_space(self):
        """The band's far field is the 4 pi point source, and at its own equal-area
        sphere radius it reads I * R: the field and the resistance agree."""
        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        a_um = math.sqrt(band.area_um2 / (4.0 * math.pi))
        assert field.potential_V(CURRENT_UA, a_um, SIGMA, electrode=band) == pytest.approx(
            CURRENT_UA * 1e-6 * band.access_resistance_ohm(SIGMA), rel=1e-12
        )


class TestTheEnvironmentIsAnInstanceField:
    """Physics M5: a class default, overridable, because presets model immersed
    electrodes as equal-area discs."""

    def test_class_defaults(self):
        for electrode in _planar():
            assert electrode.environment == "half_space"
        assert CylindricalBandElectrode(1270.0, 1500.0).environment == "full_space"

    def test_an_immersed_disc_takes_the_sphere_and_the_full_space_field(self):
        disc = DiscElectrode(91.0, "AIROF", environment="full_space")
        a_m = math.sqrt(disc.area_um2 * 1e-12 / (4.0 * math.pi))
        assert disc.access_resistance_ohm(SIGMA) == pytest.approx(
            1.0 / (4.0 * math.pi * SIGMA * a_m), rel=1e-12
        )
        assert disc.access_resistance_is_exact is False
        assert field.potential_V(1.0, 1000.0, SIGMA, electrode=disc) == pytest.approx(
            1e-6 / (4.0 * math.pi * SIGMA * 1e-3), rel=1e-12
        )

    def test_an_unknown_environment_is_refused(self):
        with pytest.raises(ValueError, match="environment"):
            DiscElectrode(100.0, "Pt", environment="vacuum")  # type: ignore[arg-type]

    def test_a_disc_standing_in_for_another_shape_is_not_exact(self):
        """Ledger 21: a preset's note can say 'equal-area disc' while describe() printed
        '(exact)'."""
        disc = DiscElectrode(228.4, "AIROF", stands_in_for="a protruding wire stub")
        assert disc.environment == "half_space"
        assert disc.access_resistance_is_exact is False
        assert "(exact)" not in disc.describe()


class TestPresetsAreTaggedFromTheirSources:
    """Each preset's environment and exactness, from what its paper describes."""

    @pytest.mark.parametrize(
        ("key", "environment", "exact"),
        [
            ("rose_robblee_typeA", "half_space", True),  # disc in a silicone support
            ("beebe_iridium_wire", "half_space", False),  # stub through a septum
            ("mccreery_microelectrode", "full_space", False),  # penetrating, faceted
            ("mccreery2010_chronic", "full_space", False),  # penetrating
            ("weiland_tin", "half_space", False),  # source not in the library
        ],
    )
    def test_the_tag(self, key, environment, exact):
        from neurostim.electrodes import electrode

        e = electrode(key)
        assert e.environment == environment
        assert e.access_resistance_is_exact is exact


class TestTheFemComparisonUsesTheElectrode:
    """Physics m4: ``compare_with_point_source`` called ``potential_V`` with no electrode, so
    it would have compared an imported planar field against a full-space source."""

    def test_an_exact_disc_field_compares_to_one_far_out(self):
        import numpy as np
        import oracles

        from neurostim.io.fem import FEMField, compare_with_point_source

        disc = DiscElectrode(1000.0, "Pt")
        r = np.array([50.0, 100.0, 200.0, 400.0]) * 500.0
        points = np.column_stack([np.zeros_like(r), np.zeros_like(r), r])
        exact = np.array(
            [oracles.disc_potential_V(1e-4, SIGMA, 500e-6, x * 1e-6) for x in r]
        )
        imported = FEMField(points_um=points, potential_V=exact, current_uA=100.0)
        table = compare_with_point_source(imported, 100.0, SIGMA, electrode=disc)
        assert np.allclose(table["ratio"], 1.0, rtol=1e-3)


class TestTheCurrentDistributionIsTheGeometrys:
    """Ledger 18 (C3.2). The disc's primary distribution was printed for every geometry.

    ``J(r)/J_avg = 0.5 / sqrt(1 - (r/a)^2)`` is the flush disc: its centre runs at half the
    average, its outer 25 % runs above it, and the density diverges at the rim. For a
    sphere, and for a hemisphere flush in its plane, the primary distribution is uniform:
    ``J = I/A`` everywhere, with no edge. A band, ring, rectangle or microwire crowds at
    its own edges, but not with the disc's numbers. No closed form is used for those here,
    and the package says so instead of borrowing the disc's.
    """

    @staticmethod
    def _density(electrode):
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            electrode, StimProtocol(100.0, 200.0, 130.0, 1.0)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Current density")
        return assessment, check

    @pytest.mark.parametrize(
        "electrode",
        [SphericalElectrode(400.0, "Pt"), HemisphericalElectrode(400.0, "Pt")],
        ids=lambda e: e.shape_name,
    )
    def test_a_sphere_and_a_hemisphere_are_uniform(self, electrode):
        """Not tautological: the expected values are the uniform distribution's own, 1 and
        0, written here. The disc's are 0.5 and 0.25."""
        from neurostim.safety import current_density as jd

        result = jd.evaluate(100.0, electrode.area_cm2, 200.0, electrode=electrode)
        assert result.distribution == "uniform"
        assert result.centre_ratio == 1.0
        assert result.fraction_above_average == 0.0
        text = result.describe()
        assert "diverges at the rim" not in text
        assert "uniform" in text
        with pytest.raises(ValueError, match="disc"):
            result.ratio_at_area_fraction(0.25)

    def test_the_disc_keeps_its_own_distribution(self):
        from neurostim.safety import current_density as jd

        disc = DiscElectrode(500.0, "Pt")
        result = jd.evaluate(100.0, disc.area_cm2, 200.0, electrode=disc)
        assert result.distribution == "disc"
        assert result.centre_ratio == 0.5
        assert result.fraction_above_average == 0.25
        assert result.ratio_at_area_fraction(0.25) == pytest.approx(1.0)
        assert "diverges at the rim" in result.describe()

    @pytest.mark.parametrize(
        "electrode",
        [
            RingElectrode(1000.0, 600.0, "Pt"),
            RectangularElectrode(700.0, 900.0, "Pt"),
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            MicrowireElectrode(50.0, 200.0, "flat"),
            DiscElectrode(91.0, "AIROF", environment="full_space", stands_in_for="a tip"),
        ],
        ids=lambda e: e.shape_name,
    )
    def test_other_geometries_do_not_borrow_the_discs_numbers(self, electrode):
        from neurostim.safety import current_density as jd

        result = jd.evaluate(100.0, electrode.area_cm2, 200.0, electrode=electrode)
        assert result.distribution == "edge"
        assert result.centre_ratio is None
        assert result.fraction_above_average is None
        text = result.describe()
        assert "0.50x" not in text
        assert "25 %" not in text
        assert "edges" in text

    def test_the_assessment_threads_the_electrode(self):
        """The API change v1 hid (execution M12): ``evaluate`` had no electrode parameter,
        so the assessment could not have passed one."""
        _, check = self._density(SphericalElectrode(400.0, "Pt"))
        assert "uniform" in check.detail
        assert "diverges at the rim" not in check.detail

    @pytest.mark.parametrize(
        "electrode",
        [SphericalElectrode(400.0, "Pt"), CylindricalBandElectrode(1270.0, 1500.0, "PtIr")],
        ids=lambda e: e.shape_name,
    )
    def test_no_margin_or_limit_moves(self, electrode):
        """The Butterwick comparison uses the average, not the peak, so the distribution is
        reporting only.

        Not tautological: the comparison without the electrode (the old code path) and with
        it are computed separately and compared bit for bit.
        """
        from neurostim.safety import current_density as jd

        without = jd.evaluate(100.0, electrode.area_cm2, 200.0)
        with_electrode = jd.evaluate(100.0, electrode.area_cm2, 200.0, electrode=electrode)
        assert with_electrode.threshold == without.threshold
        assert with_electrode.average_A_per_cm2 == without.average_A_per_cm2


class TestTheEqualAreaDiscIsAnUpperBoundForPlanarShapes:
    """Ledger 10 (C3.3). Among plane shapes of equal area the disc has the least capacity,
    so the most resistance (Polya & Szego). The equal-area disc therefore *over*estimates
    a ring's or a rectangle's access resistance: an upper bound, conservative for
    compliance. Both docstrings said the opposite, so a reader correcting in the stated
    direction would add margin the wrong way.
    """

    @pytest.mark.parametrize(
        ("aspect", "ratio"), [(2, 1.030), (5, 1.165), (10, 1.344), (50, 2.096)]
    )
    def test_an_elongated_shape_is_below_its_equal_area_disc(self, aspect, ratio):
        """Not tautological: the reference is the exact elliptic disc,
        ``K(e) / (2 pi sigma a)``, computed by the oracle with an AGM, for an ellipse of
        the rectangle's area and aspect."""
        from oracles import planar_bounds

        width = 100.0 * math.sqrt(math.pi / aspect)
        rect = RectangularElectrode(width, width * aspect, "Pt")
        a = 100e-6 * math.sqrt(aspect)
        b = 100e-6 / math.sqrt(aspect)
        exact_ellipse = planar_bounds.elliptic_disc_resistance_ohm(SIGMA, a, b)
        package = rect.access_resistance_ohm(SIGMA)
        assert package > exact_ellipse
        assert package / exact_ellipse == pytest.approx(ratio, abs=5e-4)

    def test_a_thin_ring_is_far_below_its_equal_area_disc(self):
        """The audit's case: 200 um across, 1 um wide. The equal-area disc gives
        50 634 ohm and the thin-ring asymptote about 11 682, so the substitution is 4.33x
        high, not low."""
        from oracles import planar_bounds

        ring = RingElectrode(200.0, 198.0, "Pt")
        package = ring.access_resistance_ohm(SIGMA)
        thin = planar_bounds.thin_ring_resistance_ohm(SIGMA, 200e-6, 1e-6)
        assert package == pytest.approx(50634.4, abs=0.1)
        assert package / thin == pytest.approx(4.33, abs=0.01)

    @pytest.mark.parametrize("cls", [RingElectrode, RectangularElectrode])
    def test_the_docstring_states_the_direction_the_inequality_shows(self, cls):
        doc = " ".join((cls.__doc__ or "").split())
        assert "overestimates" in doc
        assert "underestimates" not in doc
        assert "higher access resistance than the equal-area" not in doc


class TestContradictoryGeometryInputsAreRefused:
    """Ledgers 28 and 29 (C3.4). Inputs that silently produced a meaningless geometry."""

    def test_a_nan_pitch_is_refused(self):
        """``pitch_um <= 0`` is False for NaN, so ``linear_array(disc, 3, nan)`` built an
        array whose minimum pitch was NaN."""
        from neurostim.geometry import grid_array, linear_array

        disc = DiscElectrode(100.0)
        for bad in (math.nan, math.inf, -math.inf):
            with pytest.raises(ValueError, match="pitch_um"):
                linear_array(disc, 3, bad)
            with pytest.raises(ValueError, match="pitch_um"):
                grid_array(disc, 2, 2, bad)

    def test_coincident_sites_are_refused(self):
        """Two sites at one point returned a minimum pitch of 0.0 and a field that
        diverges between them."""
        from neurostim.geometry.arrays import ArraySite, ElectrodeArray

        disc = DiscElectrode(100.0)
        with pytest.raises(ValueError, match="coincide"):
            ElectrodeArray(sites=(ArraySite(disc, 0, 0, 0), ArraySite(disc, 0, 0, 0)))

    def test_a_non_finite_site_position_is_refused(self):
        from neurostim.geometry.arrays import ArraySite

        with pytest.raises(ValueError, match="finite"):
            ArraySite(DiscElectrode(100.0), x_um=math.nan)

    @pytest.mark.parametrize("tip", ["flat", "hemispherical"])
    def test_a_cone_height_on_a_non_conical_tip_is_refused(self, tip):
        """``MicrowireElectrode(50, 0, "flat", 999999.)`` had the area of the plain flat
        wire: the cone height was silently ignored."""
        with pytest.raises(ValueError, match="cone_height_um"):
            MicrowireElectrode(50.0, 0.0, tip, 999999.0)

    def test_a_conical_tip_still_needs_and_uses_its_height(self):
        wire = MicrowireElectrode(50.0, 0.0, "conical", 100.0)
        assert wire.tip_area_um2 == pytest.approx(math.pi * 25.0 * math.sqrt(25.0**2 + 100.0**2))


class TestTheCounterElectrodeEntersTheVoltageBudget:
    """Ledger 5 (C3.5, fix plan D7). The budget modelled one interface and one spreading
    resistance; a two-terminal pair has two of each.

    ``counter_electrode=None`` keeps the old arithmetic exactly, but the check says it is
    assuming a monopolar single-interface budget and is never a bare PASS: under-estimating
    the required voltage is the anti-conservative direction, and the stimulator drops out
    of regulation silently.
    """

    BAND = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")

    def _compliance(self, **kwargs):
        from neurostim import SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            self.BAND,
            StimProtocol(1000.0, 90.0, 130.0, 1.0),
            capacitance_uF_cm2=250.0,
            compliance_V=10.0,
            **kwargs,
        )
        assessment = calc.assess()
        check = next(c for c in assessment.checks if c.name == "Compliance voltage")
        return assessment.compliance, check

    def test_without_a_counter_the_number_is_unchanged_but_the_check_cautions(self):
        """0.3354767487193873 V is C3.1's value for this protocol, a pre-change literal."""
        result, check = self._compliance()
        assert result.required_V == 0.3354767487193873
        assert result.utilisation < 0.8  # would have been a bare PASS
        assert check.status.value == "CAUTION"
        assert "monopolar" in check.summary
        assert "counter_electrode" in check.summary

    def test_two_identical_immersed_contacts_are_not_twice_one(self):
        """D7: ``R = (1/(2 pi sigma)) (1/a - 1/d)`` for two equal-area spheres of radius a
        at separation d. Two 3389 contacts at 2 mm: about 431.6 ohm against 658.9 naive.

        Not tautological: the expected resistance is D7's formula written out on the band's
        equal-area sphere radius, not the package's superposition expression.
        """
        result, _ = self._compliance(counter_electrode=self.BAND, counter_separation_um=2000.0)
        a_m = math.sqrt(self.BAND.area_um2 * 1e-12 / (4.0 * math.pi))
        expected = (1.0 / (2.0 * math.pi * 0.35)) * (1.0 / a_m - 1.0 / 2e-3)
        assert result.total_resistance_ohm == pytest.approx(expected, rel=1e-12)
        assert result.total_resistance_ohm == pytest.approx(431.56, abs=0.01)

    def test_the_ratio_is_between_one_and_two(self):
        mono, _ = self._compliance()
        near, _ = self._compliance(counter_electrode=self.BAND, counter_separation_um=2000.0)
        far, _ = self._compliance(counter_electrode=self.BAND, counter_separation_um=1e12)
        ratio = near.required_V / mono.required_V
        assert 1.0 < ratio <= 2.0 + 1e-12
        assert near.required_V < far.required_V

    def test_far_apart_two_identical_interfaces_need_exactly_twice_one(self):
        """The mutual term vanishes and ohmic and polarisation terms each double.

        TiN, not Pt: the counter carries the opposite phase, and the package derives each
        material's capacitance per polarity from its own CIC and half-window. For Pt the
        two polarities differ (125 against 250 uF/cm^2), so a Pt counter polarises twice as
        much as the Pt contact and the ratio is not 2 (ledger 8's half-window is revisited
        at C4.2). TiN's two polarities agree, so here the interfaces really are identical.
        """
        from neurostim import SafetyCalculator, StimProtocol
        from neurostim.safety.water_window import effective_capacitance_uF_cm2

        band = CylindricalBandElectrode(1270.0, 1500.0, "TiN")
        assert effective_capacitance_uF_cm2(
            "TiN", anodic_first=True
        ) == effective_capacitance_uF_cm2("TiN", anodic_first=False)  # the premise

        def required(**kwargs):
            return SafetyCalculator(
                band, StimProtocol(1000.0, 90.0, 130.0, 1.0), compliance_V=10.0, **kwargs
            ).assess().compliance.required_V

        far = required(counter_electrode=band, counter_separation_um=1e12)
        assert far / required() == pytest.approx(2.0, rel=1e-8)

    def test_two_flush_discs_share_a_half_space(self):
        """Two flush discs on one insulating plane see each other through the half-space
        point source, ``I / (2 pi sigma d)`` per side, so the mutual term is
        ``2 / (2 pi sigma d)``."""
        from neurostim import SafetyCalculator, StimProtocol

        disc = DiscElectrode(500.0, "Pt")
        result = SafetyCalculator(
            disc,
            StimProtocol(100.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
            counter_electrode=disc,
            counter_separation_um=5000.0,
        ).assess().compliance
        newman = 1.0 / (4.0 * 0.35 * 250e-6)
        expected = 2.0 * newman - 2.0 / (2.0 * math.pi * 0.35 * 5e-3)
        assert result.total_resistance_ohm == pytest.approx(expected, rel=1e-12)

    def test_the_counter_interface_polarises_too(self):
        """A large, low-polarisation counter adds little; a small one adds its own
        excursion, charge over its own area."""
        small = SphericalElectrode(200.0, "Pt")
        large = SphericalElectrode(20000.0, "Pt")
        with_small, _ = self._compliance(counter_electrode=small, counter_separation_um=1e7)
        with_large, _ = self._compliance(counter_electrode=large, counter_separation_um=1e7)
        assert with_small.counter_polarisation_V > 100 * with_large.counter_polarisation_V

    def test_a_counter_clears_the_assumption_caution(self):
        _, check = self._compliance(counter_electrode=self.BAND, counter_separation_um=2000.0)
        assert check.status.value == "PASS"
        assert "monopolar" not in check.summary

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"counter_electrode": DiscElectrode(500.0)},
            {"counter_separation_um": 2000.0},
            {"counter_electrode": DiscElectrode(500.0), "counter_separation_um": math.nan},
            {"counter_electrode": DiscElectrode(500.0), "counter_separation_um": 400.0},
            {"counter_electrode": SphericalElectrode(500.0), "counter_separation_um": 5000.0},
            {
                "counter_electrode": DiscElectrode(500.0),
                "counter_separation_um": 5000.0,
                "measured_impedance_ohm": 1000.0,
            },
        ],
        ids=["no-separation", "no-counter", "nan", "overlapping", "mixed-space", "measured"],
    )
    def test_contradictory_counter_settings_are_refused(self, kwargs):
        from neurostim import SafetyCalculator, StimProtocol

        with pytest.raises(ValueError, match="counter"):
            SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 130.0, 1.0), **kwargs
            ).assess()


class TestTheLeadResistanceIsInTheBudget:
    """T18 (ledger 69). ``lead_resistance_ohm`` was non-zero nowhere in the suite, so a
    mutant dropping it from the budget survived."""

    def test_two_kiloohms_add_ohms_law_and_lower_the_limit(self):
        from neurostim import SafetyCalculator, StimProtocol

        def compliance(lead):
            return SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(1000.0, 200.0, 130.0, 1.0),
                compliance_V=5.0,
                lead_resistance_ohm=lead,
            ).assess().compliance

        bare, leaded = compliance(0.0), compliance(2000.0)
        assert leaded.required_V - bare.required_V == pytest.approx(1000e-6 * 2000.0, rel=1e-12)
        assert leaded.max_current_uA < bare.max_current_uA


class TestThePdfStatesWhichBudgetItUsed:
    """The PDF's "Required compliance" row broke the requirement into ohmic plus
    polarisation. With a counter electrode that sum would omit the counter's own
    polarisation and stop adding up; without one it would hide the assumption."""

    @staticmethod
    def _row(tmp_path, **kwargs):
        import re
        import shutil
        import subprocess

        from neurostim import SafetyCalculator, StimProtocol
        from neurostim.io import build_report

        if shutil.which("pdftotext") is None:  # pragma: no cover - environment dependent
            pytest.skip("pdftotext (poppler) not available")
        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        calc = SafetyCalculator(
            band, StimProtocol(3000.0, 90.0, 130.0, 1.0), compliance_V=10.0, **kwargs
        )
        out = build_report(calc, tmp_path / "r.pdf")
        text = subprocess.run(
            ["pdftotext", "-layout", str(out), "-"], capture_output=True, text=True,
            check=True,
        ).stdout
        return re.sub(r"\s+", " ", text), calc.assess().compliance

    def test_with_a_counter_the_breakdown_adds_up(self, tmp_path):
        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        text, result = self._row(
            tmp_path, counter_electrode=band, counter_separation_um=2000.0
        )
        assert f"{result.counter_polarisation_V:.3f} V counter polarisation" in text
        assert "counter electrode at 2000 um" in text

    def test_without_a_counter_the_assumption_is_on_the_row(self, tmp_path):
        text, _ = self._row(tmp_path)
        assert "monopolar single-interface budget" in text


class TestShannonSaysItWasFitOnDiscs:
    """Ledger 12 (C3.6). Shannon (1992): "the limit of safe stimulation is linearly related
    to electrode diameter, not electrode area. This result is probably due to the charge
    'building up' at the edges". The criterion ``Q_max = sqrt(A * 10^k)`` is written in
    area and fit on disc-shaped surface electrodes, so a ring and a disc of equal area get
    the same limit despite about three times the perimeter.

    The limit's value is not changed: no source gives a perimeter form. What changes is
    that a non-disc geometry cannot get an unqualified PASS, and its limit is flagged
    ``provisional`` so the caveat is visible when it binds (physics m6).
    """

    PROTOCOL_KW = {"current_uA": 50.0, "pulse_width_us": 400.0, "frequency_hz": 50.0,
                   "train_duration_s": 7 * 3600.0}

    @classmethod
    def _shannon(cls, electrode):
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(electrode, StimProtocol(**cls.PROTOCOL_KW)).assess()
        return assessment, next(c for c in assessment.checks if c.name == "Shannon criterion")

    def test_a_disc_keeps_its_unqualified_pass(self):
        """The premise, asserted: this protocol on a real disc is a bare PASS."""
        _, check = self._shannon(DiscElectrode(2000.0, "Pt"))
        assert check.status.value == "PASS"
        assert check.provisional is False

    @pytest.mark.parametrize(
        "electrode",
        [
            RingElectrode(2400.0, 1327.0, "Pt"),
            RectangularElectrode(1000.0, 3141.6, "Pt"),
            CylindricalBandElectrode(1270.0, 787.4, "PtIr"),
            MicrowireElectrode(250.0, 3875.0, "flat"),
            SphericalElectrode(1000.0, "Pt"),
            HemisphericalElectrode(1414.2, "Pt"),
            DiscElectrode(2000.0, "Pt", stands_in_for="a faceted tip"),
        ],
        ids=lambda e: e.shape_name,
    )
    def test_a_non_disc_is_never_a_bare_pass_and_is_provisional(self, electrode):
        """Not tautological: the premise test above shows the same protocol is a bare PASS
        on a disc; each of these is within a few per cent of the disc's area."""
        disc_area = DiscElectrode(2000.0).area_cm2
        assert electrode.area_cm2 == pytest.approx(disc_area, rel=0.03)  # the premise
        _, check = self._shannon(electrode)
        assert check.status.value == "CAUTION", check.summary
        assert check.provisional is True
        assert "diameter" in check.detail

    def test_the_limit_value_does_not_move(self):
        """Section 6 says so: the criterion's number is unchanged, only its standing."""
        from neurostim.safety import shannon

        ring = RingElectrode(2400.0, 1327.0, "Pt")
        _, check = self._shannon(ring)
        assert check.ceiling_uA == shannon.shannon_max_current_uA(ring.area_cm2, 400.0)


class TestTheReturnPhaseOnlyPolarisesPastRest:
    """Ledger 135 (Phase 3b review J1), which replaces C3.9's H5 tests.

    Under the package's capacitor model a return phase that does not overshoot rest only
    discharges the leading phase's polarity branch, so the stimulator never needs more than
    ``I_ret R`` for it. Only an overshoot, ``(r_a - 1) Q``, reaches the opposite branch and
    polarises at the opposite polarity's C_eff. That holds on both electrodes: the counter
    was charged on its opposite branch by the leading phase, and overshoots onto the leading
    polarity's branch.

    C3.9 (ledger 131, H5, retracted by the reviewer) gave the whole return charge the
    opposite polarity's C_eff. Its tests asserted that, and are replaced here. The expected
    values come from ``oracles.peak_stimulator_voltage_V``, which steps the same circuit
    through both phases with polarity-branched capacitors and evaluates no closed form.
    """

    @staticmethod
    def _c(material, anodic):
        from neurostim.safety.water_window import effective_capacitance_uF_cm2

        return effective_capacitance_uF_cm2(material, anodic_first=anodic)

    @pytest.mark.parametrize("material", ["Pt", "TiN"])
    @pytest.mark.parametrize("recovery", [0.8, 1.0, 1.3])
    @pytest.mark.parametrize("ratio", [1.0, 0.25])
    @pytest.mark.parametrize("anodic_first", [False, True])
    @pytest.mark.parametrize("with_counter", [False, True])
    @pytest.mark.parametrize("pulses", [1, 5])
    def test_the_requirement_is_the_stepped_circuits_peak(
        self, material, recovery, ratio, anodic_first, with_counter, pulses
    ):
        """Not tautological: Pt's two branches differ (250 against 125 uF/cm^2) and TiN's
        agree, and the oracle integrates the circuit rather than evaluating the package's
        per-phase expression.

        Stepped over the whole train since ledger 140 (G12: this test used a 1 s train at
        130 Hz against a one-pulse oracle, which stopped being the package's model once the
        train's DC offset entered the budget). Trains of 1 and 5 pulses, short enough that
        the water-window cap does not bind; the cap has its own tests below.
        """
        import oracles

        from neurostim import SafetyCalculator, StimProtocol

        active = DiscElectrode(500.0, material)
        counter = DiscElectrode(900.0, material)
        kwargs = (
            {"counter_electrode": counter, "counter_separation_um": 20000.0}
            if with_counter else {}
        )
        protocol = StimProtocol(
            300.0, 200.0, 100.0, pulses / 100.0, anodic_first=anodic_first,
            return_phase_ratio=ratio, charge_recovery_ratio=recovery,
        )
        assert math.ceil(protocol.n_pulses) == pulses  # the premise
        result = SafetyCalculator(active, protocol, compliance_V=10.0, **kwargs).assess().compliance
        assert result.offset_V < result.offset_cap_V  # the premise: the cap does not bind
        expected = oracles.peak_stimulator_voltage_V(
            pulses=pulses, steps=2_000,
            current_uA=300.0, pulse_width_us=200.0, return_phase_ratio=ratio,
            recovered_fraction=recovery, anodic_first=anodic_first,
            resistance_ohm=result.total_resistance_ohm, area_cm2=active.area_cm2,
            c_cathodic_uF_cm2=self._c(material, False), c_anodic_uF_cm2=self._c(material, True),
            **(
                {
                    "counter_area_cm2": counter.area_cm2,
                    "counter_c_cathodic_uF_cm2": self._c(material, False),
                    "counter_c_anodic_uF_cm2": self._c(material, True),
                }
                if with_counter else {}
            ),
        )
        # The offset itself, pinned: N - 1 residues at the offset branch's C_eff (the
        # leading one for under-recovery, the opposite one for over-recovery).
        residue = abs(1.0 - recovery) * (pulses - 1)
        if recovery < 1.0:
            assert result.offset_V == pytest.approx(residue * result.polarisation_V, rel=1e-12)
            if with_counter:
                assert result.counter_offset_V == pytest.approx(
                    residue * result.counter_polarisation_V, rel=1e-12
                )
        elif recovery > 1.0:
            density = 300.0 * 200.0 * 1e-6 / active.area_cm2
            assert result.offset_V == pytest.approx(
                residue * density / result.return_capacitance_uF_cm2, rel=1e-12
            )
            if with_counter:
                assert result.counter_offset_V == pytest.approx(
                    residue * (300.0 * 200.0 * 1e-6 / counter.area_cm2)
                    / result.counter_return_capacitance_uF_cm2,
                    rel=1e-12,
                )
        if recovery >= 1.0 or result.return_required_V < result.required_V:
            # Over-recovery, and any pulse whose leading phase binds, is exact: the last
            # pulse's leading phase (or overshoot) is the stepped circuit's peak.
            assert result.required_V == pytest.approx(expected, rel=1e-9)
        else:
            # Under-recovery ends the last return phase with the train's residue,
            # N (1 - r_a) of the leading excursion, still stored on the leading branch and
            # opposing the drive, so the stepped peak can sit below I_ret R by up to that
            # residue. The package keeps I_ret R there, as the review specified: an upper
            # bound, conservative by at most the residue.
            residual = pulses * (1.0 - recovery) * result.polarisation_V
            if with_counter:
                residual += pulses * (1.0 - recovery) * result.counter_polarisation_V
            assert expected * (1.0 - 1e-12) <= result.required_V <= expected + residual * (
                1.0 + 1e-9
            )

    def test_the_worked_example_is_restored_exactly(self):
        """0.8286922987786409 V and 965.3764143567779 uA, the values before C3.9: a symmetric
        balanced pulse is bound by its leading phase."""
        from oracles.fail_ceiling import check_fail_ceiling_uA

        from neurostim import SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        result = calc.assess().compliance
        assert result.required_V == 0.8286922987786409
        assert result.max_current_uA == 965.3764143567779
        assert check_fail_ceiling_uA(calc, "Compliance voltage") == pytest.approx(
            965.3764143567779, rel=1e-9
        )

    def test_a_measured_capacitance_still_applies_to_an_overshoot(self):
        """A measured capacitance_uF_cm2 is one value for the active interface, used for
        the overshoot as for the leading phase, and for the train offset the overshoots
        build (ledger 140).

        G12: the train was 1 s at 130 Hz, whose offset now enters the return phase and
        reaches the water-window cap there. At 0.05 s the train delivers ceil(6.5) = 7
        pulses, so the offset is 6 overshoots, below the 0.8 V cap.
        """
        from neurostim import SafetyCalculator, StimProtocol

        disc = DiscElectrode(500.0, "Pt")
        result = SafetyCalculator(
            disc, StimProtocol(200.0, 200.0, 130.0, 0.05, charge_recovery_ratio=1.5),
            compliance_V=10.0, capacitance_uF_cm2=300.0,
        ).assess().compliance
        overshoot = 0.5 * 200e-6 * 200e-6 * 1e6 / disc.area_cm2
        assert result.offset_pulses == 6.0  # the premise
        assert result.offset_V == pytest.approx(6.0 * overshoot / 300.0, rel=1e-12)
        assert result.offset_V < result.offset_cap_V
        assert result.return_required_V == pytest.approx(
            300e-6 * result.total_resistance_ohm + 7.0 * overshoot / 300.0, rel=1e-12
        )


class TestTheTrainOffsetIsInTheBudget:
    """Ledger 140. Under partial or over-recovery each pulse leaves ``|1 - r_a| Q`` on the
    interface, and under the leak-free capacitor model the drift clause uses, pulse ``N``
    starts ``(N - 1)`` residues from rest. The compliance budget took every pulse from rest.

    Expected values come from ``oracles.peak_stimulator_voltage_V`` stepped over the whole
    train, with the water window as a clamp on the active interface where the cap binds.
    """

    @staticmethod
    def _c(material, anodic):
        from neurostim.safety.water_window import effective_capacitance_uF_cm2

        return effective_capacitance_uF_cm2(material, anodic_first=anodic)

    @staticmethod
    def _calc(electrode, protocol, **kwargs):
        from neurostim import SafetyCalculator

        return SafetyCalculator(electrode, protocol, compliance_V=10.0, **kwargs)

    @pytest.mark.parametrize("material", ["Pt", "TiN"])
    @pytest.mark.parametrize("recovery", [0.8, 1.3])
    @pytest.mark.parametrize("anodic_first", [False, True])
    @pytest.mark.parametrize("with_counter", [False, True])
    def test_where_the_cap_binds_the_package_bounds_the_clamped_circuit(
        self, material, recovery, anodic_first, with_counter
    ):
        """200 pulses: the offset reaches the window edge. The stepped circuit holds the
        active interface at the edge and loses the charge beyond it; the package caps the
        offset alone and keeps the last pulse's own excursion on top, so it is high by at
        most that one excursion (the leading one for under-recovery, the overshoot for
        over-recovery). The counter is uncapped on both sides."""
        import oracles

        from neurostim import StimProtocol
        from neurostim.materials import get_material

        active = DiscElectrode(500.0, material)
        counter = DiscElectrode(900.0, material)
        kwargs = (
            {"counter_electrode": counter, "counter_separation_um": 20000.0}
            if with_counter else {}
        )
        protocol = StimProtocol(
            300.0, 200.0, 100.0, 2.0, anodic_first=anodic_first, charge_recovery_ratio=recovery
        )
        result = self._calc(active, protocol, **kwargs).assess().compliance
        assert result.offset_V == result.offset_cap_V  # the premise: the cap binds
        window = get_material(material).water_window
        expected = oracles.peak_stimulator_voltage_V(
            current_uA=300.0, pulse_width_us=200.0, return_phase_ratio=1.0,
            recovered_fraction=recovery, anodic_first=anodic_first,
            resistance_ohm=result.total_resistance_ohm, area_cm2=active.area_cm2,
            c_cathodic_uF_cm2=self._c(material, False), c_anodic_uF_cm2=self._c(material, True),
            pulses=200, steps=100, active_window_V=(-window.cathodic_V, window.anodic_V),
            **(
                {
                    "counter_area_cm2": counter.area_cm2,
                    "counter_c_cathodic_uF_cm2": self._c(material, False),
                    "counter_c_anodic_uF_cm2": self._c(material, True),
                }
                if with_counter else {}
            ),
        )
        density = 300.0 * 200.0 * 1e-6 / active.area_cm2
        excursion = (
            result.polarisation_V
            if recovery < 1.0
            else (recovery - 1.0) * density / result.return_capacitance_uF_cm2
        )
        assert expected * (1.0 - 1e-9) <= result.required_V <= expected + excursion * (
            1.0 + 1e-9
        )

    def test_the_offset_counts_the_pulses_the_duty_cycle_delivers(self):
        """``N = ceil(T f duty)``: 5 pulses at 5 % duty over 1 s at 100 Hz, and 6 at 5.2 %."""
        from neurostim import StimProtocol

        disc = DiscElectrode(500.0, "Pt")
        for duty, before in ((0.05, 4.0), (0.052, 5.0), (1.0, 99.0)):
            protocol = StimProtocol(
                100.0, 200.0, 100.0, 1.0, charge_recovery_ratio=0.9, train_duty_cycle=duty
            )
            result = self._calc(disc, protocol).assess().compliance
            assert result.offset_pulses == before, duty
            assert result.offset_factor == pytest.approx(before * 0.1, rel=1e-12), duty

    def test_a_balanced_waveform_is_unchanged_to_the_bit(self):
        """Charge balance's own test gates the offset, so a balanced train of any length
        gives the one-pulse requirement exactly, with and without a counter."""
        from dataclasses import replace

        from neurostim import StimProtocol

        for material in ("Pt", "SIROF"):
            for ratio in (1.0, 0.25):
                for kwargs in (
                    {},
                    {"counter_electrode": DiscElectrode(900.0, material),
                     "counter_separation_um": 20000.0},
                ):
                    one = StimProtocol(300.0, 200.0, 100.0, 0.01, return_phase_ratio=ratio)
                    disc = DiscElectrode(500.0, material)
                    single = self._calc(disc, one, **kwargs).assess().compliance
                    for train in (1.0, math.inf):
                        result = self._calc(
                            disc, replace(one, train_duration_s=train), **kwargs
                        ).assess().compliance
                        assert result.offset_factor == 0.0
                        assert result.required_V == single.required_V
                        assert result.max_current_uA == single.max_current_uA

    def test_the_cap_is_the_headroom_from_the_resting_potential(self):
        """A continuous train reaches the cap; from -0.2 V the cathodic headroom is 0.4 V,
        and the over-recovering drift heads for the anodic edge, 1.0 V away."""
        from neurostim import StimProtocol

        disc = DiscElectrode(500.0, "Pt")
        for recovery, cap in ((0.9, 0.4), (1.1, 1.0)):
            protocol = StimProtocol(100.0, 200.0, 100.0, math.inf, charge_recovery_ratio=recovery)
            result = self._calc(disc, protocol, resting_potential_V=-0.2).assess().compliance
            assert result.offset_cap_V == pytest.approx(cap, abs=1e-15)
            assert result.offset_V == result.offset_cap_V
            assert math.isfinite(result.required_V)

    @pytest.mark.parametrize(
        ("label", "material", "counter"),
        [("counter", "Pt", True), ("no window", "Ta2O5", False)],
    )
    def test_an_uncapped_continuous_offset_refuses_by_name(self, label, material, counter):
        """The counter (its window is not assessed) and a material with no window are not
        capped, so a continuous unbalanced train needs an infinite voltage: a ceiling of
        zero, a Compliance FAIL, and a refusal that names the check. No nan anywhere."""
        from dataclasses import fields

        from neurostim import StimProtocol

        kwargs = (
            {"counter_electrode": DiscElectrode(900.0, material), "counter_separation_um": 20000.0}
            if counter else {}
        )
        protocol = StimProtocol(100.0, 200.0, 100.0, math.inf, charge_recovery_ratio=0.9)
        assessment = self._calc(DiscElectrode(500.0, material), protocol, **kwargs).assess()
        result = assessment.compliance
        assert result.required_V == math.inf, label
        assert result.max_current_uA == 0.0, label
        check = next(c for c in assessment.checks if c.name == "Compliance voltage")
        assert check.status.value == "FAIL", label
        assert check.ceiling_uA == 0.0, label
        assert assessment.limiting_current_uA is None, label
        assert "Compliance voltage" in assessment.no_safe_amplitude_note(), label
        for entry in fields(result):
            value = getattr(result, entry.name)
            if isinstance(value, float):
                assert not math.isnan(value), (label, entry.name)
        assert "nan" not in assessment.describe(), label

    def test_the_offset_is_named_where_the_budget_is_shown(self):
        """describe() and the PDF report's row name the offset, its phase and its cap;
        a balanced train shows neither."""
        from neurostim import StimProtocol
        from neurostim.io.report import _required_compliance_text

        counter = {"counter_electrode": DiscElectrode(900.0, "Pt"),
                   "counter_separation_um": 20000.0}
        calc = self._calc(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(100.0, 200.0, 100.0, 0.05, charge_recovery_ratio=0.9),
            **counter,
        )
        result = calc.assess().compliance
        text = result.describe()
        assert "train offset  " in text and "on the leading phase after 4 unbalanced pulses" in text
        assert "counter off." in text
        row = _required_compliance_text(calc, result)
        assert f"train DC offset {result.offset_V:.3f} V" in row
        assert "on the leading phase" in row

        balanced = self._calc(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 100.0, 0.05), **counter
        )
        assert "offset" not in balanced.assess().compliance.describe()
        assert "offset" not in _required_compliance_text(
            balanced, balanced.assess().compliance
        )

    def test_the_back_solve_inverts_the_budget_across_the_cap(self):
        """The requirement is ``a I + min(b I, H)`` on the phase the offset lands on, so the
        closed-form seed is no longer a scaling. Over materials, recoveries, trains, counters
        and compliance voltages on both sides of the kink: no LimitDidNotSettle, and every
        ceiling is the float boundary of its own comparison."""
        from neurostim import SafetyCalculator, StimProtocol

        checked = 0
        for material in ("Pt", "TiN", "SIROF", "Ta2O5"):
            for recovery in (0.8, 0.95, 1.3):
                for train in (0.05, 1.0, math.inf):
                    for counter in (False, True):
                        for compliance_V in (0.3, 1.0, 3.0, 10.0, 50.0):
                            kwargs = (
                                {"counter_electrode": DiscElectrode(900.0, material),
                                 "counter_separation_um": 20000.0}
                                if counter else {}
                            )
                            result = SafetyCalculator(
                                DiscElectrode(500.0, material),
                                StimProtocol(
                                    100.0, 200.0, 130.0, train,
                                    charge_recovery_ratio=recovery,
                                ),
                                compliance_V=compliance_V, **kwargs,
                            ).assess().compliance
                            limit = result.max_current_uA
                            if limit == 0.0:
                                assert result.required_V_at(5e-324) > compliance_V
                            else:
                                assert result.required_V_at(limit) <= compliance_V
                                assert result.required_V_at(
                                    math.nextafter(limit, math.inf)
                                ) > compliance_V
                            checked += 1
        assert checked == 360

    def test_the_bisection_oracle_agrees_where_the_cap_binds(self):
        """Independent of the seed: a binary search over ``assess().failed``."""
        from oracles.fail_ceiling import check_fail_ceiling_uA

        from neurostim import SafetyCalculator, StimProtocol

        for recovery in (0.8, 1.3):
            for compliance_V in (1.0, 10.0):
                calc = SafetyCalculator(
                    DiscElectrode(500.0, "Pt"),
                    StimProtocol(100.0, 200.0, 130.0, math.inf, charge_recovery_ratio=recovery),
                    compliance_V=compliance_V,
                )
                limit = calc.assess().compliance.max_current_uA
                assert check_fail_ceiling_uA(calc, "Compliance voltage") == pytest.approx(
                    limit, rel=1e-9
                ), (recovery, compliance_V)


class TestTheSeparationGuardSeesTheWholeElectrode:
    """Ledger 130 (Phase 3 review H4). The guard used equal-area sphere radii, 690 um for a
    3389 contact. Two 1500 um bands on one shaft were accepted at centre spacings of
    1390-1499 um, where they overlap, and a resistance came back."""

    @pytest.mark.parametrize("spacing", [1390.0, 1400.0, 1499.0, 1500.0])
    def test_overlapping_bands_are_refused(self, spacing):
        from neurostim import SafetyCalculator, StimProtocol

        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        with pytest.raises(ValueError, match="counter_separation_um"):
            SafetyCalculator(
                band, StimProtocol(1000.0, 90.0, 130.0, 1.0),
                counter_electrode=band, counter_separation_um=spacing,
            )

    def test_the_clinical_spacings_are_accepted(self):
        """The 3389's 2 mm and the 3387's 3 mm centre spacings."""
        from neurostim import SafetyCalculator, StimProtocol

        band = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        for spacing in (2000.0, 3000.0):
            SafetyCalculator(
                band, StimProtocol(1000.0, 90.0, 130.0, 1.0),
                counter_electrode=band, counter_separation_um=spacing,
            )


class TestTheReachIsTheEnclosingSphere:
    """Ledger 139 (Phase 3b review J5). Half the largest dimension understates how far an
    electrode extends from its centre whenever it extends in two directions: a rectangle
    reaches half its diagonal, and a band or an exposed microwire reaches its rim,
    ``sqrt(r^2 + (L/2)^2)`` from the middle of its axial extent."""

    @staticmethod
    def _refused(electrode, spacing):
        from neurostim.safety.compliance import validate_counter

        try:
            validate_counter(electrode, electrode, spacing)
        except ValueError as error:
            assert "counter_separation_um" in str(error)
            return True
        return False

    @pytest.mark.parametrize(
        ("electrode", "reach_um"),
        [
            # half the diagonal of 300 x 400
            (RectangularElectrode(300.0, 400.0, "Pt"), 250.0),
            # sqrt(635^2 + 750^2)
            (CylindricalBandElectrode(1270.0, 1500.0, "PtIr"), math.hypot(635.0, 750.0)),
            # 100 um of shaft behind a 25 um hemispherical cap: axial extent 125 um
            (MicrowireElectrode(50.0, 100.0, tip_shape="hemispherical", material="PtIr"),
             math.hypot(25.0, 62.5)),
            # 100 um of shaft behind a 60 um cone: axial extent 160 um
            (MicrowireElectrode(
                50.0, 100.0, tip_shape="conical", cone_height_um=60.0, material="PtIr"
            ),
             math.hypot(25.0, 80.0)),
        ],
    )
    def test_two_identical_electrodes_are_refused_up_to_twice_the_reach(
        self, electrode, reach_um
    ):
        assert self._refused(electrode, 2.0 * reach_um * (1.0 - 1e-9))
        assert self._refused(electrode, 2.0 * reach_um)
        assert not self._refused(electrode, 2.0 * reach_um * (1.0 + 1e-9))

    @pytest.mark.parametrize(
        ("electrode", "reach_um"),
        [
            (DiscElectrode(200.0, "Pt"), 100.0),
            (RingElectrode(330.0, 270.0, "Pt"), 165.0),
            (SphericalElectrode(200.0, "Pt"), 100.0),
            (MicrowireElectrode(50.0, 0.0, tip_shape="flat", material="PtIr"), 25.0),
        ],
    )
    def test_a_body_with_one_extent_keeps_its_radius(self, electrode, reach_um):
        assert self._refused(electrode, 2.0 * reach_um)
        assert not self._refused(electrode, 2.0 * reach_um * (1.0 + 1e-9))


class TestADriftCautionHeaderSaysCaution:
    """Ledger 132 (Phase 3 review H6). C3.0 fixed the FAIL case; a drift that reaches the
    edge after the train is a CAUTION, and the detail header led with "PASS"."""

    def test_the_header_is_caution(self):
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(10.0, 50.0, 130.0, 1.0, charge_recovery_ratio=0.99),
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Water window")
        assert check.status.value == "CAUTION"  # the premise
        header = check.detail.splitlines()[0]
        assert "-> CAUTION (peak within window; drift reaches the edge after the train)" in header
        assert "PASS" not in header


class TestTheFlatMicrowireTipIsNotUnderstated:
    """Ledger 129 (Phase 3 review H3). A flat-tipped wire with no exposed shaft took the
    full-space sphere, 0.159/(sigma a), where a converged solve of a disc on the end of an
    insulating rod gives about 0.173: 8 % low, anti-conservative for the compliance budget.
    User decision: use Newman's half-space disc, 0.25/(sigma a), an upper bound, for that
    case, and keep the sphere elsewhere, with its measured error documented."""

    def test_a_bare_flat_tip_takes_newmans_disc(self):
        wire = MicrowireElectrode(50.0, 0.0, "flat")
        assert wire.access_resistance_ohm(SIGMA) == pytest.approx(
            1.0 / (4.0 * SIGMA * 25e-6), rel=1e-15
        )
        assert wire.access_resistance_is_exact is False
        assert "(exact)" not in wire.describe()

    def test_it_is_an_upper_bound_on_the_converged_solve(self):
        """Not tautological: the reference is the committed FV table, generated without the
        package; the sphere it replaces is below it."""
        import oracles

        reference = oracles.FD_MICROWIRE_REFERENCE[0.0]
        wire = MicrowireElectrode(50.0, 0.0, "flat")
        r_sigma_a = wire.access_resistance_ohm(SIGMA) * SIGMA * 25e-6
        assert r_sigma_a > reference * 1.02
        sphere = 1.0 / (4.0 * math.pi * math.sqrt(math.pi / (4.0 * math.pi)))
        assert sphere < reference  # the defect, written out

    @pytest.mark.parametrize("exposed", [0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0])
    def test_with_a_shaft_the_sphere_stays_within_its_documented_band(self, exposed):
        """-1.3 % at worst for 0.25a-5a, and high beyond: +6.7 % at 10a, +17 % at 20a."""
        import oracles

        wire = MicrowireElectrode(50.0, 25.0 * exposed, "flat")
        r_sigma_a = wire.access_resistance_ohm(SIGMA) * SIGMA * 25e-6
        excess = r_sigma_a / oracles.FD_MICROWIRE_REFERENCE[exposed] - 1.0
        bound = (-0.014, 0.015) if exposed <= 5.0 else (0.0, 0.18)
        assert bound[0] < excess < bound[1], (exposed, excess)

    @pytest.mark.parametrize("tip", ["hemispherical", "conical"])
    def test_other_bare_tips_stay_on_the_sphere(self, tip):
        wire = MicrowireElectrode(50.0, 0.0, tip, 30.0 if tip == "conical" else None)
        a_m = math.sqrt(wire.area_um2 * 1e-12 / (4.0 * math.pi))
        assert wire.access_resistance_ohm(SIGMA) == pytest.approx(
            1.0 / (4.0 * math.pi * SIGMA * a_m), rel=1e-12
        )

    def test_the_generator_reproduces_the_table(self):
        """A frozen table nothing can re-derive is a magic number: the 2a entry, rerun."""
        import importlib.util
        import sys
        from pathlib import Path

        import oracles

        path = Path(__file__).resolve().parents[1] / "scripts" / "fd_microwire_reference.py"
        spec = importlib.util.spec_from_file_location("fd_microwire_reference", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["fd_microwire_reference"] = module
        spec.loader.exec_module(module)
        value, order = module.converged(2.0)
        assert value == pytest.approx(oracles.FD_MICROWIRE_REFERENCE[2.0], rel=2e-3)
        assert 1.0 < order < 2.0


class TestTheCounterElectrodeIsAssessed:
    """Ledger 133 (Phase 3 review H7). Since C3.5 the counter's area and material are inputs,
    but its own charge injection was never checked: a small counter carrying the same charge
    at a higher density could exceed its limit and pass silently.

    User decision (a), CIC only: a limit-bearing "Counter charge injection" check. The
    counter sees the mirrored waveform, so a cathodic-first protocol is anodic-first at the
    counter, and the stored CICs are keyed by the waveform's leading polarity. Its phase
    charge density -- the larger of the two phases, so over-recovery is covered -- is
    compared against ``cic(anodic_first = not protocol.anodic_first)``, with the same policy,
    medium and derating as the active electrode.
    """

    @staticmethod
    def _assess(counter, protocol=None, **kwargs):
        from neurostim import SafetyCalculator, StimProtocol

        return SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            protocol or StimProtocol(100.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
            counter_electrode=counter,
            counter_separation_um=20000.0,
            **kwargs,
        ).assess()

    @staticmethod
    def _counter(assessment):
        return next(c for c in assessment.checks if c.name == "Counter charge injection")

    def test_a_small_counter_fails_its_own_limit_and_binds(self):
        """Not tautological: the expected ceiling is Pt's anodic-first conservative CIC,
        50 uC/cm^2 (Rose & Robblee), times the counter's area over the pulse width, written
        out; the active 500 um disc alone would allow far more."""
        from neurostim.materials import get_material

        small = DiscElectrode(80.0, "Pt")
        assessment = self._assess(small)
        check = self._counter(assessment)
        limit = get_material("Pt").cic_uC_cm2("conservative", anodic_first=True)
        assert limit == 50.0  # the premise: cathodic-first protocol, anodic-first at the counter
        expected = limit * small.area_cm2 / 200e-6
        assert check.status.value == "FAIL"
        assert check.ceiling_uA == pytest.approx(expected, rel=1e-12)
        assert assessment.limiting_mechanism == "Counter charge injection"
        assert assessment.limiting_current_uA == check.ceiling_uA

    def test_a_large_counter_passes_and_does_not_bind(self):
        assessment = self._assess(DiscElectrode(5000.0, "Pt"))
        check = self._counter(assessment)
        assert check.status.value == "PASS"
        assert assessment.limiting_mechanism != "Counter charge injection"

    def test_over_recovery_is_judged_on_the_larger_return_phase(self):
        """A return phase recovering 150 % carries 1.5x the leading charge through the
        counter, so the ceiling is two thirds of the leading-phase one."""
        from neurostim import StimProtocol

        counter = DiscElectrode(300.0, "Pt")
        balanced = self._counter(self._assess(counter))
        over = self._counter(
            self._assess(counter, StimProtocol(100.0, 200.0, 130.0, 1.0, charge_recovery_ratio=1.5))
        )
        assert over.ceiling_uA == pytest.approx(balanced.ceiling_uA / 1.5, rel=1e-12)

    def test_monophasic_is_not_evaluated(self):
        from neurostim import StimProtocol

        check = self._counter(
            self._assess(DiscElectrode(300.0, "Pt"), StimProtocol(100.0, 200.0, 130.0, 1.0, waveform="monophasic"))
        )
        assert check.status.value == "NOT_EVALUATED"

    def test_the_derating_applies_to_the_counter_too(self):
        counter = DiscElectrode(300.0, "Pt")
        saline = self._counter(self._assess(counter))
        in_vivo = self._counter(self._assess(counter, medium="in_vivo"))
        assert in_vivo.ceiling_uA < saline.ceiling_uA

    def test_it_is_limit_bearing_everywhere_the_package_and_oracle_say_so(self):
        import oracles

        from neurostim.safety.assessment import CEILING_INTERVALS, CHECK_KINDS, LIMIT_BEARING

        assert "Counter charge injection" in LIMIT_BEARING
        assert "Counter charge injection" in oracles.LIMIT_BEARING
        assert CHECK_KINDS["Counter charge injection"] == "electrode-acute"
        assert "Counter charge injection" in CEILING_INTERVALS

    def test_the_headline_matches_the_independent_bisection(self):
        """The fail-ceiling oracle reads only assess().failed, and writes LIMIT_BEARING out
        itself."""
        import oracles

        from neurostim import SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 130.0, 1.0),
            compliance_V=10.0, counter_electrode=DiscElectrode(80.0, "Pt"),
            counter_separation_um=20000.0,
        )
        assert calc.assess().limit_bearing_ceiling_uA == pytest.approx(
            oracles.fail_ceiling_uA(calc, names=oracles.LIMIT_BEARING), rel=1e-9
        )


class TestWithoutACounterNothingChanges:
    """Ledger 133, user decision (ii): the counter check is emitted only when a counter is
    supplied, so an assessment without one is byte-identical to before C3.11. The README
    transcript check (``regenerate_example_output.py --check``) is the byte-level golden;
    this pins the check set, and what monophasic delivery does with a counter."""

    NINE = {
        "Shannon criterion", "Charge injection limit", "Water window", "Validated envelope",
        "Current density", "Microelectrode charge/phase", "Chronic degradation",
        "Charge balance", "Compliance voltage",
    }

    def test_no_counter_emits_exactly_the_nine_checks(self):
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        ).assess()
        assert {c.name for c in assessment.checks} == self.NINE
        assert assessment.counter_charge is None

    def test_monophasic_with_a_counter_is_incomplete_for_the_counter_too(self):
        """Monophasic: the counter check is NOT_EVALUATED, like the active Charge injection
        check, so both are named in limits_incomplete. The flag was already True for every
        monophasic protocol (ledger 2); the counter adds its name to the note."""
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(100.0, 200.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0, counter_electrode=DiscElectrode(300.0, "Pt"),
            counter_separation_um=20000.0,
        ).assess()
        assert assessment.limits_incomplete
        note = assessment.limits_incomplete_note()
        assert "Counter charge injection" in note
        assert "Charge injection limit" in note


class TestAMissingCaveatRaises:
    """Ledger 137 (Phase 3b review J3). ``caveats.get(check.name, False)`` let a typo in a
    caveat key survive the full suite, silently making that limit non-provisional -- the
    ledger 97 fall-through pattern, left in place for ``provisional``."""

    def test_a_limit_bearing_check_without_a_caveat_entry_raises(self):
        from neurostim.safety.assessment import _provisional

        with pytest.raises(KeyError, match="Counter charge injection"):
            _provisional({"Shannon criterion": True}, "Counter charge injection")

    def test_an_unknown_caveat_key_raises(self):
        from neurostim.safety.assessment import LIMIT_BEARING, _check_caveat_keys

        caveats = dict.fromkeys(LIMIT_BEARING, False)
        caveats["Counter charge injectoin"] = True
        with pytest.raises(ValueError, match="Counter charge injectoin"):
            _check_caveat_keys(caveats)

    def test_a_check_that_bears_no_limit_is_never_provisional(self):
        from neurostim.safety.assessment import _provisional

        assert _provisional({}, "Charge balance") is False
        assert _provisional({}, "Validated envelope") is False
