"""Phase 4 -- provenance: every constant says where it came from, and whether it is confirmed.

The package's claim is traceable provenance. These tests pin the places where a constant's
origin or its verified flag was lost on the way to a result or a report.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from neurostim import DiscElectrode, SafetyCalculator, StimProtocol, get_material
from neurostim.materials import MATERIALS, ChronicThreshold, MeasuredRange, with_measured_cic


class TestAMeasuredRangeRefusesBoundsThatAreNotNumbers:
    """Ledger 24. ``if self.high < self.low`` is False for NaN, so a NaN bound constructed,
    and ``with_measured_cic(Pt, 100, high=nan).cic_uC_cm2("optimistic")`` returned nan;
    ``high=inf`` returned inf; ``MeasuredRange(-5, 1).value("conservative")`` returned -5."""

    @pytest.mark.parametrize(
        ("low", "high"),
        [(1.0, math.nan), (math.nan, 1.0), (1.0, math.inf), (-5.0, 1.0), (0.0, 1.0)],
    )
    def test_a_bound_that_is_not_a_positive_finite_number_raises(self, low, high):
        with pytest.raises(ValueError, match="MeasuredRange"):
            MeasuredRange(low=low, high=high, units="uC/cm2", reference="user_measurement")

    @pytest.mark.parametrize("high", [math.nan, math.inf, -1.0])
    def test_with_measured_cic_checks_its_high_end_too(self, high):
        with pytest.raises(ValueError):
            with_measured_cic(get_material("Pt"), 100.0, high)

    @pytest.mark.parametrize(
        ("low", "high"), [(1.0, math.nan), (math.nan, 1.0), (1.0, math.inf), (-1.0, 1.0)]
    )
    def test_a_chronic_threshold_refuses_them_too(self, low, high):
        with pytest.raises(ValueError, match="ChronicThreshold"):
            ChronicThreshold(low, high, mechanism="x", reference="rose_robblee1990")

    def test_every_shipped_material_still_constructs(self):
        """The premise: no shipped range is non-finite or non-positive."""
        assert len(MATERIALS) == 9


class TestAChronicThresholdCarriesItsOwnVerifiedFlag:
    """Ledger 30. ``Material.verified`` rolled up the CIC and the water window but not the
    chronic threshold, which had no ``verified`` field at all. The flag now exists, rolls
    into ``Material.verified``, and reaches ``describe()``, the JSON and the PDF's
    provenance rows."""

    @staticmethod
    def _pt_with_unverified_threshold():
        pt = get_material("Pt")
        assert pt.verified and pt.chronic_threshold is not None  # the premise
        return replace(
            pt, chronic_threshold=replace(pt.chronic_threshold, verified=False)
        )

    def test_it_rolls_into_the_material(self):
        assert self._pt_with_unverified_threshold().verified is False

    def test_every_shipped_threshold_is_verified(self):
        for material in MATERIALS.values():
            if material.chronic_threshold is not None:
                assert material.chronic_threshold.verified is True, material.key
            assert material.verified is True, material.key

    def test_describe_says_provisional(self):
        threshold = self._pt_with_unverified_threshold().chronic_threshold
        assert "PROVISIONAL" in threshold.describe()
        assert "PROVISIONAL" not in get_material("Pt").chronic_threshold.describe()

    def test_the_json_carries_each_constants_reference_and_flag(self):
        import json

        from neurostim.io.tabular import report_to_json

        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        payload = json.loads(
            report_to_json(
                SafetyCalculator(
                    DiscElectrode(100.0, "Pt"), protocol,
                    material=self._pt_with_unverified_threshold(),
                )
            )
        )
        provenance = payload["provenance"]
        assert provenance["material_verified"] is False
        # C4.4 (ledger 59) added peer_reviewed and note to each entry.
        assert {k: provenance["chronic_threshold"][k] for k in (
            "reference", "verified", "inherited_from", "peer_reviewed"
        )} == {
            "reference": "rose_robblee1990", "verified": False, "inherited_from": None,
            "peer_reviewed": True,
        }
        assert provenance["cic"]["verified"] is True
        clean = json.loads(
            report_to_json(SafetyCalculator(DiscElectrode(100.0, "Pt"), protocol))
        )["provenance"]
        assert clean["material_verified"] is True
        assert clean["chronic_threshold"]["verified"] is True

    def test_the_pdf_provenance_rows_include_the_threshold(self):
        from neurostim.io.report import _provenance_rows

        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), protocol, material=self._pt_with_unverified_threshold()
        )
        rows = dict(_provenance_rows(calc, calc.assess()))
        assert "rose_robblee1990" in rows["Chronic degradation threshold"]
        assert "PROVISIONAL" in rows["Chronic degradation threshold"]
        clean = SafetyCalculator(DiscElectrode(100.0, "Pt"), protocol)
        clean_rows = dict(_provenance_rows(clean, clean.assess()))
        assert "PROVISIONAL" not in clean_rows["Chronic degradation threshold"]
        titanium = SafetyCalculator(DiscElectrode(100.0, "TiN"), protocol)
        assert "no chronic threshold on record" in dict(
            _provenance_rows(titanium, titanium.assess())
        )["Chronic degradation threshold"]


class TestAUserMeasurementInheritsOnlyWhatItSays:
    """Ledger 25, by user decision option (c). ``with_measured_cic`` replaced only the CIC,
    so the base material's water window, chronic threshold and note survived and were
    presented as the user material's own: "[PASS] Chronic degradation: ... below the 20
    uC/cm^2 platinum dissolution threshold (platinum dissolution, rose_robblee1990)".

    Dropping them would satisfy the letter of the plan's first test ("absence of
    rose_robblee1990") but remove the platinum dissolution limit, the less conservative
    direction. So they are kept by default, labelled as inherited, and never presented as
    the user material's own. Keyword arguments replace or drop each one, and a drop is
    recorded where the limit goes missing.
    """

    PROTOCOL = StimProtocol(80.0, 200.0, 130.0, 1.0)
    LABEL = "not measured on this electrode"

    def _assess(self, material):
        return SafetyCalculator(DiscElectrode(100.0, "Pt"), self.PROTOCOL, material=material).assess()

    def test_by_default_the_published_limits_stay_in_force_labelled_inherited(self):
        user = with_measured_cic(get_material("Pt"), 100.0)
        assert user.chronic_threshold.reference == "rose_robblee1990"
        assert user.chronic_threshold.inherited_from == "Platinum"
        assert user.water_window.inherited_from == "Platinum"
        assert user.chronic_threshold.verified is True  # the label carries the caveat
        assert (
            "published for Platinum (rose_robblee1990), not measured on this electrode"
            in user.chronic_threshold.describe()
        )
        assert (
            "published for Platinum (cogan2008), not measured on this electrode"
            in user.water_window.describe()
        )
        assert user.note.startswith("User-measured charge-injection limit on Platinum")

        chronic = next(
            c for c in self._assess(user).checks if c.name == "Chronic degradation"
        )
        assert chronic.status.value != "NOT_EVALUATED"  # the Pt dissolution limit applies
        assert self.LABEL in chronic.summary

    def test_a_published_reference_is_never_presented_as_the_users_own(self):
        """Every line of every render that names an inherited reference carries the label."""
        import json

        from neurostim.io.report import _provenance_rows
        from neurostim.io.tabular import report_to_json

        user = with_measured_cic(get_material("Pt"), 100.0)
        calc = SafetyCalculator(DiscElectrode(100.0, "Pt"), self.PROTOCOL, material=user)
        assessment = calc.assess()
        texts = assessment.describe().splitlines()
        texts += [f"{k}: {v}" for k, v in _provenance_rows(calc, assessment)]
        texts += [c.summary for c in assessment.checks]
        named = [line for line in texts if "rose_robblee1990" in line or "cogan2008" in line]
        assert named, "the premise: the inherited references are rendered"
        assert all(self.LABEL in line for line in named), [
            line for line in named if self.LABEL not in line
        ]
        provenance = json.loads(report_to_json(calc))["provenance"]
        assert provenance["chronic_threshold"]["inherited_from"] == "Platinum"
        assert provenance["water_window"]["inherited_from"] == "Platinum"
        assert provenance["cic"]["inherited_from"] is None

    def test_a_replaced_constant_is_the_users_and_cites_the_user(self):
        user = with_measured_cic(
            get_material("Pt"), 100.0, chronic_threshold=(10.0, 30.0),
            water_window=(-0.5, 0.7),
        )
        assert user.chronic_threshold.reference == "user_measurement"
        assert user.chronic_threshold.verified is False
        assert user.chronic_threshold.inherited_from == ""
        assert (user.chronic_threshold.low_uC_cm2, user.chronic_threshold.high_uC_cm2) == (10.0, 30.0)
        assert user.water_window.reference == "user_measurement"
        assert (user.water_window.cathodic_V, user.water_window.anodic_V) == (-0.5, 0.7)
        assert "rose_robblee1990" not in user.chronic_threshold.describe()
        chronic = next(
            c for c in self._assess(user).checks if c.name == "Chronic degradation"
        )
        # 80 uA x 200 us on a 100 um disc is 203.7 uC/cm^2, past the user's 30.
        assert chronic.status.value == "FAIL"
        assert "30 uC/cm^2" in chronic.summary

    @pytest.mark.parametrize(
        ("keyword", "check", "phrase"),
        [
            ("chronic_threshold", "Chronic degradation", "chronic threshold"),
            ("water_window", "Water window", "water window"),
        ],
    )
    def test_a_dropped_constant_is_recorded_where_the_limit_goes_missing(
        self, keyword, check, phrase
    ):
        user = with_measured_cic(get_material("Pt"), 100.0, **{keyword: None})
        assert getattr(user, keyword) is None
        assessment = self._assess(user)
        result = next(c for c in assessment.checks if c.name == check)
        assert result.status.value == "NOT_EVALUATED"
        assert f"{phrase} was dropped" in result.summary
        assert assessment.limits_incomplete is True
        assert check in assessment.limits_incomplete_note()
        assert f"{phrase} was dropped" in assessment.limits_incomplete_note()

    def test_no_shipped_constant_is_marked_inherited(self):
        for material in MATERIALS.values():
            assert material.dropped == ()
            for constant in (material.water_window, material.chronic_threshold):
                if constant is not None:
                    assert constant.inherited_from == "", material.key


class TestTheWindowSeedReadsTheWindowItIsGiven:
    """Ledger 150, found at C4.1b. The water-window seed looked the material up by key
    (``max_charge_density_in_window_uC_cm2(result.material_key, ...)``), so a Material
    instance with its own window -- ``replace(Pt, water_window=...)``, or since C4.1b
    ``with_measured_cic(..., water_window=(c, a))`` -- was seeded from the shipped window,
    far from its own boundary, and ``assess()`` raised ``LimitDidNotSettle``."""

    @pytest.mark.parametrize("window", [(-0.5, 0.7), (-0.3, 0.9), (-0.9, 0.2)])
    @pytest.mark.parametrize("anodic_first", [False, True])
    def test_a_material_with_its_own_window_assesses_on_its_boundary(self, window, anodic_first):
        from neurostim.materials import WaterWindow
        from neurostim.safety import assessment as assessment_mod

        material = replace(
            get_material("Pt"), water_window=WaterWindow(*window, reference="cogan2008")
        )
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, anodic_first=anodic_first),
            material=material,
        )
        assessment = calc.assess()
        ceiling = next(c for c in assessment.checks if c.name == "Water window").ceiling_uA
        search = assessment_mod._water_window_search(
            assessment.water_window, calc.p, calc.e.area_cm2
        )
        assert search.passes(ceiling)
        assert not search.passes(math.nextafter(ceiling, math.inf))


class TestAnUnverifiedLimitMarksEverythingDerivedFromIt:
    """Ledgers 19 and 60 (T7). An unverified ``with_measured_cic`` value sets the interfacial
    capacitance, and through it the water-window excursion, the peak potential and the
    compliance polarisation. Raising the user CIC 100 -> 500 uC/cm^2 moved C 250 -> 833 and
    loosened the water window, and only the Charge injection row said PROVISIONAL.

    Asserted by dependency, not by a list: every limit-bearing check whose ceiling moves
    when only the unverified number moves must be provisional.
    """

    PROTOCOL = StimProtocol(80.0, 200.0, 130.0, 1.0)

    def _assess(self, cic, protocol=None, **kwargs):
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"), protocol or self.PROTOCOL,
            material=with_measured_cic(get_material("Pt"), cic), compliance_V=10.0, **kwargs,
        ).assess()

    @pytest.mark.parametrize(
        "protocol",
        [
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            StimProtocol(20.0, 200.0, 130.0, 1.0, anodic_first=True),
            StimProtocol(20.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9),
        ],
    )
    def test_every_check_that_depends_on_the_unverified_number_is_provisional(self, protocol):
        low, high = self._assess(100.0, protocol), self._assess(500.0, protocol)
        dependent = [
            a.name for a, b in zip(low.checks, high.checks, strict=True)
            if a.ceiling_uA != b.ceiling_uA
        ]
        assert "Water window" in dependent and "Compliance voltage" in dependent
        for assessment in (low, high):
            flags = {c.name: c.provisional for c in assessment.checks}
            assert all(flags[name] for name in dependent), (dependent, flags)

    def test_the_water_window_detail_says_so(self):
        text = self._assess(500.0).water_window.describe()
        assert "PROVISIONAL" in text
        assert "PROVISIONAL" not in SafetyCalculator(
            DiscElectrode(100.0, "Pt"), self.PROTOCOL
        ).assess().water_window.describe()

    def test_the_compliance_detail_says_so(self):
        assert "PROVISIONAL" in self._assess(500.0).compliance.describe()

    def test_the_pdf_rows_derived_from_it_say_so(self):
        from neurostim.io.report import _computed_rows, _provenance_rows

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), self.PROTOCOL,
            material=with_measured_cic(get_material("Pt"), 62.0), compliance_V=10.0,
        )
        assessment = calc.assess()
        provenance = dict(_provenance_rows(calc, assessment))
        computed = dict(_computed_rows(calc, assessment))
        assert "PROVISIONAL" in provenance["Interface model"]
        assert "unverified" in provenance["Water window"]
        assert "PROVISIONAL" in computed["Peak electrode potential"]
        assert "PROVISIONAL" in computed["Required compliance"]

    def test_a_measured_capacitance_is_labelled_measured_not_derived(self):
        """The interface line said "derived from the material's own CIC" whatever the
        caller passed."""
        result = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), self.PROTOCOL, capacitance_uF_cm2=300.0
        ).assess().water_window
        assert "derived" not in result.interface_model
        assert "supplied" in result.interface_model

    def test_shipped_materials_carry_no_such_flag(self):
        for key in ("Pt", "SIROF", "TiN"):
            assessment = SafetyCalculator(
                DiscElectrode(100.0, key), self.PROTOCOL, compliance_V=10.0
            ).assess()
            assert "PROVISIONAL" not in assessment.water_window.interface_model

    def test_an_unverified_chronic_threshold_makes_its_check_provisional(self):
        """Ledger 30 gave the threshold a flag; the check now reads it."""
        pt = get_material("Pt")
        material = replace(pt, chronic_threshold=replace(pt.chronic_threshold, verified=False))
        assessment = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), self.PROTOCOL, material=material
        ).assess()
        chronic = next(c for c in assessment.checks if c.name == "Chronic degradation")
        assert chronic.provisional is True


class TestADriftBoundLimitIsProvisional:
    """Ledger 118 (Phase 2 review F16). A Water window limit set by the drift clause rests
    on a no-leak capacitor the code itself calls a lower bound; Merrill 2005 sec 2.4
    describes imbalanced trains reaching a steady state. It was not flagged."""

    def test_drift_binding_is_provisional_and_says_no_leak_bound(self):
        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, charge_recovery_ratio=0.9),
        ).assess()
        window = next(c for c in assessment.checks if c.name == "Water window")
        balanced = next(
            c for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0)
            ).assess().checks if c.name == "Water window"
        )
        assert window.ceiling_uA < balanced.ceiling_uA  # the premise: the drift binds
        assert window.provisional is True
        assert "no-leak bound" in window.summary
        assert balanced.provisional is False

    def test_an_unbalanced_train_whose_peak_binds_is_not_marked_for_the_drift(self):
        """Drift participates but does not bind: a short over-recovering train heads for the
        far edge with nothing riding on it. (Under-recovery spends the riding charge first,
        ledger 105, so its drift term binds even for a very short train.)"""
        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 0.01, charge_recovery_ratio=1.001),
        ).assess()
        window = next(c for c in assessment.checks if c.name == "Water window")
        balanced = next(
            c for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 0.01)
            ).assess().checks if c.name == "Water window"
        )
        assert window.ceiling_uA == balanced.ceiling_uA  # the premise: the peak binds
        assert window.provisional is False
        assert "no-leak bound" not in window.summary


class TestAProvisionalBindingLimitIsMarkedWhereTheLimitIsShown:
    """Ledger 128 (Phase 3 review H2). ``Check.provisional`` reached only the JSON checks
    list. When a provisional check binds -- dbs_3389 at 3000 uA / 60 us / 130 Hz, 10 V,
    where Shannon binds and is provisional -- describe(), the PDF header, the GUI headline
    and the figure showed the limiting current with no caveat."""

    @staticmethod
    def _calc(current=3000.0):
        from neurostim.electrodes import electrode

        return SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(current, 60.0, 130.0, 1.0), compliance_V=10.0
        )

    def test_the_premise(self):
        assessment = self._calc().assess()
        binding = next(c for c in assessment.checks if c.name == assessment.limiting_mechanism)
        assert binding.provisional is True
        assert assessment.limiting_current_uA is not None

    def test_every_headline_surface_says_provisional(self):
        from neurostim.gui.app import headline_text
        from neurostim.io.report import _headline_html

        calc = self._calc()
        assessment = calc.assess()
        note = assessment.provisional_limit_note()
        assert note.startswith("PROVISIONAL")
        assert "Shannon criterion" in note
        # The headline block: the "Limiting current" line and its indented lines.
        lines = assessment.describe().splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Limiting current:"))
        block = [lines[start]]
        for line in lines[start + 1:]:
            if not line.startswith("  "):
                break
            block.append(line)
        assert any(note in line for line in block)
        assert "PROVISIONAL" in headline_text(assessment)
        assert "PROVISIONAL" in _headline_html(assessment)

    def test_the_figure_annotation_says_provisional(self):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from neurostim.viz.plots import safety_summary

        fig, _ = safety_summary(self._calc())
        texts = [t.get_text() for t in fig.findobj(matplotlib.text.Text)]
        plt.close(fig)
        assert any("binding limit" in t and "provisional" in t.lower() for t in texts)

    def test_a_non_provisional_binding_limit_is_not_marked(self):
        from neurostim.gui.app import headline_text

        assessment = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0), compliance_V=10.0
        ).assess()
        binding = next(c for c in assessment.checks if c.name == assessment.limiting_mechanism)
        assert binding.provisional is False  # the premise
        assert assessment.provisional_limit_note() == ""
        assert "PROVISIONAL" not in headline_text(assessment)

    def test_the_monotonicity_caps_binder_is_read_when_the_cap_binds(self):
        """The inherited limit is the biphasic counterpart's; its binder's flag is the one
        that applies."""
        from dataclasses import replace as dc_replace

        calc = self._calc()
        mono = SafetyCalculator(
            calc.e, dc_replace(calc.p, waveform="monophasic"), compliance_V=10.0
        ).assess()
        if mono.monotonicity_capped:
            assert mono.limit_is_provisional == mono.biphasic_provisional
        assert isinstance(mono.biphasic_provisional, bool)


SETTINGS_KEYS = {
    "k": "shannon_k", "policy": "cic_policy", "medium": "medium",
    "tissue_conductivity_S_per_m": "tissue_conductivity_S_per_m",
    "lead_resistance_ohm": "lead_resistance_ohm", "compliance_V": "compliance_V",
    "measured_impedance_ohm": "measured_impedance_ohm",
    "resting_potential_V": "resting_potential_V", "capacitance_uF_cm2": "capacitance_uF_cm2",
    "counter_electrode": "counter_electrode", "counter_separation_um": "counter_separation_um",
}


class TestTheReportsCarryEverySettingAndTheirOwnProvenance:
    """Ledgers 54, 59 and 126. The PDF recorded no package version, no digest and 4 of the
    11 settings, so two reports that differed only in resting_potential_V (0.0 against
    0.35) rendered identical settings with different peak potentials. report_to_json kept
    4 settings, no version, and none of the provenance flags the PDF carries. Neither
    carried the counter electrode."""

    def _calc(self, **kwargs):
        return SafetyCalculator(
            DiscElectrode(200.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, 1.0), **kwargs
        )

    def test_every_calculator_argument_has_a_settings_key(self):
        """Against the live signature, not a list: a setting added later without a
        settings key fails here."""
        import inspect

        parameters = set(inspect.signature(SafetyCalculator.__init__).parameters)
        recorded_elsewhere = {"self", "electrode", "protocol", "material"}
        assert parameters - recorded_elsewhere == set(SETTINGS_KEYS)

    def test_the_json_settings_are_complete_and_carry_the_counter(self):
        import json

        from neurostim.io.tabular import report_to_json

        counter = DiscElectrode(900.0, "Pt")
        payload = json.loads(report_to_json(self._calc(
            compliance_V=10.0, resting_potential_V=0.35, lead_resistance_ohm=2000.0,
            counter_electrode=counter, counter_separation_um=20000.0,
        )))
        settings = payload["settings"]
        assert set(settings) == set(SETTINGS_KEYS.values())
        assert settings["resting_potential_V"] == 0.35
        assert settings["lead_resistance_ohm"] == 2000.0
        assert settings["counter_electrode"]["diameter_um"] == 900.0
        assert settings["counter_separation_um"] == 20000.0
        assert json.loads(report_to_json(self._calc()))["settings"]["counter_electrode"] is None

    def test_the_json_carries_the_version_and_every_provenance_flag(self):
        import json

        from neurostim import __version__
        from neurostim.io.tabular import report_to_json

        user = with_measured_cic(get_material("Pt"), 62.0, note="EIS batch 2026-03")
        payload = json.loads(report_to_json(self._calc(material=user)))
        assert payload["package_version"] == __version__
        cic = payload["provenance"]["cic"]
        assert cic == {
            "reference": "user_measurement", "verified": False, "inherited_from": None,
            "peer_reviewed": False, "note": "EIS batch 2026-03",
        }
        published = json.loads(report_to_json(self._calc()))["provenance"]["cic"]
        assert published["peer_reviewed"] is True
        assert published["reference"] == "rose_robblee1990"

    def test_two_pdfs_that_differ_only_in_a_setting_render_different_settings(self):
        from neurostim.io.report import _reproducibility_rows, _settings_rows

        for field, (a, b) in {
            "resting_potential_V": (0.0, 0.35),
            "lead_resistance_ohm": (0.0, 2000.0),
            "medium": ("saline", "in_vivo"),
            "measured_impedance_ohm": (None, 5000.0),
        }.items():
            first, second = self._calc(**{field: a}), self._calc(**{field: b})
            assert _settings_rows(first) != _settings_rows(second), field
            assert dict(_reproducibility_rows(first))["Digest"] != dict(
                _reproducibility_rows(second)
            )["Digest"], field

    def test_the_pdf_names_the_version_the_digest_and_the_counter(self):
        from neurostim import __version__, audit
        from neurostim.io.report import _reproducibility_rows, _settings_rows

        calc = self._calc(
            compliance_V=10.0, counter_electrode=DiscElectrode(900.0, "Pt"),
            counter_separation_um=20000.0,
        )
        rows = dict(_reproducibility_rows(calc))
        assert rows["Package version"] == __version__
        assert rows["Digest"] == audit.record(calc).digest
        settings = dict(_settings_rows(calc))
        assert "900" in settings["Counter electrode"]
        assert "20000" in settings["Counter electrode"]


class TestTheAuditRecordIsStrictJSON:
    """Ledgers 149 and 126. ``AuditRecord.to_json`` wrote ``Infinity`` for a continuous train,
    the invalid JSON C3.20 removed from report_to_json, and its settings had no counter.
    The digest must stay reproducible: a stored record's digest is computed over the same
    canonical payload as before, and a record with no counter has the same settings keys."""

    @staticmethod
    def _refuse(constant):
        raise ValueError(f"non-JSON constant {constant}")

    def _calc(self, train=math.inf, **kwargs):
        return SafetyCalculator(
            DiscElectrode(200.0, "Pt"), StimProtocol(80.0, 200.0, 130.0, train), **kwargs
        )

    def test_a_continuous_record_is_strict_and_loads_back(self):
        import json

        from neurostim import audit

        record = audit.record(self._calc())
        text = record.to_json()
        payload = json.loads(text, parse_constant=self._refuse)
        assert payload["protocol"]["train_duration_s"] is None
        assert "continuous" in payload["null_reasons"]["protocol.train_duration_s"]
        loaded = audit.load(text)
        assert loaded.protocol["train_duration_s"] == math.inf
        assert loaded.digest_matches
        assert loaded.digest == record.digest
        assert audit.reproduces(loaded, self._calc())[0]

    def test_a_record_written_before_the_change_still_loads_and_matches(self):
        """The old form wrote Infinity; Python's json reads it back."""
        import json
        from dataclasses import asdict

        from neurostim import audit

        record = audit.record(self._calc())
        old_text = json.dumps(asdict(record), indent=2, default=str)
        assert "Infinity" in old_text  # the premise: the old form
        loaded = audit.load(old_text)
        assert loaded.digest_matches
        assert audit.reproduces(loaded, self._calc())[0]

    def test_without_a_counter_the_settings_keys_are_unchanged(self):
        """So a stored no-counter record's digest still reproduces."""
        from neurostim import audit

        settings = audit.record(self._calc(train=1.0)).settings
        assert set(settings) == {
            "shannon_k", "cic_policy", "medium", "tissue_conductivity_S_per_m",
            "lead_resistance_ohm", "compliance_V", "measured_impedance_ohm",
            "resting_potential_V", "capacitance_uF_cm2",
        }

    def test_with_a_counter_the_record_carries_it(self):
        from neurostim import audit

        with_counter = audit.record(self._calc(
            train=1.0, counter_electrode=DiscElectrode(900.0, "Pt"),
            counter_separation_um=20000.0,
        ))
        assert with_counter.settings["counter_electrode"]["diameter_um"] == 900.0
        assert with_counter.settings["counter_separation_um"] == 20000.0
        assert with_counter.digest != audit.record(self._calc(train=1.0)).digest
