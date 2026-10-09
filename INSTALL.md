# Install, repair and uninstall

Download the current Windows installer from the GitHub Releases link in README.md. Source ZIPs contain build tooling rather than installer binaries. Build instructions are in BUILD.md and acceptance coverage is recorded in docs/VALIDATION.md.

The configured assisted NSIS installer supports choosing the installation directory, Start Menu and Desktop shortcuts and a Windows Apps & Features uninstall entry. Icons are assigned to Electron, installer, uninstaller and shortcuts.

For repair, close the app and both legacy tools, then run the same full installer for the installed version. This reinstallation restores packaged files and shortcuts while keeping user data. `scripts/repair-windows.ps1 -InstallerPath <path>` is a maintenance launcher for that installer. This is reinstall-based repair, not an independently validated MSI repair feature or a dedicated Apps & Features Repair entry.

Uninstall removes packaged application files/registration/shortcuts and preserves user data. The installer does not delete music, exports, backups or quarantine. To remove application preferences/cache afterward, explicitly review the user-data directory first: it can also contain important metadata backups and quarantine manifests. No bulk delete option is provided without such review.

App data defaults to Electron's per-user `Unified iTunes Library Manager` directory below Windows AppData. `LIBRARY_MANAGER_DATA_DIR` can select a separate directory for development/testing. Music remains at user-selected paths. Original tools run in `legacy/cleaner` and `legacy/consolidator` under user data, with their own exact UI and state.
