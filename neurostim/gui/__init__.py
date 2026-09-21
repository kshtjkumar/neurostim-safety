"""PyQt6 desktop application.

Importing this package pulls in PyQt6 and switches matplotlib to the Qt backend, so it
is kept out of the top-level :mod:`neurostim` namespace. Launch with::

    python -m neurostim.gui

or ``neurostim-gui`` once the package is installed.
"""

from .app import SafetyWindow, main

__all__ = ["SafetyWindow", "main"]
