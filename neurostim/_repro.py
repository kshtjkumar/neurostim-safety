"""Reproducible-output helpers.

Generated artifacts are committed and diffed, so two runs of unchanged code on unchanged
inputs must produce identical bytes. Otherwise a real numeric change cannot be told apart
from clock noise, and the committed output stops being evidence of anything. At the audit
baseline five of the eight artifacts ``examples/worked_example.py`` writes differed between
two back-to-back runs, at identical file lengths.

This module implements the reproducible-builds contract: when ``SOURCE_DATE_EPOCH`` is set
in the environment, every timestamp the package writes is that instant rather than the wall
clock. When it is not set the wall clock is used, so an ordinary report still carries the
time it was really generated.

Nothing here changes a computed value.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

SVG_HASH_SALT = "neurostim-safety"
"""Salt for matplotlib's generated SVG element ids.

``rcParams["svg.hashsalt"]`` defaults to ``None``, which makes matplotlib salt every
``<path id=...>`` and ``xlink:href`` from a fresh ``uuid4`` per process. Two runs then
produce files of identical length that differ on every element id. The ids are internal
to one file, so any fixed string does; this one is fixed so that diffs are empty.
"""

VECTOR_METADATA: dict[str, dict[str, None]] = {
    "svg": {"Creator": None},
    "pdf": {"Creator": None, "Producer": None},
}
"""Fields matplotlib would otherwise stamp with its own version number.

Both backends write "Matplotlib v3.10.8, https://matplotlib.org" into the file, and the
PDF backend also writes "Matplotlib pdf backend v3.10.8" as the producer. A matplotlib
upgrade would then change every committed artifact without any number moving. The date is
deliberately *not* suppressed -- ``SOURCE_DATE_EPOCH`` pins it, and an artifact that
carries no date at all is reproducible for the wrong reason.
"""


def source_date_epoch() -> int | None:
    """The pinned build timestamp in seconds, or ``None`` to use the wall clock."""
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"SOURCE_DATE_EPOCH must be an integer number of seconds since the epoch, "
            f"got {raw!r}"
        ) from None


def build_time() -> datetime:
    """The UTC instant to stamp on generated output."""
    epoch = source_date_epoch()
    if epoch is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def is_pinned() -> bool:
    """Whether output timestamps are pinned by the environment."""
    return source_date_epoch() is not None
