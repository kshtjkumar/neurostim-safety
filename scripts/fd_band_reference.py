#!/usr/bin/env python3
"""Converged finite-volume reference for the access resistance of a band on an insulating shaft.

There is no compact exact solution for a cylindrical band electrode flush in the surface
of an insulating shaft, which is the geometry of every clinical DBS contact. This script
computes the answer directly, and the table it prints is the reference the tests pin
against (``tests/oracles/fd_band.FD_BAND_REFERENCE``). It imports no part of ``neurostim``.

The problem
-----------
Axisymmetric Laplace, ``div(sigma grad V) = 0``, outside an infinite insulating cylinder of
radius ``r0 = d/2``:

* the band, ``|z| <= h/2`` at ``r = r0``, is held at ``V = 1``;
* the rest of the shaft, ``|z| > h/2`` at ``r = r0``, is insulating (zero normal flux);
* the plane ``z = 0`` is a symmetry plane, so only ``z >= 0`` is solved;
* ``V = 0`` on a far box, whose finite size is removed by extrapolation (below).

``R = 1 / I`` with ``I`` the current leaving the band at ``V = 1``, counted as the net flux
out of every electrode node of a conservative node-centred finite-volume scheme.

Why it was rewritten (ledger 127)
---------------------------------
The first version placed its radial nodes geometrically from the shaft *radius*, so the
first radial cell was a fixed fraction of ``r0`` whatever the band height, and the
current-density singularity at the band edge was under-resolved -- worse as the band
shortened. Refined radially, it fell from 335.1 toward 328 ohm at the clinical aspect and
from 739.9 toward 675 at aspect 0.2. The table it produced certified an equal-area sphere
"within 2 %" that is in fact 10 % high at aspect 0.39.

This version clusters nodes at the band edge from both sides in ``z`` and outward from the
shaft in ``r``, with the first cell ``h / n_edge`` -- tied to the band height, which is the
length scale of the singularity. Each value is then extrapolated twice:

1. **Far field.** ``R(L) = R_inf + b / L`` is the leading behaviour of a truncated
   exterior Laplace problem; two boxes give ``R_inf``.
2. **Grid.** Three refinements, each halving the first cell and the geometric growth
   excess together, give an observed order ``p`` and a Richardson estimate. The
   difference between the finest grid and the Richardson value is reported as the
   discretisation uncertainty.

The same solver, pointed at Newman's flush disc (exact ``1/(4 sigma a)``), is
``--disc-check``. It reproduces the exact value to well under 0.1 % after extrapolation,
which is what licenses trusting it on the band.

Usage
-----
::

    python scripts/fd_band_reference.py                 # the reference sweep (minutes)
    python scripts/fd_band_reference.py --convergence   # refinement table, clinical aspect
    python scripts/fd_band_reference.py --disc-check    # validation on the exact disc
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

SIGMA_S_PER_M = 0.35
"""Grey-matter conductivity used throughout the package."""

SHAFT_DIAMETER_M = 1270e-6
"""Medtronic 3389 lead diameter. Aspect ratio is band height / shaft diameter."""

REFERENCE_ASPECTS = (0.2, 0.39, 0.5, 1.0, 1.181, 2.0, 4.0, 10.0)
"""1.181 is the clinical contact: 1500 um of band on a 1270 um shaft."""

REFINEMENTS = ((250, 0.20), (500, 0.10), (1000, 0.05))
"""``(n_edge, growth excess)`` per level: first cell ``length / n_edge``, ratio ``1 + g``."""

BOXES = (200.0, 400.0)
"""Far-box sizes, as multiples of the problem's length scale, for the ``1/L`` extrapolation."""


def _clustered(start: float, stop: float, first: float, growth: float) -> np.ndarray:
    """Nodes from ``start`` toward ``stop``, first gap ``first``, each gap ``growth`` x the last.

    Works in either direction. The last node is ``stop`` exactly, and the final gap is
    merged into the previous one if it would be shorter than half of it.
    """
    direction = 1.0 if stop > start else -1.0
    span = abs(stop - start)
    offsets = [0.0]
    gap = first
    while offsets[-1] + gap < span:
        offsets.append(offsets[-1] + gap)
        gap *= growth
    if span - offsets[-1] < 0.5 * (offsets[-1] - offsets[-2] if len(offsets) > 1 else span):
        offsets[-1] = span
    else:
        offsets.append(span)
    return start + direction * np.asarray(offsets)


