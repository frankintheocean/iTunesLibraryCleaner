# ✅ Test results

Validated on Linux with Python 3.12.14 and Node 24.19.0. Source tests and Windows installer tests are listed separately.

| Check | Actual result |
| --- | --- |
| Original source preservation | All 86 supplied project files verified; the documented Last.fm credential removal and guide wording changes are documented (`scripts/verify-originals.py`) |
| Python suites | 196 passed: 141 original Consolidator tests plus 55 unified domain/API/filesystem/COM-contract cases |
| IPC contracts | 3 Node tests passed: endpoint/method restrictions and payload limits |
| Frontend | TypeScript check and Vite 8.3.4 production build passed |
| Desktop integration | Passed: actual Electron + backend startup, synthetic 120-track scan, virtualized table, preview/commit of a real file-tag update, persisted dark theme, all 11 navigation sections, maximize/restore and 820×620 layout |
| Linux PyInstaller bundle | Built and exercised: startup with authentication, real XML scan, SQLite index, playlist and bundled changelog |
| Legacy launch | Original Cleaner and Consolidator windows opened; Consolidator app-data redirect fixed in wrapper. Frozen Linux Consolidator also opened successfully |
| Reusable setup | `scripts/setup-cloud.sh` executed successfully; pinned pip install, `npm ci`, verified Electron download and production frontend build |
| Windows Python dependencies | Every pinned CPython 3.12 win_amd64 wheel downloaded successfully, including pywin32/Qt/PyInstaller. Not a Windows execution test |
| Dependency advisories | npm audit and pip-audit of the full Linux Python lock reported zero known advisories after pinned updates |
| Icon | Original generated source plus PNG sizes; ICO includes 16, 24, 32, 48, 64, 128 and 256 px |
| Source ZIP | `scripts/package-source.py` verifies archive integrity and exactly one `iTunes-Manager/` root; SHA-256 supplied beside ZIP |
| Real iTunes COM | User-run source script reported PASS on Apple-distributed iTunes 12.13.11.1 after the Dispatch fallback fix: all 14 live metadata fields, independent readback and undo that keeps later changes. Detailed JSON/high-bit PID coverage not supplied; live editing through the installed app and dialog/restart checks remain. Contract tests cover signed persistent IDs, live multi-field edits, readback, busy reconnect, concurrent changes, partial outcomes, DRM rejection and optional members |
| Windows installer/repair/uninstall | Passed on Windows Server 2022 x64: actual NSIS install, packaged Electron workflow, repair of a deleted backend, uninstall/reinstall and unchanged saved app data. Run [37873855493](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37873855493); Windows 10/11 manual checks remain |

## 🚧 Test limits

Linux desktop tests used a temporary Xvfb display and the test-only `LIBRARY_MANAGER_TEST_NO_SANDBOX=1` flag because this cloud cannot configure Chromium’s SUID sandbox helper. Production sandboxing remains enabled. Linux results do not prove Windows sandbox support, display scaling, multiple monitors or full accessibility.

Two test warnings concern older Starlette test adapters, not failed checks. Tests used generated media and temporary folders; no personal collection was changed. Screenshots came from working app requests with generated data.

Earlier failures were fixed: an archive had the wrong extension, Electron needed proxy/cache setup, a file-collision fixture was incorrect, a UI test targeted an off-screen row, and original-tool launches needed app-data fixes. Dependency updates resolved the known audit findings.

## 🧩 Remaining work

See [known limits](LIMITATIONS.md) for incomplete requested features. Advanced original workflows remain available in the original tools. This is a testing preview, not a claim that every requested feature or Windows production check is complete. See [required checks](../TESTING.md).

Reusable install and startup instructions were saved to the cloud environment draft. Saving that draft did not publish the environment. To keep it, review and save the draft in environment settings, then publish it there.

## 🎵 Version 2.0.0 checks

Six new Python tests cover safe queue clearing, elapsed-time pausing, old-database upgrades, bounded artwork, preferences and signed-ID live-artwork access. The desktop test checks whole-page heading scroll, centered title text, embedded covers, genre percentages, queue clearing, OLED black backgrounds, font selection and enlarged text, plus the existing scan/edit workflow. Windows 2.0.0 passed on Server 2022: 195 Python tests plus one Linux-only skip, 3 IPC tests, bundle startup, installed-app workflow, repair and uninstall/reinstall with unchanged saved data. [Build evidence](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37878468914). Real installed-app live iTunes and live artwork remain pending.

## 🎵 Version 3.0.0 checks

