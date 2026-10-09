# Changelog

All notable changes to LibraryCleaner are listed here.

Version 1.0 is the first official release. From here, version numbers
go up in steps of 0.5 (1.5, 2.0, 2.5, ...) for subsequent releases.
Entries below are grouped by type, each with an emoji: 🐛 Fixed,
✨ Added, 🔧 Changed, ⚡ Improved.

## v3.0

### 🐛 Fixed
- **Merge Albums false positives on same-titled albums by different
  artists** - a small (1-4 track) bucket sharing an album name with a
  larger main group was being folded in as a "stray" purely by track
  count, even when its actual track Artist was a completely different,
  unrelated act (e.g. Slow Pulp tracks titled "Big Day" being offered
  as strays of Chance The Rapper's "The Big Day"). Detection now also
  checks the candidate group's Artist field against the main group's
  Artist/AlbumArtist before treating it as a split remainder - a
  blank artist, a matching artist, or a "feat."-style credit still
  qualifies, but an unrelated artist no longer does.

### ✨ Added
- **Optional online confirmation for Merge Albums** - a new "Confirm
  matches online" checkbox (off by default) in the Merge Albums
  dialog runs one extra check per candidate group after the offline
  scan: it looks up the main and stray group's (artist, album) via
  the iTunes Search API and drops the group if both sides confidently
  resolve to different Apple Music albums by different artists. This
  catches coincidental title matches the offline heuristic's own
  artist check might still miss (e.g. ambiguous or blank-artist
  cases); a failed, empty, or inconclusive lookup never removes a
  group, so leaving the checkbox off (or being offline) behaves
  exactly as before. No new dependency - reuses the `requests`
  library already used for genre lookups.
- **Cancel button in Merge Albums** - while a merge is applying, a
  Cancel button now sits next to Merge selected (mirrors the main
  window's Stop button). Clicking it stops the merge after the track
  currently being written finishes; tracks already merged stay
  merged, matching the existing `AlbumMergeEngine.stop()` behavior
  that was previously only reachable by closing the whole dialog.

### ⚡ Improved
- Merge Albums' library scan now scales its status-update frequency
  to library size instead of always updating every 100 tracks - large
  libraries (5,000+ tracks, and especially 30,000+) spend less time
  marshalling status-label updates onto the UI thread during the scan,
  with no change to what's scanned or found.
- Album-name/artist normalization (used to detect split albums) now
  compiles its matching patterns once at startup instead of on every
  call - on a 30,000+ track library this function runs 60,000+ times
  per scan, so the fixed per-call overhead is removed. Matching
  behavior is unchanged.

## v2.5

### ✨ Added
- **Merge Albums** - a new "Merge Albums…" button on the main window
  scans your library for albums iTunes has split into two entries -
  the common case being an 11/12-track album plus one stray track
  left with a blank or mismatched Album Artist (or a slightly
  different Album title, e.g. a trailing "(Deluxe)") that keeps it
  from being recognized as part of the same album. Detected groups
  are shown for review - each with a plain-language before/after
  preview of exactly which fields (Album, Album Artist, Track/Disc
  Number, Track/Disc Count, Year, Genre) will change on the stray
  track(s) - and you can untick any group before merging. Only
  clearly-split cases are flagged: a small (1-4 track) stray group
  sharing an album name with a larger (3+ track) main group. Two
  same-titled albums that are both reasonably large (e.g. two
  different "Greatest Hits") are left alone rather than guessed at.
  Applying a merge writes only the fields that actually differ, the
  same reused-session/reconnect-on-failure COM pattern already used
  for genre writes and deletes.

### ⚡ Improved
- **New app/taskbar icon** - replaced the old 16×16-only icon (which
  looked blurry when Windows scaled it up for the taskbar, and had
  square corners) with a crisp, rounded-square icon rendered at nine
  sizes (16 up to 256px) from a single high-resolution master, so it
  looks sharp at every size Windows actually uses it at.

## v2.0

### 🔧 Changed
- Version bump only - no functional changes from v1.6.

## v1.6

### ✨ Added
- **Auto theme** - Settings → Themes now has an "Auto (match Windows)"
  option alongside the 10 fixed themes. It follows your Windows
  light/dark setting (Settings → Personalization → Colors) instead of
  a fixed choice, switching between the existing Light and Midnight
  themes to match. Checked fresh each time the theme is applied (app
  start, and reopening Settings), so changing the Windows setting and
  restarting - or reopening Settings - picks it up. If the setting
  can't be read (non-Windows, or an unreadable registry key), it falls
  back to Midnight. The 10 fixed themes are unchanged and still work
  exactly as before.

### ⚡ Improved
- **Simpler wording throughout the app** - several Settings labels and
  messages were trimmed to say the same thing in fewer words (e.g.
  the font, output folder, delete-batch-size, and built-in-rules
  descriptions in Settings, and the toast-notification hint on the
  About tab). No functional change - same options, same behavior.

## v1.5

### ✨ Added
- **Pluggable online-lookup providers** - `online_lookup.py` now
  exposes an abstract `GenreProvider` interface (`lookup(session,
  artist, title) -> str`), with `ITunesProvider` and `LastFmProvider`
  as the built-in implementations. `OnlineLookup` accepts an optional
  `providers=` list to override the default iTunes→Last.fm (or
  Last.fm→iTunes, if "prefer Last.fm" is set) chain. Adding a new
  source no longer means editing `OnlineLookup` itself - subclass
  `GenreProvider` and pass it in. No behavior change for existing
  installs: the default chain, retry/backoff schedules, and caching
  are unchanged.
- **Output folder picker** - Settings → General → "Output folder"
  lets you redirect where `changelog.txt`, the undo log
  (`GenreCleanup_UndoLog.csv`), the debug log
  (`GenreCleanup_Debug.log`), and the processed-tracks cache are
  written, instead of always using the app's install directory.
  Useful for portable installs (e.g. running from a USB drive) or
  keeping those files in a synced folder (Dropbox/OneDrive). Existing
  files aren't moved when you change it. `settings.json` itself stays
  in the install directory, since it's what tells the app where the
  chosen output folder is.

### 🐛 Fixed
- **Closing the window mid-run could abandon it instead of stopping it
  cleanly** - the in-app "Close" button called `root.destroy()`
  directly, bypassing the same `on_close` handling the window's own
  [X] button used (so it skipped saving your presets/window position,
  and gave a run in progress no chance to stop cleanly). Neither Close
  path checked whether a run was still active: destroying the window
  out from under the worker thread meant its progress/status/finished
  callbacks could still fire afterward against an already-destroyed
  window, and any in-progress iTunes work, undo-log, and cache writes
  were abandoned mid-flight rather than stopped. Both Close paths now
  go through `on_close`, which asks for confirmation and stops the run
  (same as clicking Stop) before closing if one is active; a background
  callback that still lands after the window is gone is now a clean
  no-op instead of an unhandled error.
- **Repeated stopped runs leaked tooltip bindings on Start** - the
  tooltip added to the Start button each time a run was stopped
  (explaining that "Start New Run" begins fresh) was recreated from
  scratch on every stop instead of reusing the existing one, silently
  stacking another set of hover bindings underneath it each time.
  Tooltip is now idempotent per widget - re-tooltipping the same
  widget updates its text in place instead of adding a duplicate.

### ⚡ Improved
- **Drag-and-drop reordering for custom genre rules** - rows in
  Settings → Genres can now be dragged to a new position directly in
  the list, in addition to the existing ↑/↓ buttons (which are
  unchanged and still work).

### 🔧 Changed
- **Main window remembers its size and position** - the Settings
  dialog already restored its last size on reopen; the main window
  now does the same (size and position), saved on close.

## v1.0 (release)

### ✨ Added
- **Per-phase progress breakdown** - the main progress bar previously
  blended junk-track deletion and genre writing into one percentage.
  A new two-segment bar under it now shows how many tracks were
  handled by each phase this run ("🗑 Deleting junk: N &nbsp;
  🔎 Genres: N"), so a run dominated by one phase (e.g. a library
  with lots of malformed imports) is visible at a glance instead of
  reading as generic slow progress. `CleanupStats` gained a `phase`
  field plus `deleting_phase_count`/`genres_phase_count`, set per
  track in `_process_one_index()`.
- **Bulk genre rule import from CSV** - the Genre Rule Editor's
  "Import CSV…" button loads a `pattern,target` CSV file (with or
  without a header row; column order is read from the header if
  present) and adds every valid row in one go, instead of typing
  rules one at a time. Existing patterns are updated in place rather
  than duplicated; unparseable lines are reported by line number
  without discarding the rest of the file. New `parse_patterns_csv()`
  in `genre_rules.py`.
- **Visual paused/stopped state** - pausing or stopping a run now
  shows a banner above the progress bar ("⏸ Paused — Resume
  continues from exactly this track" / "■ Stopping…") and switches
  the main progress bar to a dimmed style, in addition to the
  existing Pause/Stop button text changes - so the state is visible
  even if the buttons are out of view or not being watched closely.

### ⚡ Improved
- **Inline shadow warning in the Genre Rule Editor** - typing a
  pattern that would never fire because an existing higher-priority
  rule (an earlier custom row, or a built-in) already matches every
  genre string it could ever match now shows a warning right under
  the Pattern/Target fields, before Add/Update is even clicked - not
  only in the separate test box, which needs a sample genre string
  typed in first. New `find_shadowing_rule()` in `genre_rules.py`
  does a structural substring check (no sample string required); the
  test box's `preview_genre_mapping()`-based check is unchanged and
  still checks one concrete genre string against the full pipeline.
- **Investigated batching iTunes COM writes** - looked at whether
  `IITTrack`'s COM interface (genre writes via `track.Genre = ...`,
  deletes via `track.Delete()`) exposes any multi-track/batch
  operation to cut down per-track round-trips on very large
  libraries. It does not: both are single-object calls with no bulk
  equivalent in the interface iTunes exposes. No batching was added
  here since there's nothing at the COM layer to batch against -
  documenting this so it isn't re-investigated from scratch later.
  (The existing delete-batch-size setting already limits how often
  the library is *re-enumerated* after a run of deletes, which is a
  different thing from batching the writes/deletes themselves.)

## v7.0 (pre-release)

### 🐛 Fixed
- **Eager delete-batch reenumeration was silently discarded** -
  `_handle_junk_delete()` re-walks the library via COM once enough
  junk-named tracks have been deleted in a row, to recover from the
  index drift a delete causes. That reenumerated list was being
  thrown away instead of replacing the list the run loop was actually
  iterating over, and the pending-delete counter was reset anyway -
  so on a run with many consecutive junk deletions, the safety
  boundary this exists for stopped taking effect for the rest of the
  run instead of refreshing on schedule. The refreshed list is now
  correctly handed back to the run loop every time.
- **Custom genre rules weren't crash-safe to save** -
  `save_custom_patterns()` wrote `custom_genre_rules.json` directly,
  unlike every other file this app persists (settings, the undo log,
  changelog.txt, the processed-track cache), all of which already
  write to a temp file and atomically replace the real one. A crash
  or power loss while saving a custom rule could have left that file
  truncated or corrupt, silently losing custom rules on next launch.
  It now uses the same atomic write pattern as the rest of the app.
- **Settings' "Reclaim space" and "Clear cache" could freeze the app**
  - both ran their SQLite work (`VACUUM`, `DELETE`) directly on the
  UI thread, unlike every other slow action in the app (Start,
  Undo, refresh playlists), which already run off-thread. On a
  processed-track cache built up over a long time, this could freeze
  the whole window for the duration. Both now run in the background
  with a status indicator on the button, matching the rest of the app.

### 🔧 Changed
- Removed an unused `import unicodedata` in `genre_rules.py` (accent
  stripping has used a plain translation table since it was added;
  no behavior change).

## v6.5 (pre-release)

### ✨ Added
- **Verbose COM error detail in the debug log** - `itunes_com.py`
  gained `describe_exception()`, which pulls the full detail out of
  a `pywintypes.com_error` (HRESULT, the COM-reported source/
  description via `excepinfo`, and the failing argument index when
  present) instead of the plain `str(e)` that was all the debug log
  saw before. Genre-write, delete, and reconnect failures now log
  this detail at DEBUG level in `GenreCleanup_Debug.log`, alongside
  (not replacing) the short reason already shown in the changelog
  and the Failures list. Non-COM exceptions still get a plain
  `repr(e)` fallback, so this adds detail without changing what
  users see or how failures are classified/retried.

### ⚡ Improved
- **Capped Last.fm retry backoff per lookup** - `_lookup_lastfm`'s
  retry backoff (0.4s, then 0.8s) runs as `time.sleep()` inside a
  lookup-executor worker thread (`max_workers=4`), so it's real
  thread time taken from other queued lookups, not just latency on
  one track. A new `LASTFM_RETRY_BACKOFF_CAP` (1.2s) now bounds the
  *total* backoff sleep a single track's lookup can accumulate,
  trimming the final sleep instead of skipping it if the schedule
  would otherwise exceed the cap. Same three attempts, same
  doubling schedule, same retry-on-transient-failure behavior -
  only the worst-case total sleep time per track changes, which
  matters more as the queue behind those 4 slots grows on larger
  libraries.
- **Centralized icon/label constants** - the ~30 emoji used as status/
  log-message prefixes (🎵 🔎 🌐 👀 🔁 ✅ ❌ ⚠ 📁 🗑 ▶ ⏸ etc.) across
  `gui.py` and `cleanup_engine.py` were each hand-copied at every call
  site, including into `_log_tag_for()`'s prefix-matching log-pane
  classifier - three independent places a typo or a near-duplicate
  icon could quietly drift the log pane's colour-coding out of sync
  with the messages it's classifying. They're now named constants in
  a new `icons.py` (matching the existing `style.py` pattern for
  shared UI constants), with `_log_tag_for()` matching against the
  same grouped tuples (`icons.ERROR_ICONS`, `icons.SUCCESS_ICONS`,
  `icons.INFO_ICONS`) the messages are built from - one definition per
  icon's meaning instead of scattered literals, and a smaller surface
  for a future localization pass to change. No visible change - same
  glyphs, same messages, same classification.

## v6.0 (pre-release)

### ⚡ Improved
- **Faster genre-rule matching for large custom rule lists** -
  `map_genre()`/`genre_lookup_key()` in `genre_rules.py` previously
  re-scanned the full built-in + custom pattern list with a plain
  substring check per pattern on every track (fine at the built-in
  table's size, but scaling linearly if you accumulate hundreds of
  custom rules). They now match against a small Aho-Corasick automaton
  built once from the same pattern list (rebuilt only when a custom
  rule is actually saved), finding the same first-match-wins result in
  a single pass over the genre string instead of one pass per pattern.
  No behavior change - built-in rules, custom-rule priority, and the
  Genre Rule Editor's test box are unaffected.
- **One quick retry on iTunes Search lookups** - blank-genre online
  lookups already retried transient Last.fm failures; the iTunes
  Search call (the default first/primary source) now gets a single
  quick retry of its own on a timeout, connection error, or 5xx/429
  response before falling back to Last.fm, raising the odds a brief
  network blip doesn't cost a track its primary lookup source. Non-
  transient errors (e.g. a bad request) still fail immediately with no
  retry, same as before.
- **Theme styling is now data-driven** - `_apply_theme()`'s ~40 lines
  of repeated `style.configure()`/`style.map()` calls are now a single
  small loop over a style spec (`style.ttk_style_spec()`) listing each
  ttk style's colours/fonts once. Same styles, same values, same call
  order - just less room for a future style or theme change to
  accidentally miss a widget.

### 🐛 Fixed
- **Non-atomic changelog/undo-log writes** - `_write_changelog` and
  `_flush_undo_log` now write to a temp file in the app folder and
  atomically replace `changelog.txt` / `GenreCleanup_UndoLog.csv`
  (`os.replace`), the same crash-safe pattern already used for
  `settings.json` (v5.6) and the processed-track cache (v3.5), so a
  crash or power loss mid-write can no longer leave either file
  half-written.

## v5.9 (pre-release)

### 🐛 Fixed
- **Silent re-enumeration fallback** - if `_reenumerate_from` (the
  periodic re-walk of the library after a batch of deletes) fails,
  the engine now surfaces a one-time warning via the status log
  instead of falling back to the existing (possibly stale)
  `track_refs` completely silently. The warning is shown at most once
  per run so a run with many delete batches doesn't get spammed.

## v5.8 (pre-release)

### ✨ Added
- **Confirmation before deleting a custom genre rule** - Settings →
  Genres → Delete now asks "Delete the custom rule ... ?" before
  removing it, matching the careful confirmation UX used elsewhere in
  the app (e.g. the live-run warning) instead of deleting immediately
  with no undo.

## v5.7 (pre-release)

### ✨ Added
- **Cache maintenance in Settings** - Settings → General now has
  "🧹 Reclaim space" (VACUUMs the processed-track cache database to
  shrink the file, keeping all entries) and "🗑 Clear cache" (removes
  every cached entry, including stale rows left behind for tracks
  later deleted from iTunes, then VACUUMs). Neither runs automatically
  - the cache has no size cap or periodic maintenance on its own, so
  on a library used for years this is the way to reclaim space or
  drop stale entries without deleting `GenreCleanup_Processed.db` by
  hand. Clear cache asks for confirmation first since it makes the
  next run re-check every track.

## v5.6 (pre-release)

### 🐛 Fixed
- **Non-atomic settings.json writes** - `save_preferences()` now
  writes to a temp file in the same folder and atomically replaces
  `settings.json` (`os.replace`) instead of writing the file in
  place, so a crash or power loss mid-write can no longer leave a
  truncated/corrupt `settings.json` behind.

## v5.5 (pre-release)

### ✨ Added
- **Configurable delete-batch size** - the number of junk-named tracks
  deleted before the engine re-checks iTunes' track order (previously
  a fixed `DELETE_BATCH_SIZE = 20` constant) is now an advanced
  Settings → General option. Lower it on slow/network drives if
  deletes seem to skip tracks; raise it on fast local libraries to
  cut down on re-enumeration overhead during large cleanups. Defaults
  to the previous value of 20 and is validated on load, so existing
  `settings.json` files keep working unchanged.
- **Toast-notification availability hint** - Settings → About now
  shows a note when the optional `win10toast` package isn't installed,
  explaining that Windows toast notifications are unavailable and how
  to enable them (`pip install win10toast`), instead of the feature
  silently no-op'ing with no indication why. The taskbar-flash
  notification is unaffected either way.

## v5.0 (pre-release)

### 🔧 Changed
- **Genre writes now use the same reused-session-with-fallback pattern
  as deletes** - `do_genre_write_with_fallback()` in `itunes_com.py`
  reuses the run's existing iTunes COM session first and only
  reconnects (re-resolving the track by persistent ID) if a write
  attempt on it fails, matching how deletes already behaved. Retrying
  failed genre writes from the Failures dialog goes through the same
  path.
- **Shared `run_in_background()` helper** - `on_refresh_playlists`,
  `on_undo`, and the Failures dialog's Retry action now go through one
  small `thread + widget.after(0, ...)` helper in `gui.py` instead of
  each hand-rolling its own copy of that pattern, reducing duplication
  and the chance of a future copy forgetting to marshal back onto the
  Tk thread.

## v4.5 (pre-release)

### 🐛 Fixed
- **Pause vs. Stop confusion** - Pause and Stop now have tooltips
  explaining the difference (Pause resumes from the exact same track;
  Stop ends the run and starting again begins fresh). The button
  shown after a stopped run is now labeled "▶ Start New Run" instead
  of "▶ Resume" so it no longer implies it will continue where you
  left off, with a tooltip reiterating that Pause is what preserves
  progress. Stopping also logs a one-line reminder of the difference.
- **Fragile placeholder-text credential fields** - the Last.fm
  username/API key fields no longer use hand-rolled "placeholder text
  living inside the real input" logic. Each field now has a small,
  always-visible "(optional)" hint label above it instead, which is
  simpler, cannot be accidentally saved/submitted as real input, and
  is readable by screen readers.

### ✨ Added
- **Color-coded log lines** - the scrolling log pane now colors each
  line by outcome (success/warning/error/info) in addition to its
  existing emoji prefix, using colours drawn from the active theme so
  contrast stays correct in every theme, dark or light.
- **Resizable, remembered Settings window** - the Settings window now
  opens larger by default (640×480, up from 520×400) so the Genres and
  Built-in rules tabs have more room, and remembers whatever size you
  last resized it to across app restarts.

### ⚡ Improved
- **Smoother ETA** - the time-remaining estimate now uses an
  exponential moving average of recent per-track pace instead of a
  single elapsed-time/track-count ratio, so it no longer swings
  wildly in the first few tracks of a run.
- **Less repetitive live-run warning** - the confirmation dialog shown
  before a live (non-dry-run) run now has a "Don't ask again this
  session" checkbox. Checking it skips the dialog for the rest of the
  current app session; it always reappears on the next launch.
- **Scope picker auto-refreshes** - opening "Choose…" now refreshes
  the playlist list from iTunes automatically (showing a brief
  "Refreshing playlists…" indicator), instead of requiring a separate
  manual ⟳ Refresh click first to see playlists created, renamed, or
  deleted since the app opened.
- **Structured logging** - internal status messages are now also
  routed through Python's standard `logging` module (in addition to
  the existing on-screen status/log pane), and written to a rotating
  `GenreCleanup_Debug.log` file in the app folder. This gives a fuller
  diagnostic trail (with real timestamps and severity levels) for
  troubleshooting without changing anything shown in the app itself.