def _solve(
    r: np.ndarray,
    z: np.ndarray,
    electrode: np.ndarray,
    neumann_r0: bool,
) -> float:
    """``sum G (1 - V)`` over conductances leaving electrode nodes, sans ``2 pi sigma``.

    ``electrode`` is a boolean (nr, nz) mask of nodes held at ``V = 1``. Nodes on the last
    row and column are held at ``V = 0``. Every other boundary is zero-flux, which the
    node-centred control volumes give for free: a boundary node's volume simply has no
    face beyond the boundary. ``neumann_r0`` only documents intent; the axis ``r = 0`` of the
    disc problem has zero face area automatically.
    """
    del neumann_r0
    nr, nz = len(r), len(z)
    rf = np.empty(nr + 1)
    rf[1:-1] = 0.5 * (r[:-1] + r[1:])
    rf[0], rf[-1] = r[0], r[-1]
    zf = np.empty(nz + 1)
    zf[1:-1] = 0.5 * (z[:-1] + z[1:])
    zf[0], zf[-1] = z[0], z[-1]
    dz = np.diff(zf)
    annulus = 0.5 * (rf[1:] ** 2 - rf[:-1] ** 2)  # (area of the ring face) / (2 pi)

    # Conductances without 2*pi*sigma: radial faces between (i, j) and (i+1, j), and axial
    # faces between (i, j) and (i, j+1).
    g_r = (rf[1:-1] / np.diff(r))[:, None] * dz[None, :]  # (nr-1, nz)
    g_z = annulus[:, None] / np.diff(z)[None, :]  # (nr, nz-1)

    far = np.zeros((nr, nz), dtype=bool)
    far[-1, :] = True
    far[:, -1] = True
    fixed = electrode | far
    index = -np.ones((nr, nz), dtype=np.int64)
    free = ~fixed
    index[free] = np.arange(int(free.sum()))
    n = int(free.sum())

    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    diag = np.zeros(n)
    rhs = np.zeros(n)
    value = np.where(electrode, 1.0, 0.0)

    def couple(a_idx, b_idx, g, a_fixed, b_fixed, b_value):
        # a is free; b is its neighbour through conductance g.
        np.add.at(diag, a_idx, g)
        both = ~b_fixed
        rows.append(a_idx[both])
        cols.append(b_idx[both])
        vals.append(-g[both])
        np.add.at(rhs, a_idx[b_fixed], g[b_fixed] * b_value[b_fixed])

    ii, jj = np.meshgrid(np.arange(nr - 1), np.arange(nz), indexing="ij")
    for (ia, ja), (ib, jb), g in (
        ((ii, jj), (ii + 1, jj), g_r),
        ((ii + 1, jj), (ii, jj), g_r),
    ):
        mask = free[ia, ja]
        couple(
            index[ia, ja][mask], index[ib, jb][mask], g[mask],
            None, fixed[ib, jb][mask], value[ib, jb][mask],
        )
    ii, jj = np.meshgrid(np.arange(nr), np.arange(nz - 1), indexing="ij")
    for (ia, ja), (ib, jb) in (((ii, jj), (ii, jj + 1)), ((ii, jj + 1), (ii, jj))):
        mask = free[ia, ja]
        couple(
            index[ia, ja][mask], index[ib, jb][mask], g_z[mask],
            None, fixed[ib, jb][mask], value[ib, jb][mask],
        )
    rows.append(np.arange(n))
    cols.append(np.arange(n))
    vals.append(diag)
    matrix = sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    )
    solution = spla.spsolve(matrix.tocsc(), rhs)
    potential = value.copy()
    potential[free] = solution

    # Net conductance-weighted flux out of every electrode node.
    current = 0.0
    e = electrode
    current += float(np.sum(g_r[e[:-1, :] & ~e[1:, :]] * (1.0 - potential[1:, :][e[:-1, :] & ~e[1:, :]])))
    current += float(np.sum(g_r[e[1:, :] & ~e[:-1, :]] * (1.0 - potential[:-1, :][e[1:, :] & ~e[:-1, :]])))
    current += float(np.sum(g_z[e[:, :-1] & ~e[:, 1:]] * (1.0 - potential[:, 1:][e[:, :-1] & ~e[:, 1:]])))
    current += float(np.sum(g_z[e[:, 1:] & ~e[:, :-1]] * (1.0 - potential[:, :-1][e[:, 1:] & ~e[:, :-1]])))
    return current


def band_resistance_ohm(
    shaft_radius_m: float,
    band_height_m: float,
    *,
    n_edge: int,
    growth: float,
    box: float,
    conductivity_S_per_m: float = SIGMA_S_PER_M,
) -> float:
    """One solve: first cell ``h / n_edge``, growth ``1 + growth``, far box ``box`` x length."""
    half = band_height_m / 2.0
    first = band_height_m / n_edge
    scale = max(band_height_m, shaft_radius_m)
    r = _clustered(shaft_radius_m, shaft_radius_m + box * scale, first, 1.0 + growth)
    below = _clustered(half, 0.0, first, 1.0 + growth)[::-1]
    above = _clustered(half, box * scale, first, 1.0 + growth)
    z = np.concatenate([below, above[1:]])
    electrode = np.zeros((len(r), len(z)), dtype=bool)
    electrode[0, z <= half * (1.0 + 1e-12)] = True
    current = _solve(r, z, electrode, neumann_r0=False)
    # 2 pi sigma restored, and doubled for the mirror half z < 0.
    return 1.0 / (2.0 * 2.0 * math.pi * conductivity_S_per_m * current)


