# 🗓️ Cleaner release history

These are the original Cleaner versions, separate from the unified app’s version 1.0. Later official versions use steps of 0.5.

[Full historical notes](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/v1.0/legacy/cleaner/CHANGELOG.md) keep the detailed fixes and behavior for every version.


## v3.0 🕰️

### 🐛 Fixed

- Merge Albums false positives on same-titled albums by different artists.
### ✨ Added

- Optional online confirmation for Merge Albums.
- Cancel button in Merge Albums.
### ⚡ Improved

- Merge Albums' library scan now scales its status-update frequency to library size instead of always updating every 100 tracks - large libraries (5,000+ tracks, and especially 30,000+) spend less time marshalling status-label updates onto the UI thread during the scan, with no change to what's scanned or found.
- Album-name/artist normalization (used to detect split albums) now compiles its matching patterns once at startup instead of on every call - on a 30,000+ track library this function runs 60,000+ times per scan, so the fixed per-call overhead is removed.

## v2.5 🕰️

### ✨ Added

- Merge Albums.
### ⚡ Improved

- New app/taskbar icon.

## v2.0 🕰️

### 🔧 Changed

- Version bump only - no functional changes from v1.6.

## v1.6 🕰️

### ✨ Added

- Auto theme.
### ⚡ Improved

- Simpler wording throughout the app.

## v1.5 🕰️

### ✨ Added

- Pluggable online-lookup providers.
- Output folder picker.
### 🐛 Fixed

- Closing the window mid-run could abandon it instead of stopping it cleanly.
- Repeated stopped runs leaked tooltip bindings on Start.
### ⚡ Improved

- Drag-and-drop reordering for custom genre rules.
### 🔧 Changed

- Main window remembers its size and position.

## v1.0 (release) 🕰️

### ✨ Added

- Per-phase progress breakdown.
- Bulk genre rule import from CSV.
- Visual paused/stopped state.
### ⚡ Improved

- Inline shadow warning in the Genre Rule Editor.
- Investigated batching iTunes COM writes.

## v7.0 (pre-release) 🕰️

### 🐛 Fixed

- Eager delete-batch reenumeration was silently discarded.
- Custom genre rules weren't crash-safe to save.
- Settings' "Reclaim space" and "Clear cache" could freeze the app.
### 🔧 Changed

- Removed an unused `import unicodedata` in `genre_rules.py` (accent stripping has used a plain translation table since it was added; no behavior change).

## v6.5 (pre-release) 🕰️

### ✨ Added

- Verbose COM error detail in the debug log.
### ⚡ Improved

- Capped Last.fm retry backoff per lookup.
- Centralized icon/label constants.

## v6.0 (pre-release) 🕰️

### ⚡ Improved

- Faster genre-rule matching for large custom rule lists.
- One quick retry on iTunes Search lookups.
- Theme styling is now data-driven.
### 🐛 Fixed

- Non-atomic changelog/undo-log writes.

## v5.9 (pre-release) 🕰️

### 🐛 Fixed

- Silent re-enumeration fallback.

## v5.8 (pre-release) 🕰️

### ✨ Added

- Confirmation before deleting a custom genre rule.

## v5.7 (pre-release) 🕰️

### ✨ Added

- Cache maintenance in Settings.

## v5.6 (pre-release) 🕰️

### 🐛 Fixed

- Non-atomic settings.json writes.

## v5.5 (pre-release) 🕰️

### ✨ Added

- Configurable delete-batch size.
- Toast-notification availability hint.

## v5.0 (pre-release) 🕰️

### 🔧 Changed

- Genre writes now use the same reused-session-with-fallback pattern as deletes.
- Shared `run_in_background()` helper.

## v4.5 (pre-release) 🕰️

### 🐛 Fixed

- Pause vs. Stop confusion.
- Fragile placeholder-text credential fields.
### ✨ Added

- Color-coded log lines.
- Resizable, remembered Settings window.
### ⚡ Improved

- Smoother ETA.
- Less repetitive live-run warning.
- Scope picker auto-refreshes.
- Structured logging.

## v4.0 (pre-release) 🕰️

### ✨ Added