## v4.0 (pre-release)

### ✨ Added
- **Multi-playlist and exclude-mode scope** - the Scope picker is no
  longer limited to a single playlist. A new "Choose…" dialog lets you
  select several playlists at once ("only these"), or flip to "entire
  library except these" to exclude a handful of playlists instead of
  listing everything else. Existing single-playlist scope preferences
  from older versions still load correctly.
- **Pattern test box in the Genre Rule Editor** - Settings → Genres now
  has a small "Test pattern against a genre string" box. Type a sample
  genre and click Test (or press Enter) to see whether the pattern
  you're about to save would match it, and whether a higher-priority
  existing rule would shadow it first - without needing to save the
  rule and re-run a cleanup to find out.
- **Built-in rules browser** - Settings has a new "Built-in rules" tab:
  a searchable, read-only list of every built-in pattern → target
  genre mapping the app ships with, in the order they're checked. Lets
  you answer "why did this get mapped to X" and shows exactly which
  pattern a custom rule needs to out-rank to override a built-in one.
- **Failure drill-down with one-click retry** - the post-run review
  popup's Failures filter now lists each failed track individually
  (artist/title and the specific reason - locked file, iTunes COM
  error, track not found, etc.) instead of only a count. A "Retry
  failed" button re-attempts just those tracks by their persistent ID
  and reports how many succeeded, without needing a full re-run.

