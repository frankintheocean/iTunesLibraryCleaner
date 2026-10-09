# 🚦 GitHub workflows

- 🪟 `windows-build.yml` builds the Windows app, tests the bundled backend and desktop, validates the installer, creates ZIPs/checksums, and publishes the 4.0.0 release when all required steps pass.
- 📝 `release-notes.yml` assists with release-note maintenance.
- 🧪 `windows-diagnostics.yml` gathers extra Windows diagnostics.
- 👀 `publish-windows-preview.yml` handles preview-release artifacts.

Check the workflow run and its logs before calling a release complete.
