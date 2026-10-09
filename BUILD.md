# Build

## Windows release

Use Windows 10/11 x64, Python 3.12 x64 and Node 22.12 or later. From the project root run `powershell -File scripts/build-windows.ps1`. The script installs pinned Python and npm dependencies, runs tests, builds React, bundles the backend and both legacy interfaces with PyInstaller, then packages Electron using an assisted NSIS installer. Output is `dist/windows/`. No end-user Python/Node dependency remains in a successfully bundled build.

`requirements-lock-windows.txt` pins the complete Python dependency set. Its wheel availability was checked for CPython 3.12 win_amd64 on Linux, including pywin32, Qt, PyInstaller, pefile and pywin32-ctypes. This does not establish successful Windows installation. `package-lock.json` pins npm package integrity. Packaging artifacts must still be built and tested on Windows; code signing is not configured because no signing identity was supplied.

The Linux lock is for the development host. It must not be substituted for the Windows lock. Build caches and output directories are intentionally excluded from source packaging.

## Linux development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock-linux.txt
npm ci
npm run build
npm run desktop
```

Use a graphical session for Electron. For Vite live reload run `npm run dev` in one terminal and `LIBRARY_MANAGER_DEV=1 npm run desktop` in another. The renderer deliberately requires Electron's preload bridge; an ordinary browser alone cannot access libraries. Backend only: set a random `LIBRARY_MANAGER_TOKEN` (at least 32 characters) in the process environment and run `.venv/bin/python -m backend --data-dir /absolute/writable/app-data`. It binds to loopback on an ephemeral port and prints a non-secret readiness record. Requests require the token.

When the package manager must use the cloud HTTPS proxy, configure `ELECTRON_GET_USE_PROXY=1` and `GLOBAL_AGENT_HTTP_PROXY` from the supplied HTTPS proxy. Keep TLS/checksum verification enabled. Cache directories can be placed under `/tmp` or the writable workspace; do not change HOME or disable certificate verification.

## Source deliverable

Run `python3 scripts/package-source.py`. It creates a ZIP under the sibling `deliverables/` directory, verifies ZIP integrity and exactly one root folder, and writes SHA-256. The ZIP contains source, originals, tests, lockfiles, docs, icons and built frontend assets. It excludes credentials, runtime state, node_modules, Python environments and build caches. No Windows executable is included unless separately built and validated.
