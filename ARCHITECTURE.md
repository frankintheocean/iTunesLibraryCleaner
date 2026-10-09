# 🏗️ How the app works

## 🖥️ Desktop and interface

React and TypeScript build the interface. Vite builds its files. Track tables load pages as you browse. Tailwind provides style tools, Lucide provides icons, and Zustand stores interface state.

Electron runs the desktop window. Its browser sandbox and context isolation stay enabled, and the interface cannot use Node directly. A small preload bridge allows approved requests, file dialogs, original-tool launches and window controls.

The desktop host starts and stops the Python backend. It creates a random session token and keeps it out of the interface. FastAPI listens only on `127.0.0.1`, checks the token and validates request data with Pydantic. New browser windows and permission requests are blocked.

## 💾 Saved state

SQLite stores libraries, searchable tracks, change previews, jobs, change records, file-transfer records and history. It uses WAL mode and records schema version 1. XML imports keep unknown fields and their original data types. Original matching, playlist merging, genre rules and album detection are reused through `backend/legacy.py`.

## ✍️ Editing

One worker applies changes in order. Scans and transfers save progress between tracks or files. Live iTunes COM runs in its own process with a time limit; COM objects stay in that process and thread.

Before changing each field, the app saves a pending record. It then reads the value back from iTunes. A failed edit can leave some fields changed. Uncertain results are recorded and are not retried automatically.

## 📁 Files and exports

Copies are staged in the destination folder and checked with SHA-256. A hard link publishes the verified copy without replacing an existing file. Unsupported filesystems fail safely. Sources are removed only after a verified copy. Interrupted transfers with an existing destination need review. Tag edits keep unrelated tags and save a verified full-file backup.

Live iTunes edits and file-tag edits are separate choices. XML merging and relinking create a new export; they do not edit ITL databases or automatically update live iTunes. Advanced original tools remain available in Settings. Online lookups are optional. No telemetry or public network server is configured.

## ⚡ Saved libraries and search

The service keeps up to eight parsed libraries ready in memory. Code that changes a library receives a separate copy, so previews cannot change the saved data. Searches use SQLite’s text index. Overview results are cached until an index changes; typing does not reload overview or playlist data. Metadata writes update only affected search rows.

Each save writes and checks a fresh snapshot, then changes its SQLite reference. It does not replace a snapshot a Windows reader may still have open. XML scans copy the source to a private staging file and parse that exact copy once. The source must remain unchanged during copying. One previous snapshot is kept.

Live scans read the actual iTunes COM collection and verify the library ID and track count. Runtime database IDs speed up playlist links. Live writes still require the exact persistent ID and matching preview values, with a durable field record and readback. Name and runtime-ID hints only help find a candidate; its persistent ID must match.

## 🎧 Listening data

`backend/lastfm.py` reads profile and chart data over HTTPS. Its API key is kept outside general preferences, never returned to the renderer, and removed on disconnect. Only approved Last.fm image hosts can be fetched; each CDN redirect is checked and downloads are bounded. Missing pictures can be resolved through Last.fm metadata or public page image tags, without running page scripts. The renderer receives small data-URL pictures, so the existing content policy stays unchanged. Last.fm has no account-write or scrobbling methods.

Live COM scans use a progress-aware stall deadline and a six-hour hard limit. Metadata writes retain a fixed deadline and field records. Slow scans check cancellation while waiting, including before the first progress message.
