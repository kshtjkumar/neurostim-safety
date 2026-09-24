"""Headless tests for the PyQt6 desktop application.

The GUI was the only part of this package with no tests. That is a worse gap than it
sounds, because the window is a *second* place where defaults are declared. A literal
typed into a spin box that disagrees with the library constant it mirrors gives the same
electrode and protocol two different answers depending on how they were entered, and
nothing else in the suite would notice. :class:`TestDefaultsMatchTheLibrary` exists
specifically to catch that: the Shannon ``k`` box had drifted to 1.7 while the library
moved to 1.5, in the less conservative direction.

These run offscreen, so they need no display and are safe in CI. Every test drives the
real widgets and the real :meth:`SafetyWindow.recompute`; nothing is mocked.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets", reason="PyQt6 not installed")

from PyQt6.QtWidgets import QApplication

from neurostim.gui.app import SHAPES, SafetyWindow
from neurostim.materials import list_materials
from neurostim.safety import shannon
from neurostim.safety.assessment import Status


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the module; Qt permits only a single instance."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    """A fresh window per test, closed afterwards."""
    win = SafetyWindow()
    yield win
    win.close()


class TestDefaultsMatchTheLibrary:
    """A default typed into the GUI must equal the constant it mirrors."""

    def test_shannon_k_default(self, window):
        """The box must open at the library default, not at a literal beside it.

        Regression: this read 1.7 while SafetyCalculator defaulted to 1.5. Higher k
        permits more charge, so the GUI was the more permissive of the two.
        """
        import inspect

        from neurostim.safety.assessment import SafetyCalculator

        library_default = inspect.signature(SafetyCalculator.__init__).parameters[
            "k"
        ].default
        assert window.k_value.value() == pytest.approx(shannon.K_SHANNON)
        assert window.k_value.value() == pytest.approx(library_default)

    def test_k_range_spans_the_published_band(self, window):
        """Both ends of the literature band must be reachable from the widget."""
        assert window.k_value.minimum() <= shannon.K_SHANNON
        assert window.k_value.maximum() >= shannon.K_DAMAGE_OBSERVED

    def test_tissue_conductivity_default(self, window):
        import inspect

        from neurostim.safety.assessment import SafetyCalculator

        library_default = inspect.signature(SafetyCalculator.__init__).parameters[
            "tissue_conductivity_S_per_m"
        ].default
        assert window.sigma.value() == pytest.approx(library_default)

    def test_policy_defaults_to_conservative(self, window):
        assert window.policy.currentText() == "conservative"

    def test_gui_and_api_agree_on_an_untouched_window(self, window):
        """A freshly opened window must agree with the API called on library defaults.

        The API side deliberately passes no ``k``, ``policy`` or conductivity: every one
        of them is left to the library default, so the test only passes while all three
        GUI widgets still open on those same values. That is the drift this catches.
        """
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        assert window.shape_combo.currentText() == "Ring / annulus"
        assert window.material_combo.currentData() == "Pt"

        gui = window._build_calculator().assess()
        api = SafetyCalculator(
            RingElectrode(
                window._dimension_widgets["outer_diameter_um"].value(),
                window._dimension_widgets["inner_diameter_um"].value(),
                "Pt",
            ),
            StimProtocol(
                window.current.value(),
                window.pulse_width.value(),
                window.frequency.value(),
                window.train.value(),
            ),
            compliance_V=window.compliance.value(),
        ).assess()
        assert gui.limiting_current_uA == pytest.approx(api.limiting_current_uA)
        assert gui.status is api.status
        assert gui.limiting_mechanism == api.limiting_mechanism


class TestEveryMaterialRenders:
    """Selecting any material must produce a result, not an exception."""

    @pytest.mark.parametrize("index", range(len(list_materials())))
    def test_material_recomputes(self, window, index):
        window.material_combo.setCurrentIndex(index)
        assert window.headline.text() != "Invalid input"
        assert window.table.rowCount() > 0
        assert window.detail.toPlainText().strip()

    def test_ta2o5_reports_the_window_as_not_evaluated(self, window):
        """Ta2O5 has no water window, and the table must say so rather than PASS.

        A capacitor electrode's ceiling is dielectric breakdown at 80 % of its forming
        voltage, which is a property of the individual electrode. Showing PASS would
        claim a check ran that did not.
        """
        self._select(window, "Ta2O5")
        row = self._row(window, "Water window")
        assert row == Status.NOT_EVALUATED.value

    def test_ss316lvm_evaluates_its_polarisation_limit(self, window):
        """316LVM gained a 1.2 V limit, so its check must now actually run."""
        self._select(window, "SS316LVM")
        assert self._row(window, "Water window") != Status.NOT_EVALUATED.value

    @staticmethod
    def _select(window, key: str) -> None:
        index = window.material_combo.findData(key)
        assert index >= 0, f"{key} missing from the material list"
        window.material_combo.setCurrentIndex(index)

    @staticmethod
    def _row(window, name: str) -> str:
        for r in range(window.table.rowCount()):
            if window.table.item(r, 0).text() == name:
                return window.table.item(r, 1).text()
        raise AssertionError(f"no {name!r} row in the results table")


class TestEveryGeometryRenders:
    @pytest.mark.parametrize("shape", list(SHAPES))
    def test_shape_recomputes(self, window, shape):
        window.shape_combo.setCurrentText(shape)
        assert window.headline.text() != "Invalid input"
        assert window.table.rowCount() > 0

    def test_switching_shape_rebuilds_the_dimension_fields(self, window):
        window.shape_combo.setCurrentText("Disc")
        assert set(window._dimension_widgets) == {"diameter_um"}
        window.shape_combo.setCurrentText("Cylindrical band (DBS)")
        assert set(window._dimension_widgets) == {"diameter_um", "height_um"}


class TestInvalidInputSurfaces:
    """The window must show the failure, never silently revert to a valid state."""

    def test_ring_with_inner_at_least_outer(self, window):
        window.shape_combo.setCurrentText("Ring / annulus")
        window._dimension_widgets["inner_diameter_um"].setValue(400.0)
        window._dimension_widgets["outer_diameter_um"].setValue(300.0)
        assert window.headline.text() == "Invalid input"
        assert window._calc is None
        assert window.table.rowCount() == 0
        assert "Error" in window.detail.toPlainText() or ":" in window.detail.toPlainText()

    def test_pulse_that_does_not_fit_its_period(self, window):
        window.frequency.setValue(1000.0)
        window.pulse_width.setValue(900.0)  # 2 x 900 us > 1000 us period
        assert window.headline.text() == "Invalid input"
        assert window._calc is None

    def test_recovers_when_the_input_is_made_valid_again(self, window):
        window.frequency.setValue(1000.0)
        window.pulse_width.setValue(900.0)
        assert window._calc is None
        window.pulse_width.setValue(100.0)
        assert window._calc is not None
        assert window.headline.text() != "Invalid input"

    def test_exports_refuse_to_run_on_invalid_input(self, window, monkeypatch):
        """Neither export may open a file dialog while there is nothing to export."""
        from neurostim.gui import app as app_mod

        opened: list[str] = []
        monkeypatch.setattr(
            app_mod.QFileDialog,
            "getSaveFileName",
            lambda *a, **k: (opened.append("dialog"), ("", ""))[1],
        )
        monkeypatch.setattr(app_mod.QMessageBox, "warning", lambda *a, **k: None)

        window.frequency.setValue(1000.0)
        window.pulse_width.setValue(900.0)
        assert window._calc is None
        window.export_pdf()
        window.export_figure()
        assert opened == []


class TestExports:
    def test_pdf_export_writes_a_file(self, window, tmp_path, monkeypatch):
        from neurostim.gui import app as app_mod

        target = tmp_path / "report.pdf"
        monkeypatch.setattr(
            app_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
        )
        monkeypatch.setattr(app_mod.QMessageBox, "information", lambda *a, **k: None)
        window.export_pdf()
        assert target.exists()
        assert target.stat().st_size > 0

    def test_figure_export_writes_all_three_formats(self, window, tmp_path, monkeypatch):
        from neurostim.gui import app as app_mod

        target = tmp_path / "summary.svg"
        monkeypatch.setattr(
            app_mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
        )
        monkeypatch.setattr(app_mod.QMessageBox, "information", lambda *a, **k: None)
        window.export_figure()
        for suffix in (".svg", ".pdf", ".tiff"):
            assert target.with_suffix(suffix).exists()

    def test_cancelled_dialog_writes_nothing(self, window, tmp_path, monkeypatch):
        from neurostim.gui import app as app_mod

        monkeypatch.setattr(
            app_mod.QFileDialog, "getSaveFileName", lambda *a, **k: ("", "")
        )
        window.export_pdf()
        window.export_figure()
        assert list(tmp_path.iterdir()) == []


class TestLiveRecompute:
    """Every input is wired to recompute; a disconnected signal is a silent bug."""

    def test_raising_current_lowers_the_headroom(self, window):
        window.current.setValue(10.0)
        low = window.detail.toPlainText()
        window.current.setValue(5000.0)
        high = window.detail.toPlainText()
        assert low != high

    @staticmethod
    def _ceiling(window, name: str) -> float:
        """One named check's own ceiling, from the window's live calculator.

        The headline stopped being the right probe for "is this widget wired through" at
        C1.6: it is a minimum over seven checks, so a widget that moves exactly one of
        them is invisible there whenever another binds. Reading the check the widget
        actually controls is stronger evidence of wiring, not weaker.
        """
        return next(
            c for c in window._calc.assess().checks if c.name == name
        ).ceiling_uA

    def test_k_changes_the_shannon_verdict(self, window):
        """k is the single most consequential setting; it must be live."""
        window.shape_combo.setCurrentText("Disc")
        window._dimension_widgets["diameter_um"].setValue(1000.0)
        window.current.setValue(2000.0)
        window.k_value.setValue(shannon.K_SHANNON)
        strict = self._ceiling(window, "Shannon criterion")
        window.k_value.setValue(shannon.K_DAMAGE_OBSERVED)
        permissive = self._ceiling(window, "Shannon criterion")
        assert permissive > strict

    def test_policy_changes_the_charge_injection_limit(self, window):
        window.policy.setCurrentText("conservative")
        low = window._calc.assess().limiting_current_uA
        window.policy.setCurrentText("optimistic")
        high = window._calc.assess().limiting_current_uA
        assert high >= low

    def test_disabling_compliance_removes_that_constraint(self, window):
        window.use_compliance.setChecked(True)
        window.compliance.setValue(1.0)
        constrained = window._calc.assess().limiting_current_uA
        window.use_compliance.setChecked(False)
        unconstrained = window._calc.assess().limiting_current_uA
        assert unconstrained >= constrained

    def test_anodic_first_is_wired_through(self, window):
        """Pt's limit is polarity-resolved, so the checkbox must reach the protocol."""
        self_key = window.material_combo.findData("Pt")
        window.material_combo.setCurrentIndex(self_key)
        window.anodic_first.setChecked(False)
        cathodic = self._ceiling(window, "Charge injection limit")
        window.anodic_first.setChecked(True)
        anodic = self._ceiling(window, "Charge injection limit")
        assert anodic != cathodic


