# 📥 Install, repair and remove

## 🚀 Install

Download the Windows installer from [GitHub Releases](https://github.com/frankintheocean/iTunesLibraryCleaner/releases). The **Windows app ZIP** runs without installation: extract every file together, then open `iTunes Manager.exe`. Python and Node are not needed. Settings and backups still use AppData, so this is not a self-contained data folder. The **source ZIP** is for building and does not contain an installer. See [build steps](BUILD.md) and [test results](docs/VALIDATION.md).

The installer lets you choose a folder and create Start Menu and Desktop shortcuts. It adds an uninstall entry to Windows Apps & Features. The app, installer, uninstaller and shortcuts use the app icon.

## 🔧 Repair

Close the app and both original tools. Run the full installer for the same version again. This restores app files and shortcuts while keeping user data.

You can also run `scripts/repair-windows.ps1 -InstallerPath <path>`. This launches the installer; there is no separate Repair button or MSI repair feature.

## 🗑️ Uninstall

Uninstall removes app files, shortcuts and its Windows registration. It keeps user data, music, exports, backups and quarantined files.

To remove settings or caches afterward, review the user-data folder first. It may also hold backups and records needed to restore files. There is no bulk-delete option.

## 💾 Data locations

By default, app data is in the existing per-user `Unified iTunes Library Manager` folder under Windows AppData. Set `LIBRARY_MANAGER_DATA_DIR` only when you need a separate development or test folder. Music stays in the folders you choose.

The original tools run from writable `legacy/cleaner` and `legacy/consolidator` folders under app data, with their own interfaces and state.

## 🔄 Upgrade to 4.0.0

The app is now called **iTunes Manager**. Its application ID and data folder stay the same, so your libraries, settings, history and backups remain available. Close the old app before installing the new version.

## 🗂️ Saved libraries

Version 3 writes a new checked snapshot before changing its saved reference. This avoids replacing an XML file Windows has open. One previous snapshot is kept for recovery; locked older copies are left alone. If the app folder itself is not writable, saving still fails with a clear error. Do not delete saved copies or change permissions blindly.

## 🎧 Optional Last.fm

Connect your own API key and username in the Last.fm tab. Internet access is needed. No shared secret is required. See the [connection guide](docs/LASTFM.md).
