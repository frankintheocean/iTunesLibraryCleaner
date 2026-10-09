# Windows installer (optional)

`setup.iss` is an [Inno Setup 6](https://jrsoftware.org/isinfo.php) script
that packages the already-built app into a normal Windows installer.
This step is optional — the app runs fine from the plain
`iTunesLibraryConsolidator.exe` (copied to the project root automatically
after a successful build) or from `dist\iTunesLibraryConsolidator\`
produced by `build_windows.bat` without it.

## What it installs

- The app itself, into `%LocalAppData%\Programs\iTunes Library
  Consolidator` by default (per-user install, no admin rights required —
  this app only ever writes to your own AppData cache and files you
  explicitly choose, so nothing it does needs a machine-wide install).
- A Start Menu shortcut (and an optional desktop shortcut, unchecked by
  default).
- A proper uninstaller, listed in Windows Settings → Apps → Installed apps
  (and the classic Control Panel → Programs and Features).
- **The Microsoft Visual C++ Redistributable (x64)**, silently and only if
  a compatible copy isn't already present on the machine. The bundled
  Python DLL depends on it (`VCRUNTIME140.dll` and the `api-ms-win-crt-*`
  API Set stubs); without it, the built .exe fails to start with "Failed
  to load Python DLL ... LoadLibrary: The specified module could not be
  found" even though every file PyInstaller bundled is present and
  intact. Most Windows machines already have a compatible runtime
  installed (it's shared by many other apps), so this step is usually a
  no-op that adds a second or two to install time.
- **Optionally** (unchecked by default): associates `.xml` files with the
  app under a distinct identifier (`iTunesLibraryConsolidator.xml`), so
  double-clicking a `Library.xml` opens it here. This is opt-in and
  per-user (`HKCU`, not `HKLM`) specifically because `.xml` is a generic
  extension other installed software may already own — installing this
  app never silently changes what happens when you open your *other*
  `.xml` files unless you explicitly check that box.

## How to build it

1. Install Inno Setup 6 (free) from https://jrsoftware.org/isinfo.php.
2. Build the app first: `dist_config\build_windows.bat` (see the main
   README) — this must produce the standalone folder
   `dist\iTunesLibraryConsolidator\iTunesLibraryConsolidator.exe`
   before the installer script can package it (build.spec builds a
   standalone folder, not a single-file .exe, so this installer packages
   the whole folder — DLLs and bundled resources included).
3. Download the Visual C++ Redistributable (x64) bootstrapper from
   https://aka.ms/vs/17/release/vc_redist.x64.exe and save it as
   `dist_config\vc_redist.x64.exe`. This isn't committed to the repo (a
   ~25MB Microsoft-signed binary that Microsoft updates independently of
   this project), so it's a one-time manual download per build machine.
   If it's missing, step 4 below fails immediately with a clear "source
   file not found" error rather than silently shipping a broken
   installer.
4. Run:
   ```
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
   ```
5. The installer is written to
   `dist_config\Output\iTunesLibraryConsolidator-Setup-<version>.exe`.

Both installation and uninstallation run entirely through Inno Setup's own
GUI wizard — no console/cmd window is shown at any point.
