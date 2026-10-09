# 🛠️ Build and run

## 🪟 Windows installer

Use Windows 10/11 x64, Python 3.12 x64, and Node 22.12 or later. Run the command from a PowerShell session at the repository root:

```powershell
powershell -File scripts/build-windows.ps1
```

The script installs the locked dependencies, runs backend and desktop tests, builds the frontend and Python backend, and creates an NSIS installer under `dist/windows/`. The Windows workflow then validates the installed app before creating the portable ZIP, source ZIP, and SHA-256 sidecars. A local build alone does not publish a release.

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
