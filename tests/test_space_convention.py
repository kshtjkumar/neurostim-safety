"""Phase 3 -- one half-space/full-space convention per geometry (fix plan D4, C3.1).

The field model gave every electrode but the hemisphere a full-space point source,
``V = I / (4 pi sigma r)``, while the access resistance of the planar geometries was
Newman's *half*-space disc. The same disc was therefore half-space in the compliance budget
and full-space in the field, so its far field was exactly half the true value (ledger 17).
Immersed geometries -- the clinical band and the microwire -- took the half-space disc
formula for a body with tissue on every side, high by a factor that the FD solve below
measures at 40-70 % (ledger 20).

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
    """The band against a converged FD Laplace solve (``tests/oracles/fd_band``)."""

    @pytest.mark.parametrize("aspect", [0.39, 0.5, 1.0, 1.181, 2.0])
    def test_within_five_per_cent_over_the_clinical_range(self, aspect):
        import oracles

        band = CylindricalBandElectrode(1270.0, 1270.0 * aspect, "PtIr")
        fd = oracles.FD_BAND_REFERENCE[aspect]
        assert abs(band.access_resistance_ohm(0.35) / fd - 1.0) < 0.05

    @pytest.mark.parametrize("aspect", [4.0, 10.0])
    def test_within_twenty_per_cent_to_aspect_ten(self, aspect):
        import oracles

        band = CylindricalBandElectrode(1270.0, 1270.0 * aspect, "PtIr")
        fd = oracles.FD_BAND_REFERENCE[aspect]
        assert abs(band.access_resistance_ohm(0.35) / fd - 1.0) < 0.20

    def test_the_clinical_contact_is_the_equal_area_sphere(self):
        """``1/(4 pi sigma a)`` with ``4 pi a^2 = A``: 329.5 ohm, against 517.5 before.

        Not tautological: the expected value is the sphere formula written out here on the
        band's lateral area, and the FD solve puts the truth at 335.1 ohm.
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
