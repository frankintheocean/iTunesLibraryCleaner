# 🧰 Build and maintenance scripts

Run scripts from the repository root. Use the locked dependency files and review generated outputs before publishing them.

- 🪟 `build-windows.ps1` installs locked dependencies, runs checks, bundles the backend, and builds the installer.
- 📦 `package-windows.py` and `package-source.py` create the portable and source ZIPs.
- 🧪 `test-windows-installer.ps1` checks the installed app and desktop workflows.
- 🔐 `verify-originals.py` checks preserved legacy files.
- 🧾 `collect-licenses.py` refreshes bundled dependency license notices.
- 🖼️ `generate-icon.py` creates the app icon assets.
- ⚙️ `benchmark-library.py`, `smoke-bundle.py`, and the live-COM validators support performance, packaging, and Windows checks.

Keep generated version strings and asset names aligned with `package.json`. Build and validate Windows installers on Windows; do not treat a source-only test as live COM validation.