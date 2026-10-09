# LibraryCleaner

Version 3.0

A Windows desktop app (Tkinter) that cleans up genre tags in your local
iTunes library: consolidates messy/inconsistent genres down to a
canonical list, looks up unknown genres online, tags foreign-language
titles as International, and deletes junk-named tracks left over from
bad CD rips. Ported from the original `GenreCleanup.hta`.

> Version 1.0 was the first official release. From there, version
> numbers go up in steps of 0.5 (1.5, 2.0, 2.5, ...) for subsequent
> releases. See `CHANGELOG.md` (or Settings → Changelog in the app)
> for release notes.

## Features

- **Merge Albums** - click **Merge Albums…** on the main window to scan
  your library for albums iTunes has split into two entries - most
  often an 11/12-track album plus one stray track left with a blank or
  mismatched Album Artist (or a slightly different Album title, e.g. a
  trailing "(Deluxe)"). Detected groups are listed for review, each
  with a before/after preview of exactly which fields (Album, Album
  Artist, Track/Disc Number, Track/Disc Count, Year, Genre) will
  change - untick any group that isn't a real match, then **Merge
  selected**. Detection is deliberately conservative: only a small
  (1-4 track) stray group sharing an album name with a larger (3+
  track) main group is flagged, so two same-titled but both-large
  albums (e.g. two different "Greatest Hits") are left alone rather
  than guessed at. A candidate stray group is also checked against the
  main group's track Artist (not just AlbumArtist), so a same-titled
  album by a genuinely different artist isn't offered as a match even
  if the track count alone would look small enough to be a stray.
  Optionally, tick **Confirm matches online** before scanning to add
  one iTunes Search API lookup per candidate group as an extra check -
  a group is dropped only if both sides confidently resolve to
  different albums by different artists; an inconclusive or failed
  lookup never removes a group. Applying a merge only writes fields
  that actually differ, using the same reused-session/reconnect-on-
  failure COM pattern as genre writes and deletes. A **Cancel** button
  appears while a merge is applying - it stops after the track
  currently being written finishes, leaving already-merged tracks
  merged.
- **Genre consolidation** - maps a large table of genre variants
  (e.g. "Hip-Hop", "Trap", "Drill") down to a small set of canonical
  genres, using ordered pattern matching (`genre_rules.py`). Matching
  runs on a small Aho-Corasick automaton built from the built-in and
  custom rule tables, so a run's per-track lookup cost tracks the
  length of the genre string rather than the number of rules - this
  keeps things fast even if you accumulate a large custom rule list,
  not just the built-in table.
- **Unknown-genre lookup** - for tracks with a blank genre, queries the
  iTunes Search API first, then Last.fm, and writes back whatever it
  finds. A single transient failure (timeout, connection reset, a
  5xx/429 response) on the iTunes call gets one quick retry before
  falling back to Last.fm, so a brief blip doesn't cost the track its
  primary lookup source. The two sources are pluggable
  `GenreProvider` implementations (`online_lookup.py`) behind a small
  abstract interface, so adding another lookup source doesn't require
  touching `OnlineLookup` itself.
- **Foreign-language detection** - flags tracks whose title (or any
  artist name in a multi-artist field) looks non-English and tags them
  `International`.
- **Junk-track deletion** - detects and deletes tracks whose name (or,
  if untagged, filename) matches the pattern left behind by badly
  ripped, numbered CD track lists (e.g. `006 - Some Song-1-1-1`).
- **Library scope picker** - run against your entire library, or click
  **Choose…** to scope a run to one or more playlists ("only these"),
  or flip to "entire library except these" to exclude a handful of
  playlists instead. Use the refresh (⟳) button to reload the current
  list of playlists from iTunes.
- **Dry run** - preview every change (genre rewrites and deletions)
  with nothing actually written or deleted.
- **Undo** - reverts genre changes from the most recent live run.
  Deleted tracks cannot be restored automatically (iTunes has no
  "undelete" via COM) - the undo report tells you how many were
  skipped so you know to restore those from a backup if needed.
- **Force full re-scan** - ignores the "already fixed" cache from past
  runs and reprocesses every track.
- **Custom genre mapping editor** - add, edit, delete and reorder your
  own pattern → genre rules from Settings → Genres, instead of hand-
  editing `genre_rules.py`. Reorder by dragging a rule to a new spot in
  the list, or with the ↑/↓ buttons. Your rules are checked before the
  built-in table and are stored separately, so they survive app
  updates. A test box lets you check whether a pattern matches a
  sample genre string - and whether a higher-priority existing rule
  would shadow it - before you save it.
