#!/usr/bin/env python3
"""Converged finite-volume reference for the access resistance of an insulated microwire tip.

A microwire is a conducting cylinder of radius ``a`` inside insulation, exposed at a flat
end face and, optionally, along a length ``l`` of shaft behind it. It is immersed in tissue
on every side, and no closed form exists. The package substitutes the equal-area sphere,
and this solve says how good that is: in units of ``R sigma a``, against ``l / a``. It
imports no part of ``neurostim``. The table it prints is
``tests/oracles/fd_microwire.FD_MICROWIRE_REFERENCE``.

The problem: axisymmetric Laplace in the full space outside a semi-infinite insulating rod
of radius ``a`` occupying ``r < a, z > 0``. The end face ``z = 0, r <= a`` and the shaft
``r = a, 0 <= z <= l`` are held at ``V = 1``; the rest of the rod surface is zero-flux; and
``V = 0`` on a far box whose size is extrapolated away in ``1/L``. The grid clusters at the
tip edge, and at the end of the exposed shaft, from both sides. Three refinements are
Richardson-extrapolated, as for the band (``scripts/fd_band_reference.py``, whose node
spacing helper this reuses).

**What it found (ledger 129).** The sphere is within about +-1.4 % from ``l = 0.25a`` to
``5a``, dipping to -1.3 % near ``2a``. It is +6.7 % at ``10a`` and +17 % at ``20a``, high
and growing for long exposures. At ``l = 0``, the flat end face alone, it is about 8 %
*low*, which is anti-conservative. That case converges slowly: the tip edge is a 270 degree
re-entrant corner, and the order observed there is about 0.7. The tabulated value is
therefore uncertain by a couple of per cent, and an independent solve by the Phase 3
reviewer gives 0.1755 against the 0.1726 here. Either way the sphere's 0.1592 is low, which
is why the package uses Newman's half-space disc, 0.25, a bound from above, for that one
case.

Usage::

    python scripts/fd_microwire_reference.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fd_band_reference import _clustered

EXPOSED_LENGTHS = (0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0)
"""Shaft exposure behind the flat tip, in wire radii."""

REFINEMENTS = ((100, 0.20), (200, 0.10), (400, 0.05))
BOXES = (100.0, 200.0)


def _solve(r: np.ndarray, z: np.ndarray, electrode: np.ndarray, removed: np.ndarray) -> float:
    """Net ``sum G (1 - V)`` out of electrode nodes, without ``2 pi sigma``.

    Node-centred finite volume, as in the band generator, with the nodes strictly inside the
    rod removed. A conductance between two nodes is dropped if either is inside the rod, so
    nodes on the rod surface keep only the half of their control volume that is in tissue:
    zero flux into the insulation.
    """
    nr, nz = len(r), len(z)
    rf = np.empty(nr + 1)
    rf[1:-1] = 0.5 * (r[:-1] + r[1:])
    rf[0], rf[-1] = r[0], r[-1]
    zf = np.empty(nz + 1)
    zf[1:-1] = 0.5 * (z[:-1] + z[1:])
    zf[0], zf[-1] = z[0], z[-1]
    dz = np.diff(zf)
    annulus = 0.5 * (rf[1:] ** 2 - rf[:-1] ** 2)
    g_r = (rf[1:-1] / np.diff(r))[:, None] * dz[None, :]
    g_z = annulus[:, None] / np.diff(z)[None, :]
    g_r = g_r * ~(removed[:-1, :] | removed[1:, :])
    g_z = g_z * ~(removed[:, :-1] | removed[:, 1:])

    far = np.zeros((nr, nz), dtype=bool)
    far[-1, :] = True
    far[:, 0] = True
    far[:, -1] = True
    fixed = electrode | far | removed
    free = ~fixed
    index = -np.ones((nr, nz), dtype=np.int64)
    index[free] = np.arange(int(free.sum()))
    n = int(free.sum())
    value = np.where(electrode, 1.0, 0.0)
    diag = np.zeros(n)
    rhs = np.zeros(n)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    def couple(ia, ja, ib, jb, g):
        mask = free[ia, ja] & (g > 0)
        a_idx, b_idx, gg = index[ia, ja][mask], index[ib, jb][mask], g[mask]
        b_fixed = fixed[ib, jb][mask]
        np.add.at(diag, a_idx, gg)
        rows.append(a_idx[~b_fixed])
        cols.append(b_idx[~b_fixed])
        vals.append(-gg[~b_fixed])
        np.add.at(rhs, a_idx[b_fixed], gg[b_fixed] * value[ib, jb][mask][b_fixed])

    ii, jj = np.meshgrid(np.arange(nr - 1), np.arange(nz), indexing="ij")
    couple(ii, jj, ii + 1, jj, g_r)
    couple(ii + 1, jj, ii, jj, g_r)
    ii, jj = np.meshgrid(np.arange(nr), np.arange(nz - 1), indexing="ij")
    couple(ii, jj, ii, jj + 1, g_z)
    couple(ii, jj + 1, ii, jj, g_z)
    rows.append(np.arange(n))
    cols.append(np.arange(n))
    vals.append(diag)
    matrix = sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    )
    potential = value.copy()
    potential[free] = spla.spsolve(matrix.tocsc(), rhs)

    current = 0.0
    e = electrode
    for g, (sa, sb) in (
        (g_r, (np.s_[:-1, :], np.s_[1:, :])),
        (g_r, (np.s_[1:, :], np.s_[:-1, :])),
        (g_z, (np.s_[:, :-1], np.s_[:, 1:])),
        (g_z, (np.s_[:, 1:], np.s_[:, :-1])),
    ):
        mask = e[sa] & ~e[sb] & ~removed[sb]
        current += float(np.sum(g[mask] * (1.0 - potential[sb][mask])))
    return current


def tip_resistance_sigma_a(exposed: float, *, n_edge: int, growth: float, box: float) -> float:
    """``R sigma a`` for a wire of radius 1 with ``exposed`` radii of shaft, one grid."""
    a = 1.0
    first = a / n_edge
    far = box * a
    r = np.concatenate([
        _clustered(a, 0.0, first, 1.0 + growth)[::-1],
        _clustered(a, far, first, 1.0 + growth)[1:],
    ])
    below = _clustered(0.0, -far, first, 1.0 + growth)[::-1]
    if exposed > 0.0:
        above = np.concatenate([
            _clustered(0.0, exposed / 2.0, first, 1.0 + growth),
            _clustered(exposed, exposed / 2.0, first, 1.0 + growth)[::-1][1:],
            _clustered(exposed, far, first, 1.0 + growth)[1:],
        ])
    else:
        above = _clustered(0.0, far, first, 1.0 + growth)
    z = np.unique(np.concatenate([below, above]))
    rr, zz = np.meshgrid(r, z, indexing="ij")
    tol = 1e-12
    removed = (rr < a - tol) & (zz > tol)
    electrode = ((np.abs(zz) <= tol) & (rr <= a + tol)) | (
        (np.abs(rr - a) <= tol) & (zz >= -tol) & (zz <= exposed + tol)
    )
    return 1.0 / (2.0 * math.pi * _solve(r, z, electrode, removed))


def converged(exposed: float) -> tuple[float, float]:
    """Box- then Richardson-extrapolated ``R sigma a``, and the observed order."""
    levels = []
    for n_edge, growth in REFINEMENTS:
        small, large = (
            tip_resistance_sigma_a(exposed, n_edge=n_edge, growth=growth, box=b) for b in BOXES
        )
        l1, l2 = BOXES
        levels.append((l2 * large - l1 * small) / (l2 - l1))
    coarse, mid, fine = levels
    ratio = (coarse - mid) / (mid - fine)
    order = math.log(ratio, 2.0) if ratio > 0 else math.nan
    if math.isfinite(order) and order > 0:
        return fine + (fine - mid) / (2.0**order - 1.0), order
    return fine, order


def sphere_sigma_a(exposed: float) -> float:
    """The package's equal-area sphere for a flat tip plus ``exposed`` radii of shaft."""
    area = math.pi + 2.0 * math.pi * exposed
    return 1.0 / (4.0 * math.pi * math.sqrt(area / (4.0 * math.pi)))


def main() -> int:
    print(f"{'l/a':>6} {'FV R.sigma.a':>13} {'order':>6} {'sphere':>8} {'sphere/FV':>10}")
    for exposed in EXPOSED_LENGTHS:
        value, order = converged(exposed)
        sphere = sphere_sigma_a(exposed)
        print(f"{exposed:6.2f} {value:13.4f} {order:6.2f} {sphere:8.4f} {sphere / value - 1:+10.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