### 🔧 Changed
- **COM apartment lifecycle in Undo** - `undo_last_run()`'s COM
  init/uninit is now wrapped in the same `com_apartment()` context
  manager `CleanupEngine._run()` already used, instead of a manual
  `CoUninitialize()` call whose correctness depended on a comment
  pointing back at that other call site. No behavior change; this
  just makes the pairing self-enforcing instead of comment-enforced.

## v3.6 (pre-release)

### ✨ Added
- **Post-run review popup** - when a run finishes (and wasn't stopped
  early), a "Run review" window now opens automatically showing every
  genre change and deletion from that run, filterable by All / Genre
  changes / Deletions / Failures, plus a one-line summary. No more
  opening `changelog.txt` separately to see what happened.
- **Confirmation dialog before a live run** - starting a run with Dry
  run turned off now shows a warning dialog explaining that genre tags
  may be rewritten and junk tracks permanently deleted (deletions can't
  be undone), before anything actually runs. Dry runs are unaffected.
- **Finish notification when the window isn't focused** - if
  LibraryCleaner isn't the focused window when a run finishes, it now
  flashes the taskbar icon (Windows) and rings the system bell. If the
  optional `win10toast` package is installed, a native Windows toast is
  also shown; if not, this is skipped with no error.

### ⚡ Improved
- **Last.fm lookups now retry transient failures** - `online_lookup.py`
  previously gave up on a single failed/timed-out Last.fm request. It
  now retries up to twice more with a short backoff (0.4s, 0.8s) for
  timeouts, connection errors, and 5xx/429 responses, while still
  failing fast (no retry) on definitive non-transient errors. The
  iTunes Search lookup and its existing Last.fm fallback are unchanged.
