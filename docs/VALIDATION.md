# Build and validation report

Validated on Linux with Python 3.12.14 and Node 24.19.0. This report distinguishes implemented source functionality from Windows acceptance.

| Check | Actual result |
| --- | --- |
| Original source preservation | All 86 supplied project files verified; the documented Last.fm credential removal is the sole publication change (`scripts/verify-originals.py`) |
| Python suites | 187 passed: 141 original Consolidator tests plus 46 unified domain/API/filesystem/COM-contract cases |
| IPC contracts | 2 Node tests passed: endpoint/method restrictions and payload limits |
| Frontend | TypeScript check and Vite 8.3.4 production build passed |
| Desktop integration | Passed: actual Electron + backend startup, synthetic 120-track scan, virtualized table, preview/commit of a real file-tag update, persisted dark theme, all 11 navigation sections, maximize/restore and 820×620 layout |
| Linux PyInstaller bundle | Built and exercised: authenticated readiness, real XML scan, SQLite index, playlist and bundled changelog |
| Legacy launch | Original Cleaner and Consolidator windows opened; Consolidator app-data redirect fixed in wrapper. Frozen Linux Consolidator also opened successfully |
| Reusable setup | `scripts/setup-cloud.sh` executed successfully; pinned pip install, `npm ci`, verified Electron download and production frontend build |
| Windows Python dependencies | Every pinned CPython 3.12 win_amd64 wheel downloaded successfully, including pywin32/Qt/PyInstaller. Not a Windows execution test |
| Dependency advisories | npm audit and pip-audit of the full Linux Python lock reported zero known advisories after pinned updates |
| Icon | Original generated source plus PNG sizes; ICO includes 16, 24, 32, 48, 64, 128 and 256 px |
| Source ZIP | `scripts/package-source.py` verifies archive integrity and exactly one `Unified-iTunes-Library-Manager/` root; SHA-256 supplied beside ZIP |
| Real iTunes COM | Not yet executed against classic iTunes. Windows contract tests passed; a real empty-library validation script is provided. Contract tests cover signed persistent IDs, live multi-field edits, readback, busy reconnect, concurrent changes, partial outcomes, DRM rejection and optional members |
| Windows installer/repair/uninstall | Passed on Windows Server 2022 x64: actual NSIS install, packaged Electron workflow, repair of a deleted backend, uninstall/reinstall and byte-identical generated SQLite state preservation. Run [37870955008](https://github.com/frankintheocean/iTunesLibraryCleaner/actions/runs/37870955008); Windows 10/11 manual acceptance remains outstanding |

## Important test limits

The cloud cannot configure Chromium's SUID sandbox helper. Linux desktop integration used the explicit test-only `LIBRARY_MANAGER_TEST_NO_SANDBOX=1` flag and a temporary Xvfb display. Production Electron keeps sandbox/context isolation enabled. Linux UI passing is not sandboxed Windows validation, a high-DPI/multi-monitor pass or a complete accessibility audit.

Two test-only deprecation warnings concern Starlette's httpx/AnyIO TestClient adapters. They do not change test outcomes. No real user library or collection was modified. Screenshots show generated fixture data, not dummy application APIs. Domain/filesystem mutation tests use isolated temporary directories.

Initial failures were diagnosed and corrected: the mislabeled Consolidator ZIP was extracted by its actual signature; Electron download needed proxy/cache configuration; a collision fixture incorrectly used an overlapping target; a virtualized UI test requested an off-screen row; legacy package imports/app-data paths required wrapper changes. Early dependency audits found advisories in development tools and Python dependencies; final pinned locks pass the known-advisory checks.

## Remaining scope

See [LIMITATIONS.md](LIMITATIONS.md) for the advanced master-prompt features not complete. Original advanced functionality is retained in explicit legacy tools rather than silently omitted. This is not represented as a fully certified production Windows release or complete fulfillment of every new master-prompt requirement. Windows release acceptance in TESTING.md is required before distributing an installer.

Reusable installation and start instructions were saved to the cloud configuration draft. Saving did not publish an environment or push/upload this project to GitHub or any remote repository. To retain the environment snapshot, review/save the draft in environment settings and publish through the product.
