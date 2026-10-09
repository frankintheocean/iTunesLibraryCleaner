# 🔨 Build and run

## 🪟 Windows installer

Use Windows 10/11 x64, Python 3.12 x64 and Node 22.12 or later. From the repository folder, run:

```powershell
powershell -File scripts/build-windows.ps1
```

The script installs locked dependencies, runs tests, builds the interface, bundles Python and the original tools, and creates an NSIS installer in `dist/windows/`. Users of the installer do not need Python or Node.

Use `requirements-lock-windows.txt` on Windows and `requirements-lock-linux.txt` on Linux. Do not swap them. `package-lock.json` fixes JavaScript dependency versions and integrity checks. Windows installers must be built and tested on Windows. Signing is not configured.

GitHub Actions runs the Windows build and installer checks. See [Windows checks](docs/WINDOWS_VALIDATION.md) and [results](docs/VALIDATION.md).

## 🐧 Linux development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock-linux.txt
npm ci
npm run build
npm run desktop
```

Electron needs a graphical session. For live interface reloads, run `npm run dev` in one terminal and `LIBRARY_MANAGER_DEV=1 npm run desktop` in another. The interface needs Electron's preload bridge; a browser alone cannot access libraries.

To run only the backend, set `LIBRARY_MANAGER_TOKEN` to a random value of at least 32 characters, then run:

```sh
.venv/bin/python -m backend --data-dir /absolute/writable/app-data
```

It listens on a local, automatically chosen port and prints a readiness record without the token. Requests need that token.

If the cloud package manager needs its supplied HTTPS proxy, set `ELECTRON_GET_USE_PROXY=1` and `GLOBAL_AGENT_HTTP_PROXY` to that proxy. Keep TLS and checksum checks enabled. Put caches in `/tmp` or the writable workspace; do not change HOME or disable certificate checks.

## 🗜️ Source ZIP

Run `python3 scripts/package-source.py`. It creates a ZIP and SHA-256 file in the sibling `deliverables/` folder. It checks the archive, its single root folder and the original-file checksums.

The ZIP includes source, original tools, tests, locked dependencies, guides, icons and built interface files. It excludes credentials, user data, installed dependencies and build caches. The Windows app ZIP and installer are separate downloads.

## 🎁 Windows app ZIP

After building on Windows, run `.venv\Scripts\python scripts/package-windows.py`. It checks the complete app, adds a short start guide and writes the ZIP with a checksum in `dist/windows/`.

Run `.venv\Scripts\python scripts/package-source.py --output-dir dist/windows` for the source ZIP. Both archives record the source commit. The release workflow checks these records and checksums against the successful installer test run before publishing.