- **Option presets are saved more reliably** - Last.fm username/API key
  and all toggle states were already restored on launch, but only saved
  when you clicked Start. They're now also saved when the window is
  closed, so changing settings and quitting without running no longer
  loses them.
- **Last.fm API key field is now password-masked** - the key entry
  shows `•` characters once you've typed a real key, instead of plain
  text. The placeholder text itself ("Last.fm API key") is still shown
  unmasked, since it isn't a secret.

## v2.0 (pre-release)

### 🐛 Fixed
- **Entry field placeholders broke if you typed the placeholder text
  itself** - the Last.fm username/API key fields used to decide
  "is this the placeholder?" by comparing your typed text against the
  placeholder string, so typing the literal words "Last.fm username"
  as your real username got silently thrown away as blank. Placeholder
  state is now tracked with its own flag instead, so it can never be
  confused with anything you type.

### ✨ Added
- **Pause, not just Stop** - a new Pause button lets you suspend a run
  in place and pick it back up exactly where it left off (same track
  index, same in-memory undo log and processed cache), instead of
  Stop's "you can only start a fresh run from here" behavior.

### 🔧 Changed
- Rounded corners across the UI - stat cards, the log pane, the
  progress bar track, buttons, and the entry/dropdown fields.

## v1.5

### 🐛 Fixed
- **ETA wasn't updating** - the ETA stat was only ever set to
  `--:--` at the start and `Complete` at the end; it never updated
  during a run. It now recalculates from your average pace so far
  every time progress updates.
