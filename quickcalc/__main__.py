"""Entry point: ``python -m quickcalc``, ``pythonw quickcalc/__main__.py``, or the built exe.

Options:
    --tray    start hidden in the system tray (used by "Start with Windows")
    --quit    ask the running copy to exit
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    # Run as a plain script (autostart entry, PyInstaller): make the package importable.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quickcalc.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
