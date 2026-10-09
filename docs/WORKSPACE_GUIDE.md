# 🧭 Workspace guide

The workspace connects Overview, Libraries, Cleaner, Consolidation, Duplicates, Metadata, Playlists, Organizer, Queue, History and Settings to backend operations. Tables support paged virtualization and SQLite search. Profiles retain source configuration, scans reuse unchanged metadata, and scheduled scans run while the app is open.

Jobs serialize mutations and pause or cancel between tracks. Interrupted checkpoints appear after restart; a partially completed metadata edit requires a fresh preview before retrying.

Settings launches preserved original Cleaner and Consolidator interfaces for advanced workflows, including cleanup presets, audio previews, named restore points and rebuild/undo. This does not imply every legacy screen has a React replacement.

Live COM edits use persistent IDs, isolated COM apartments, readback and per-field journals. File-tag edits save verified full-file backups. Duplicate consolidation produces a separate XML and repoints playlists without deleting media. File organization stages and verifies copies; moving files can require relinking live references.

The interface prefers installed SF Pro fonts with system fallbacks. Apple fonts are not distributed. The distinct flat record-and-note icon is inspired by the supplied ScoutTool visual style.
