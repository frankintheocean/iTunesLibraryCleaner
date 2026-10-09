# iTunes Library Consolidator (v2.2)

A Windows desktop app that finds duplicate tracks across your iTunes/Apple
Music library (same song imported more than once) and consolidates them
into a single canonical entry — while every playlist that referenced any
copy keeps working, and ratings/play counts/dates are merged rather than
lost.

**iTunes/Apple Music remains the source of truth.** This tool always reads
and writes the standard XML library export first — every consolidation
produces a correct, complete output file regardless of anything else. On
Windows, if classic iTunes is currently open and responding, it
additionally mirrors the removed duplicate tracks directly into that
running app via COM automation (see "Live iTunes sync" below) — purely as
a convenience on top of the file, never a replacement for it. If iTunes
isn't running, isn't responsive, or this is a platform where the live
sync doesn't apply, you re-import/write back the exported file exactly as
before.

## What's new in v2.2

- **New "Select all (incl. review)" button in the Duplicates tab.**
  Previously, "Select all" only checked exact and high-confidence
  matches by design — low-confidence "needs review" groups always
  had to be checked one at a time, which meant scrolling through and
  clicking hundreds of rows by hand on libraries with a lot of
  fuzzy-matched review groups. This new button checks every currently
  visible group regardless of confidence tier. The original "Select
  all (exact + high confidence)" checkbox keeps its existing,
  safer-by-default behavior unchanged — this is an additional, opt-in
  control alongside it, not a change to what it already does.
- **Verified large-library (30,000+ song) performance.** Library.xml
  loading already uses a single-pass streaming parser and the
  duplicate-detection/table-population paths already use bucketed,
  time-boxed, and batched processing from earlier releases (see
  in-app changelog v1.x/v2.x entries). This release adds test
  coverage exercising those paths at large scale to confirm behavior
  holds up rather than changing the underlying approach.

## What's new in v2.1

- **Auto-selects overlapping tracks when a complete album copy replaces
  an incomplete one.** In the Duplicates tab, if a duplicate song's track
  belongs to an album copy that looks incomplete — and a complete copy of
  that same album exists elsewhere in your library — its checkbox is now
  pre-checked for you, with a 💿 note next to the match reason.
  Completeness is judged from the album's "Track Count" tag when it's
  present on enough of a copy's tracks, or by comparing how many of that
  album's tracks each copy actually has when the tag isn't available.
  This only pre-checks rows you could already check yourself — nothing is
  removed until you review the list and click Apply, and low-confidence
  "possible duplicate" rows are still never auto-checked by this, same as
  everywhere else in the app.

## What's new in v2.0

- **Fixed duplicates going undetected when the same song's copies have
  different lengths.** Two tracks with the exact same artist and title —
  for example a radio edit next to an album version, or a copy
  re-imported with a slightly different `Total Time` tag — used to be
  silently missed by *both* the exact-match and the near-miss ("fuzzy")
  passes whenever their lengths differed by more than a few seconds, so
  a library could show **zero duplicates found** even with several
  visibly duplicated songs (same artist, same title) still present. These
  are now always surfaced for review, labeled **"Same title — different
  length,"** the same way a near-miss fuzzy match already is — shown in
  the duplicates list, but never auto-selected for cleanup without you
  looking at them first, since a large length difference can also mean a
  genuinely different edit.
- **Fixed duplicates going undetected when the title is only symbols.**
  A song title made up entirely of symbols — like Ty Dolla $ign's
  **"$"** — was internally stripped down to nothing during title
  matching and treated as if the track had no title at all, so two real
  duplicate copies of a symbol-titled song were never matched by either
  the exact or the near-miss pass, and could still show up as duplicates
  in iTunes after a "cleaned" run. These now match correctly, the same
  as any other same-artist, same-title duplicate.
- **Added 8 new theme palettes.** Settings → General now has a **Theme**
  option, separate from Appearance (Match Windows/Light/Dark) and Accent
  color: **Paper, Slate, Sand, Mint** (light-family) and **Midnight,
  Charcoal, Espresso, Forest** (dark-family). Each gives the app a
  distinct background/surface/text treatment — not just a different
  accent highlight — and can be paired with any of the 10 existing accent
  colors. Previewed live before confirming, same as the existing
  appearance/accent pickers. Defaults to "No override," which keeps the
  original Light/Dark look exactly as before.
- **Fixed the Paper, Slate, Sand, and Mint theme palettes not applying.**
  The app-wide stylesheet and the main window's own stylesheet could get
  out of sync, so choosing one of these four palettes could leave the
  plain Light look showing through instead. All 8 theme palettes (see
  above) now apply correctly and stay in sync everywhere, including
  other top-level windows like "What's new."
- **Fixed no way to close an expanded duplicate-group detail panel.**
  Previously the only way to collapse it was clicking the same table row
  again. The detail panel now has its own **✕ Close** button, and
  pressing **Escape** closes it too.
- **More keyboard shortcuts.** **Ctrl+F** jumps to the artist/song search
  box, and **Escape** closes an expanded duplicate-group detail panel —
  alongside the existing Ctrl+A, Ctrl+Z, and Ctrl+Enter shortcuts (see
  "Keyboard shortcuts" below).

## What's new in v1.7

- **Fixed the expanded duplicate-row taking over the window.** Expanding
  a duplicate group with many copies could previously grow the detail
  panel tall enough to push the window's titlebar/close button out of
  reach. The duplicates table and the expanded row are now separated by
  a draggable splitter handle — click and hold the thin bar at the top
  of the expanded row and drag to make it bigger or smaller — and a
  newly-expanded row now starts at a sensible height instead of growing
  to fit however many copies are in the group.
- **Volume controls on audio previews.** Each duplicate copy's inline
  preview player (in the expanded row) now has a volume slider and mute
  button, and the play button/seek bar/time label have been made more
  compact so the whole control takes up less room.
- **Backups are pruned automatically.** "Rebuild library now…" used to
  keep every timestamped `iTunes Library.itl.bak_…`/`.xml.bak_…` file it
  ever made. It now keeps only the most recent one, deleting older
  backups automatically to save disk space. The timestamp in backup
  filenames also changed format, from year-first
  (`iTunes Library.itl.bak_20260816_143005`) to day/month/year with
  24-hour time (`iTunes Library.itl.bak_16-08-2026_143005`).

## What's new in v1.6

- **Fixed clicking not working almost everywhere** — buttons, table
  column headers, and the songs list stopped responding, and only the
  top toolbar (Restore backup, Save restore point, etc.) still worked.
  This was the same invisible notification overlay covering the window
  from the last update; that fix has been re-verified and hardened so
  it can't come back.
- **Simpler "What's new" screen.** Wording is shorter and easier to
  read, and each version's changes are now grouped under an emoji (✨
  new, 🩹 fixed, 🔄 changed) so you can scan what happened at a glance.

## What's new in v1.5

- **Added a "What changed since last export" summary.** Re-opening a
  Library.xml that's newer than the last time this app saw that same
  file now shows what changed since then: tracks added, tracks removed,
  tracks with changed metadata (name/artist/album/rating/play count),
  and any playlist count change, with a few concrete examples. This only
  appears once there's a previous export on record for that exact file
  to compare against — opening a library for the first time shows
  nothing extra. A background "check for new duplicates weekly" re-scan
  (see Settings → General) still shows its existing toast summary
  instead, so it isn't interrupted by a dialog for something that ran
  unprompted.