def disc_resistance_ohm(
    radius_m: float,
    *,
    n_edge: int,
    growth: float,
    box: float,
    conductivity_S_per_m: float = SIGMA_S_PER_M,
) -> float:
    """Newman's flush disc by the same solver: electrode on ``z = 0``, ``r <= a``."""
    first = radius_m / n_edge
    inner = _clustered(radius_m, 0.0, first, 1.0 + growth)[::-1]
    outer = _clustered(radius_m, box * radius_m, first, 1.0 + growth)
    r = np.concatenate([inner, outer[1:]])
    z = _clustered(0.0, box * radius_m, first, 1.0 + growth)
    electrode = np.zeros((len(r), len(z)), dtype=bool)
    electrode[r <= radius_m * (1.0 + 1e-12), 0] = True
    current = _solve(r, z, electrode, neumann_r0=True)
    return 1.0 / (2.0 * math.pi * conductivity_S_per_m * current)


@dataclass(frozen=True)
class Converged:
    """A value extrapolated in box size and grid, with what the extrapolation moved."""

    finest_ohm: float
    richardson_ohm: float
    order: float

    @property
    def uncertainty_ohm(self) -> float:
        return abs(self.finest_ohm - self.richardson_ohm)


def converge(solve) -> Converged:
    """Box-extrapolate each refinement level, then Richardson over the three levels."""
    levels = []
    for n_edge, growth in REFINEMENTS:
        small, large = (solve(n_edge=n_edge, growth=growth, box=b) for b in BOXES)
        l1, l2 = BOXES
        levels.append((l2 * large - l1 * small) / (l2 - l1))
    coarse, mid, fine = levels
    ratio = (coarse - mid) / (mid - fine) if mid != fine else math.inf
    order = math.log(ratio, 2.0) if ratio > 0 and math.isfinite(ratio) else math.nan
    if math.isfinite(order) and order > 0:
        richardson = fine + (fine - mid) / (2.0**order - 1.0)
    else:
        richardson = fine
    return Converged(finest_ohm=fine, richardson_ohm=richardson, order=order)


def equal_area_sphere_ohm(area_m2: float, conductivity_S_per_m: float = SIGMA_S_PER_M) -> float:
    return 1.0 / (4.0 * math.pi * conductivity_S_per_m * math.sqrt(area_m2 / (4.0 * math.pi)))


def sweep() -> None:
    print(f"sigma = {SIGMA_S_PER_M} S/m, shaft d = {SHAFT_DIAMETER_M * 1e6:.0f} um\n")
    print(f"{'aspect':>7} {'finest':>9} {'Richardson':>11} {'p':>5} {'+-':>6} {'sphere':>8} {'sph/FV':>8}")
    for aspect in REFERENCE_ASPECTS:
        height = aspect * SHAFT_DIAMETER_M
        result = converge(
            lambda h=height, **kw: band_resistance_ohm(SHAFT_DIAMETER_M / 2.0, h, **kw)
        )
        sphere = equal_area_sphere_ohm(math.pi * SHAFT_DIAMETER_M * height)
        print(
            f"{aspect:7.3f} {result.finest_ohm:9.2f} {result.richardson_ohm:11.2f} "
            f"{result.order:5.2f} {result.uncertainty_ohm:6.2f} {sphere:8.1f} "
            f"{sphere / result.richardson_ohm - 1.0:+8.2%}"
        )


def convergence() -> None:
    height = 1.181 * SHAFT_DIAMETER_M
    print("clinical contact, 1500 um band on a 1270 um shaft\n")
    for n_edge, growth in REFINEMENTS:
        for box in BOXES:
            value = band_resistance_ohm(
                SHAFT_DIAMETER_M / 2.0, height, n_edge=n_edge, growth=growth, box=box
            )
            print(f"n_edge {n_edge:5d}  growth {growth:4.2f}  box {box:6.0f}  R {value:9.3f}")


def disc_check() -> None:
    radius = 250e-6
    exact = 1.0 / (4.0 * SIGMA_S_PER_M * radius)
    result = converge(lambda **kw: disc_resistance_ohm(radius, **kw))
    print(
        f"Newman disc a = 250 um: exact {exact:.3f}, finest {result.finest_ohm:.3f} "
        f"({result.finest_ohm / exact - 1:+.3%}), Richardson {result.richardson_ohm:.3f} "
        f"({result.richardson_ohm / exact - 1:+.3%}), order {result.order:.2f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--convergence", action="store_true")
    parser.add_argument("--disc-check", action="store_true")
    args = parser.parse_args(argv)
    if args.disc_check:
        disc_check()
    elif args.convergence:
        convergence()
    else:
        sweep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
