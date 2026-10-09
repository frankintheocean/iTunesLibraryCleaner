# 🧭 Move from the original tools

The original tools remain under `legacy/`. Their code is unchanged except for the documented removal of a shared Last.fm key. Their guides now use simpler wording; the source inventory records these edits. New libraries, settings and change records start separately in your writable app-data folder. Old installations are not changed automatically.

## 📥 Import settings

In Settings, choose a Cleaner settings JSON file or a Consolidator SQLite settings file. Imports read the source without changing it. Unknown settings are saved under `legacy_settings`; Cleaner credentials are excluded. An imported preference may not have an equivalent new control.

Import custom genre rules as `pattern,target` CSV, or add and reorder them in the rule editor.

## 🏛️ Keep old history

To keep the original workflow and records:

1. Close the old program and make a backup.
2. Open the matching original tool from the new app's Settings, then close it.
3. Copy old settings, rule JSON, processed caches, undo logs and history into that tool's writable app-data folder. Do not overwrite newer data without reviewing it.
4. Reopen the tool and check its output folder and presets. Cleaner may still use an old output path.

Consolidator keeps its original database and snapshot support. Old caches, undo records, snapshots and notifications are not all converted into the new database. They remain usable in the original tools. Credentials stay local and are excluded from source downloads.

## 🎵 Live iTunes

Live scans read real iTunes persistent IDs. Folder scans create local IDs that cannot be used for live editing. XML tracks with genuine IDs can be edited live while classic iTunes runs. Apple Music for Windows does not offer this COM connection.
