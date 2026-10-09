# 🔌 Python backend

The backend is the local service layer: it reads library sources, indexes tracks, prepares edit previews, queues jobs, and delegates live classic-iTunes operations to a separate Windows COM process.

- 🌐 `api.py` defines authenticated loopback HTTP routes.
- 📚 `service.py` scans XML, folders, and live libraries and builds overview statistics.
- 🗄️ `store.py` owns SQLite records and database migrations.
- 🎵 `com_service.py` coordinates guarded live iTunes operations without moving COM objects out of their owning process.
- 🎨 `artwork.py` and `lastfm.py` handle artwork lookup and optional listening-chart data.
- 🧰 `jobs.py`, `metadata.py`, and `filesystem.py` support queued work, tag changes, and file operations.

Keep API inputs validated, filesystem writes verified, and uncertain live-edit outcomes visible rather than silently retrying them.