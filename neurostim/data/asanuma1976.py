"""Chronaxie, threshold and spread for intracortical microstimulation.

Why this closes a gap
---------------------
:mod:`neurostim.models.strength_duration` deliberately ships no default rheobase or
chronaxie: those depend on the distance between electrode and target and must be
measured. That is still true. What was missing was any *measured* chronaxie at all, so
there was nothing to check a fit against -- a fit returning a 3 ms chronaxie for a
cortical neuron would have passed silently.

Asanuma et al. measured 11 strength-duration curves in cat motor cortex with the shock
artifact cancelled, separating cell bodies from axons for the first time, and the two
populations differ:

============  =============  ==============  =========
Structure     Chronaxie      Median          n curves
============  =============  ==============  =========
cell bodies   0.12-0.2 ms    0.14 ms         4
axons         0.06-0.13 ms   0.085 ms        7
============  =============  ==============  =========

Mann-Whitney U, p < 0.012. In the one neuron where both were measured, the same cell gave
0.13 ms at the soma and 0.10 ms at its fibre.

**Axons are the shorter-chronaxie, lower-threshold structure**, and their thresholds went
as low as 0.4 uA. Combined with the finding that PT-cell axon collaterals run 1.0 mm
laterally, this is why intracortical microstimulation cannot be assumed to be activating
the neuron under the electrode. It sets a floor on how spatially selective any
stimulation claim can be, independent of the charge involved.

The functional damage threshold
-------------------------------
Separately from any electrochemical or histological limit, this paper records a
*physiological* one. Trains at 80 uA (0.2 ms, the intensity another group had been using
for mapping) markedly reduced descending volleys in 5 of 7 trials, with a second,
longer-lasting depression beginning 3-5 minutes afterwards. See
:data:`NOXIOUS_CURRENT_UA`. At 0.2 ms that is 16 nC/phase -- orders of magnitude below
any charge density this package would flag, on an electrode whose area makes the charge
density enormous. Reversible functional depression is simply not what the Shannon
criterion measures.

A transcription note
--------------------
The Figure 4 caption gives fibre rheobases as "20, 2.5 and 1.0 ua". Twenty is almost
certainly a typographic slip for 2.0 -- it is eight times the next value, and the paper's
own text puts axon thresholds "frequently less than 5.0 ua". It is stored here as
printed, flagged, rather than silently corrected.
"""

from __future__ import annotations

from dataclasses import dataclass

REFERENCE = "asanuma1976"

PULSE_WIDTH_US = 200.0
"""Cathodal, used throughout, chosen for comparability with the surrounding literature."""

ELECTRODE_TIP_UM = (10.0, 15.0)
"""Tungsten microelectrode tip, following Stoney et al. (1968)."""

PREPARATION = "cat pericruciate motor cortex, pentobarbital anaesthesia"


@dataclass(frozen=True)
class ChronaxieRange:
    """Chronaxie measured for one class of neural structure."""

    structure: str
    low_ms: float
    high_ms: float
    median_ms: float
    n_curves: int
    reference: str
    note: str = ""

    @property
    def low_us(self) -> float:
        return self.low_ms * 1e3

    @property
    def high_us(self) -> float:
        return self.high_ms * 1e3

    @property
    def median_us(self) -> float:
        return self.median_ms * 1e3

    def contains(self, chronaxie_us: float) -> bool:
        """Whether a fitted chronaxie falls inside the measured range."""
        return self.low_us <= chronaxie_us <= self.high_us

    def describe(self) -> str:
        text = (
            f"{self.structure}: {self.low_ms:g}-{self.high_ms:g} ms "
            f"(median {self.median_ms:g}, n={self.n_curves}) [{self.reference}]"
        )
        return f"{text} -- {self.note}" if self.note else text


CHRONAXIES: tuple[ChronaxieRange, ...] = (
    ChronaxieRange(
        structure="cortical cell bodies",
        low_ms=0.12,
        high_ms=0.2,
        median_ms=0.14,
        n_curves=4,
        reference="asanuma1976",
        note="PT cells in cat motor cortex, ICMS with shock artifact cancelled",
    ),
    ChronaxieRange(
        structure="cortical axons and collaterals",
        low_ms=0.06,
        high_ms=0.13,
        median_ms=0.085,
        n_curves=7,
        reference="asanuma1976",
        note="significantly shorter than cell bodies, Mann-Whitney p<0.012",
    ),
    ChronaxieRange(
        structure="PT cells (earlier measurement)",
        low_ms=0.12,
        high_ms=0.4,
        median_ms=0.26,
        n_curves=3,
        reference="stoney1968",
        note=(
            "quoted by Asanuma et al. as the value their cell-body range is "
            "compatible with; median is the midpoint, not a reported statistic"
        ),
    ),
    ChronaxieRange(
        structure="spinal cord fibres",
        low_ms=0.04,
        high_ms=0.08,
        median_ms=0.06,
        n_curves=0,
        reference="asanuma1976",
        note=(
            "cited from BeMent & Ranck (1969) and Jankowska et al.; median is the "
            "midpoint. Shorter still than cortical axons"
        ),
    ),
)

