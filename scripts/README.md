# 🧰 Build and maintenance scripts

Run scripts from the repository root so relative paths resolve correctly.

- 🪟 `build-windows.ps1` installs locked dependencies, runs checks, bundles the backend, and builds the installer.
- 📦 `package-windows.py` and `package-source.py` create portable/source ZIPs and checksums.
- 🧪 `test-windows-installer.ps1` validates the installed app and desktop workflows.
- 🔐 `verify-originals.py` checks preserved legacy files.
- 🧾 `collect-licenses.py` refreshes dependency license notices.
- ⚙️ Other scripts support fixtures, benchmarking, audits, and release checks.

Keep generated version strings and asset names aligned with `package.json`.
