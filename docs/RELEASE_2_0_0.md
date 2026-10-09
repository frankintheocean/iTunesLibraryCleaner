# 🎵 iTunes Manager 2.0.0

Manage your music with a clearer interface, album covers and more display choices.

## 🐛 Fixes

- Scroll the heading and tab content together.
- Use the available window height for song lists.
- Center the app name in the title bar.

## ✨ New features

- Clear waiting and finished queue tasks. Active work, history and undo records stay safe.
- See live elapsed time and estimated time left for each task.
- Show album covers in song lists, duplicates and playlist details when available.
- Choose the current live iTunes library from the top-right menu.
- Open the GitHub project using the button beside that menu.
- Show genre percentages for the whole loaded library.

## 🎨 More choice

OLED Black, Ocean, Rose and Forest themes use true-black page backgrounds. Choose a font and text size from 25% to 400%. Accessibility options include less animation, stronger keyboard focus, larger controls and underlined links.

## 🛡️ Before using it

Simple emoji tooltips explain changes before you confirm them. Preview and undo protections remain. The app is renamed **iTunes Manager**, with the same application ID and data folder to keep existing libraries, settings, history and backups.

Requires Windows 10/11 x64. Live editing needs classic iTunes; Apple Music for Windows does not offer this connection. The installer is unsigned. New installed-app live iTunes and live-artwork checks still need a disposable Windows library. The earlier source-level metadata test passed on iTunes 12.13.11.1; it is not a fresh real-COM test of this version.

## ✅ Validation

Local checks passed: 196 Python tests, 3 IPC tests, the interface build and real Electron tests using generated media with embedded artwork. Windows Server 2022 passed 195 Python tests (one Linux-only test skipped), the build, installed-app workflow, repair and uninstall/reinstall with saved app data unchanged.

[Windows build and test run](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37878468914). Built from `e588f819c51ac01e932ffe0cfe6da8730f89b638`. The `.sha256` download checks the installer, and `installer-validation.json` records its acceptance results.

[Install](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/INSTALL.md) · [Known limits](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LIMITATIONS.md)
