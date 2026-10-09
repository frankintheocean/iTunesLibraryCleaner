"""
PyInstaller entry point.

src/main.py uses package-relative imports (`from .changelog import ...`,
`from .ui.main_window import MainWindow`), so it must be imported as part
of the `src` package -- it cannot be analyzed or executed as a bare script.
Running it directly (or pointing PyInstaller's Analysis straight at
src/main.py) fails with:

    ImportError: attempted relative import with no known parent package

This launcher lives one level up from src/ (the project root, once
PyInstaller's pathex=['..'] is applied) and does exactly what
`python -m src.main` does: import src.main as a package and call main().
"""

import sys

# Imported at module level (not inside `if __name__ == "__main__":`) so
# PyInstaller's static analyzer treats it as unconditionally reachable and
# actually bundles the `src` package -- a conditional/deferred import here
# gets dropped from the frozen build with "ModuleNotFoundError: No module
# named 'src'" even though the same code runs fine unfrozen.
from src.main import main

if __name__ == "__main__":
    sys.exit(main())
