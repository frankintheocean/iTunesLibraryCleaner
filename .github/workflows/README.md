# 🚦 GitHub workflows

- 🪟 `windows-build.yml` builds and tests the Windows app, validates the installer, creates the portable/source ZIPs and SHA-256 files, and refreshes the published **v1.0.0** release assets when checks pass.
- 📝 `release-notes.yml` syncs the stable v1.0.0 release body from `docs/RELEASE_1_0_0.md` and refreshes older pre-release notes from their versioned guides.
- 🧪 `windows-diagnostics.yml` gathers extra Windows build diagnostics.
- 👀 `publish-windows-preview.yml` handles preview-release artifacts.

Check the workflow run and logs before calling a build or release complete. A source-level COM test is not the same as testing through the installed app on the target Windows/iTunes setup.