- **Some real songs were wrongly deleted as "junk"** - tracks whose
  title is itself a run of digits and dashes (e.g. Logic's
  "1-800-273-8255") could accidentally match the ripped-CD junk-name
  pattern. The junk-name check now requires the ripped-CD-style
  spacing real junk names have (e.g. "031 - Song Title-1"), so
  legitimate numeric titles are left alone.
- **App froze for 10-20 seconds after deleting a junk track** - a
  full library re-scan was accidentally being triggered after almost
  every single delete instead of only once per batch, undoing the
  batching optimization from v2.1. Deletes now only trigger a re-scan
  at the intended batch size.

### ✨ Added
- **Scrollable log pane** - a live, scrolling, timestamped log now
  sits below the status line so you can see everything that's
  happened during a run, not just the current line.
- Simpler wording and emojis throughout the app, to make status
  and settings easier to read at a glance.

### 🔧 Changed
- Renamed the app to **LibraryCleaner**.
- Versioning scheme: this is pre-release 1.0. Future pre-release
  bumps go up in 0.5 increments (1.5, 2.0, 2.5, ...) until the
  official 1.0 release.

## v3.5

### ✨ Added
- **Shared widget-styling module** (`style.py`) - the raw tk widgets
  ttk has no equivalent for (the log pane and changelog `Text`
  widgets, the genre-editor `Listbox`, tooltip popups, and the main/
  Settings windows) used to repeat the same `bg=`, `fg=`,
  `insertbackground=`, etc. keyword arguments at every construction
  and theme-refresh call site. Those bundles now live in one place as
  small factory functions (`surface_window_kwargs`, `text_widget_kwargs`,
  `listbox_kwargs`, `tooltip_label_kwargs`), keyed off the same theme
  dict the rest of the app already uses - a theme's colours for a
  given widget kind now only need to be listed once.

