# Architecture

React + TypeScript + Vite provide navigation, virtualized track tables, themes, review dialogs and forms. Tailwind is available alongside custom design tokens; Lucide and Zustand handle icons and lightweight navigation state.

Electron isolates the renderer (`sandbox`, `contextIsolation`, no Node integration). Preload exposes only allowlisted API routes, native file dialogs, named legacy tools and window controls. Main owns a random session token that is never exposed to React, launches the bundled backend, validates readiness, denies new windows/permissions and supervises child shutdown. FastAPI binds only 127.0.0.1, requires authenticated requests and validates inputs with Pydantic.

SQLite WAL stores profiles, searchable track rows, previews, jobs, field journals, transfer manifests and history; schema version 1 is recorded in migrations. XML snapshots preserve plist types and unknown fields. Original streaming parsing, exact/fuzzy matching, playlist-aware merge rules, genre automaton and album splitting are adapted through `backend/legacy.py`.

One worker serializes mutations. Scans, file transfers and verification checkpoint between items; COM lives in a spawned subprocess/apartment with timeouts. No COM object crosses a thread or process boundary. The writer commits a pending journal before each property, verifies readback and labels uncertain failures. COM edits are not transactional. The service does not auto-retry an ambiguous outcome.

Copies stage in the destination directory, verify SHA-256 and atomically publish using a hard link with exclusive destination semantics. Unsupported filesystems fail without deleting the source. Manifests are committed before transfer; files are removed only after verified copy. Interrupted copies with a published destination require inspection instead of being silently overwritten. Metadata preserves unrelated tags and saves a verified full-file backup.

Live iTunes and file-tag writes are separate targets. XML merge/relink/playlist imports create a new export rather than modifying ITL or representing XML export as a live sync. Advanced original routines remain in explicit legacy interfaces. No telemetry or external backend listening is configured; online genre/catalog lookup is opt-in.
