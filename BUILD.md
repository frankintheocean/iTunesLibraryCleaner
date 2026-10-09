# 🛠️ Build and run

## 🪟 Windows installer

Use Windows 10/11 x64, Python 3.12 x64, and Node 22.12 or later. From the repository root, run:

```powershell
powershell -File scripts/build-windows.ps1
```

The script installs locked dependencies, runs backend and desktop tests, builds the frontend and Python backend, and creates an NSIS installer under `dist/windows/`. The portable app ZIP, source ZIP, and SHA-256 sidecars are made by the Windows workflow after the installer checks pass.

## 🐧 Linux development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock-linux.txt
npm ci
npm run build
npm run desktop
```

Electron needs a graphical session. To use Vite reloads, run `npm run dev` and `LIBRARY_MANAGER_DEV=1 npm run desktop` in separate terminals.

## 🔐 Notes

Use `requirements-lock-windows.txt` on Windows and `requirements-lock-linux.txt` on Linux; do not swap them. `package-lock.json` pins JavaScript dependencies. Build and validate Windows installers on Windows. Code signing is not configured.

See [Windows checks](docs/WINDOWS_VALIDATION.md), [test instructions](TESTING.md), and [validation evidence](docs/VALIDATION.md).
