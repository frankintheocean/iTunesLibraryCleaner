# 🧭 Move from the original tools

The Cleaner and Consolidator remain under `legacy/`. New libraries, settings, and edit records use the current app-data folder. Old installations are not modified automatically.

## 📥 Import settings

In **Settings**, import a Cleaner settings JSON or Consolidator SQLite settings file. Imports read the source without changing it. Unknown settings are preserved; Cleaner credentials are excluded. Some old preferences have no new control.

Custom genre rules can be imported as `pattern,target` CSV, then reviewed in Settings.

## 🏛️ Keep the original history

1. Close the old program and make a backup.
2. Open the matching original tool from Settings, then close it.
3. Copy its old settings, rules, caches, undo logs, and history into that tool's writable app-data folder.
4. Reopen it and check its output paths and presets.

Not every old history item converts to the new database. Use the original tool to review its older records; do not overwrite newer data without checking it.

## 🎵 Live iTunes

Live profiles use the persistent IDs from the classic iTunes library that is currently open. Folder scans do not provide the IDs needed for live COM edits. Switching the library in iTunes requires a rescan or a separate profile.

## 🗂️ Version 1.0.0

**Libraries** and **History** now open from Settings. **Clear history** deletes both operation history and Field journal entries, so those cleared metadata edits can no longer be undone through the app. Saved safety copies and transfer manifests remain separate.
