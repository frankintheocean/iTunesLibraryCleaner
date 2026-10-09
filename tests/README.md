# 🧪 Automated tests

- 🐍 Python tests cover API requests, scans, metadata changes, filesystem safety, history, playlists, and job handling.
- 🖥️ `desktop.test.cjs` tests the renderer IPC allowlist.
- 🪟 `desktop-integration.cjs` launches Electron and checks real local-library UI flows with generated test data.
- 🌱 `make_fixture.py` creates synthetic libraries; tests should not use a personal music collection.

Run `.venv/bin/python -m pytest tests legacy/consolidator/tests -q`, `npm test`, and `npm run build`. Windows COM behavior must be tested separately with classic iTunes.
