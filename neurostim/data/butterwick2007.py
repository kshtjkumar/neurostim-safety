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
"""Exponent fitted to their two retina anchor points; about -0.44."""

# --- electrode size regimes -------------------------------------------------------

SIZE_INDEPENDENT_ABOVE_UM = 300.0
"""Above this diameter the threshold current density no longer depends on size."""

CONSTANT_CURRENT_BELOW_UM = 200.0
"""Below this diameter the threshold *total current* is constant, so J_th scales d^-2."""

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
        Duration exponent. Defaults to the value fitted to the authors' own anchor
        points; pass :data:`QUOTED_DURATION_EXPONENT` for the -0.5 they quote.
    """
    if pulse_width_us <= 0 or not math.isfinite(pulse_width_us):
        raise ValueError(f"pulse_width_us must be finite and > 0, got {pulse_width_us!r}")
    if n_pulses < 1:
        raise ValueError(f"n_pulses must be >= 1, got {n_pulses}")

    n = FITTED_DURATION_EXPONENT if exponent is None else exponent
    base = RETINA_THRESHOLD_AT_6MS_A_PER_CM2 * (pulse_width_us / ANCHOR_LONG_US) ** n

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
        """Multi-line summary."""
        return "\n".join(
            [
                f"  applied     {self.applied_A_per_cm2:.4g} A/cm^2",
                f"  threshold   {self.threshold_A_per_cm2:.4g} A/cm^2 "
                f"({self.utilisation * 100:.1f} % used, {self.margin:.2f}x margin)",
                f"  conditions  {self.pulse_width_us:g} us, {self.n_pulses} pulses, "
                f"{self.regime}",
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
