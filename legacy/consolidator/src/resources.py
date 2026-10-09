"""
Locates bundled non-Python resources (currently just the app icon) so the
same path logic works both when running from source and when frozen by
PyInstaller into a single .exe.

PyInstaller unpacks `datas` entries into a temp dir exposed as
`sys._MEIPASS` at runtime; when running from source there is no such
attribute and files live relative to the project root instead.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    # src/resources.py -> src/ -> project root
    return Path(__file__).resolve().parent.parent


def app_icon_path() -> Path | None:
    """Path to the app icon (.ico), or None if it isn't present. Checked
    both in the PyInstaller-frozen bundle location and the source tree so
    this works identically in `python -m src.main` and the built .exe."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "app_icon.ico")
    candidates.append(_project_root() / "assets" / "app_icon.ico")
    for c in candidates:
        if c.is_file():
            return c
    return None