- Multi-playlist and exclude-mode scope.
- Pattern test box in the Genre Rule Editor.
- Built-in rules browser.
- Failure drill-down with one-click retry.
### 🔧 Changed

- COM apartment lifecycle in Undo.

## v3.6 (pre-release) 🕰️

### ✨ Added

- Post-run review popup.
- Confirmation dialog before a live run.
- Finish notification when the window isn't focused.
### ⚡ Improved

- Last.fm lookups now retry temporary failures.
- Option presets are saved more reliably.
- Last.fm API key field is now password-masked.

## v2.0 (pre-release) 🕰️

### 🐛 Fixed

- Entry field placeholders broke if you typed the placeholder text itself.
### ✨ Added

- Pause, not just Stop.
### 🔧 Changed

- Rounded corners across the UI - stat cards, the log pane, the progress bar track, buttons, and the entry/dropdown fields.

## v1.5 🕰️

### 🐛 Fixed

- ETA wasn't updating.
- Some real songs were wrongly deleted as "junk".
- App froze for 10-20 seconds after deleting a junk track.
### ✨ Added

- Scrollable log pane.
- Simpler wording and emojis throughout the app, to make status and settings easier to read at a glance.
### 🔧 Changed

- Renamed the app to **LibraryCleaner**.
- Versioning scheme: this is pre-release 1.0.

## v3.5 🕰️

### ✨ Added

- Shared widget-styling module.
### ⚡ Improved

- Processed-track cache moved to SQLite.
- `_run_inner` split into focused methods.
- Disk-write failures during wrap-up are no longer silently swallowed.
### 🔧 Changed

- `processed_id_cache` reads/writes now go through `ProcessedCache`, which guards its in-memory key set with its own lock.

## v3.0 🕰️

### 🐛 Fixed

- Settings → Changelog tab created an unused, invisible duplicate text widget.
### ⚡ Improved

- Genre-cleanup pass was noticeably slower than it needed to be.
- Folded the "already a target genre?" check and the pattern-matching map into one combined lookup (`genre_lookup_key`) so each track's genre is scanned against the pattern list once instead of twice.
### 🔧 Changed

- `ViewState` now owns the mapping from its fields (percent, processed, remaining, changed, deleted, eta, elapsed, current track, output folder) to the ttk labels that display them.

## v2.5 🕰️

### 🐛 Fixed

- Changelog notes were missing from Settings.
### ✨ Added

- Custom genre mapping editor.
- Persistent option presets.
### 🔧 Changed

- COM initialization is now owned by a context manager, so every worker-thread COM apartment is initialized and uninitialized as one enforced lifecycle.
- Cleanup processing is split into focused methods for per-track processing, junk deletion and genre updates.
- Main-window reset state is represented by a single `ViewState` object instead of manually maintaining unrelated widget reset values.
### ⚡ Improved

- Foreign-language detection and blank-genre online lookup now run concurrently when both are enabled, reducing network wait time.
- Progress animation interpolates toward the target value without repeatedly measuring widget geometry, avoiding resize/repaint jitter.
- Progress and settings UI continue to use ttk styling, with rounded visual treatment retained for the primary surfaces.

## v2.1 🕰️

### 🔹 Improved

- Batched delete re-enumeration: after a junk-track delete, the library is no longer re-walked via COM on every single delete.
- `itunes_com.do_track_delete` now reuses the existing iTunes COM session for deletes instead of opening a brand-new session for every delete.
- Main window is now resizable (with a sensible minimum size), instead of a fixed 520x716, so it's usable on high-DPI displays and smaller screens.
### 🔹 Added

- Library scope picker: choose "Entire library" or a specific iTunes playlist to scope a run to, instead of always processing the whole library.
- Settings window with tabs (alphabetical order): Accessibility, Changelog, Diagnostics, General, Themes.
- Changelog output (`changelog.txt`) now records which scope (entire library or a named playlist) a run was scoped to.

## v2.0 🕰️

- Initial Python/Tkinter port of the original GenreCleanup.hta: genre-mapping cleanup engine, junk-track-name deletion, online genre lookup (iTunes Search API + Last.fm), foreign-title detection, undo log, and processed-track cache.
