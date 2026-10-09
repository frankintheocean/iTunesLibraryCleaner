# 🧪 Run checks

## ⚡ Local checks

From the repository root, after installing the locked dependencies:

```sh
.venv/bin/python -m pytest tests legacy/consolidator/tests -q
npm test
npm run build
```

Windows PowerShell uses `.venv\Scripts\python.exe`. Tests use temporary media and library fixtures.

## 🖥️ Desktop integration

Run `npm run test:desktop` to launch Electron and exercise the real local API. It covers Overview, Current Library, Settings-based Libraries and History, selection/sorting, history and Field journal clearing, themes, and Last.fm UI fixtures. The Linux test needs a display. A cloud-only `--no-sandbox` flag is for test harnesses; production sandboxing stays enabled.

## 🪟 Before a public release

GitHub Actions builds the Windows installer, checks a bundled backend and generated library, runs the desktop integration workflow, verifies the installer and produces ZIPs/checksums only after validation succeeds.

Use a disposable classic iTunes library on Windows for real-COM validation. Never test delete or reorder actions against a personal library. Check live scans, metadata writes, undo, playlist reorder success/failure, and playlist-picture behavior. If COM exposes no safe playlist move or art setter, the app should report the limitation and leave tracks unchanged.
