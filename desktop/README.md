# 🖥️ Electron desktop shell

Electron opens the app window, starts the local Python service, handles operating-system dialogs, and exposes a narrow preload bridge to the React interface.

- 🚪 `main.cjs` owns startup, window settings, and approved IPC handlers.
- 🔐 `preload.cjs` exposes only the renderer actions needed by the interface.
- ✅ `contracts.cjs` limits requests to known local API paths.

Keep the renderer isolated: do not enable unrestricted Node.js access, add broad IPC passthroughs, or give the renderer an unrestricted network client. Changes to the bridge should be covered by the desktop tests.