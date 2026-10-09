# ⚖️ Licenses and artwork

New code uses the repository's GNU GPL v3 license (LICENSE). The uploaded original projects did not include separate LICENSE files; their source and origin is preserved in `legacy/` and `docs/source-inventory.json`. Confirm that you have permission to distribute the uploaded source before publishing binaries.

Dependencies retain their own licenses: React (MIT), TypeScript (Apache-2.0), Vite (MIT), Tailwind CSS (MIT), Lucide (ISC), Zustand (MIT), TanStack Virtual (MIT), Electron (MIT plus Chromium/Node third-party notices), electron-builder (MIT), FastAPI (MIT), Pydantic (MIT), Uvicorn (BSD-3-Clause), SQLite (public domain), Mutagen (GPL-2.0-or-later), Requests (Apache-2.0), pywin32 (PSF), PyQt6/Qt (GPL/commercial and Qt applicable licenses), PyInstaller (GPL with bootloader exception), Pillow (HPND) and pytest (MIT).

Original themes/icons remain only with the preserved tools. The geometric music-library icon was generated specifically for this project and is distinct from the supplied icons, including the ScoutTool style reference; source PNG and derived sizes are included. SF Pro is used only when already installed. Apple fonts, Apple logos and proprietary Apple artwork are not bundled.

`package-lock.json` and Python locks identify the exact dependencies. `scripts/collect-licenses.py` collects installed notices and a manifest; the Windows build invokes it automatically. Releases must include dependency license files, Electron LICENSE/LICENSES.chromium.html and Qt/pywin32/Python notices alongside binaries. This summary does not replace the notices required with binaries. No private Apple Music database library, copy-protection bypass tool or telemetry SDK is included.

🔐 Published-source change: the bundled Last.fm credential was removed from `legacy/cleaner/online_lookup.py`. Last.fm lookup requires a user-provided API key. The source inventory records both the original and sanitized checksums.

📘 Original-tool guides use simpler wording. Their original checksums and the published guide checksums are recorded in the source inventory; the complete historical text remains at the `v1.0` source tag. Original application code and license notices were not rewritten for these guide changes.
