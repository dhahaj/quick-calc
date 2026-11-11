"""Build the portable app:  python build.py

Produces dist/QuickCalc/ (PyInstaller --onedir). Copy that folder anywhere in your
user profile and run QuickCalc.exe; no installer, no admin rights, no network.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"

# Qt modules the app never touches; leaving them out keeps the folder small.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "numpy", "pytest", "ssl", "_ssl", "PySide6.QtNetwork",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtConcurrent",
    "PySide6.QtPrintSupport", "PySide6.QtHelp", "PySide6.QtDesigner", "PySide6.QtUiTools",
]  # fmt: skip


def make_icon(path: Path) -> bool:
    """Render the in-code app icon to an .ico file for the exe. Optional."""
    sys.path.insert(0, str(ROOT))
    try:
        from PySide6.QtWidgets import QApplication

        from quickcalc.gui.theme import app_icon

        app = QApplication.instance() or QApplication(["build", "-platform", "offscreen"])
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = app_icon().pixmap(256, 256).save(str(path), "ICO")
        del app
        return ok and path.exists()
    except Exception as exc:
        print(f"icon skipped: {exc}")
        return False


def main() -> int:
    icon = BUILD / "quickcalc.ico"
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "QuickCalc",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        "--collect-data", "pint",  # Pint's unit definition text files
    ]  # fmt: skip
    if make_icon(icon):
        command += ["--icon", str(icon)]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    command.append(str(ROOT / "quickcalc" / "__main__.py"))

    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        return result.returncode

    app_dir = DIST / "QuickCalc"
    # Not used by a widgets app: translations, software OpenGL, and every Qt network plugin.
    for extra in ("translations", "opengl32sw.dll", "tls", "networkinformation", "Qt6Network.dll"):
        for found in app_dir.rglob(extra):
            shutil.rmtree(found) if found.is_dir() else found.unlink()
    size = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file()) / 1e6
    print(f"\nBuilt {app_dir / 'QuickCalc.exe'}  ({size:.0f} MB folder)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
