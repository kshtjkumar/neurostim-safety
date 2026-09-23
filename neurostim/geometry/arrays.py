"""Multi-site electrode arrays.

An array is a named collection of :class:`~neurostim.geometry.base.Electrode` sites at
known positions. Positions matter for two things this package models: superposition of
the point-source potential field, and the caution that simultaneous stimulation on
neighbouring sites does not simply share charge in proportion to area.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .base import Electrode


@dataclass(frozen=True)
class ArraySite:
    """One electrode at a position, in micrometres, in the array's own frame."""

    electrode: Electrode
    x_um: float = 0.0
    y_um: float = 0.0
    z_um: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        for name, value in (("x_um", self.x_um), ("y_um", self.y_um), ("z_um", self.z_um)):
            if not math.isfinite(value):
                raise ValueError(f"site position {name} must be finite, got {value!r}")

    def position_um(self) -> tuple[float, float, float]:
        """Cartesian position tuple."""
        return (self.x_um, self.y_um, self.z_um)

    def distance_to_um(self, other: ArraySite) -> float:
        """Centre-to-centre distance to another site."""
        return math.dist(self.position_um(), other.position_um())


@dataclass(frozen=True)
class ElectrodeArray:
    """A collection of electrode sites."""

    sites: tuple[ArraySite, ...] = field(default_factory=tuple)
    name: str = "array"

    def __post_init__(self) -> None:
        if not self.sites:
            raise ValueError("An ElectrodeArray needs at least one site")
        # Two sites at one point are one site twice: a minimum pitch of 0.0 and a field
        # that diverges between them (ledger 28). A pitch too small to be physical is the
        # caller's to judge; zero is not a pitch at all.
        seen: dict[tuple[float, float, float], str] = {}
        for index, site in enumerate(self.sites):
            label = site.label or f"#{index}"
            position = site.position_um()
            if position in seen:
                raise ValueError(
                    f"sites {seen[position]} and {label} coincide at {position} um"
                )
            seen[position] = label

    def __len__(self) -> int:
        return len(self.sites)

    def __iter__(self):
        return iter(self.sites)

    def __getitem__(self, index: int) -> ArraySite:
        return self.sites[index]

    @property
    def total_area_cm2(self) -> float:
        """Summed geometric area of every site."""
        return sum(s.electrode.area_cm2 for s in self.sites)

    @property
    def mean_area_cm2(self) -> float:
        """Mean geometric area per site."""
        return self.total_area_cm2 / len(self.sites)

    @property
    def is_homogeneous(self) -> bool:
        """Whether every site has the same geometry and material."""
        first = self.sites[0].electrode
        return all(s.electrode == first for s in self.sites)

    def min_pitch_um(self) -> float:
        """Smallest centre-to-centre distance between any two sites.

        Returns ``inf`` for a single-site array.
        """
        if len(self.sites) < 2:
            return math.inf
        return min(
            self.sites[i].distance_to_um(self.sites[j])
            for i in range(len(self.sites))
            for j in range(i + 1, len(self.sites))
        )

    def describe(self) -> str:
        """Multi-line summary."""
        pitch = self.min_pitch_um()
        pitch_text = "n/a" if math.isinf(pitch) else f"{pitch:g} um"
        lines = [
            f"{self.name}: {len(self)} sites, "
            f"total area {self.total_area_cm2:.4g} cm^2, min pitch {pitch_text}",
            f"  homogeneous: {self.is_homogeneous}",
        ]
        for s in self.sites:
            label = s.label or "site"
            lines.append(f"  {label} @ {s.position_um()}: {s.electrode.describe()}")
        return "\n".join(lines)


def linear_array(
    electrode: Electrode,
    n_sites: int,
    pitch_um: float,
    *,
    name: str = "linear array",
    axis: str = "z",
) -> ElectrodeArray:
    """Build an evenly spaced 1-D array of identical sites, e.g. a DBS lead."""
    if n_sites < 1:
        raise ValueError(f"n_sites must be >= 1, got {n_sites}")
    _check_pitch(pitch_um)
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis must be x, y or z, got {axis!r}")

    sites = []
    for i in range(n_sites):
        offset = i * pitch_um
        coords = {"x": 0.0, "y": 0.0, "z": 0.0}
        coords[axis] = offset
        sites.append(
            ArraySite(electrode=electrode, label=f"{i}", **{f"{k}_um": v for k, v in coords.items()})
        )
    return ElectrodeArray(sites=tuple(sites), name=name)


def grid_array(
    electrode: Electrode,
    n_rows: int,
    n_cols: int,
    pitch_um: float,
    *,
    name: str = "grid array",
) -> ElectrodeArray:
    """Build a rectangular grid of identical sites in the x-y plane, e.g. a Utah array."""
    if n_rows < 1 or n_cols < 1:
        raise ValueError(f"n_rows and n_cols must be >= 1, got {n_rows}x{n_cols}")
    _check_pitch(pitch_um)

    sites = tuple(
        ArraySite(
            electrode=electrode,
            x_um=col * pitch_um,
            y_um=row * pitch_um,
            label=f"r{row}c{col}",
        )
        for row in range(n_rows)
        for col in range(n_cols)
    )
    return ElectrodeArray(sites=sites, name=name)


def _check_pitch(pitch_um: float) -> None:
    """Finite and positive. ``pitch_um <= 0`` alone is False for NaN (ledger 28)."""
    if not math.isfinite(pitch_um) or pitch_um <= 0:
        raise ValueError(f"pitch_um must be finite and > 0, got {pitch_um!r}")
