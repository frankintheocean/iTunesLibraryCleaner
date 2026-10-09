# 🔌 Python backend

The backend reads libraries, indexes tracks, previews edits, queues jobs, and talks to classic iTunes through a separate Windows COM process.

- 🌐 `api.py` defines authenticated local HTTP routes.
- 📚 `service.py` scans XML/folders/live libraries and builds overview statistics.
- 🗄️ `store.py` owns SQLite records and migrations.
- 🎵 `com_service.py` handles guarded live iTunes operations.
- 🎨 `artwork.py` and `lastfm.py` resolve small artwork images and listening charts.

Keep filesystem writes verified and keep COM objects inside their owning process.