- **Built-in rules browser** - Settings → Built-in rules shows the full
  built-in pattern → target genre table the app ships with, searchable,
  read-only, in the order it's checked - so you can see why a genre
  mapped the way it did, and know exactly which pattern to out-rank
  with a custom rule if you want to override it.
- **Settings window** - tabs: General, Themes, Genres, Built-in rules,
  Changelog, About. See below.
- **Live scrolling log** - a timestamped, scrollable log pane shows
  everything that's happened during a run, alongside the single-line
  status.
- **ETA** - a live estimate of time remaining, based on your average
  pace so far.
- **Pause** - suspend a run in place and resume from the exact same
  track, without losing progress the way stopping and restarting does.
  Pause and Stop both have tooltips explaining the difference, since
  only Pause preserves your place - Stop ends the run, and starting
  again after a Stop always begins a fresh run from the top. A banner
  above the progress bar, plus a dimmed progress bar style, make the
  paused/stopped state visible beyond the button text alone.
- **Per-phase progress breakdown** - a two-segment bar under the main
  progress bar shows how many tracks this run has handled via junk
  deletion versus genre writing, so the two kinds of work (which can
  otherwise blend into one percentage) are visible separately.
- **Bulk genre rule import from CSV** - Settings → Genres →
  **Import CSV…** loads a `pattern,target` CSV (header row optional)
  and adds every valid row at once - faster than typing rules in one
  at a time for a large rule set. Existing patterns are updated in
  place rather than duplicated; any unparseable lines are reported by
  line number.
- **Inline shadow warning** - typing a pattern in the Genre Rule
  Editor that would be fully shadowed by an existing higher-priority
  rule (an earlier custom row, or a built-in) now shows a warning
  right under the Pattern/Target fields as you type, in addition to
  the existing test-box check against a sample genre string.
