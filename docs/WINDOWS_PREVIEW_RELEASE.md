Windows x64 testing preview, built from commit `643c4c33c961a5e850448d77031a981404658606`.

Download `Unified-iTunes-Library-Manager-4.0.0-win-x64.exe`. The adjacent `.sha256` file provides its checksum; `installer-validation.json` records the actual installer acceptance results.

The Windows Server 2022 runner passed 186 Python tests (one Linux-only test skipped), both IPC tests, frontend compilation, the frozen backend smoke test, and the actual packaged Electron workflow. Silent install, repair of a deleted backend, uninstall/reinstall, and byte-identical application-state preservation passed. [Validation run](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37870955008).

The installer is unsigned. Real classic iTunes COM validation awaits a Windows test-library report; modal/restart recovery, Windows 10/11 clean-machine acceptance, high-DPI/multi-monitor behavior and manual shortcut checks remain outstanding. This preview is not a certified production release.

For real COM testing with a new empty disposable classic iTunes library, use [the validation instructions](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/WINDOWS_VALIDATION.md). No personal collection was used by the automated tests. The release's source scope and remaining feature limitations are documented in `docs/LIMITATIONS.md`.