PAIRED_SAME_NEURON_MS = {"cell_body": 0.13, "fibre": 0.10}
"""The one neuron measured at both sites, which rules out between-cell variation."""

RHEOBASE_CELL_BODIES_UA = (2.0, 3.0, 3.5)
RHEOBASE_FIBRES_UA_AS_PRINTED = (20.0, 2.5, 1.0)
"""Figure 4 rheobases. The leading fibre value is transcribed as printed; see module
docstring. Use :func:`rheobase_fibres_ua` for the corrected reading."""

MIN_AXON_THRESHOLD_UA = 0.4
TYPICAL_AXON_THRESHOLD_CEILING_UA = 5.0
"""Axon thresholds were "frequently less than 5.0 ua", minimum observed 0.4 uA."""

# --- spatial spread ---------------------------------------------------------------

COLLATERAL_REACH_MM = 1.0
"""Horizontal extent of PT-cell axon collaterals from the soma."""

LOW_THRESHOLD_CYLINDER_RADIUS_MM = 1.0
"""Radius of the radially oriented region from which a given PT cell can be fired."""

SURFACE_LOW_THRESHOLD_AREA_MM2 = (2.0, 4.0)
"""Cortical surface area over which a single PT cell has a low threshold."""

SURFACE_EXTENT_AT_HIGH_CURRENT_MM = (4.0, 5.0)
SURFACE_HIGH_CURRENT_UA = (400.0, 500.0)
"""At the currents used for surface mapping, the effective extent is millimetres.

Asanuma et al.'s conclusion: surface stimulation cannot localise a cortical efferent
zone, because it recruits collaterals of cells a millimetre away as readily as the cells
beneath the electrode.
"""

MONOSYNAPTIC_SPREAD_SUPERFICIAL_MM = 0.4
"""Horizontal spread of monosynaptic connections when superficial layers are stimulated."""

# --- functional damage ------------------------------------------------------------

NOXIOUS_CURRENT_UA = 80.0
"""ICMS current at which descending volleys were markedly reduced.

0.2 ms cathodal, five successive trains. Observed in 5 of 7 trials, prominent in layer
III and weak or absent in layers V and VI. Volleys recovered by 3 min, then a second
reduction began 3-5 min later and lasted 30 min.
"""

NOXIOUS_RECOVERY_MIN = 3.0
NOXIOUS_SECOND_DEPRESSION_DURATION_MIN = 30.0
NOXIOUS_TRIALS_AFFECTED = (5, 7)

# --- train parameters -------------------------------------------------------------

OPTIMAL_TRAIN_FREQUENCY_HZ = (300.0, 400.0)
"""Frequencies at and above 300 Hz are equally efficient; below, thresholds rise."""

TRAIN_DURATION_TO_MIN_THRESHOLD_MS = {
    "surface": (8.0, 18.0, 11.8),
    "depth": (20.0, 32.0, 27.2),
}
"""(low, high, mean) train duration to reach 1.5x the minimum threshold.

Depth stimulation needs the longer train because ICMS works largely through indirect
descending volleys, which take 15-20 ms of the train to reach full size. A six-pulse
train is not a shorter version of a thirty-pulse train; it is a weaker stimulus at the
same current, which is why short-train mapping studies needed larger currents and
found larger zones.
"""

I_WAVE_PLATEAU_MS = (15.0, 20.0)


def rheobase_fibres_ua(as_printed: bool = False) -> tuple[float, ...]:
    """Figure 4 fibre rheobases, with the suspected typo corrected by default."""
    if as_printed:
        return RHEOBASE_FIBRES_UA_AS_PRINTED
    return (2.0, *RHEOBASE_FIBRES_UA_AS_PRINTED[1:])


def chronaxie_for(structure: str) -> ChronaxieRange:
    """Look up a chronaxie range by structure name, case-insensitively."""
    key = structure.strip().lower()
    for row in CHRONAXIES:
        if key in row.structure.lower():
            return row
    raise KeyError(
        f"No chronaxie on record for {structure!r}. "
        f"Known: {[r.structure for r in CHRONAXIES]}"
    )


def plausible_cortical_chronaxie(chronaxie_us: float) -> bool:
    """Whether a fitted chronaxie is within the range measured in cortex.

    Spans axons through cell bodies, 60-200 us. A fit outside this is not necessarily
    wrong -- it may be a different preparation or a different structure -- but it is
    outside everything this paper measured, and worth checking before it is used.
    """
    return 60.0 <= chronaxie_us <= 200.0


def threshold_ratio_at(pulse_width_us: float, chronaxie_us: float) -> float:
    """Threshold as a multiple of rheobase, the ordinate of Figure 4.

    ``1 + t_c / W``. Equals 2 at chronaxie by definition, for both the Weiss and
    Lapicque forms.

    The measured curves rise more steeply than this below about 0.15 ms: the published
    figure reaches 4-5x rheobase at 0.1 ms, where the fitted chronaxies predict 1.9-2.4x.
    Treat the classical forms as interpolation between measured points, not as a
    description of the short-pulse limit.
    """
    if pulse_width_us <= 0 or chronaxie_us <= 0:
        raise ValueError("pulse width and chronaxie must both be > 0")
    return 1.0 + chronaxie_us / pulse_width_us