### ⚡ Improved
- **Processed-track cache moved to SQLite** - the "already fixed"
  cache (`GenreCleanup_Processed.csv`) was a plain-text file of
  `pid|genre` lines, rewritten wholesale on every run. A crash or two
  runs started at once could leave it half-written and silently
  truncate the cache, and on very large libraries rewriting the whole
  file on every save doesn't scale well. It's now `GenreCleanup_Processed.db`,
  a small SQLite database (Python's built-in `sqlite3` - no new
  dependency) with atomic commits and row-at-a-time updates. Existing
  `.csv` caches are migrated automatically and transparently the first
  time a run needs the cache after updating - nothing to do manually,
  and force-rescan behavior is unaffected.
- **`_run_inner` split into focused methods** - the per-run driver
  method mixed iTunes-connect/scope-resolution/enumeration setup with
  the main per-track loop in one long, deeply nested block. Setup is
  now `_prepare_run()` (returns `None` and reports status/finishes on
  failure) and the per-index loop body is `_process_one_index()`, so
  `_run_inner` itself is now just the loop-control skeleton.
- **Disk-write failures during wrap-up are no longer silently
  swallowed** - `_flush_undo_log`, `_flush_processed_log`, and
  `_write_changelog` used to catch and discard *any* exception,
  including genuine bugs, and give no indication that the undo log,
  processed cache, or changelog.txt failed to save. They now catch the
  I/O-specific `OSError`, log it, and surface a status message (via
  the existing `on_status` callback) telling you what didn't save and
  why, instead of leaving you to discover a missing file later.

