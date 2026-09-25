"""Butterwick et al. (2007) current-density damage thresholds.

*Tissue damage by pulsed electrical stimulation*, IEEE Trans Biomed Eng 54:2261-7.

Why this matters
----------------
Until this was read, :mod:`neurostim.safety.current_density` computed a number with no
threshold to compare it against. This is that threshold, and it governs a damage mode
the Shannon criterion does not describe: **electroporation**, the formation of pores in
the lipid bilayer under a pulsed field.

The scalings, and what they mean
--------------------------------
**Pulse duration.** Threshold current density falls roughly as ``t^-0.5``, which the
authors identify as characteristic of electroporation. Fitting their two retina anchor
points gives an exponent of -0.44, close to the -0.5 they quote; both are recorded here.

**Electrode size.** Above about 300 um diameter the threshold current density is
essentially *independent* of size. Below about 200 um the threshold **total current**
becomes constant instead, so the threshold current density rises as ``d^-2``. Small
electrodes therefore tolerate far higher current densities -- the same qualitative
conclusion Cogan et al. (2016) reach for charge density, arrived at independently.

**What the paper measured on small electrodes, and why the model does not use it.**
Below 200 um they give the damaging *total current* directly: 139 uA on retina at
600 us and 55 uA on CAM at 60 us (p. 2264, Fig. 5), and a strength-duration slope of
t^-0.29 for the 0.115 mm pipette against t^-0.48 for the 1 mm one (Fig. 6). This module
does not model that line. It extends the large-electrode density from 200 um as d^-2,
which sits below every measured point checked: at 600 us and 200 um it gives
0.169 A/cm^2, where 139 uA over a 200 um disc is 0.44 A/cm^2 -- 2.62x below on retina,
and 1.12x below on CAM at 60 us, the same at every diameter since both scale as d^-2
(ledger 77, S-13). Adopting the measured line instead would relax small-electrode
thresholds 1.3-3.7x across 6 us to 6 ms, and put a step at 200 um, where the 200-300 um
band keeps the large-electrode value.

Two things keep the measured line from being adopted as it stands. The CAM and retina
anchors disagree under this module's CAM rule: the retina line at 60 us is
139 x 10^0.29 = 271 uA, a third of which is about 90 uA, against the 55 uA measured on
CAM, and the paper gives no small-electrode slope for CAM. And the text says Fig. 5 was
measured with "only one pulse", while its caption calls the exposures sustained; its
large-electrode values sit at the sustained level of Fig. 4.

The comparison above is at the saturated pulse count, this module's default. Below it
the single-pulse relief is applied on top of d^-2, a combination that was
not measured below 200 um. The current-density check is provisional at every size, and its
detail says so for this regime.

**Pulse count.** The threshold drops steeply over the first pulses and then *saturates*:
by a factor of about 7 on retina and 14 on chorioallantoic membrane between 1 and 50
pulses, and is constant thereafter. A protocol is therefore either a single-shot case or
a repeated-exposure case, with little in between.

Independent agreement with McCreery
-----------------------------------
The authors note their sustained CAM threshold is "very similar to that measured during
chronic in vivo stimulation of the cat cortex using a large (0.5 cm^2) electrode",
i.e. McCreery et al. (1990) -- a different tissue, assay and laboratory landing on a
comparable number.

Their thermal estimate also agrees with this package's: for a 1 mm electrode at typical
rates and durations they compute a rise of order millikelvin and conclude "no
hyperthermia can be expected as a result of chronic stimulation".

Scope
-----
Chick chorioallantoic membrane in vivo and chick retina in vitro, verified on porcine
retina. **Not** cortex, and not chronic in the months sense. Applying these numbers to
brain tissue is an extrapolation across preparation, which is why the check built on
them reports a comparison rather than a verdict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Tissue = Literal["retina", "cam"]

# --- anchor points, repeated exposure (>= 50 pulses), retina ----------------------

RETINA_THRESHOLD_AT_6MS_A_PER_CM2 = 0.061
"""Threshold current density on retina at 6 ms per phase, repeated exposure."""

RETINA_THRESHOLD_AT_6US_A_PER_CM2 = 1.3
"""Threshold current density on retina at 6 us per phase, repeated exposure."""

ANCHOR_LONG_US = 6000.0
ANCHOR_SHORT_US = 6.0

QUOTED_DURATION_EXPONENT = -0.5
"""The exponent the authors quote, identified as characteristic of electroporation."""

FITTED_DURATION_EXPONENT = math.log(
    RETINA_THRESHOLD_AT_6US_A_PER_CM2 / RETINA_THRESHOLD_AT_6MS_A_PER_CM2
) / math.log(ANCHOR_SHORT_US / ANCHOR_LONG_US)
"""Exponent of the straight line through their two retina anchor points; about -0.44."""

PUBLISHED_EXPONENT_RETINA_SUSTAINED = -0.48
"""The authors' own power fit for retina under sustained pulsing (p. 2264: "the power fit
slopes are t^-0.52 and t^-0.48 in the chronic regime, and t^-0.49 and t^-0.41 with the
single shots on CAM and retina, respectively", read from the page image; the exponents are
typeset as glyphs the text layer drops). The default duration dependence uses it, capped as
:func:`threshold_A_per_cm2` describes (ledger 77, S-6)."""

# --- electrode size regimes -------------------------------------------------------

SIZE_INDEPENDENT_ABOVE_UM = 300.0
"""Above this diameter the threshold current density no longer depends on size."""

CONSTANT_CURRENT_BELOW_UM = 200.0
"""Below this diameter the threshold *total current* is constant, so J_th scales d^-2."""

SMALL_ELECTRODE_THRESHOLD_CURRENT_UA = {"retina": 139.0, "cam": 55.0}
"""Damaging total current below 200 um, as measured (p. 2264, Fig. 5 caption).

