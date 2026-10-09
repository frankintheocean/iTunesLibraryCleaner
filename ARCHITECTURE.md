# 🏗️ App architecture

## 🧭 🖥️ Desktop and interface

React + TypeScript render the workspace. Vite builds the interface; Electron hosts it in a sandboxed window. The preload bridge exposes only approved local requests, dialogs, and window actions.

## 🧭 🔌 Local API

Electron starts the Python/FastAPI service on loopback with a random session token. Requests are authenticated and validated. The renderer does not get direct Node.js access, and no public network server or telemetry is configured.

## 🧭 💾 Saved data

SQLite stores profiles, searchable tracks, previews, queued jobs, metadata Field journal records, transfer records, and operation history. XML snapshots preserve unknown fields and original data types. Search and overview caches are updated when the indexed library changes.

## 🧭 ✍️ Live and file edits

Live iTunes COM runs in a separate Windows process; COM objects stay in that process. Each live field write is journaled and read back. File-tag edits keep verified backups. Some multi-field operations can partially succeed, so uncertain outcomes are recorded and are not automatically retried.

## 🧭 🎵 Playlists and safety

Playlist reorder calls use a playlist-only move method only when the running COM interface exposes one and the result can be verified. The app never calls `IITTrack.Delete` to simulate a reorder. Playlist pictures are saved locally first; live application is attempted only through an available playlist-art setter.

Current Library delete makes and verifies a safety copy before removing a song from iTunes and disk. Duplicate creates a verified media copy before asking iTunes to import it. Clearing history deletes both operation history and metadata Field journal rows; separate file backups and transfer manifests remain in app data.

## 🧭 📁 Files and exports

Media copies are checked with SHA-256 and are never allowed to overwrite an existing destination. XML merge and relink workflows produce separate exports; they do not edit iTunes' private database files. Advanced original tools remain under `legacy/` and keep their own confirmations and backups.

## 🧭 🎧 Last.fm

The Last.fm integration reads profile and chart data over HTTPS. API keys stay in app data and are not returned to the renderer. Image downloads are bounded and redirects are checked against an allowlist. The integration does not scrobble or change the account.
