; Re-running the full installer repairs packaged files and shortcuts.
; User data is deliberately preserved. Electron-builder's assisted installer
; detects an existing installation and supports reinstalling the binaries.
!macro customHeader
  !define MUI_WELCOMEPAGE_TEXT "Install or repair Unified iTunes Library Manager. Reinstalling restores application files and shortcuts while preserving your library profiles, history, backups and music. Close the application before continuing."
!macroend
!macro customUnInstall
  ; No deletion of userData, library paths, backups, exports or quarantine.
!macroend
