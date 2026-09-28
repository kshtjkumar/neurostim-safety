#!/usr/bin/env python3
"""Coverage of the Lapicque chronaxie interval, measured by simulation (ledger 183).

For each design and noise level, draws seeded replicates from a known Lapicque curve
(rheobase 20 uA, chronaxies 50 / 100 / 200 / 500 us), fits them with :func:`neurostim.models.strength_duration.fit_lapicque`,
and reports:

- how many fits were accepted;
- how many of those had their interval withheld (rule A: an interval lying below every
  width tested);
- how many carry the narrow-design caveat (width span below ``NARROW_SPAN``);
- how many intervals are vacuous (upper end infinite, or more than ``VACUOUS_RATIO`` times
  the lower): counted here and left out of the coverage (ledger 193);
- the coverage of the intervals still reported: the fraction that contain the true
  chronaxie.

The committed output is ``docs/audit/lapicque_coverage.txt``, and the
``StrengthDurationFit`` docstring and the narrow-design caveat quote it. Re-run it after
any change to the fit::

    python scripts/lapicque_coverage.py > docs/audit/lapicque_coverage.txt
    python scripts/lapicque_coverage.py 192 > docs/audit/lapicque_coverage_seed192.txt

The second seed checks that the quoted ranges reproduce (ledger 192).
"""

from __future__ import annotations

import itertools
import math
import sys
import warnings

import numpy as np

DESIGNS = {
    "50-800": [50.0, 100.0, 200.0, 400.0, 800.0],
    "20-3200": [20.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0],
    "50-200": [50.0, 100.0, 150.0, 200.0],
    "400-3200": [400.0, 800.0, 1600.0, 3200.0],
    "2000-8000": [2000.0, 4000.0, 6000.0, 8000.0],
}
NOISE = (0.02, 0.05, 0.10, 0.20)
CHRONAXIES_US = (50.0, 100.0, 200.0, 500.0)
REPLICATES = 600
SEED = 191


def main(argv: list[str] | None = None) -> int:
    from neurostim.models import strength_duration as sd

    args = sys.argv[1:] if argv is None else argv
    seed = int(args[0]) if args else SEED
    rng = np.random.default_rng(seed)
    print(f"fit_lapicque coverage: {REPLICATES} replicates per cell, seed {seed}, "
          f"rheobase 20 uA; vacuous = upper end inf or > {sd.VACUOUS_RATIO:g}x the lower, "
          f"excluded from coverage")
    print(f"{'chronaxie':>9} {'widths (us)':<11} {'noise':>5} {'accepted':>8} "
          f"{'withheld':>8} {'caveat':>6} {'vacuous':>7} {'reported':>8} {'coverage':>8}")
    for chronaxie, (name, widths_list) in itertools.product(CHRONAXIES_US, DESIGNS.items()):
        tau = chronaxie / math.log(2.0)
        widths = np.array(widths_list)
        for noise in NOISE:
            accepted = withheld = caveat = reported = covered = vacuous = 0
            for _ in range(REPLICATES):
                thresholds = 20.0 / (-np.expm1(-widths / tau)) * (
                    1.0 + noise * rng.standard_normal(widths.size)
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        fit = sd.fit_lapicque(widths, thresholds)
                    except (ValueError, RuntimeError):
                        continue
                accepted += 1
                if fit.chronaxie_ci95_us is None:
                    withheld += 1
                    continue
                low, high = fit.chronaxie_ci95_us
                if not math.isfinite(high) or low <= 0 or high > sd.VACUOUS_RATIO * low:
                    vacuous += 1
                    continue
                reported += 1
                caveat += bool(fit.coverage_caveat)
                covered += low <= chronaxie <= high
            coverage = f"{covered / reported:.3f}" if reported else "-"
            print(f"{chronaxie:>9g} {name:<11} {noise:>5.0%} {accepted:>8} {withheld:>8} "
                  f"{caveat:>6} {vacuous:>7} {reported:>8} {coverage:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
