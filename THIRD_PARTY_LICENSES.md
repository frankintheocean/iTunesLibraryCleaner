# Third-party software and assets

New project code uses the repository's GNU GPL v3 license (LICENSE). The uploaded original projects did not include separate LICENSE files; their source/provenance is preserved in `legacy/` and `docs/source-inventory.json`. Confirm permission/licensing for distributing those uploaded sources before a public binary release.

Dependencies retain their own licenses: React (MIT), TypeScript (Apache-2.0), Vite (MIT), Tailwind CSS (MIT), Lucide (ISC), Zustand (MIT), TanStack Virtual (MIT), Electron (MIT plus Chromium/Node third-party notices), electron-builder (MIT), FastAPI (MIT), Pydantic (MIT), Uvicorn (BSD-3-Clause), SQLite (public domain), Mutagen (GPL-2.0-or-later), Requests (Apache-2.0), pywin32 (PSF), PyQt6/Qt (GPL/commercial and Qt applicable licenses), PyInstaller (GPL with bootloader exception), Pillow (HPND) and pytest (MIT).

Original themes/icons remain only with the preserved tools. The unified stacked-record icon was generated specifically for this project and is distinct from both supplied icons; source PNG and derived sizes are included. SF Pro is referenced only as an installed font preference. Apple fonts, Apple logos and proprietary Apple artwork are not bundled.

`package-lock.json` and Python locks identify the exact dependencies. `scripts/collect-licenses.py` collects installed notices and a manifest; the Windows build invokes it automatically. The release process must distribute the installed dependency license files, Electron LICENSE/LICENSES.chromium.html and Qt/pywin32/Python notices alongside binaries. The included source license summary does not replace all binary-distribution notices. No proprietary Apple Music database library, DRM tool or telemetry SDK is bundled.

Publication change: the bundled Last.fm credential was removed from `legacy/cleaner/online_lookup.py`. Last.fm lookup requires a user-provided API key. The source inventory records both the original and sanitized checksums.