### 🔧 Changed
- `processed_id_cache` reads/writes now go through `ProcessedCache`,
  which guards its in-memory key set with its own lock. All access
  today is still from the worker thread only, but this means a future
  feature that reads the cache from the GUI thread mid-run (e.g. a
  live "already processed" counter) won't race with the worker
  thread's updates.

## v3.0

### 🐛 Fixed
- **Settings → Changelog tab created an unused, invisible duplicate
  text widget** on every open (leftover from the widget being rebuilt
  inside a scrollable wrapper). Harmless to output but wasted a widget
  per open; removed.

### ⚡ Improved
- **Genre-cleanup pass was noticeably slower than it needed to be** -
  every single track re-read and re-parsed `custom_genre_rules.json`
  from disk twice (once to check "is this genre already a target?",
  once to map it), even when you have no custom rules at all. Custom
  rules are now loaded once and cached in memory, and invalidated only
  when you actually save a change in the genre editor. On a ~90-track
  library this cut per-track overhead from disk I/O + JSON parsing
  down to an in-memory list scan.
- Folded the "already a target genre?" check and the pattern-matching
  map into one combined lookup (`genre_lookup_key`) so each track's
  genre is scanned against the pattern list once instead of twice.

### 🔧 Changed
- `ViewState` now owns the mapping from its fields (percent, processed,
  remaining, changed, deleted, eta, elapsed, current track, output
  folder) to the ttk labels that display them. Returning to the main
  menu after a run is "reset the state, then push it to whichever
  widgets are bound" (`ViewState.bind_widgets()` / `.push()`) instead
  of a hand-maintained list of nine `(attribute, widget)` pairs kept
  in sync by hand at each call site.