class TestPdfReport:
    """The PDF is the deliverable; these lock in defects found in real output."""

    @pytest.fixture
    def report_text(self, tmp_path):
        import shutil
        import subprocess

        from neurostim import RingElectrode, SafetyCalculator, StimProtocol
        from neurostim.io.report import build_report

        if shutil.which("pdftotext") is None:
            pytest.skip("pdftotext (poppler) not available")
        calc = SafetyCalculator(
            RingElectrode(314.0, 216.0, "SS316LVM"),
            StimProtocol(40.0, 200.0, 130.0, 1.54),
            k=3.0,
            policy="nominal",
            compliance_V=7.0,
        )
        out = build_report(calc, tmp_path / "r.pdf")
        return subprocess.run(
            ["pdftotext", "-layout", str(out), "-"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    @pytest.mark.parametrize(
        "entity", ["&micro;", "&sup2;", "&ohm;", "&sigma;", "&middot;", "&mdash;"]
    )
    def test_no_raw_html_entities(self, report_text, entity):
        """Raw strings in a ReportLab table cell are not entity-decoded.

        Real output printed "314 &micro;m" and "0.0004079 cm&sup2;" throughout the
        electrode and protocol tables, because only Paragraph decodes entities and the
        value cells were plain strings.
        """
        assert entity not in report_text

    def test_units_render_as_glyphs(self, report_text):
        """Units must reach the page as characters, not as entity source.

        Compared under NFKC: the ohm comes back as U+2126 OHM SIGN rather than U+03A9
        GREEK CAPITAL OMEGA, because the built-in Helvetica has no omega and ReportLab
        substitutes. The two are canonically equivalent, so normalising is the correct
        comparison rather than a workaround.
        """
        import unicodedata

        normalised = unicodedata.normalize("NFKC", report_text)
        # Written as escapes: ruff flags these literals as visually ambiguous, and it
        # is right to -- the whole bug class here is characters that look correct.
        glyphs = (
            "\u00b5m",  # MICRO SIGN + m
            "cm\u00b2",  # SUPERSCRIPT TWO
            "\u03a9",  # GREEK CAPITAL OMEGA, matches U+2126 after NFKC
            "\u03c3",  # GREEK SMALL SIGMA
            "\u00b5A",
            "\u00b5s",
        )
        for glyph in glyphs:
            assert unicodedata.normalize("NFKC", glyph) in normalised

    def test_provenance_row_is_not_truncated(self, report_text):
        """A plain-string cell clips at the column edge instead of wrapping.

        The charge-injection provenance row ended mid-word at "on 0.016 cm^2, geo",
        losing the area basis -- in the one section of the report whose entire purpose
        is to state measurement conditions.
        """
        # G12 (C4.6, ledger 73): the record no longer attaches the corrosion test's
        # conditions to the limit, so the row that clipped is shorter. The long cell now
        # is the note; its last words must reach the page.
        import re

        flat = re.sub(r"\s+", " ", report_text)
        assert "(riedy_walter1996)" in flat
        assert "Stainless steel does not appear in Cogan 2008 Table 2." in flat

    def test_peak_potential_uses_the_material_scale(self, report_text):
        """316LVM's limits are a polarisation magnitude, not a potential vs Ag|AgCl.

        The row hardcoded "vs Ag|AgCl", which is the misstatement WaterWindow.scale
        exists to prevent -- and the provenance table two inches below said something
        different about the same number.
        """
        assert "of polarisation from rest (measured vs SCE)" in report_text
        assert "V vs Ag|AgCl" not in report_text

    def test_every_source_named_in_the_body_is_in_the_bibliography(self, report_text):
        """No dangling citations.

        Butterwick and Kuncel & Grill were discussed in the warnings text with no
        bibliography entry, because the reference list was hand-maintained and had gone
        stale. It is now derived from the assembled text.
        """
        body, _, biblio = report_text.partition("References")
        assert biblio, "no References section"
        for surname, year in [
            ("Butterwick", "2007"),
            ("Kuncel", "2004"),
            ("Shannon", "1992"),
            ("Gabriel", "1996"),
        ]:
            if surname in body:
                assert surname in biblio, f"{surname} cited but not listed"
                assert year in biblio

    def test_bibliography_lists_no_paper_twice(self, report_text):
        """Two keys pointed at one Kuncel & Grill paper; both would have printed."""
        _, _, biblio = report_text.partition("References")
        titles = [ln for ln in biblio.splitlines() if "doi:" in ln]
        dois = [ln.split("doi:")[1].split()[0] for ln in titles]
        assert len(dois) == len(set(dois)), f"duplicate DOI in bibliography: {dois}"

    def test_limitations_do_not_contradict_the_interface_model(self, report_text):
        """The boilerplate claimed a pure double-layer model; the report says otherwise.

        The Provenance section prints "capacitance derived from the material's own CIC
        and window". The Limitations paragraph said the check "models the interface as a
        pure double-layer capacitance". Both cannot be true of one report.
        """
        assert "capacitance derived from the material's own CIC and window" in report_text
        assert "pure double-layer capacitance" not in report_text

    def test_shannon_note_distinguishes_threshold_from_metric(self, report_text):
        """"k = -0.80 ... (k above Shannon's 1.5)" asserted two things about one symbol."""
        if "above Shannon's 1.5" in report_text:
            assert "threshold k above Shannon's 1.5" in report_text


class TestReferenceRegistry:
    def test_no_duplicate_dois(self):
        """One paper, one key. A duplicate prints the same entry twice."""
        from collections import Counter

        from neurostim.references import REFERENCES

        dois = Counter(r.doi for r in REFERENCES.values() if r.doi)
        assert [d for d, n in dois.items() if n > 1] == []

    def test_every_key_is_reachable_from_the_package(self):
        """A reference nothing cites is dead weight and drifts out of date.

        This scan used to shell out to ``grep -rho -E ... neurostim``, which named the
        package by a path relative to the working directory: run from anywhere but the
        repository root it matched nothing and reported all 45 references unused. It also
        depended on ``-o`` and ``-h`` behaving as GNU grep spells them, and on grep being
        installed at all. The rglob below is the same regex over the same files, anchored
        to this file's own location.
        """
        import pathlib
        import re

        from neurostim.references import REFERENCES

        package = pathlib.Path(__file__).resolve().parents[1] / "neurostim"
        assert package.is_dir(), f"package source not found at {package}"
        sources = sorted(package.rglob("*.py"))
        assert sources, f"no source files under {package}"

        used = {
            word
            for path in sources
            for word in re.findall(r"[a-z0-9_]+", path.read_text(encoding="utf-8"))
        }
        unused = [k for k in REFERENCES if k not in used]
        assert unused == [], f"references defined but never cited: {unused}"


class TestReportShowsSourceCaveats:
    """Stored provenance that never reaches the page is not provenance."""

    @pytest.fixture
    def text(self, tmp_path):
        import shutil
        import subprocess

        from neurostim import RingElectrode, SafetyCalculator, StimProtocol
        from neurostim.io.report import build_report

        if shutil.which("pdftotext") is None:
            pytest.skip("pdftotext (poppler) not available")
        calc = SafetyCalculator(
            RingElectrode(330.0, 215.0, "SS316LVM"),
            StimProtocol(40.0, 200.0, 130.0, 1.54),
            k=1.0,
            policy="nominal",
            compliance_V=7.0,
        )
        out = build_report(calc, tmp_path / "r.pdf")
        return subprocess.run(
            ["pdftotext", "-layout", str(out), "-"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def test_material_note_reaches_the_page(self, text):
        """576 characters of caveat were stored and rendered nowhere.

        G12 (C4.6, ledgers 72, 73): the caveat now says where each figure came from.
        """
        import re

        flat = re.sub(r"\s+", " ", text)
        assert "their ref. [8] (p. 663)" in flat
        assert "Those are the corrosion test's conditions" in flat

    def test_policy_warning_is_printed(self, text):
        """Whitespace is collapsed first: the sentence wraps across PDF lines."""
        import re

        flat = re.sub(r"\s+", " ", text)
        assert "POLICY:" in flat
        # Floored to four significant digits since ledger 100: both numbers are maxima.
        assert "endorses the 'conservative' end at 20.00 uC/cm^2" in flat
        assert "applies 30.00 uC/cm^2" in flat

    def test_pulse_width_is_visible_next_to_the_limit(self, text):
        """The limit is only valid at the width it was measured at; show it.

        G12 (C4.6, ledger 73): 316LVM's figures have no measured pulse width -- the 100 us
        was the corrosion test's -- so what the page must show is that the width is
        unknown, beside the limit.
        """
        import re

        flat = re.sub(r"\s+", " ", text)
        assert "carries no stated pulse width" in flat


class TestTheProtocolFormCanExpressPhase2Faults:
    """A protocol the library can express and the window cannot is a second default.

    :class:`TestDefaultsMatchTheLibrary` above exists because the Shannon ``k`` box drifted
    away from the library constant. The same failure mode applies to a whole *field*: a
    charge imbalance the library now models and the form cannot enter is a fault a GUI user
    can neither reproduce nor diagnose, and the GUI is the surface most users reach first.

    Fixture rule: every value set here differs from the field's own default, so a widget
    wired to the wrong constructor argument -- or not wired at all -- changes an asserted
    number rather than nothing.
    """

    def test_the_charge_recovery_box_opens_at_the_library_default(self, window):
        """1.0, taken from the dataclass rather than typed as a literal beside it."""
        from neurostim.protocol import StimProtocol

        default = StimProtocol.__dataclass_fields__["charge_recovery_ratio"].default
        assert window.charge_recovery.value() == pytest.approx(default)

    def test_the_train_duty_box_opens_at_the_library_default(self, window):
        """Ledger 107 (F5): C2.5 added ``train_duty_cycle`` and section 6 booked a GUI
        input for it; there was none. 1.0, taken from the dataclass."""
        from neurostim.protocol import StimProtocol

        default = StimProtocol.__dataclass_fields__["train_duty_cycle"].default
        assert window.train_duty.value() == pytest.approx(default)

    def test_train_duty_reaches_the_protocol(self, window):
        """Not tautological: the expected pulse count is ``T * f * duty`` from the boxes'
        own values, against a protocol the window builds; the default would give twice
        it."""
        window.frequency.setValue(130.0)
        window.train.setValue(2.0)
        window.train_duty.setValue(0.5)

        protocol = window._build_calculator().p

        assert protocol.train_duty_cycle == pytest.approx(0.5)
        assert protocol.n_pulses == pytest.approx(2.0 * 130.0 * 0.5, rel=1e-12)

    def test_the_train_duty_box_recomputes(self, window):
        """A box that does not trigger a recompute shows a stale verdict."""
        window.train_duty.setValue(0.25)
        assert window._calc is not None
        assert window._calc.p.train_duty_cycle == pytest.approx(0.25)

    def test_charge_recovery_reaches_the_protocol(self, window):
        """Not tautological: the expected net charge is ``(1 - r_a) * I * W * 1e-6``,
        computed here from the three boxes' own values, against a protocol the window
        builds."""
        window.current.setValue(80.0)
        window.pulse_width.setValue(200.0)
        window.charge_recovery.setValue(0.8)

        protocol = window._build_calculator().p

        assert protocol.charge_recovery_ratio == pytest.approx(0.8)
        assert protocol.net_charge_per_pulse_uC == pytest.approx(
            0.2 * 80.0 * 200.0 * 1e-6, rel=1e-12
        )

    def test_an_imbalance_is_visible_in_the_window(self, window):
        """The headline or the detail pane must say so; a silent CAUTION is no better
        than the dead branch it replaces.

        Not tautological: the assertion is on the rendered detail text, and the status it
        must agree with is read from the assessment the window itself computed.
        """
        window.charge_recovery.setValue(0.8)
        window.recompute()

        detail = window.detail.toPlainText()
        assert "Charge balance" in detail
        balance = next(
            c
            for c in window._calc.assess().checks  # type: ignore[union-attr]
            if c.name == "Charge balance"
        )
        assert balance.status is Status.CAUTION
        assert balance.summary in detail
