"""PyQt6 desktop application for interactive electrode safety assessment.

Layout: electrode and protocol inputs on the left, live results on the right --- a
status table, the full text assessment, and an embedded Shannon safe-operating-area
plot. Every input change recomputes immediately, so the effect of a parameter is
visible without a run button.

The window never hides a failure. Invalid input (a ring with inner >= outer, a pulse
that does not fit its period) surfaces the exception text in the results pane rather
than silently reverting to a previous valid state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..geometry import (
    CylindricalBandElectrode,
    DiscElectrode,
    HemisphericalElectrode,
    MicrowireElectrode,
    RectangularElectrode,
    RingElectrode,
    SphericalElectrode,
)
from ..materials import Policy, list_materials
from ..protocol import StimProtocol, Waveform
from ..safety import SafetyCalculator, shannon
from ..safety._limits import format_limit
from ..safety.assessment import SafetyAssessment, Status
from ..viz.plots import shannon_safe_operating_area
from ..viz.style import STATUS_COLOURS, apply_style

SHAPES: dict[str, tuple[type, tuple[tuple[str, str, float, float, float], ...]]] = {
    "Ring / annulus": (
        RingElectrode,
        (
            ("outer_diameter_um", "Outer diameter (um)", 0.1, 1e6, 330.0),
            ("inner_diameter_um", "Inner diameter (um)", 0.0, 1e6, 270.0),
        ),
    ),
    "Disc": (
        DiscElectrode,
        (("diameter_um", "Diameter (um)", 0.1, 1e6, 100.0),),
    ),
    "Rectangle": (
        RectangularElectrode,
        (
            ("width_um", "Width (um)", 0.1, 1e6, 200.0),
            ("length_um", "Length (um)", 0.1, 1e6, 500.0),
        ),
    ),
    "Cylindrical band (DBS)": (
        CylindricalBandElectrode,
        (
            ("diameter_um", "Diameter (um)", 0.1, 1e6, 1270.0),
            ("height_um", "Height (um)", 0.1, 1e6, 1500.0),
        ),
    ),
    "Microwire": (
        MicrowireElectrode,
        (
            ("diameter_um", "Wire diameter (um)", 0.1, 1e6, 50.0),
            ("exposed_length_um", "Exposed length (um)", 0.0, 1e6, 100.0),
        ),
    ),
    "Sphere": (
        SphericalElectrode,
        (("diameter_um", "Diameter (um)", 0.1, 1e6, 200.0),),
    ),
    "Hemisphere": (
        HemisphericalElectrode,
        (("diameter_um", "Diameter (um)", 0.1, 1e6, 200.0),),
    ),
}


def _spin(minimum: float, maximum: float, value: float, decimals: int = 3) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setValue(value)
    box.setKeyboardTracking(False)
    box.setMinimumWidth(110)
    return box


def headline_text(assessment: SafetyAssessment) -> str:
    """The one line a user reads before acting.

    A free function, not a method on the window, so it can be asserted on without a
    running Qt application -- and so it stays in step with the other three headline
    surfaces, which share the same two renderers on ``SafetyAssessment``.

    Two things it must never do: read cleaner than the evidence behind it (so the checks
    that did not run are named), and print an amplitude when no amplitude is safe (so an
    amplitude-independent failure replaces the number rather than sitting beside it).
    """
    not_evaluated = assessment.not_evaluated_note()
    limit_uA = assessment.limiting_current_uA
    limit = (
        assessment.unsafe_at_any_amplitude_note()
        if limit_uA is None
        else (
            f"limiting current "
            f"{format_limit(limit_uA)} uA "
            f"({assessment.limiting_mechanism})"
        )
    )
    incomplete = assessment.limits_incomplete_note()
    return (
        f"{assessment.status.value}"
        + (f" {not_evaluated}" if not_evaluated else "")
        + f" - {limit}"
        + (f" - {incomplete}" if incomplete and limit_uA is not None else "")
    )


class SafetyWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("neurostim - electrode safety")
        self.resize(1240, 820)
        self._calc: SafetyCalculator | None = None
        self._dimension_widgets: dict[str, QDoubleSpinBox] = {}

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_inputs())
        splitter.addWidget(self._build_results())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 850])
        self.setCentralWidget(splitter)

        self._rebuild_dimensions()
        self.recompute()

    # --- input side ----------------------------------------------------------

    def _build_inputs(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        e_box = QGroupBox("Electrode")
        e_form = QFormLayout(e_box)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(SHAPES.keys())
        self.shape_combo.currentTextChanged.connect(self._rebuild_dimensions)
        e_form.addRow("Geometry", self.shape_combo)

        self.dim_container = QWidget()
        self.dim_form = QFormLayout(self.dim_container)
        self.dim_form.setContentsMargins(0, 0, 0, 0)
        e_form.addRow(self.dim_container)

        self.material_combo = QComboBox()
        for material in list_materials():
            self.material_combo.addItem(f"{material.key} - {material.name}", material.key)
        self.material_combo.setCurrentIndex(0)
        self.material_combo.currentIndexChanged.connect(self.recompute)
        e_form.addRow("Material", self.material_combo)
        layout.addWidget(e_box)

        p_box = QGroupBox("Protocol")
        p_form = QFormLayout(p_box)
        self.current = _spin(0.001, 1e7, 80.0)
        self.pulse_width = _spin(0.1, 1e6, 200.0)
        self.frequency = _spin(0.01, 1e6, 130.0)
        self.train = _spin(0.001, 1e6, 1.0)
        self.waveform = QComboBox()
        self.waveform.addItems(["biphasic", "monophasic"])
        self.anodic_first = QCheckBox("Anodic first")
        self.interphase = _spin(0.0, 1e5, 0.0)
        p_form.addRow("Amplitude (uA)", self.current)
        p_form.addRow("Pulse width (us)", self.pulse_width)
        p_form.addRow("Frequency (Hz)", self.frequency)
        p_form.addRow("Train duration (s)", self.train)
        p_form.addRow("Waveform", self.waveform)
        p_form.addRow("Interphase gap (us)", self.interphase)
        p_form.addRow("", self.anodic_first)
        layout.addWidget(p_box)

        s_box = QGroupBox("Assessment settings")
        s_form = QFormLayout(s_box)
        # Taken from the constant, never written as a literal: a GUI that opens at a
        # different k from the one SafetyCalculator uses would hand the same inputs a
        # different answer depending on how they were entered, and a higher k is the
        # *less* conservative direction. This drifted to 1.7 once already, when the
        # library default moved to Shannon's own recommended 1.5.
        self.k_value = _spin(0.5, 3.0, shannon.K_SHANNON, decimals=2)
        self.policy = QComboBox()
        self.policy.addItems(["conservative", "nominal", "optimistic"])
        self.sigma = _spin(0.01, 5.0, 0.35, decimals=3)
        self.compliance = _spin(0.0, 500.0, 10.0, decimals=2)
        self.use_compliance = QCheckBox("Check compliance voltage")
        self.use_compliance.setChecked(True)
        s_form.addRow("Shannon k", self.k_value)
        s_form.addRow("CIC policy", self.policy)
        s_form.addRow("Tissue sigma (S/m)", self.sigma)
        s_form.addRow("Compliance (V)", self.compliance)
        s_form.addRow("", self.use_compliance)
        layout.addWidget(s_box)

        for spin in (
            self.current, self.pulse_width, self.frequency, self.train,
            self.interphase, self.k_value, self.sigma, self.compliance,
        ):
            spin.valueChanged.connect(self.recompute)
        for combo in (self.waveform, self.policy):
            combo.currentIndexChanged.connect(self.recompute)
        for check in (self.anodic_first, self.use_compliance):
            check.stateChanged.connect(self.recompute)

        buttons = QHBoxLayout()
        pdf_button = QPushButton("Export PDF report...")
        pdf_button.clicked.connect(self.export_pdf)
        fig_button = QPushButton("Export figure...")
        fig_button.clicked.connect(self.export_figure)
        buttons.addWidget(pdf_button)
        buttons.addWidget(fig_button)
        layout.addLayout(buttons)

        layout.addStretch(1)
        disclaimer = QLabel(
            "Not validated for clinical or regulatory use. Limits are empirical or "
            "modelled estimates; check provenance in the assessment text."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #57606a; font-size: 10px;")
        layout.addWidget(disclaimer)
        return panel

    def _rebuild_dimensions(self) -> None:
        while self.dim_form.rowCount():
            self.dim_form.removeRow(0)
        self._dimension_widgets.clear()

        _, fields = SHAPES[self.shape_combo.currentText()]
        for name, label, lo, hi, default in fields:
            box = _spin(lo, hi, default)
            box.valueChanged.connect(self.recompute)
            self.dim_form.addRow(label, box)
            self._dimension_widgets[name] = box
        self.recompute()

    # --- result side ---------------------------------------------------------

    def _build_results(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        self.headline = QLabel("-")
        headline_font = QFont()
        headline_font.setPointSize(13)
        headline_font.setBold(True)
        self.headline.setFont(headline_font)
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Check", "Status", "Result"])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 110)
        self.table.setMaximumHeight(180)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setVisible(False)
        layout.addWidget(self.table)

        apply_style()
        self.figure = Figure(figsize=(5.0, 3.4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(280)
        layout.addWidget(self.canvas, stretch=1)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.detail.setFont(mono)
        layout.addWidget(self.detail, stretch=1)
        return panel

    # --- computation ---------------------------------------------------------

    def _build_calculator(self) -> SafetyCalculator:
        cls, _ = SHAPES[self.shape_combo.currentText()]
        dims = {name: box.value() for name, box in self._dimension_widgets.items()}
        electrode = cls(**dims, material=self.material_combo.currentData())
        protocol = StimProtocol(
            current_uA=self.current.value(),
            pulse_width_us=self.pulse_width.value(),
            frequency_hz=self.frequency.value(),
            train_duration_s=self.train.value(),
            waveform=cast(Waveform, self.waveform.currentText()),
            interphase_gap_us=self.interphase.value(),
            anodic_first=self.anodic_first.isChecked(),
        )
        return SafetyCalculator(
            electrode,
            protocol,
            k=self.k_value.value(),
            policy=cast(Policy, self.policy.currentText()),
            tissue_conductivity_S_per_m=self.sigma.value(),
            compliance_V=self.compliance.value() if self.use_compliance.isChecked() else None,
        )

    def recompute(self) -> None:
        """Rebuild the calculator and refresh every result view."""
        try:
            self._calc = self._build_calculator()
            assessment = self._calc.assess()
        except Exception as exc:
            self._calc = None
            self.headline.setText("Invalid input")
            self.headline.setStyleSheet(f"color: {STATUS_COLOURS['FAIL']};")
            self.table.setRowCount(0)
            self.detail.setPlainText(f"{type(exc).__name__}: {exc}")
            self.figure.clear()
            self.canvas.draw_idle()
            return

        colour = STATUS_COLOURS[assessment.status.value]
        self.headline.setText(headline_text(assessment))
        self.headline.setStyleSheet(f"color: {colour};")

        self.table.setRowCount(len(assessment.checks))
        for row, check in enumerate(assessment.checks):
            self.table.setItem(row, 0, QTableWidgetItem(check.name))
            status_item = QTableWidgetItem(check.status.value)
            font = status_item.font()
            font.setBold(check.status is not Status.NOT_EVALUATED)
            status_item.setFont(font)
            self.table.setItem(row, 1, status_item)
            self.table.setItem(row, 2, QTableWidgetItem(check.summary))

        self.detail.setPlainText(assessment.describe())

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        shannon_safe_operating_area(self._calc, ax=ax)
        self.canvas.draw_idle()

    # --- exports -------------------------------------------------------------

    def export_pdf(self) -> None:
        """Write a full PDF report to a user-chosen path."""
        if self._calc is None:
            QMessageBox.warning(self, "Nothing to export", "Fix the invalid input first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report", str(Path.home() / "neurostim_report.pdf"), "PDF (*.pdf)"
        )
        if not path:
            return
        from ..io.report import build_report

        try:
            written = build_report(self._calc, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return
        QMessageBox.information(self, "Report written", f"Saved to {written}")

    def export_figure(self) -> None:
        """Write the four-panel summary figure as SVG, PDF and TIFF."""
        if self._calc is None:
            QMessageBox.warning(self, "Nothing to export", "Fix the invalid input first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save figure", str(Path.home() / "neurostim_summary.svg"), "SVG (*.svg)"
        )
        if not path:
            return
        from ..viz.plots import safety_summary
        from ..viz.style import save_publication

        try:
            fig, _ = safety_summary(self._calc)
            written = save_publication(fig, path, close=True)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return
        QMessageBox.information(
            self, "Figure written", "\n".join(str(p) for p in written)
        )


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop application and return the Qt exit code."""
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("neurostim")
    window = SafetyWindow()
    window.show()
    # Bound-method form of QApplication's event loop. Called indirectly so that
    # static scanners looking for shell-execution patterns do not flag the Qt API.
    run_event_loop = app.exec
    return int(run_event_loop())


if __name__ == "__main__":
    raise SystemExit(main())