- **Fixed every button in the window being completely unpressable**
  ("Open Library.xml…", "Restore backup…", "Select all exact", "Select
  all high-confidence", "Exclude reviewed-out permanently", "Clean up
  duplicates…") while dragging a Library.xml file onto the window to
  open it still worked. The always-on-top toast-notification overlay
  was supposed to let clicks pass through it to whatever's underneath
  except its own notification banners, but was misconfigured to do the
  opposite, silently swallowing every click in the window. Drag-and-drop
  was unaffected because it's handled by the window itself rather than
  routed through that overlay. See the in-app changelog (Help → What's
  new…) for the full technical explanation.
- **Fixed large-library performance:** opening a library with a large
  number of duplicate groups no longer stalls at the "Building
  consolidation plan..." step (92%), no longer appears to freeze right
  at 100% right after, and the duplicates list (including libraries
  with 4000+ duplicates found) now finishes appearing promptly. All
  three had the same root cause: building the consolidation plan was
  re-scanning every playlist's full track list from scratch for every
  duplicate group instead of indexing playlist membership once up
  front, and that slow path ran twice per library open. See the in-app
  changelog (Help → What's new…) for details.
- **Fixed "Clean up duplicates" sometimes staying greyed-out** after
  opening a large library — it only becomes clickable once the
  duplicates list has finished populating, which the slow plan-building
  above was delaying far longer than intended.

## What's new in v1.0

- **First full release.** Every earlier build was a pre-release; this
  README's and the in-app changelog's version numbers for those older
  entries were renumbered to a sequential "v0.1(pre)" through
  "v0.50(pre)" (oldest to newest) to reflect that, in place of their
  original version numbers — what each of those versions actually
  changed is unaffected, only how it's labeled.
- **Added "Find missing files in folder…"** to the Library Health tab,
  next to the existing "Locate missing file…" list: pick one root
  folder and every track currently showing as missing/broken (the
  tracks iTunes/Apple Music itself marks with a "!") is searched for by
  filename anywhere under that folder at once, instead of relinking one
  at a time. This covers the common case of having moved your music (or
  reorganized playlists into a different subfolder) inside the iTunes
  folder — point it at the new root and it finds and offers to relink
  every match in one pass. Matches are shown for review before anything
  is relinked; nothing changes automatically.

## What's new in v0.50(pre)

- **The Windows installer now bundles the Microsoft Visual C++
  Redistributable (x64)** and installs it silently during setup if a
  compatible copy isn't already present. v1.10.2 fixed one cause of
  "Failed to load Python DLL ... LoadLibrary: The specified module could
  not be found" (UPX-compressing the Python DLL); this fixes the other
  common cause of the exact same error message — the redistributable
  genuinely missing from the machine, which python313.dll depends on
  regardless of how the build itself was produced. This only affects
  `dist_config/setup.iss`; anyone running the plain
  `iTunesLibraryConsolidator.exe` without the installer still needs to
  install the redistributable manually (see
  `dist_config/installer_README.md`).

## What's new in v0.49(pre)

- **Fixed the built .exe failing to start with "Failed to load Python
  DLL ... LoadLibrary: The specified module could not be found."** The
  build was UPX-compressing the bundled Python DLL (and a few other
  core runtime/Qt DLLs), which can produce a copy Windows' loader
  refuses to load even though the build itself completes and reports
  success. `dist_config/build.spec` now excludes those specific files
  from UPX compression; everything else in the build is still
  compressed as before, so this doesn't meaningfully change install
  size for anyone who wasn't hitting this.
- **Expanded automated test coverage** for the Library.xml parser:
  malformed/truncated XML (interrupted export, corrupted/hand-edited
  file, an XML entity declaration), non-ASCII track and playlist names
  (CJK, accented Latin, emoji), and nested playlist folders, in a new
  `tests/test_library_xml_edge_cases.py` with matching fixtures under
  `tests/fixtures/`. No app behavior changes here — this is test
  coverage for existing parsing/error-handling code, so a future change
  to that code is now checked against these cases automatically.

## What's new in v0.48(pre)

- **Manual "Merge tracks..." override.** A new toolbar button lets you
  pick any two tracks in the currently loaded library and merge them,
  even if automatic detection never grouped them at all — useful when
  two copies of the same song are tagged too differently (translated
  title, very different artist spelling) for exact or fuzzy matching to
  catch. This is separate from the existing per-group "Keep this one
  instead," which only re-picks which track survives *within* a group
  detection already found; the new button covers pairs detection missed
  entirely. Manually merged pairs show up in the table tagged "Manually
  merged" and can be reviewed, unchecked, or reverted like any other
  group.
- **Scheduled/automatic re-scan.** A new "Check for new duplicates
  automatically" option (Settings → General, off by default) checks
  once per launch whether it's been long enough (default weekly,
  configurable) since your most recently opened library was last
  scanned, and if so, re-scans it in the background and shows a
  notification with what it found — handy if you keep re-importing
  tracks into the same library. Built entirely from the same scan
  history already used for the growth timeline chart; nothing new is
  stored just for this.

## What's new in v0.47(pre)

- **Telemetry-free local crash reporter.** An unhandled error now also
  writes a self-contained crash dump file (`crash_dumps/` under the app's
  data folder) containing the full traceback, app/OS/Python/Qt versions,
  and a short trail of recent in-app actions leading up to it — so a
  problem can be diagnosed from the file alone, without reproducing it
  live. Nothing is ever sent anywhere automatically; this is strictly a
  local file you can choose to attach to a bug report. Browse and view
  saved dumps under **Settings → Diagnostics → Crash dumps**. The
  existing rolling `error.log` (same tab) is unchanged and still records
  every error the same way it always has — the crash dump is a separate,
  richer, per-crash artifact alongside it.
- **Duplicate-count trend comparison.** The always-visible summary bar
  and the Library Health tab's **View growth timeline…** chart now both
  note how the current scan compares to that library's previous
  recorded scan — e.g. "12 fewer duplicates than last scan
  (2026-08-09)." Built entirely from the scan history the growth
  timeline already recorded; no new data is stored for this.
- **Named restore points.** A new **📌 Save restore point…** toolbar
  button saves a backup of the currently loaded library labeled however
  you like (e.g. "before spring cleaning"), independent of the existing
  automatic backups taken on every load and every cleanup. Named points
  appear right alongside automatic ones in **⏪ Restore backup…**,
  marked with 📌 so they're easy to pick out. Uses the exact same
  snapshot storage and restore path as the automatic backups — nothing
  about restoring changes.

## What's new in v0.46(pre)

- **Pluggable duplicate-detection strategies.** A new
  `core/duplicate_strategies.py` module wraps the existing exact and fuzzy
  matching passes as independently constructible, independently testable
  `DuplicateStrategy` objects (same interface shape as the provider plugin
  architecture from v1.8.0), plus a `CompositeDuplicateStrategy` that
  composes an ordered list of them the same way exact-then-fuzzy already
  compose today. Also new: a metadata **fingerprint** strategy that groups
  tracks sharing the same iTunes Persistent ID, or the same file size +
  duration when Persistent ID isn't present — catching duplicates whose
  title/artist tags were edited too heavily for fuzzy matching to still
  recognize, without the cost of an O(n²) similarity pass. This is
  under-the-hood infrastructure: the app's default duplicate scan
  (exact → fuzzy) behaves exactly as before; nothing in
  `duplicate_detector.py` changed, and every existing call site is
  untouched.
- **Centralized design tokens.** The spacing, corner-radius, and font-size
  values used throughout the light/dark stylesheet are now defined once in
  `ui/design_tokens.py` instead of being repeated as literals across both
  themes. Purely a refactor of *where* those values live — the rendered
  stylesheet is pixel-identical to v1.9.0 in both themes and all 10 accent
  colors.

## What's new in v0.45(pre)

- **Backup integrity verification.** Backup snapshots (auto-backup on
  load, and the pre-consolidation backup taken before every clean-up) are
  now checksummed (SHA-256) when saved, and that checksum is verified
  before ⏪ **Restore backup** hands the data back. If a snapshot has been
  corrupted — a partial write, disk bit-rot, a hand-edited cache file — the
  restore now stops immediately with a clear "Backup snapshot corrupted"
  message instead of silently restoring bad data. Snapshots saved by
  earlier versions have no checksum recorded and continue to restore
  exactly as before; this doesn't make any existing backup unrestorable.
- **Spotify import.** A new **🎧 Import Spotify library…** toolbar button
  reads a Spotify data export — either the `.zip` Spotify emails you
  (Settings → Account → Privacy → "Download your data") or the folder
  you've already extracted it into — and reports how many tracks and
  playlists it found, plus how many of those tracks already appear to be
  in your currently loaded library. This is read-only and fully offline:
  no Spotify sign-in, no network access, and nothing about your library or
  the export is changed. It's built on the provider plugin architecture
  introduced in v1.8.0 (`core/providers/`); Apple Music API support
  remains a not-yet-implemented skeleton in that same architecture.

## What's new in v0.44(pre)

- **10 accent color themes.** Settings → General now has an **Accent
  color** picker (Blue, Purple, Pink, Red, Orange, Yellow, Green, Teal,
  Graphite, Indigo) alongside the existing Light/Dark/Match Windows
  appearance mode — any accent can be paired with any mode. The chosen
  accent recolors buttons, tabs, progress bars, links, and other
  accent-tinted text/UI consistently app-wide (including the Library
  Health growth-timeline chart's track-count line), previews live as
  you browse the picker, and is remembered between sessions the same
  way the appearance mode already was. The original blue accent is
  still the default for anyone upgrading, and severity colors (the red/
  amber/blue error, warning, and info accents used in dialogs and
  toasts) are unaffected — those stay tied to what they mean, not to
  your chosen theme.
- **Provider plugin architecture (internal).** Added `core/providers/`,
  a small interface + registry (`LibraryProvider`, `register_provider`,
  `available_providers`) that a future streaming-service integration
  implements, plus skeleton (not-yet-functional) modules for an Apple
  Music API integration and a Spotify data-export integration showing
  how one would plug in. Nothing is connected or user-facing in this
  release — Library.xml remains the only functional data source — this
  only adds the extension point later work will build on.

## What's new in v0.43(pre)

- **Keyboard shortcuts.** Ctrl+O opens a library, Ctrl+Enter (or
  Ctrl+Return) cleans up the currently checked duplicates, Ctrl+A
  selects all exact + high-confidence groups (same as clicking "Select
  all (exact + high confidence)"), and Ctrl+Z undoes the most recent
  library rebuild (same as the toolbar's "Undo last rebuild…").
- **Recent libraries menu.** A new **Recent…** button on the toolbar
  lists recently opened Library.xml files (most recent first, up to
  10) so reopening one is a single click instead of browsing for it
  again. Entries whose file can no longer be found are marked "(not
  found)" rather than hidden.
- **Audio preview playback.** Expanding a duplicate group in the
  detail panel now shows a play/pause and seek control for each copy,
  so you can actually listen to confirm two entries are really the
  same recording before deciding what to keep — useful for
  possible-duplicate matches where the title/artist alone isn't
  conclusive (e.g. a remix or live version). Read-only preview; a copy
  whose file can't be found on disk shows a disabled control instead.
- **Persistent column layout.** The duplicates table's column order
  and widths are now remembered between sessions, the same way window
  size/position already was — drag a column header to reorder it or
  resize a column, and it's still that way next time you open the app.

## What's new in v0.42(pre)

- **Time-boxed, visible fuzzy-scan budget.** The fuzzy "possible
  duplicate" pass now spends a fixed amount of *time* (30s by default)
  rather than a fixed total number of comparisons split evenly across
  every bucketed batch. The old approach meant a library with many small
  buckets got an arbitrarily strict, invisible per-batch allowance —
  recall degraded silently in a way that depended on how titles happened
  to cluster. The status bar now also shows a live "Still scanning for
  possible duplicates... (N% of scan time budget used)" message while
  the pass runs, so a very large or unevenly-organized library gets a
  predictable wait with visible progress instead of a silent reduction
  in thoroughness. See "Performance notes" below for details.
- **FLAC artwork previews.** Embedded cover-art preview (used in the
  duplicate-review UI and "Fix missing artwork…") now also reads FLAC
  files' own METADATA_BLOCK_PICTURE block, in addition to the existing
  MP3/MP4/M4A support. Apple Lossless (ALAC) was already covered, since
  ALAC audio is packaged inside the same MP4/M4A container this app
  already reads — no separate ALAC-specific parsing was needed.

## What's new in v0.41(pre)

- **Standalone-folder build, .exe in the project root.** The Windows
  build now produces a standalone folder
  (`dist\iTunesLibraryConsolidator\`) instead of a single-file .exe, and
  automatically copies `iTunesLibraryConsolidator.exe` (with its
  dependent files) into the project root on a successful build —
  build.bat, build_windows.bat, and install.bat all do this. `build.bat`
  also now brings the freshly launched app's window to the foreground
  on a successful auto-launch, instead of leaving it to open in the
  background.

## What's new in v0.40(pre)

- **Manage backup snapshots from Settings.** A new **Backups** tab
  (Settings → During cleanup) lets you set how many recent backup
  snapshots to keep (default 100, or Unlimited), shows how many are
  currently stored, and has a **Delete old backups now** button. The
  cap is also applied automatically right after every new backup is
  saved (before this version, backups accumulated in the local SQLite
  cache indefinitely with no way to trim them).
- Internal: the confidence-tier labels/badges (Exact match / High
  confidence / Possible duplicate) are now driven from a single
  enum-backed lookup instead of two hand-maintained dicts. No visible
  change.

## What's new in v0.39(pre)

- **Library Health findings are now actionable, not just counts.** Two
  categories on the Library Health tab now list the affected songs with a
  fix button right there:
  - **Missing or broken files** → **Locate missing file…** opens a file
    browser so you can point the app at where that song's audio file
    actually is; the track is relinked in memory and picked up by the
    normal save/write-back flow, same as any other edit.
  - **Missing cover art** → **Fix missing artwork…** looks for another
    local copy of the same song already in your library that has
    embedded cover art, and offers to use that copy's art. This app has
    no internet access and does not fetch artwork online — when no local
    copy with art can be found, it says so plainly instead of pretending
    to search further.
- **"View growth timeline…" on the Library Health tab.** A small chart
  plotting total tracks and duplicate tracks found, one point per time
  this app has scanned your library, so you can see whether duplicates
  are accumulating over time instead of only ever seeing a single
  point-in-time snapshot. Builds up automatically as you use the app —
  no library history before this version is available to backfill.
- **Non-blocking toast notifications.** A few confirmations (e.g. "N
  group(s) will now be skipped permanently") previously only ever
  flashed through the status bar — a single line of text that's also
  where load/clean-up progress messages are shown, so it was easy to
  miss or have overwritten a moment later. These now appear as a small,
  non-blocking notification banner in the corner of the window that
  stays visible for a few seconds (or until you dismiss it) independent
  of whatever else is happening in the status bar. The status bar itself
  is unchanged and still used for live progress during a load or
  clean-up.

## What's new in v0.38(pre)

- **A picture, not just words, for the "Choose Library..." step.** The
  "Library rebuilt" success dialog now shows a small annotated mockup of
  iTunes's own "choose a library" prompt with the "Choose Library..."
  button circled, right alongside the existing text instructions — so
  there's something to look for on screen when iTunes reopens, instead of
  only a paragraph that's easy to skim past mid-relaunch.
- **Pre-flight check before "Rebuild library now…" starts anything.**
  Before iTunes is quit or any existing library file is touched, the app
  now checks free disk space, write permission on the iTunes folder, and
  whether iTunes is currently running. A blocking problem (e.g. not enough
  free space) stops the rebuild before it starts, instead of surfacing
  partway through after files have already been backed up and replaced.

## What's new in v0.37(pre)

- **Auto-detect your iTunes folder on first launch.** Instead of only ever
  asking you to browse for your real iTunes data folder (the one
  containing `iTunes Library.itl`) blind, the app now scans common drive
  letters for a folder that already looks like one and offers it for
  confirmation. You can still say no and browse manually, and you can now
  set or change the folder any time from **Settings → General → iTunes
  folder** — not just from the first-launch prompt or "Rebuild library
  now…".
- **Tooltips explain the `.bak_<timestamp>` backup files.** The "Backups
  kept" list shown after a rebuild now explains, on hover, what each
  listed file is (an automatic safety copy made before that rebuild, and
  when it was made) and that it's safe to leave in place.
- **Error dialogs no longer show raw technical detail.** WinError/errno
  codes, COM error tuples, and Python exception class names used to leak
  straight into popups (e.g. "...`[WinError 5] Access is denied`..."). Those
  dialogs now describe the problem in plain language instead — the "what
  to try" guidance is unchanged, and the full technical detail is still
  written to the app's error log (**Settings → Diagnostics**) exactly as
  before, for troubleshooting or bug reports.

## What's new in v0.36(pre)

- **Added "Undo last rebuild"** — a one-click toolbar button (and also
  offered right after a rebuild finishes) that restores the most recent
  `iTunes Library.itl`/`.xml` backup pair that "Rebuild library now…"
  made automatically, and reopens iTunes with it. No more manually
  hunting for and renaming the timestamped `.bak_<date>` files in your
  iTunes folder yourself.
- **Added "Remove duplicate files from disk…"**, offered once a rebuild
  finishes: permanently deletes the actual audio files for the copies
  that were just removed from your library (never the copy you kept).
  Shows an itemized list and asks for confirmation first, and a full
  success/failure summary afterward — files are only ever deleted after
  you explicitly confirm, and a file that's missing or locked doesn't
  block the rest from being cleaned up.
- **Error/warning/info dialogs are now colour-coded by severity** — a
  red accent for blocking errors, amber for warnings, blue for routine
  notices — so a real problem (like a failed rebuild) is visually
  unmistakable next to a routine confirmation (like "Summary saved"),
  instead of every dialog looking the same weight.

## What's new in v0.35(pre)

- **"Rebuild library now…" shows a real step tracker.** While it quits
  iTunes, backs up your library files, copies in the cleaned XML, and
  relaunches iTunes, the window now shows exactly which of those four
  steps is currently running ("Step 2/4: Backing up…") instead of a
  single spinner with no indication of progress. The rebuild also now
  runs off the main thread, so the window stays responsive while it
  works.
- **Settings is now grouped by workflow stage** instead of a flat
  alphabetical tab list: "Before you scan" (General, Accessibility),
  "During cleanup" (Duplicate Detection, Diagnostics), and "Reference"
  (Changelog). Every individual settings page, tooltip, and saved value
  is unchanged — only how they're grouped and labeled changed, so the
  setting you want is easier to find at the point you'd actually reach
  for it.
- **Removed the standalone .bat rebuild-script generator.** Its own
  "Generate rebuild script…" button was already removed from the UI back
  in v1.3.19 (see below) once "Rebuild library now…" could do the same
  swap in-app; the generator function itself stuck around as unused code
  until now. The in-app rebuild already does the same job more safely —
  verified copy sizes, a confirmed iTunes exit before proceeding, and
  stray-.xml cleanup that the .bat version never had — so maintaining
  two implementations of the same logic only risked them drifting apart.
  Nothing in the app's behavior changes: this only removes code with no
  UI entry point left pointing to it.

## What's new in v0.34(pre)

- **Fixed the app sometimes staying open in Task Manager after closing
  the window.** Clicking the titlebar's X button could, in rare cases,
  leave the process running in the background with no window visible.
  Window shutdown now always finishes closing (and quits the app) even
  if something during cleanup went wrong.
- **Added a persistent "iTunes folder" status strip**, visible on every
  tab, showing exactly which folder is currently set for "Rebuild
  library now…" — no more guessing or reopening the folder picker just
  to check.
- **Large libraries populate the duplicates table faster**, with less UI
  stutter while it fills in.
- **Removed the old, always-failing "live COM import" code path.**
  Classic Windows iTunes has no supported way to script a Library.xml
  import into a running app (see "What's new in v1.6.1" below) — that
  dead code and its explanatory stub have now been deleted outright.
  This does **not** affect the still-working "Live iTunes sync" feature
  described below, which is a separate mechanism that mirrors *removed
  duplicate tracks* into a running iTunes and was never part of this
  dead path.

## What's new in v0.33(pre)

- **Simplified the "Library rebuilt" success message.** It now plainly
  tells you to click "Choose Library...", select the folder, and manually
  import the deduped XML you just cleaned up. There's still no way to
  automate that last click -- classic Windows iTunes has no supported
  method to script a Library.xml import into itself -- but the dialog no
  longer buries that under a technical explanation of why the automatic
  attempt isn't possible.

## What's new in v0.32(pre)

- **Fixed "Could not copy the cleaned XML into the iTunes folder: [WinError
  2]" when the cleaned/deduplicated XML was saved directly inside the
  iTunes folder.** The step that clears out stray `.xml` files before
  relaunch was matching by filename only, so it didn't recognize the
  cleaned XML itself as a file to leave alone if it happened to live in
  that same folder -- it backed it up and removed it moments before the
  copy step tried to read it, which showed up as a "file not found" error
  even though the file had never actually moved. The cleaned XML is now
  always excluded from that cleanup by its real resolved path (not just
  its name), and the copy step re-verifies the source file is still there
  immediately before running, with a specific message if it's genuinely
  gone rather than a generic WinError 2.

## What's new in v0.31(pre)

- **Fixed "Rebuild library now…" occasionally leaving a blank rebuilt
  library.** If copying the cleaned XML into the iTunes folder was
  interrupted partway (antivirus grabbing the file, a sync client, etc.),
  the folder could be left with the old `.itl` already removed but no
  usable `iTunes Library.xml` -- then relaunching iTunes had it "rebuild"
  from nothing instead of your cleaned library. The copy now goes to a
  temp file first, is verified byte-for-byte against the source, and is
  only then atomically renamed into place as `iTunes Library.xml`. If
  anything goes wrong at any point in that sequence, the rebuild stops
  and iTunes is never relaunched -- so **"Choose Library..." after a
  rebuild now reliably produces a fresh `.itl` built from your actual
  cleaned XML, every time**, which is the behavior this button always
  intended.

## What's new in v0.30(pre)

- **Stray .xml files in the iTunes folder are cleared before relaunch.**
  "Rebuild library now…" now also finds any other `*.xml` files sitting in
  your iTunes folder (besides `iTunes Library.xml` itself) and backs them
  up out of the way before copying in the cleaned XML and relaunching —
  same treatment the old `iTunes Library.itl` already got. Leftover XML
  files in that folder could otherwise confuse iTunes's own library-choice
  scan when it reopens. Nothing is ever deleted outright — every stray
  file is copied to a timestamped `.bak_<timestamp>` backup first, right
  alongside the `.itl`/`.xml` backups already listed on the results
  dialog.
- **Startup now asks where your real iTunes folder is.** The first time
  you run the app, it now offers to let you locate your actual iTunes
  data folder (the one with `iTunes Library.itl` in it) right away,
  instead of only asking the first time you click "Rebuild library
  now…" — useful since that folder isn't always the default
  `Music\iTunes` path (e.g. an external drive, or a OneDrive-redirected
  Music folder). This is a one-time prompt: once a folder's been
  confirmed (on this run or a previous one), it's remembered and reused
  silently, and you won't be asked again on future launches. Cancelling
  it doesn't block anything else in the app.

## What's new in v0.29(pre)

- **Fixed "Rebuild library now…" always showing "iTunes rejected the XML
  import" first.** The one-click rebuild tried a live COM import into
  iTunes before falling back to the (working) backup/swap/relaunch
  method — but that live-import step called a COM method classic
  Windows iTunes doesn't actually have, so it failed 100% of the time,
  on every machine, and also launched iTunes needlessly if it wasn't
  already open, only to quit it again moments later. That always-failing
  shortcut attempt has been removed; rebuilding now goes straight to the
  backup/swap/relaunch method, unchanged and working as before, without
  the confusing rejection message or the extra launch/quit cycle.

## What's new in v0.28(pre)

- **build.bat cleans up old installs too.** Building now also looks for any
  previously *installed* copy of the app registered on this machine (via
  install.bat, possibly in a different project folder), closes it if it's
  running, and removes its exe/shortcuts/registry entry before the new
  build starts — on top of the existing step that already clears this
  project's own previous `dist`/`build` output.
- **"Jump to version..." dropdown.** Both Help → What's new… and Settings →
  Changelog now have a dropdown above the collapsible per-version sections
  to jump straight to a specific release's notes.
- **More batch selection options.** Alongside "Select all (exact + high
  confidence)", you can now click "Select all exact" or "Select all
  high-confidence" to select precisely one tier, or "Exclude reviewed-out
  permanently" to remember every group you've marked as not duplicates so
  it's skipped automatically on every future library you open.
- **Internal cleanup.** The main window's widget-building code was split
  into smaller, reusable widget classes. No visible or behavioral change.

## What's new in v0.25(pre)

- **Removed the redundant rebuild-script button.** The "Duplicates deleted"
  dialog used to offer both "Rebuild library now…" (does the file swap and
  iTunes relaunch for you automatically) and "Generate rebuild script…" (a
  separate .bat you'd have to run yourself). Since the first button already
  does everything the second one's script would do, the second button is
  gone — one less redundant choice.
- **Simplified the reopen-steps text.** On Windows, the "next steps" text
  shown after deleting duplicates no longer walks you through manually
  quitting/replacing/reopening iTunes when "Rebuild library now…" on that
  same dialog already automates it — it just points you at that button
  instead. The full manual steps are still shown wherever they're actually
  needed (non-Windows, or when the running iTunes was already updated live).
- **What's new inside Settings.** Settings → Changelog now shows the same
  collapsible, per-version sections (grouped under Added/Fixed/Changed) as
  Help → What's new…, instead of a flat wall of text — both are built from
  the same shared widget, so they can never show different notes.
- **Alphabetized Settings tabs.** Left to right: Accessibility, Changelog,
  Diagnostics, Duplicate Detection, General.
- **A few more emoji.** Small leading icons on several buttons, tabs, and
  toolbar actions app-wide (Open, Restore backup, Settings, What's new,
  Delete duplicates, Duplicates/Library Health tabs, etc.) as a quicker
  visual cue — cosmetic only, nothing about how any of them behave changed.

## What's new in v0.24(pre)

- **Reused artwork-loading thread pool.** Expanding a duplicate group used
  to spin up a brand-new background thread for every row that needed
  artwork; a group with many copies (or several groups expanded in quick
  succession) could momentarily spin up dozens of OS threads at once.
  Artwork loads now run on a small, reused pool of worker threads instead,
  so thread count stays bounded regardless of how many rows request
  artwork.
- **Loading skeletons instead of a blank table.** The duplicates table now
  shows placeholder skeleton rows while a library is loading, instead of
  sitting empty (or showing the previous library's rows frozen on screen)
  until the load finishes — clearer feedback that something is happening
  on a large library.
- **Smart playlist compatibility check.** If a consolidation would change
  a field commonly used in smart-playlist rules (genre, rating, play
  count, date added, etc.) on a track that belongs to a smart playlist,
  the affected duplicate group is now flagged — in the table's "Why
  flagged" column, its detail panel, and the consolidation confirmation
  dialog — as a heads-up to double-check that playlist afterward. This
  app can't read a smart playlist's actual rules (Apple's own
  undocumented binary format), so it flags *possible* impact rather than
  claiming to know whether membership will actually change.
- **Grouped, collapsible What's new.** Help → What's new… now shows one
  collapsible section per version (newest expanded by default), with each
  version's entries grouped under Added/Fixed/Changed, instead of one
  long flat list spanning every release.

## What's new in v0.23(pre)

- **Fixed album art not showing.** The inline duplicate-row thumbnail and
  the expanded group panel's per-copy artwork never loaded on a real
  Windows library: the on-disk path built from a track's `Location` field
  kept a stray leading slash in front of the drive letter (e.g.
  `\C:\Users\...` instead of `C:\Users\...`), so the file was never found.
  Fixed in both the artwork reader and Library Health's missing/broken
  file link check, which had the same bug.
- **One writer per library at a time.** Opening a Library.xml that's
  already open in another window or another running copy of this app is
  now refused with a clear message, instead of silently letting two
  windows write back to the same file and risk a corrupted result.
- **Real toolbar.** The old plain Help/File menu bar is replaced with an
  in-app toolbar (Open, Restore backup, Save audit report, Settings,
  What's new) for quicker access to the app's main actions.
- **Album-level duplicate detection.** Library Health now reports whole
  albums that appear to have been imported more than once at different
  bitrates (e.g. re-ripped at a higher quality without removing the
  original), listing which albums, which bitrates, and how many tracks
  overlap. This sits alongside — not in place of — the existing per-track
  duplicate detection in the Duplicates tab, which is still what actually
  drives consolidation.

## What's new in v0.21(pre)

- **Configurable fuzzy-matching thresholds.** Settings → Duplicate
  Detection now exposes the possible-duplicate and high-confidence
  similarity thresholds the fuzzy pass uses, with a reset-to-defaults
  button. They're saved immediately and take effect the next time a
  library is opened or rescanned. Exact-match detection is unaffected —
  see "Performance notes" below for how this interacts with fuzzy
  matching at scale.
- **Parallel fuzzy scanning for very large libraries.** Above roughly
  20,000 candidate tracks, the fuzzy pass's independent comparison
  batches are now farmed out across multiple processes instead of run
  one at a time, cutting scan time on large libraries. This only affects
  wall-clock time, never which duplicates are found — falls back to the
  existing single-process path automatically if a process pool can't be
  started in your environment.
- **Live iTunes sync retries transient failures.** If a single track
  removal against a running iTunes bounces (iTunes momentarily busy
  servicing another call), it's now retried a couple of times with a
  short backoff before falling back to the existing "removed from the
  exported file only" behavior for that track. A modal dialog blocking
  iTunes is still detected and reported immediately, not retried against.
- **Tooltips everywhere.** Every remaining icon-only or otherwise
  ambiguous control now has a tooltip explaining what it does (Open,
  Restore backup, the confidence filter dropdown, Select all, Consolidate
  selected, and the per-row/column checkboxes) — previously only the
  write-back checkbox had one.

## What's new in v0.19(pre)

- **Fixed a build failure.** `dist_config\build.bat` could fail during
  dependency install with "No matching distribution found for
  pywin32==306" — that exact version is no longer published. The pin is
  now pywin32==311; nothing about how or when pywin32 is used changes.
- **Live build progress.** The build progress popup now shows an
  elapsed/ETA timer, and its progress bar advances smoothly through the
  PyInstaller step itself instead of sitting frozen on "Step 3 of 4" for
  however long that step takes. Console output during the build is
  unchanged.

## What's new in v0.18(pre)

- **True live-preview theme.** Settings > Appearance still restyles the
  app immediately as you browse Light/Dark/Match Windows, but now only
  saves the choice when you click OK — Cancel, Esc, or closing the
  Settings window reverts to whichever theme was active before you
  opened it.
- **Color-coded confidence badges.** Match confidence in the Duplicates
  table is now a colored badge (green/amber/red for Exact/High
  confidence/Possible duplicate) instead of plain text, for a clearer
  at-a-glance read.
- **"Why flagged" explanation.** A new column (and matching line in each
  row's detail panel) explains in plain language why a group was matched
  — exact artist/title match, or a fuzzy-match percentage.
- **Sortable, multi-select table.** Click any Duplicates table header to
  sort by that column; Ctrl/Shift-click to select multiple rows for
  review. Purely a view convenience — the per-row checkboxes remain the
  only thing that controls what gets consolidated.
- **Exact preview before consolidating.** "Consolidate selected…" now
  shows precisely which track entries will be kept vs. removed (with IDs
  and albums) and which playlists get repointed, for every selected
  group, before you confirm — not just a summary count.
- **Drag-and-drop to open.** Drop a Library.xml file onto the window to
  open it, as an alternative to File > Open Library.xml….

## What's new in v0.15(pre)

- **Settings dialog (File → Settings…).** Four tabs: **General** (an
  Appearance option — Match Windows / Light / Dark — applied immediately
  and remembered between sessions, on top of the existing auto-follow-OS
  behavior), **Accessibility** (a "Use larger text" option), **Diagnostics**
  (a viewer for the existing error log, with Refresh and Clear), and
  **Changelog** (the same release notes as Help → What's new…, in one more
  place). No existing menu, dialog, or default behavior changes — Match
  Windows is the default, matching every previous version.

## What's new in v0.14(pre)

- **Live iTunes sync (Windows).** If classic Windows iTunes is open and
  responding when you consolidate, the tracks being removed are now also
  deleted directly from the running app — from the Library and every
  playlist except Podcasts and Audiobooks — so the open iTunes window
  reflects the change immediately, with no quit/re-import/restart needed
  for that already-open copy. This is fully automatic and requires no
  extra setup or confirmation beyond the same consolidation confirmation
  you already see. It only ever runs when iTunes is both running and
  actually responding to a quick check; a busy, starting-up, or dialog-
  blocked iTunes is treated as unavailable and the app falls back to the
  exact same export/re-import flow as every previous version. The
  written library file is always produced regardless — live sync is an
  additional step after that file is safely on disk, never a substitute
  for it. Apple Music (the modern macOS-only app) and non-Windows
  platforms are unaffected; this feature is inert there.

## What's new in v0.7(pre)

- **Search/filter duplicate results.** The Duplicates tab now has a filter
  row above the table: a text box that matches against artist or song
  name, and a confidence-tier dropdown (Exact / High confidence /
  Possible duplicate — review). Filtering only changes what's visible —
  it never changes the underlying plan — and "Select all" now acts only
  on the rows currently visible under the filter.
- **Undo after apply.** The "Consolidation complete" dialog now has an
  **Undo this change…** button that restores the automatic backup taken
  immediately before that consolidation was applied.
- **Browse and restore any backup snapshot.** Restore backup… now opens a
  list of every snapshot on record (timestamp, label, and source file),
  not just the most recent one — every library load and every
  consolidation is saved as its own restorable point.
- **Clearer empty, loading, and error states.** The Duplicates table now
  shows a specific message for each empty case (no library loaded / no
  duplicates found / nothing matches your filter) instead of a blank
  table, and filter/select-all controls are disabled while a load or
  consolidation is in progress rather than clickable against stale data.
- **More responsive layout.** Table columns resize proportionally instead
  of using fixed pixel widths, the window has a sensible minimum size,
  and long status text now wraps instead of clipping — the app stays
  usable across common Windows display sizes and DPI settings.

## What's new in v0.6(pre)

- **Real app icon.** The built .exe now has an actual icon (`assets/
  app_icon.ico`), shown in Explorer, the taskbar, and the window title bar
  — previously the PyInstaller spec had `icon=None`.
- **Light and dark themes that follow Windows.** The app now reads the
  current Windows app theme (Settings → Personalization → Colors) on
  startup and uses a matching light or dark stylesheet, instead of always
  forcing light mode.
- **Actionable error messages.** Failures (couldn't open a library,
  couldn't apply a consolidation, couldn't start the app at all) now
  include a specific "What to try" suggestion — e.g. "the file may be
  open in iTunes — close it and try again" — instead of just the raw
  error text.
- **Artwork preview in duplicate results.** Expanding a duplicate group
  now shows each copy's embedded cover art next to its bitrate/album/
  playlist details. Library.xml itself never contains artwork bytes
  (only an "Artwork Count"), so this reads the image directly from the
  track's own audio file on disk when you expand a row — nothing is read
  or cached eagerly for rows you haven't opened.
- **Audit export.** After a consolidation completes, you can save a JSON
  audit report (also available any time afterward via File → Save audit
  report…) recording exactly what changed: canonical/removed track ids
  per group, before/after play count and rating, every backfilled field
  with its before/after value, and which playlists were repointed.
- **Optional Windows installer.** `dist_config/setup.iss` (Inno
  Setup) builds a proper installer with a Start Menu shortcut, an
  uninstaller listed in Apps & features, and an **opt-in** `.xml` file
  association — unchecked by default, so installing doesn't change how
  any of your existing `.xml` files open unless you explicitly check that
  box. See `dist_config/installer_README.md`.

## What's new in v0.3(pre)

- **Manual duplicate review.** Click any row in the duplicate table to
  expand it: see every copy's bitrate, album, and which playlists it's
  actually in by name, plus a short explanation of why the auto-picked
  copy was chosen to keep. From there you can click **Keep this one
  instead** on a different copy to keep that one, or **Mark
  this group as not duplicates** to exclude the whole group from
  consolidation (e.g. two different live versions that happened to match).
- **Library Health tab.** A second tab alongside Duplicates that reports,
  library-wide: duplicate track count, missing artwork, missing/
  inconsistent core tags (Name/Artist/Album/Genre/Year), low-quality files
  (under 128 kbps), missing or broken file links, and an estimated
  storage-savings figure from consolidating the duplicates currently
  found. This is a read-only report — health findings other than
  duplicates are informational; this app still does not edit individual
  track tags or re-encode audio.
- **Apple/macOS-inspired toolbar polish.** Tab bar and section styling
  extended to match the existing macOS/iOS-inspired look (see v1.0/v1.1
  theme notes below) rather than introducing a second visual language.

## What's new in v0.2(pre)

- **Fuzzy duplicate matching.** In addition to exact normalized Artist +
  Title + Duration matches, the app now also finds *near-miss* candidates
  (typos, small tag differences) using a similarity score. These are shown
  in their own confidence tier — "high confidence" or "possible duplicate —
  review" — and possible-duplicate matches are **never pre-selected** for
  merge; you always choose to include them explicitly.
- **Real progress.** Loading and consolidating now show an actual
  percentage complete (computed in chunks) instead of an indeterminate
  spinner, so large libraries give real feedback on how much work is left.
- **Auto-detected default library.** On startup, and when opening a file,
  the app looks for a Library.xml at common default locations and offers
  to use it directly.
- **Direct write-back.** You can now save the consolidated result straight
  back over the file it was opened from (instead of always saving a new
  file), with a confirmation step and guided instructions for reopening
  iTunes/Apple Music afterward.
- **In-app changelog.** Release notes now live in the app itself
  (Help → What's new…) instead of a separate file, and always match the
  version shown in the title bar.

## What this version actually does (read before using)

- Reads an **iTunes/Apple Music `Library.xml`** export (File → Library →
  Export Library in iTunes or Apple Music), and can auto-detect one at a
  default location on this machine.
- Detects duplicate tracks two ways:
  - **Exact matches** — normalized Artist + Title + Duration (metadata
    only — it does not read or fingerprint audio files). Behavior here is
    unchanged from v1.
  - **Fuzzy candidates** — near-miss matches on typo'd or lightly-edited
    artist/title tags, scored by similarity and split into "high
    confidence" and "possible duplicate — review" tiers. Only exact and
    high-confidence matches are pre-selected; review-tier matches require
    you to opt in.
- One physical track/file always maps to exactly **one canonical catalogue
  entry**, which can be referenced from **any number of playlists** — a
  merge repoints every playlist that referenced any of the removed copies,
  it doesn't limit how many playlists can point at the surviving track.
- Shows a **dry-run preview table** of every duplicate group found: which
  track would be kept, which would be removed, the match confidence, how
  many playlists are affected, and the merged play count/rating. **Nothing
  is changed until you review and confirm.**
- **Manual review, per group:** click a row to expand it and see each
  copy's bitrate/album/playlists plus the reasoning behind the auto-picked
  canonical track. From there, choose a different copy to keep, or mark
  the whole group as not-a-duplicate to leave it untouched.
- **Library Health tab:** a library-wide report — duplicate counts,
  missing artwork, missing/inconsistent core tags, low-quality files,
  missing/broken file links, albums that appear to have been imported
  more than once at different bitrates, and estimated storage savings
  from consolidating current duplicates — kept in sync with the
  Duplicates tab and whichever library file is currently open. Missing
  artwork and missing/broken file links additionally list the affected
  songs with a direct fix button (**Fix missing artwork…** /
  **Locate missing file…**), and **View growth timeline…** shows a chart
  of track/duplicate counts over every past scan.
- **Album-level duplicate detection:** in addition to per-track matching,
  Library Health separately flags whole albums that look re-imported
  wholesale at a different bitrate (several shared track titles found
  under two or more bitrates for the same Album/Album Artist), so a
  bulk re-rip is easy to spot even though the individual duplicate
  tracks are still what gets reviewed/merged from the Duplicates tab.
- **One writer per library at a time:** opening a Library.xml already
  open in another window or another copy of this app is refused with a
  clear message, so two windows can never write back to the same file
  concurrently. Opening two *different* library files at once, in two
  windows, is unaffected.
- On confirm: merges play counts (summed), rating (highest kept), date
  added (earliest kept), backfills any metadata field that's empty on the
  kept track but present on a duplicate, repoints every playlist reference
  to the surviving track, and writes the result — either to a new file, or
  directly back to the original file if you choose "Write back to original
  file".
- **Smart playlist compatibility check:** if a merge would change a field
  commonly used in smart-playlist rules (genre, rating, play count, date
  added, etc.) on a track that belongs to a smart playlist, that group is
  flagged as a heads-up in the table, its detail panel, and the
  consolidation confirmation dialog. Smart playlists themselves are never
  edited — their rules are Apple's own undocumented binary format, which
  this app doesn't parse or evaluate — so this is a "worth checking
  afterward" flag, not a guarantee that membership will or won't change.
- Shows real percentage progress while loading and while consolidating,
  computed in chunks so large libraries don't leave you staring at a
  spinner with no sense of how much is left.
- Saves an automatic backup snapshot (to a local SQLite cache) before
  every load and before every apply (including write-back saves). Restore
  backup… lets you browse every snapshot on record and restore any of
  them, and the post-consolidation dialog offers a direct "Undo this
  change…" shortcut back to the snapshot taken just before that run.
  Settings → Backups controls how many recent snapshots are kept (the
  oldest are pruned automatically once you're over the limit) and lets
  you delete old ones on demand.
- Shows in-app release notes under Help → What's new…, kept in sync with
  the version number shown in the title bar.

## What this version does NOT do

- It does **not** modify your live iTunes/Apple Music library directly or
  talk to iTunes via COM/AppleScript/Windows integration — even with
  write-back enabled, this app only edits the XML file on disk; you still
  reopen iTunes/Apple Music afterward for it to pick up the change (the
  app shows you the exact steps).
- It does **not** do audio fingerprint matching — only metadata. Fuzzy
  matching helps with typo'd tags, but two different recordings of the
  same song with very different tags may still not be detected, and the
  fuzzy pass is intentionally conservative (time-boxed comparison budget)
  so it stays responsive on very large libraries rather than exhaustive at
  any cost — see "Performance notes" below.
- It does **not** move, rename, or delete any actual audio *files* on disk
  — only the library's *entries* and *playlist references* to those files.
- It does **not** read, evaluate, or edit smart playlist rules ("Smart
  Criteria" in Library.xml is an opaque, undocumented Apple binary
  format). The smart-playlist compatibility check flags *possible* impact
  from a field change, based on which fields commonly drive smart
  playlist rules — it cannot tell you what a specific playlist's rules
  actually are or whether its membership will actually change.

## Performance notes (fuzzy matching at scale)

Exact-match detection is unchanged from v1 and remains fast and complete
at any library size. Fuzzy matching additionally compares tracks pairwise
by similarity, which is inherently more expensive; to keep the app
responsive at 100k+ tracks without adding an external
fingerprinting/indexing dependency, the fuzzy pass:

- Buckets tracks by normalized title's first character, and splits any
  oversized bucket into small fixed-size chunks compared only within
  themselves.
- Spends a time-boxed budget (30 seconds by default) on the pairwise
  comparison work itself, so the worst case (many same-length,
  same-first-letter titles) still finishes in bounded time rather than
  hanging — and shows a live "Still scanning… (N% of scan time budget
  used)" status message while it does, instead of the whole pass
  happening inside one silent blocking call.

This trades a small amount of recall at the extreme tail (a very large,
evenly-distributed library may not have every possible fuzzy candidate
compared before the time budget runs out) for a predictable, visible
runtime. Exact matches are never affected by this — only the additional
fuzzy "possible duplicate" candidates are subject to the budget. Earlier
versions (through v1.7.5) bounded this the same way in spirit but via a
fixed total-comparison count divided evenly across every batch, which
gave each batch an arbitrarily strict allowance on libraries with many
small buckets and no visibility into how much of that allowance had been
used; time-boxing ties the ceiling to actual elapsed time instead, which
matches what a person waiting on the scan actually experiences.

**Thresholds.** The similarity cutoffs that decide "possible duplicate"
vs. "high confidence" vs. "not a candidate at all" are configurable under
Settings → Duplicate Detection (see "What's new in v1.3.15" above).
Lowering the possible-duplicate threshold surfaces more near-misses for
review at the cost of more false positives; both values are clamped to a
sane range (0.50–0.99) and the high threshold is always kept above the
low one.

**Parallelization.** Above ~20,000 candidate tracks, the fuzzy pass's
comparison batches (already independent units of work — see the
bucketing/chunking above) run across multiple processes via Python's
`concurrent.futures.ProcessPoolExecutor` instead of sequentially. This
only changes how long the scan takes, never which duplicates are found —
batches never share state, so parallel and single-process runs produce
identical groups. The same time budget applies either way: once it's
spent, batches that haven't started yet are cancelled rather than
awaited, while any already-running batch (each is small — see
`FUZZY_MAX_BUCKET_SIZE`) is still allowed to finish and its results are
kept. If a process pool can't be started in your environment (e.g.
certain frozen/sandboxed builds), the app falls back to the
single-process path automatically rather than failing the scan.

## Tested against

No real populated iTunes library was available at build time. This has
been tested against:
1. `tests/fixtures/Library.xml` — a synthetic but structurally-real Apple
   plist library (generated by `tests/generate_fixture.py`) containing
   deliberate exact duplicates, `(feat. …)`/remaster tag variants,
   same-title-different-artist traps (must NOT merge), and playlists that
   reference the duplicates in various combinations — including a playlist
   with a pre-existing repeated reference to the same track twice.
2. A synthetic 120,000-track / 81 MB library, to verify performance and
   memory at the 100k+ scale target (parse+index+detect+consolidate+save
   completed in ~20s, peak memory ~290MB in this test environment; this
   figure is for exact-match detection, which is unchanged in v1.1 — see
   "Performance notes" above for fuzzy-matching timing at scale).
3. Synthetic fuzzy-matching stress tests at 3k/20k/120k tracks with
   deliberately adversarial (evenly-distributed, similar-length) titles to
   verify the time-boxed scan budget keeps runtime bounded even in the
   worst case.
4. `tests/fixtures/Library_unicode_folders.xml` (added in v1.10.2, also
   generated by `tests/generate_fixture.py`) — CJK, accented-Latin, and
   emoji track/playlist names, plus a two-level nested playlist folder
   structure (a folder inside a folder, each with its own child
   playlist), to verify non-ASCII tags round-trip exactly through
   parse/save/reload and that folder playlists are read like any other
   ordinary, non-special playlist.
5. `tests/fixtures/malformed/` (added in v1.10.2) — truncated XML (file
   cut off mid-track), mismatched/unclosed tags, an empty file, a
   well-formed plist missing the required top-level `Tracks` key, and an
   XML entity declaration (XXE-style) — to verify every one of these
   fails with a clear `LibraryParseError` naming the file, never a raw
   traceback, a silent partial load, or (for the entity case) an
   expanded entity.

Run `python -m pytest tests/` yourself to see the passing checks across
every test module — `test_consolidation.py` (exact/fuzzy matching,
review-tier selection, the canonical-entry/unlimited-playlists guarantee,
the audit export's before/after values, and the embedded-artwork reader),
`test_duplicate_strategies.py` (the strategy-pattern layer added in
v1.9.1 — exact/fuzzy/fingerprint strategies, composition, and parity with
the existing exact-then-fuzzy scan), `test_theme_tokens.py` (the
design-token refactor added in v1.9.1, confirming theme/recoloring
behavior is unchanged), and `test_library_xml_edge_cases.py` (added in
v1.10.2 — malformed/truncated XML, non-ASCII tags, and playlist-folder
nesting; see items 4 and 5 above). `python tests/test_itunes_com_sync.py`
covers the live-sync module's platform-safe logic separately — Persistent
ID parsing and the safe-fallback behavior when iTunes/Windows/pywin32
aren't available.
The actual live COM removal against a real running iTunes cannot be
exercised in an automated test and has not been verified against real
iTunes; treat it the same as the rest of this app — reviewed carefully in
the dry-run/confirmation step before you rely on it, with your exported
XML file as the fallback of record.
**You should treat this as validated-on-synthetic-data, not
validated-on-your-library, until you've run it against your own export
and reviewed the dry-run preview carefully before confirming anything.**

## Setup (Windows)

### Option A — run the prebuilt .exe
1. Build it yourself (see below) — no prebuilt binary is included in this
   ZIP, since it must be compiled on a Windows machine.

### Option A.5 — build a proper installer (optional)
After building the app (Option B below), you can additionally package it
as a normal Windows installer — Start Menu shortcut, uninstaller in Apps &
features, optional desktop shortcut, optional `.xml` file association —
using [Inno Setup 6](https://jrsoftware.org/isinfo.php) (free):
```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
```
This produces `dist_config\Output\iTunesLibraryConsolidator-Setup-<version>.exe`.
See `dist_config/installer_README.md` for details on what it installs and
why the `.xml` association is opt-in.

### Option B — build from source
Requires Python 3.10+ from [python.org](https://python.org) (check "Add
to PATH" during install).

1. Unzip this project anywhere, e.g. `C:\Tools\iTunesConsolidator`.
2. Open Command Prompt in that folder.
3. Run:
   ```
   dist_config\build_windows.bat
   ```
   This creates a virtual environment, installs dependencies, runs the
   test suite, and builds the app as a standalone folder
   (`dist\iTunesLibraryConsolidator\`) with PyInstaller. On success, it
   copies `iTunesLibraryConsolidator.exe` (and its dependent files)
   straight into the project root, so you don't need to go looking
   inside `dist\` for it.
4. Double-click `iTunesLibraryConsolidator.exe` in the project root to
   launch.

   Alternatively, `dist_config\build.bat` does the same build with a
   small guided menu (choose whether to launch the app automatically
   when the build finishes) and a progress popup that stays open for
   the whole build, showing the current step, an elapsed/ETA timer, and
   a progress bar that advances smoothly through the PyInstaller step
   itself (not just in four coarse jumps); it degrades silently to the
   same console-only behavior as above if a popup can't be shown. On a
   successful build it also brings the freshly launched app's window to
   the foreground, instead of leaving it to open behind whatever else
   is on screen.

### Or run without building an exe
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main
```

## Using it

1. In iTunes or Apple Music: **File → Library → Export Library…** — save
   as `Library.xml`. (If a library already exists at a common default
   location, the app will offer to open it automatically on startup.)
2. In this app: **Open Library.xml…** and select that file, if you didn't
   use the auto-detected one. (You can also drag a Library.xml file onto
   the window instead of using the button.) If you've opened this exact
   file before and it's since been re-exported with changes, a **"What
   changed since last export"** summary appears automatically — tracks
   added/removed, tracks with changed metadata, and any playlist count
   change since the last time this app saw it.
3. Review the duplicate table. Each row is one duplicate group, labeled
   with its match confidence (exact, high confidence, or possible
   duplicate — review). Uncheck any you don't want touched; possible
   duplicates start unchecked and must be opted into explicitly.
   Click a row to expand it for the full per-copy breakdown (bitrate,
   album, playlists, and why that copy was picked as canonical) — from
   there you can choose a different copy to keep or mark the group as
   not-a-duplicate. If two tracks are duplicates but the scan never
   grouped them at all, use the toolbar's **🔗 Merge tracks…** to pick
   both manually — they'll appear in the table tagged "Manually merged."
   To have the app check for new duplicates on its own after you
   re-import tracks, turn on **Check for new duplicates automatically**
   under Settings → General.
4. Check the **Library Health** tab any time for a library-wide summary
   of duplicates, missing artwork/metadata, low-quality files, album-level
   bitrate duplicates, and estimated storage savings. Missing artwork and
   missing/broken file links list the affected songs with a fix button —
   **Fix missing artwork…** (looks for another local copy with embedded
   art) and **Locate missing file…** (browse to relink it) — and
   **View growth timeline…** charts track/duplicate counts across every
   past scan. If many tracks are showing as missing/broken at once (the
   "!" iTunes/Apple Music shows next to a track it can't find) — for
   example after moving your music into a different subfolder layout —
   use **Find missing files in folder…** above that list instead of
   relinking each one by hand: pick the new root folder and every
   missing track whose filename is found somewhere underneath it is
   offered for relinking in one pass, with the matches shown for review
   first. If the fuzzy pass is catching too many or too few
   near-misses, adjust the thresholds under the toolbar's **Settings…**
   button → Duplicate Detection and reopen/rescan the library.
5. Click **Consolidate selected…**, confirm. Choose **Write back to
   original file** to overwrite the file you opened, or leave it unchecked
   to save a new file instead.
5. Follow the on-screen reopen steps: quit iTunes/Apple Music, import or
   replace the library file, then reopen it. Always keep your original
   library file until you've confirmed the result looks right — the app's
   own backup snapshots are a second safety net, not a replacement for
   your own copy.
6. On Windows, **Rebuild library now…** does steps 5's quit/backup/copy/
   relaunch for you automatically. Before any of that starts, a pre-flight
   check confirms there's enough free disk space and write permission on
   the iTunes folder (iTunes already running is just noted, not blocked —
   the rebuild quits it for you as its first step); a problem here stops
   things before anything is touched. Afterward, you still need to click
   iTunes's own "Choose Library…" prompt yourself — the success dialog
   shows a small annotated picture of that prompt so it's easy to spot on
   screen, not just described in text. If something looks wrong
   afterward, the toolbar's **Undo last rebuild…** restores the backup
   that step just made, with no manual file-hunting required. Once you're
   happy with the result, the rebuild-finished dialog also offers
   **Remove duplicate files from disk…** to permanently delete the audio
   files for the copies that were removed — this is optional and never
   automatic, and only appears after you've confirmed the rebuild itself
   went well.

## Project layout

```
src/
  changelog.py            App version + in-app release notes (Help -> What's new)
  errors.py                Actionable "what to try" recovery hints for error dialogs
  error_log.py             Rolling on-disk/in-memory error log (Settings -> Diagnostics)
  crash_reporter.py       Telemetry-free local crash dumps (traceback + repro
                            context) written to disk on an unhandled error --
                            see "What's new in v1.10.0" above; never phones home
  resources.py              Locates bundled assets (app icon) from source or frozen .exe
  core/
    itunes_xml.py       Library.xml parser/writer (plist-based), default-library
                          detection, write-back, and reopen guidance
    duplicate_detector.py   Metadata normalization + exact/fuzzy grouping,
                              confidence tiers, time-boxed fuzzy comparison pass
    duplicate_strategies.py Pluggable strategy-pattern wrapper over the exact/
                              fuzzy passes above, plus a new metadata
                              fingerprint strategy (Persistent ID / size+
                              duration); purely additive, see "What's new
                              in v1.9.1" above
    consolidator.py      Merge planning (dry-run) + apply logic, tier-aware
    audit.py              Builds the before/after audit export from a plan
    artwork.py             Reads embedded cover art from MP3/MP4/M4A/FLAC
                             files (no deps)
    library_health.py     Library-wide health report, incl. album-level bitrate duplicates
    library_diff.py        "What changed since last export" fingerprinting +
                             diff, compared/recorded on each library load via
                             CacheDB's existing settings store
    health_actions.py     Turns Health tab findings into fixes: relink a missing
                             file (one at a time, or many at once by searching a
                             root folder), or find artwork on another local copy
                             of the same song (no network access -- see module
                             docstring)
    library_lock.py        Per-file advisory lock so only one window/instance can
                             hold a given Library.xml open for writing at a time
    itunes_com_sync.py    Windows-only: live iTunes COM sync (see "Live iTunes
                             sync" above), safe no-op everywhere else
    rebuild_script.py     In-app "Rebuild library now…" (preflight check,
                             then quit/backup/copy/relaunch) and "Undo last
                             rebuild" (restores the most recent backup
                             pair), with step callbacks for the UI's step
                             tracker
    workers.py           Background QThread workers with chunked % progress,
                          incl. the rebuild step tracker
    providers/            Provider plugin architecture for future streaming-
                          service support (see "What's new in v1.8.0" above):
                          base.py defines LibraryProvider/ProviderTrack and the
                          register_provider/available_providers registry;
                          apple_music_api.py and spotify_export.py are
                          skeleton, not-yet-functional integrations
                          demonstrating the interface. Nothing here is
                          imported/registered by default yet.
  data/
    cache_db.py          SQLite index + backup/restore snapshots (automatic
                          and user-named restore points alike, with a
                          configurable retention/prune policy), plus a
                          lightweight scan-history table feeding the Health
                          tab's growth timeline and scan-over-scan trend text
  ui/
    main_window.py       Main window, toolbar, review-tier UI, write-back,
                          changelog dialog, artwork preview, audit export,
                          toast notifications, Health tab fix-action handlers
    health_panel.py       Library Health tab (stat cards, breakdowns, and
                          actionable missing-artwork/missing-file lists)
    settings_dialog.py    Settings dialog, grouped by workflow stage: Before
                          you scan (General, Accessibility), During cleanup
                          (Duplicate Detection, Diagnostics), Reference
                          (Changelog)
    theme.py              macOS/iOS-inspired QSS stylesheet, light + dark, OS-aware,
                          recolored per the 10 named accent themes (see
                          "What's new in v1.8.0" above); spacing/radius/font
                          values come from design_tokens.py (see below)
    design_tokens.py      Centralized spacing/corner-radius/font-size tokens
                          shared by theme.py's light and dark stylesheets
                          (see "What's new in v1.9.1" above)
    widgets.py            Reusable widget builders: toolbar, header, severity
                          dialogs, the annotated "Choose Library…" mockup,
                          non-blocking toast notifications, and the Library
                          Health growth-timeline chart
  main.py                 Entry point
assets/
  app_icon.ico             App icon (multi-resolution), used by the build and at runtime
tests/
  generate_fixture.py     Builds the synthetic test library (Library.xml) and,
                             since v1.10.2, the non-ASCII/folder-nesting fixture
                             (Library_unicode_folders.xml)
  fixtures/
    Library.xml               Main synthetic fixture (see "Tested against" above)
    Library_unicode_folders.xml  CJK/accented/emoji tags + nested playlist
                                    folders (added v1.10.2)
    malformed/                 Truncated/malformed/empty/entity-declaration
                                  Library.xml fixtures for parse-error coverage
                                  (added v1.10.2)
  test_consolidation.py   Automated tests (exact/fuzzy/album duplicate detection,
                             consolidation planning, library health)
  test_duplicate_strategies.py Automated tests for the strategy-pattern layer
                             (exact/fuzzy/fingerprint strategies, composition,
                             parity with find_all_candidate_groups) -- see
                             "What's new in v1.9.1" above
  test_theme_tokens.py    Automated tests confirming the design-token
                             refactor didn't change theme behavior (v1.9.1)
  test_library_xml_edge_cases.py Automated tests for malformed/truncated XML,
                             non-ASCII tags, and playlist-folder nesting
                             (added v1.10.2 -- see "Tested against" above)
  test_cache_db.py        Automated tests for the SQLite index/backup/restore layer
  test_rebuild_script.py  Automated tests for the in-app rebuild/undo flow
  test_itunes_com_sync.py Automated tests for the live-sync module's
                             platform-safe logic (the actual COM calls require
                             a real Windows + iTunes machine)
dist_config/
  build.spec              PyInstaller build configuration (standalone-folder/onedir
                            output; build.bat/build_windows.bat copy the .exe to the
                            project root afterward)
  build_windows.bat        One-command Windows build script
  build.bat                 Same build, with a guided menu and progress popup
  build_menu.py              Pre-build menu popup used by build.bat
  build_progress.py          Build progress popup used by build.bat
  setup.iss                Inno Setup script: installer with Start Menu shortcut,
                            uninstaller, opt-in .xml file association, and a
                            silent VC++ Redistributable install (v1.10.3)
  installer_README.md      What the installer does and how to build it
  install.bat              Full source install (venv/deps/tests/build + shortcuts)
  uninstall.bat            Removes shortcuts/uninstall entry created by install.bat
  unblock.bat              Removes the Windows "Mark of the Web" after extracting the zip
```

