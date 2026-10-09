# 🖥️ Desktop shell

Electron opens the app window, starts the Python service, manages local dialogs, and exposes a small preload bridge.

- 🚪 `main.cjs` owns startup, window settings, and allowed IPC calls.
- 🔐 `preload.cjs` exposes approved renderer actions.
- ✅ `contracts.cjs` restricts renderer requests to a known set of local API paths.

Do not expose Node.js or unrestricted network access to the renderer.
