# Migration

Both original projects are preserved byte-for-byte under `legacy/` (see checksums in the source inventory). Unified settings, journals and profiles start independently in writable per-user app data. No old installation is scanned or modified automatically.

Settings offers explicit imports of Cleaner settings JSON and Consolidator SQLite settings. Unknown values are retained under `legacy_settings`; credential-bearing keys are excluded from Cleaner import. Source files are opened read-only. Imported old preferences are preserved, not assumed to map one-to-one to every new control. Custom genre rules can be imported using `pattern,target` CSV or entered/reordered in the editor.

For exact existing workflows/history, close the old program, open the named original tool once from Unified Settings, close it, and copy your old settings, custom rule JSON, processed cache/CSV, undo log and history into its writable user-data mirror. Consolidator keeps its original SQLite schema/settings/snapshot support. Back up before copying and never overwrite current state blindly. Reopen the tool and confirm its output folder and presets. Cleaner may retain an old output path; review it explicitly.

This release does not automatically convert all historical legacy cache, undo, snapshot and notification data into the unified SQLite schema. Those original records remain usable by the retained tools. Secrets stay local in the old program or its user-data mirror and are not included in source deliverables.

A live scan reads real iTunes persistent IDs. A folder scan uses synthetic local IDs that cannot be sent to COM. XML exports with genuine IDs can be edited live when classic iTunes is running. Apple Music for Windows has no equivalent supported iTunes COM target.