Recorded, not used by :func:`threshold_A_per_cm2` (ledger 77, S-13)."""

SMALL_ELECTRODE_PULSE_WIDTH_US = {"retina": 600.0, "cam": 60.0}
"""Pulse width each small-electrode current was measured at (p. 2264)."""

SMALL_ELECTRODE_DURATION_EXPONENT_RETINA = -0.29
"""Strength-duration slope for the 0.115 mm pipette on retina (p. 2264, Fig. 6), read
from the page image; the exponent is typeset as a glyph the text layer drops."""

SMALL_ELECTRODE_QUOTE = (
    "In the regime of constant current, electrodes smaller than 200 um, the threshold "
    "value of total current for damage is 139 uA on retina and 55 uA on CAM (Fig. 5 "
    "caption); these measurements were performed with only one pulse of duration 60 us "
    "on CAM and 600 us on the retina; the slopes are also t^-0.48 for the large pipette "
    "and t^-0.29 for the small one (Butterwick et al. 2007, p. 2264)"
)

# --- pulse count ------------------------------------------------------------------

PULSE_COUNT_SATURATION = 50
"""Beyond about this many pulses the threshold stops falling."""

REPEATED_EXPOSURE_FACTOR_RETINA = 7.0
"""Threshold falls by this factor from 1 pulse to saturation, on retina."""

REPEATED_EXPOSURE_FACTOR_CAM = 14.0
"""Same, on chorioallantoic membrane."""

PREPARATION = "chick chorioallantoic membrane in vivo, chick retina in vitro"
REFERENCE = "butterwick2007"


def threshold_A_per_cm2(
    pulse_width_us: float,
    diameter_um: float | None = None,
    *,
    n_pulses: int = PULSE_COUNT_SATURATION,
    tissue: Tissue = "retina",
    exponent: float | None = None,
) -> float:
    """Damage-threshold current density for a pulse width, size and exposure.

    Parameters
    ----------
    pulse_width_us:
        Per-phase pulse width.
    diameter_um:
        Electrode diameter. Below 200 um the threshold rises as ``d^-2``; above 300 um
        size has no effect. ``None`` assumes the large-electrode regime.
    n_pulses:
        Number of pulses. Defaults to the saturated repeated-exposure case, which is
        the conservative choice for any train.
    exponent:
        Duration exponent. By default the authors' published fit,
        :data:`PUBLISHED_EXPONENT_RETINA_SUSTAINED` (-0.48), anchored at 6 ms and taken as
        the minimum with the line through both published anchors, so that neither
        anchor (0.061 A/cm^2 at 6 ms, 1.3 at 6 us) is exceeded. The cap is this package's
        construction, not the paper's: the published slope from the 6 ms anchor would give
        1.67 A/cm^2 at 6 us, above the 1.3 they measured (ledger 77, S-6). In practice the
        two-anchor line is the lower below 6 ms and the published slope above it. Pass a
        number (for example :data:`QUOTED_DURATION_EXPONENT`, the -0.5 they quote) for a
        plain power law.
    """
    if pulse_width_us <= 0 or not math.isfinite(pulse_width_us):
        raise ValueError(f"pulse_width_us must be finite and > 0, got {pulse_width_us!r}")
    if n_pulses < 1:
        raise ValueError(f"n_pulses must be >= 1, got {n_pulses}")

    ratio = pulse_width_us / ANCHOR_LONG_US
    if exponent is None:
        base = RETINA_THRESHOLD_AT_6MS_A_PER_CM2 * min(
            ratio**PUBLISHED_EXPONENT_RETINA_SUSTAINED, ratio**FITTED_DURATION_EXPONENT
        )
    else:
        base = RETINA_THRESHOLD_AT_6MS_A_PER_CM2 * ratio**exponent

    if tissue == "cam":
        # Their CAM thresholds run about threefold below retina at matched settings.
        base /= 3.0

    # Single-pulse exposure tolerates more than the saturated repeated case.
    if n_pulses < PULSE_COUNT_SATURATION:
        factor = (
            REPEATED_EXPOSURE_FACTOR_RETINA
            if tissue == "retina"
            else REPEATED_EXPOSURE_FACTOR_CAM
        )
        # Log-linear interpolation between 1 pulse and saturation.
        fraction = math.log(n_pulses) / math.log(PULSE_COUNT_SATURATION)
        base *= factor ** (1.0 - fraction)

    if diameter_um is not None:
        if diameter_um <= 0:
            raise ValueError(f"diameter_um must be > 0, got {diameter_um!r}")
        if diameter_um < CONSTANT_CURRENT_BELOW_UM:
            # Threshold total current is constant below 200 um, so J_th goes as d^-2.
            base *= (CONSTANT_CURRENT_BELOW_UM / diameter_um) ** 2

    return base


def measured_small_electrode_A_per_cm2(
    diameter_um: float, tissue: Tissue = "retina"
) -> float:
    """The paper's small-electrode total current over a disc of ``diameter_um``.

    At the anchor's own pulse width (:data:`SMALL_ELECTRODE_PULSE_WIDTH_US`). For
    comparison only; :func:`threshold_A_per_cm2` sits below it (ledger 77, S-13).
    """
    if not 0 < diameter_um < CONSTANT_CURRENT_BELOW_UM:
        raise ValueError(
            f"the small-electrode anchor holds below {CONSTANT_CURRENT_BELOW_UM:g} um, "
            f"got {diameter_um!r}"
        )
    area_cm2 = math.pi * (diameter_um * 1e-4 / 2.0) ** 2
    return SMALL_ELECTRODE_THRESHOLD_CURRENT_UA[tissue] * 1e-6 / area_cm2


def size_regime(diameter_um: float) -> str:
    """Which electrode-size regime a diameter falls in."""
    if diameter_um < CONSTANT_CURRENT_BELOW_UM:
        return "constant-current (threshold density rises as d^-2)"
    if diameter_um > SIZE_INDEPENDENT_ABOVE_UM:
        return "size-independent"
    return "transition (200-300 um; neither scaling established)"


@dataclass(frozen=True)
class ThresholdComparison:
    """An applied current density against the Butterwick threshold."""

    applied_A_per_cm2: float
    threshold_A_per_cm2: float
    pulse_width_us: float
    diameter_um: float | None
    n_pulses: int
    tissue: str
    regime: str

    @property
    def utilisation(self) -> float:
        """Applied as a fraction of threshold."""
        return self.applied_A_per_cm2 / self.threshold_A_per_cm2

    @property
    def margin(self) -> float:
        """Threshold divided by applied."""
        if self.applied_A_per_cm2 <= 0:
            return math.inf
        return self.threshold_A_per_cm2 / self.applied_A_per_cm2

    @property
    def exceeds(self) -> bool:
        """Whether the applied density is at or above threshold."""
        return self.applied_A_per_cm2 >= self.threshold_A_per_cm2

    def describe(self) -> str:
        """Multi-line summary, with the threshold floored (ledger 96).

        The threshold is a maximum, and ``:.4g`` rounds a maximum up: 32 of 56 swept
        (diameter, pulse width) pairs printed a threshold strictly above the threshold.
        The applied density beside it keeps round-to-nearest -- flooring it would
        understate what is being delivered.

        Imported inside the function: ``neurostim.safety`` imports ``neurostim.data`` at
        module scope, so a module-level import here would close the cycle.
        ``uncertainty.Interval.describe`` does the same, for the same reason.
        """
        from ..safety._limits import format_limit

        small = (
            self.diameter_um is not None and self.diameter_um < CONSTANT_CURRENT_BELOW_UM
        )
        regime_lines = (
            [
                f"  regime      provisional below 200 um: d^-2 from the large-electrode "
                f"density, below the measured {SMALL_ELECTRODE_THRESHOLD_CURRENT_UA['retina']:g} uA "
                f"(retina, 600 us) and {SMALL_ELECTRODE_THRESHOLD_CURRENT_UA['cam']:g} uA "
                f"(CAM, 60 us) small-electrode currents"
            ]
            if small
            else []
        )
        if small and self.n_pulses < PULSE_COUNT_SATURATION:
            regime_lines.append(
                "              the single-pulse relief on top of d^-2 was not measured "
                "below 200 um"
            )
        return "\n".join(
            [
                f"  applied     {self.applied_A_per_cm2:.4g} A/cm^2",
                f"  threshold   {format_limit(self.threshold_A_per_cm2)} A/cm^2 "
                f"({self.utilisation * 100:.1f} % used, {self.margin:.2f}x margin)",
                f"  conditions  {self.pulse_width_us:g} us, {self.n_pulses} pulses, "
                f"{self.regime}",
                *regime_lines,
                f"  source      Butterwick et al. 2007, {PREPARATION};"
                f"\n              applying it to other tissue is an extrapolation "
                f"across preparation",
            ]
        )


def compare(
    applied_A_per_cm2: float,
    pulse_width_us: float,
    diameter_um: float | None = None,
    *,
    n_pulses: int = PULSE_COUNT_SATURATION,
    tissue: Tissue = "retina",
) -> ThresholdComparison:
    """Compare an applied current density against the threshold."""
    return ThresholdComparison(
        applied_A_per_cm2=applied_A_per_cm2,
        threshold_A_per_cm2=threshold_A_per_cm2(
            pulse_width_us, diameter_um, n_pulses=n_pulses, tissue=tissue
        ),
        pulse_width_us=pulse_width_us,
        diameter_um=diameter_um,
        n_pulses=n_pulses,
        tissue=tissue,
        regime=(
            "large-electrode regime"
            if diameter_um is None
            else size_regime(diameter_um)
        ),
    )