Linux source checks passed 210 Python tests, 4 IPC checks and the desktop scan/edit workflow. New cases cover snapshot publication while the old file is open, failed-save recovery, cached-library isolation, partial indexing, exact live-ID fallback, wrong-library refusal, queue timing, library removal, history clearing, default paths and playlist pictures. The desktop test also switches between a blank and loaded library during background refreshes. These tests use generated data.

On the generated 40,000-song XML, v3 loading took 2.17 seconds versus 3.21 for the v2 library and database code. Searches took 17–25 ms. Cached overview lookup took 0.74 ms; a one-file title edit took 2.52 seconds versus 3.32. Run `scripts/benchmark-library.py --compare-v2` to repeat the comparison. These Linux fixture timings do not measure live COM or promise the same speed on other machines.

Windows 3.0.0 passed 209 Python tests with one Linux-only skip, 4 IPC checks, installer, packaged-app, repair and uninstall/reinstall checks with saved data preserved. Both release ZIPs and the 40,000-song loading/edit check passed. [Windows build evidence](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37896971968). The published [3.0.0 downloads](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/tag/v3.0.0) were downloaded again and checked against all three SHA-256 records; both ZIPs passed integrity and source-commit checks. Release artifacts include a report tied to source commit `fa70d0e2a9f19babdb22d922826b739731c58103`; this does not replace manual Windows 10/11 and real iTunes checks.

The Windows archive check exposed database connections left open after transactions. The service now closes them explicitly, including failed transactions. A new test checks rollback, closed handles and removal of a closed database on Windows.

## 🎵 Version 3.1.0 checks

Linux source checks passed 263 Python tests, 5 IPC checks and the production interface build. Tests cover scan progress beyond the old deadline, stalled scans, unchanged write deadlines, cancellation, all 48,000 generated IDs, every Last.fm chart and period, rejected keys, profile pictures, safe picture hosts, bounded image downloads, track album covers, private-data errors and hidden discovery paths. Last.fm fixtures contain no real account or key.

Fresh large-library COM and real-account Last.fm checks remain pending. Windows 3.1.0 passed 262 Python tests with one Linux-only skip, 5 IPC checks, bundle startup, the installed-app workflow, repair and uninstall/reinstall with saved data preserved. Both ZIPs and the generated 40,000-song loading/edit check passed. [Windows evidence](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37902074381).

The published [3.1.0 downloads](https://github.com/frankintheocean/iTunesLibraryCleaner/releases/tag/v3.1.0) were downloaded again. All three SHA-256 records matched; both ZIPs passed integrity and source-commit checks. Their report identifies source commit `40afc9d0f6d603398d8fee86975ba81ff2ce9f56`.

The desktop check passed all 12 navigation sections, Settings-only GitHub access, hidden/restored suggestions, Last.fm connection errors, profile picture size, charts, paging and disconnect. Its Last.fm responses are demo fixtures; library scan/edit requests use the actual service.

A separate generated 48,000-song XML check passed: loading took 1.54 seconds, indexed searches took 20–39 ms, and a real one-file title edit took 2.39 seconds on this Linux machine. These fixture results do not measure live COM or promise timings on other hardware.

## 🎵 Version 3.1.1 checks

Linux checks passed 278 Python tests, 5 IPC tests, the production build and the real desktop library scan/edit workflow. New cases cover HTTPS upgrades for old image links, approved CDN redirects, blocked redirects to other hosts, valid binary image responses, public artist-page pictures, recovery of missing profile images, 256-pixel profile thumbnails, track/album lookups, failed-image retries, scan warm-up and uncapped large-scan estimates.

Desktop checks confirm that only Overview has the library picker, and the same loaded library remains usable in File Organizer and Metadata. Last.fm pictures in this desktop test are fixtures; public-page and CDN behaviours are tested through provider-shaped HTTP responses. A fresh real-account image check is blocked by this cloud’s Last.fm network restrictions. The required domains were saved to an environment draft; that draft has not been applied or published.

Windows release downloads require a successful installer, repair, uninstall and archive check for their source commit. Real classic iTunes testing remains separate.


## 🎵 Version 1.0.0 validation

This release adds API and user-interface regression tests for distinct album counting, Library Stats, sorting and selection, history/Field journal clearing, and guarded playlist operations. Playlist cover application inside classic iTunes is conditional on an artwork setter being exposed by the installed COM object; unsupported builds retain the manager-side image and report that limitation. Final Windows build and installer/repair checks are performed by GitHub Actions.
