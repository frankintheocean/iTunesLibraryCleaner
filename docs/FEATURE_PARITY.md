# Source analysis and parity plan

Both archives were inspected recursively before implementation; `source-inventory.json` records every file, checksum, import and Python symbol. The consolidator upload is a ZIP with a .7z extension. LibraryCleaner is a genuine 7z. Original source, resources, tests and packaging remain in `legacy/`.

| Source capability | Unified implementation / preservation route |
| --- | --- |
| Cleaner ordered Aho-Corasick genre rules, custom priority, CSV import, shadow tests | Reuse `legacy/cleaner/genre_rules.py` in Cleaner and Settings |
| Cleaner live genre editing, signed persistent IDs, reconnect fallback | Shared `backend/com_service.py`; metadata, genre cleanup and album merge use the same writer |
| Cleaner split-album conservative detection, optional catalog confirmation | Reuse `album_merge.py`; preview plans and apply through shared metadata service |
| Cleaner unknown genre and foreign language checks, source order | Reuse `online_lookup.py`, explicitly enabled scan options |
| Cleaner junk detection, playlist include/exclude, force scan, processed cache | Cleaner previews plus retained original engine; no automatic deletion in unified workflow |
| Cleaner pause/resume/stop, retry failures, undo, logs, presets, notifications | Unified persistent queue/history and metadata undo; original detailed workflow retained as a legacy tool |
| Cleaner ten themes, font, output directory, advanced delete batch, window geometry | Original settings are preserved by explicit import and legacy tool; unified themes and writable app-data directory |
| Consolidator exact/fuzzy/duration mismatch/symbol title/album completeness | Reuse original detector and merge planner, including confidence and smart playlist warnings |
| Consolidator rating/playcount/date merging and playlist repointing | Reuse `apply_plan`; export to a separate XML, original remains untouched |
| Consolidator manual canonical selection, manual merge, exclusions, scope, reports | Duplicate review endpoint and UI; advanced original workflow retained in legacy tool |
| Consolidator streaming XML, malformed XML checks, SQLite cache | Original parser; unified SQLite WAL profiles and track index |
| Consolidator health, artwork, missing-file relink, bulk search, audio preview | Original health/artwork/relink functions retained; unified inspection and relink; original audio preview in legacy tool |
| Consolidator Spotify import, provider abstraction | Original provider retained with unified comparison endpoint; Apple Music API was already a nonfunctional skeleton |
| Consolidator restore points, history trends, diff, rebuild/undo, live duplicate removal | Original routines and UI retained; unified audit/export workflows. Rebuild and irreversible COM deletion stay explicit legacy actions |
| Consolidator themes, appearance/accent, backup retention, scheduled checks, settings | Original SQLite settings preserved via read-only import; original UI still available |
| New safe file consolidation/organization/quarantine | Verified staging copies, collision/overlap rejection, manifests, restore and previews |
| New metadata including live COM app-wide edits | Strict allowlist, persistent identity, readback, per-field journal, conditional undo; separate file-tag target |
| New React desktop shell | Electron isolated renderer, restricted preload, authenticated loopback backend |

Retention is not a claim that every original dialog has been redesigned. The legacy tools provide exact original interfaces for workflows not yet exposed in the React shell. See the validation report for unimplemented new requirements and platform checks.

## Risks found in source

Cleaner defaults to live mode and irreversible COM junk deletion; unified operations require preview and explicit confirmation. Its installation-folder output/settings paths may be unwritable under Program Files; legacy copies are run from a writable user-data mirror. Multi-field COM writes are not transactional; the new writer journals each field before writing and records readback/partial failures. Consolidator's COM sync passes unsigned persistent-ID halves and probes an apartment-owned object from another thread; the new shared writer uses the Cleaner's signed halves and keeps all COM objects in one worker thread. Proprietary ITL/database bytes are never directly edited by the unified service. Original rebuild routines remain opt-in legacy behavior. Fuzzy matching has a deliberate time/chunk budget that can reduce recall. No audio transcoding or DRM bypass is introduced.

## Migration

Explicitly select the old Cleaner settings JSON/custom rules or Consolidator SQLite cache to import. Preserve unknown settings under `legacy_settings`; never delete old files. Databases, undo logs, history, presets and original backup files remain usable through writable legacy mirrors. Credentials are never included in exports or diagnostic reports. Automatic conversion of all historical legacy records is not claimed.

## Architecture

React handles navigation, virtualized track review and confirmations. FastAPI validates typed requests and requires a session token. SQLite owns profiles, tracks, operation previews, jobs, field journals and history. A bounded single operation worker serializes filesystem changes and COM sessions, with checkpoints at file/track boundaries. Legacy pure algorithms are adapted rather than rewritten. Electron owns backend lifecycle and native file dialogs. Windows builds bundle Python with PyInstaller and ship via electron-builder NSIS.
