# 🚦 GitHub workflow guide

These workflows automate Windows packaging, release-note updates, and diagnostic collection. A green source-level test is not proof that the installed app works on every Windows/iTunes setup.

- 🪟 `windows-build.yml` runs on Windows, builds and tests the app, validates install/repair/uninstall, packages the portable and source ZIPs, and writes SHA-256 sidecars.
- 📦 Release publishing is gated by the version in `package.json`. The workflow currently contains explicit **1.0.0** release logic and legacy **4.0.0** migration handling; do not describe it as a generic “publish latest version” job.
- 📝 `release-notes.yml` updates only the release tags and note files listed in its script. Check that list before assuming a new release guide will be published automatically.
- 🧪 `windows-diagnostics.yml` collects extra build diagnostics.
- 👀 `publish-windows-preview.yml` handles preview artifacts.

Before calling a release complete, inspect the workflow run, confirm the expected release tag and assets, and verify the uploaded checksums. Use a disposable library for live COM validation.