# 🧪 Automated test guide

Use synthetic fixtures for routine tests. Never point destructive test flows at a personal music library.

- 🐍 Python tests cover API requests, scans, metadata edits, filesystem safety, history, playlists, and job handling.
- 🖥️ `desktop.test.cjs` checks the renderer IPC allowlist.
- 🪟 `desktop-integration.cjs` launches Electron and exercises local-library UI flows with generated test data.
- 🌱 `make_fixture.py` creates synthetic library fixtures for repeatable tests.

From the repository root, run:

```sh
.venv/bin/python -m pytest tests legacy/consolidator/tests -q
npm test
npm run build
```

On Windows, use `.venv\\Scripts\\python.exe` in place of `.venv/bin/python`. Classic-iTunes COM behavior still needs separate validation on Windows with a disposable library.