- **Live-run confirmation** - starting a run with Dry run turned off
  shows a warning dialog first, since a live run may rewrite genres and
  permanently delete junk-named tracks (deletions can't be undone).
  The dialog has a "Don't ask again this session" checkbox so it
  doesn't have to be dismissed on every single live run; it always
  reappears the next time the app is launched.
- **Post-run review popup** - when a run finishes, a review window
  opens showing every genre change and deletion from that run, with a
  filter for All / Genre changes / Deletions / Failures. Failures are
  listed individually (which track, and why - locked file, iTunes COM
  error, track not found, etc.), with a **Retry failed** button that
  re-attempts just those tracks instead of a full re-run.
- **Finish notification** - if the window isn't focused when a run
  finishes, LibraryCleaner flashes the taskbar icon and rings the
  system bell (plus a native Windows toast if `win10toast` is
  installed).
- **Saved option presets** - your Last.fm username/API key and every
  toggle (lookup order, dry run, force re-scan, scope) are remembered
  between launches, saved both when you start a run and when you close
  the app.
- **Live scrolling log with color-coded lines** - success, warning,
  error and informational lines are colored distinctly (in addition to
  their emoji prefix) so scanning a long run's history is faster.
- **Debug log file** - alongside the user-facing `changelog.txt`, a
  `GenreCleanup_Debug.log` file in the app folder keeps a rotating,
  timestamped record of internal status/error messages for
  troubleshooting. iTunes COM failures (a locked file, a dropped COM
  session, a rejected write) now log a verbose detail line here -
  HRESULT, the COM-reported source/description, and the failing
  argument index when available - separate from the short reason
  shown in the changelog/Failures list, so a user-reported issue can
  usually be diagnosed from this file alone without needing to
  reproduce it.

## Requirements

- Windows, with iTunes installed (the app talks to iTunes over COM via
  `pywin32`).
- Python 3.9+ if running from source. See `requirements.txt`.

## Running from source

```
pip install -r requirements.txt
python main.py
```

## Building a standalone .exe / installer

See `build/build.bat` (PyInstaller onefile build, plus an optional
Inno Setup installer via `build/installer.iss`). Run it from a Windows
command prompt in the project root:

```
build\build.bat
```

On success this produces `GenreCleanup.exe` in the project root, and
(if Inno Setup is installed) `dist_installer\GenreCleanup-Setup.exe`.

## Using the app

1. Choose your options:
   - **Look up unknown/blank genres online** - on by default.
   - **Detect foreign-language titles online** - on by default; tags
     matches as `International`.
   - **Dry run** - preview only, nothing is written or deleted.
   - **Force full re-scan** - ignore the already-fixed cache.
   - **iTunes first / Last.fm first** - which online genre source to
     try first when both are available.
   - **Scope** - "Entire library" (default), or click **Choose…** to
     run against one or more selected playlists, or against the whole
     library except selected playlists. Click ⟳ to refresh the
     playlist list from iTunes.
2. If you want Last.fm lookups under your own API key/account, enter
   your Last.fm username and API key (both optional - a shared
   fallback key is used if you leave the key blank).
3. Click **Start Cleanup**. If Dry run is off, you'll be asked to
   confirm the live run first, since it can rewrite genres and
   permanently delete junk-named tracks. Progress, per-track status,
   running stats (processed/remaining/changed/deleted/elapsed/ETA), and
   a scrolling log all update live. Use **Pause** to suspend a run in
   place and pick it back up from the exact same track, or **Stop** to
   end the run early (resuming after Stop starts a fresh run instead).
   If the window isn't focused when the run finishes, the taskbar icon
   flashes and the system bell rings.
4. When a run finishes (and wasn't stopped early), a **review popup**
   opens automatically listing every genre change and deletion from
   that run, filterable by type. If anything failed, the Failures
   filter lists each one individually with its reason, and a **Retry
   failed** button lets you re-attempt just those tracks. Close the
   popup to return to the main window.
5. When a live (non-dry-run) run finishes, three files are written to
   the app's folder:
   - `GenreCleanup_UndoLog.csv` - used by **Undo Last Run**.
   - `GenreCleanup_Processed.db` - a small SQLite database used as the
     already-fixed cache to skip previously-processed tracks on future
     runs (unless "Force full re-scan" is checked). If you're
     upgrading from an older version, an existing
     `GenreCleanup_Processed.csv` is migrated into this automatically
     the first time it's needed - nothing to do manually. This cache
     has no automatic size cap and can accumulate stale rows for
     tracks later deleted from iTunes over years of use; use
     Settings → General → "Reclaim space" or "Clear cache" to
     maintain it.
   - `changelog.txt` - a human-readable summary of that run
     (options used, scope, counts, and a per-track list of changes).

   `GenreCleanup_UndoLog.csv` and `changelog.txt` are both written to a
   temp file in the app folder first, then atomically renamed into
   place - the same crash-safe pattern already used for
   `settings.json` and the processed-track cache - so a crash or power
   loss mid-write can't leave either file half-written.
6. Use **Undo Last Run** to revert genre changes from the most recent
   live run. Deleted junk tracks are reported but not restored.
7. Use **Merge Albums…** to find and fix albums iTunes has split into
   two entries. Optionally tick **Confirm matches online** for an
   extra iTunes-catalog check before results are shown. Click **Scan
   library**, review the detected group(s) and their field-change
   previews, untick anything that isn't a real match, then **Merge
   selected**. Click **Cancel** at any point while it's applying to
   stop after the current track. This is independent of Start
   Cleanup/Undo - it can be run any time, before or after a cleanup.

> **Pause vs. Stop:** Pause suspends a run in place - Resume continues
> from the exact same track. Stop ends the run early - starting again
> afterward always begins a brand-new run from the beginning, it does
> not continue where Stop left off. Use Pause if you want to preserve
> your place.

## Settings window

Click **⚙ Settings** on the main window. Tabs:

- **General** - choose the app-wide font family, applied to labels,
  controls, statistics, the log and the settings window itself; and
  choose the **output folder** - where `changelog.txt`, the undo log,
  the debug log, and the processed-tracks cache are written. Defaults
  to the app's install folder; click **Choose…** to pick somewhere
  else (e.g. a portable USB install or a Dropbox/OneDrive-synced
  folder), or **Reset to default** to go back. Existing files aren't
  moved when you change it - only future writes go to the new folder.
  `settings.json` itself always stays in the install folder, since
  it's what tells the app where the chosen output folder is.
- **Themes** - ten built-in colour themes (dark and light), plus an
  **Auto** option that follows your Windows light/dark setting.
- The Settings window itself remembers the size you last resized it
  to, so more room for the Genres/Built-in rules tabs persists across
  app restarts. The main window remembers its size *and* position the
  same way.
- **Genres** - the custom genre mapping editor. Add a pattern (e.g.
  `"phonk"`) and the genre it should map to (e.g. `"Hip-Hop/Rap"`),
  then **Add**. Select a row to edit its pattern/target and **Update**
  or **Delete** it, drag a row to a new position to reorder it, or use
  the ↑/↓ buttons instead - custom rules are checked in the order
  shown, before the built-in table, so earlier rows win on overlapping
  patterns. Changes save immediately and take effect on your next
  cleanup run without editing any code. Use the test box below the
  list to check a pattern against a sample genre string before saving
  it.
- **Built-in rules** - a searchable, read-only list of every built-in
  pattern → target genre mapping, in the order it's checked.
- **Changelog** - shows `CHANGELOG.md` from the app folder in-app.
- **About** - app name/version and a one-line summary of what
  LibraryCleaner talks to (iTunes COM locally; online services only
  when a lookup/language check needs them).

## Project layout

```
main.py             Entry point
gui.py               Tkinter UI (main window + Settings dialog)
style.py              Shared bg/fg/etc. styling kwargs for the raw tk
                       widgets ttk has no equivalent for
icons.py               Shared emoji/icon constants used in status and
                       log messages, so a given icon's meaning (and the
                       log pane's colour classification) is defined
                       once instead of copy-pasted at every call site
cleanup_engine.py     Core cleanup pass, run in a background thread
album_merge.py         Split-album detection/merge-plan logic (offline,
                       unit-testable) plus the COM-facing merge engine
                       used by the "Merge Albums…" dialog
genre_rules.py        Pure genre-mapping / junk-name-detection logic
custom_genre_rules.json  Your custom pattern -> genre rules (created on
                       first save from Settings -> Genres; not required
                       to exist)
itunes_com.py          Thin wrapper around the iTunes COM interface
online_lookup.py        Pluggable GenreProvider interface (ITunesProvider,
                       LastFmProvider) plus LibreTranslate language calls
build/                 PyInstaller + Inno Setup packaging scripts
CHANGELOG.md            Version history (also shown in-app)
GenreCleanup_Debug.log  Rotating internal diagnostic log (created on
                       first run; separate from the user-facing
                       changelog.txt summary)
```

`changelog.txt`, `GenreCleanup_UndoLog.csv`, `GenreCleanup_Debug.log`,
and the processed-tracks cache all live in the **output folder**
(Settings → General → Output folder) - the app install folder by
default. `settings.json`, `custom_genre_rules.json`, and the files
listed above it stay in the install folder regardless of that
setting.

## Notes on how deletes work

Deleting a track through iTunes' COM interface re-indexes the
library's track collection, which can invalidate references obtained
from an earlier enumeration. The engine re-enumerates the library (or
scoped playlist) periodically during a run with many deletions -
batched rather than after every single delete - to stay accurate
without paying the cost of a full COM re-walk on every delete. The
COM session used for deletes is also reused across deletes where
possible, falling back to a fresh session automatically if a delete
attempt on the reused session fails. Genre writes use the same
reused-session-with-fallback pattern, so a flaky COM session is
handled the same way for both.

The batch size (how many deletes accumulate before a re-enumeration)
defaults to 20 and can be tuned in Settings → General → Advanced.
Lower it on slow/network drives if deletes seem to skip tracks; raise
it on fast local libraries to reduce re-enumeration overhead on large
cleanups.

## Optional: toast notifications

If the optional `win10toast` package (see `requirements.txt`) isn't
installed, run-finished notifications fall back to a taskbar flash
only. Settings → About shows a note when this is the case, with the
install command needed to enable native Windows toasts.

## Project layout note

`gui.py` currently holds the whole UI layer (app shell, `ViewState`,
`Tooltip`, `SmoothProgressbar`, `GenreCleanupApp`, `GenreRuleEditor`,
`ScopePickerDialog`, `RunReviewDialog`, `MergeAlbumsDialog`,
`BuiltinRuleBrowser`, `SettingsDialog`) in one file. Splitting it into `widgets.py` plus a
`dialogs/` package (`scope_picker.py`, `run_review.py`,
`settings.py`) would improve maintainability and is a reasonable
follow-up, but hasn't been done yet since it's a structural change
best done deliberately/tested on its own rather than bundled with
unrelated fixes.