## v2.5

### 🐛 Fixed
- **Changelog notes were missing from Settings** - the Changelog tab now loads the bundled `CHANGELOG.md` into a readable, scrollable view.

### ✨ Added
- **Custom genre mapping editor** - add, edit, delete and reorder custom pattern → genre rules from Settings → Genres. Custom rules are stored separately from the built-in rules and take priority.
- **Persistent option presets** - Last.fm username/API key, lookup source, cleanup toggles and selected scope are remembered between launches.

### 🔧 Changed
- COM initialization is now owned by a context manager, so every worker-thread COM apartment is initialized and uninitialized as one enforced lifecycle.
- Cleanup processing is split into focused methods for per-track processing, junk deletion and genre updates.
- Main-window reset state is represented by a single `ViewState` object instead of manually maintaining unrelated widget reset values.

### ⚡ Improved
- Foreign-language detection and blank-genre online lookup now run concurrently when both are enabled, reducing network wait time.
- Progress animation interpolates toward the target value without repeatedly measuring widget geometry, avoiding resize/repaint jitter.
- Progress and settings UI continue to use ttk styling, with rounded visual treatment retained for the primary surfaces.

## v2.1

### Improved
- Batched delete re-enumeration: after a junk-track delete, the library
  is no longer re-walked via COM on every single delete. It now
  re-enumerates once per batch of deletes (default batch size 20, plus
  once more before any genre work resumes), which cuts COM round-trips
  dramatically on libraries with many junk-named tracks while producing
  identical results to the old per-delete behavior.
- `itunes_com.do_track_delete` now reuses the existing iTunes COM
  session for deletes instead of opening a brand-new session for every
  delete. It still falls back to a fresh session automatically if the
  reused one fails, matching the previous reconnect-on-failure safety
  net.
- Main window is now resizable (with a sensible minimum size), instead
  of a fixed 520x716, so it's usable on high-DPI displays and smaller
  screens.

### Added
- Library scope picker: choose "Entire library" or a specific iTunes
  playlist to scope a run to, instead of always processing the whole
  library. A refresh button re-reads the current playlist list from
  iTunes.
- Settings window with tabs (alphabetical order): Accessibility,
  Changelog, Diagnostics, General, Themes.
  - **General**: app name/version and a summary of where the main
    run options live.
  - **Accessibility**: notes on contrast, keyboard navigation, and
    window resizing.
  - **Diagnostics**: pywin32/COM availability, app folder path, and
    where run logs are written.
  - **Changelog**: this file, shown in-app.
  - **Themes**: current theme info (dark, built-in only for now).
- Changelog output (`changelog.txt`) now records which scope
  (entire library or a named playlist) a run was scoped to.

## v2.0

- Initial Python/Tkinter port of the original GenreCleanup.hta:
  genre-mapping cleanup engine, junk-track-name deletion, online
  genre lookup (iTunes Search API + Last.fm), foreign-title
  detection, undo log, and processed-track cache.
