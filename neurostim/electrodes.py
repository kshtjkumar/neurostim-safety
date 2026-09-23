"""Electrode presets, every one taken from a paper in this package's bibliography.

Why these and not a catalogue
-----------------------------
It would be easy to fill this file with commercial part numbers and plausible-looking
dimensions. Nothing here is guessed: each preset reproduces an electrode that a cited
paper describes, with the citation attached, so a report built on one can be traced the
same way the constants can.

That makes the library smaller than a vendor catalogue and more useful than one, because
these are the geometries the damage and charge-injection data were actually measured on.
Using a preset means the limits being applied were measured on something like it.

For anything else, construct the geometry directly -- the presets are a convenience, not
a gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import CylindricalBandElectrode, DiscElectrode, Electrode
from .references import cite


@dataclass(frozen=True)
class ElectrodePreset:
    """A published electrode, its geometry, and what it was used for."""

    key: str
    name: str
    electrode: Electrode
    reference: str
    context: str
    note: str = ""

    def __post_init__(self) -> None:
        cite(self.reference)

    def describe(self) -> str:
        """Multi-line summary with provenance."""
        lines = [
            f"{self.name} ({self.key})",
            f"  {self.electrode.describe()}",
            f"  source: {self.reference} -- {self.context}",
        ]
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


_PRESETS: tuple[ElectrodePreset, ...] = (
    # --- clinical deep brain stimulation ---
    ElectrodePreset(
        key="dbs_3389",
        name="DBS lead, 1.5 mm contact at 0.5 mm spacing",
        electrode=CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
        reference="elwassif2006",
        context="Medtronic 3389-style lead modelled in their bio-heat study",
        note=(
            "0.0598 cm^2, matching the 0.06 cm^2 Cogan (2008) quotes for clinical DBS. "
            "Runs about 0.2 K hotter than the wider-spaced 3387 at matched settings"
        ),
    ),
    ElectrodePreset(
        key="dbs_3387",
        name="DBS lead, 1.5 mm contact at 1.5 mm spacing",
        electrode=CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
        reference="elwassif2006",
        context="Medtronic 3387-style lead modelled in their bio-heat study",
        note=(
            "Same contact geometry as the 3389; the wider inter-contact spacing is what "
            "makes it cooler, and is not represented by a single-contact model"
        ),
    ),
    ElectrodePreset(
        key="dbs_kuncel",
        name="DBS contact as modelled by Kuncel & Grill",
        electrode=CylindricalBandElectrode(1260.0, 1500.0, "PtIr"),
        reference="kuncel_grill2004_full",
        context="1.26 x 1.5 mm contact driven at 3 V in their current-distribution model",
        note=(
            "The geometry behind their 0.0993 A/cm^2 average current density and the "
            "25.6 % of surface above it"
        ),
    ),
    # --- the electrodes the Shannon criterion was measured on ---
    ElectrodePreset(
        key="mccreery_surface_smallest",
        name="Cortical surface disc, 0.01 cm^2",
        electrode=DiscElectrode(1128.4, "Pt"),
        reference="mccreery1990",
        context="smallest platinum surface disc in the study behind the Shannon fit",
        note="Damaged at 1 uC/phase and 100 uC/cm^2 in 3 of 4 sites",
    ),
    ElectrodePreset(
        key="mccreery_surface_largest",
        name="Cortical surface disc, 0.5 cm^2",
        electrode=DiscElectrode(7978.8, "Pt"),
        reference="mccreery1990",
        context="largest platinum surface disc in the study behind the Shannon fit",
        note=(
            "The 12 uC/cm^2 lower bound on damage anywhere in that study came from this "
            "electrode, at 6 uC/phase"
        ),
    ),
    ElectrodePreset(
        key="mccreery_microelectrode",
        name="Penetrating activated-iridium microelectrode",
        electrode=DiscElectrode(
            91.0, "AIROF", environment="full_space",
            stands_in_for="a faceted penetrating wire tip",
        ),
        reference="mccreery1990",
        context=(
            "75 um iridium wire ground to a conical point with an ellipsoidal facet "
            "of 6.5e-5 cm^2 at 45 degrees to the shaft"
        ),
        note=(
            "Modelled as an equal-area disc: the facet is elliptical, and the paper "
            "gives its mean radius as about 45 um. Showed no damage at 800 and "
            "1600 uC/cm^2 -- the observation that forces charge density and charge per "
            "phase to be treated as cofactors. Full-space: 'The penetrating "
            "microelectrodes were inserted approximately 1.5 mm deep into the parietal "
            "cortex'"
        ),
    ),
    # --- chronic microstimulation ---
    ElectrodePreset(
        key="mccreery2010_chronic",
        name="Chronic activated-iridium microelectrode, 2000 um^2",
        electrode=DiscElectrode(
            50.5, "AIROF", environment="full_space",
            stands_in_for="a penetrating microelectrode site",
        ),
        reference="mccreery2010",
        context="implanted 450-1282 days in cat sensorimotor cortex, pulsed 240 h",
        note=(
            "Safe at 2 nC/phase; 4 nC/phase caused neuron loss to at least 150 um at "
            "100 % duty cycle and about 60 um at 50 %. Tagged full-space as a penetrating "
            "microelectrode; geometry not verified against the source, because the paper "
            "is not in the package's library"
        ),
    ),
    # --- electrochemical characterisation ---
    ElectrodePreset(
        key="rose_robblee_typeA",
        name="Smooth platinum disc, 1.1 mm",
        electrode=DiscElectrode(1100.0, "Pt"),
        reference="rose_robblee1990",
        context="Type A electrode used to set the 50-150 uC/cm^2 platinum limit",
        note=(
            "Measured roughness factor 3x; 9.5e-3 cm^2 geometric. 'A smooth disk, 1.1 mm "
            "diam, cut from Pt foil and mounted in a silicone rubber support' -- a real "
            "flush disc, so the half-space Newman resistance applies"
        ),
    ),
    ElectrodePreset(
        key="beebe_iridium_wire",
        name="Activated iridium wire, 4.1e-4 cm^2",
        electrode=DiscElectrode(
            228.4, "AIROF", stands_in_for="a wire stub protruding through a septum",
        ),
        reference="beebe_rose1988",
        context="iridium wire in bicarbonate buffered saline at pH 7.3",
        note=(
            "Source of the AIROF limits: 1.0 mC/cm^2 cathodic-first, 2.1 anodic-first, "
            "3.5 biased to +0.8 V vs SCE. The wires 'were inserted through a silicone "
            "septum, sanded flat, and then positioned to leave an exposed length of under "
            "0.01 cm': a stub protruding into the half-space the septum bounds, so "
            "half-space, and the disc resistance is an approximation"
        ),
    ),
    ElectrodePreset(
        key="weiland_tin",
        name="Porous titanium nitride, 4000 um^2",
        electrode=DiscElectrode(
            71.4, "TiN", stands_in_for="an electrode whose geometry the library cannot check",
        ),
        reference="weiland2002_tin",
        context="in vitro measurement giving 0.9 mC/cm^2 at 0.5 ms",
        note=(
            "Geometry not verified against the source; the paper is not in the package's "
            "library, so whether this was a planar thin-film site or an immersed wire "
            "cannot be checked. Left half-space by default and marked approximate"
        ),
    ),
)

PRESETS: dict[str, ElectrodePreset] = {p.key: p for p in _PRESETS}

# Case-insensitive index. Built separately rather than lowering the query against
# PRESETS directly, which would make any mixed-case key unreachable.
_INDEX: dict[str, str] = {p.key.lower(): p.key for p in _PRESETS}


def get_preset(key: str) -> ElectrodePreset:
    """Look up a preset by key, case-insensitively."""
    try:
        return PRESETS[_INDEX[key.strip().lower()]]
    except KeyError:
        raise KeyError(
            f"Unknown electrode preset {key!r}. Available: {sorted(PRESETS)}"
        ) from None


def electrode(key: str) -> Electrode:
    """The geometry of a preset, ready to hand to :class:`SafetyCalculator`."""
    return get_preset(key).electrode


def list_presets() -> list[ElectrodePreset]:
    """Every preset in registry order."""
    return list(_PRESETS)
