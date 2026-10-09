"""
In-app changelog and version constant.

Per product decision, release notes live here (shown via a dialog in the
app) instead of a separate CHANGELOG.md file, so users see what changed
without leaving the app, and the version shown in the UI/title bar can
never drift out of sync with the notes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Product decision: v1.0 is the first full release. Every prior build was
# a pre-release, numbered sequentially as "0.1(pre)" through "0.50(pre)"
# (oldest to newest) instead of their original raw semantic versions --
# see the CHANGELOG list below -- so the pre-release history reads as a
# clean run-up to 1.0 rather than a semantic-version sequence that jumps
# around (1.3.20 followed by 1.5, etc.) for reasons that only made sense
# during development. From this point on, ordinary semantic versioning
# resumes for real releases (1.1, 1.2, 2.0, ...); there is no more
# "-pre"/"(pre)" wrapper to apply.
_RAW_VERSION = "2.2"
APP_VERSION = _RAW_VERSION

# Categories used to group each version's changelog entries in the
# in-app "What's new" dialog (see ui/main_window._on_show_changelog).
# Kept as plain strings (not an enum) since they're only ever used as
# dict keys/display labels here.
CATEGORY_ADDED = "Added"
CATEGORY_FIXED = "Fixed"
CATEGORY_CHANGED = "Changed"
CATEGORY_ORDER = (CATEGORY_ADDED, CATEGORY_FIXED, CATEGORY_CHANGED)

# One emoji per category, shown next to its heading in the "What's new"
# dialog (see ui/settings_dialog.ChangelogVersionSection) so the three
# groups -- new stuff, bug fixes, everything else -- are easy to tell
# apart at a glance without reading every heading. Purely cosmetic: the
# plain-text CATEGORY_* names above are unchanged and are still what
# _classify_change matches bullets against, so this is a display-only
# addition, not a new classification rule.
CATEGORY_EMOJI = {
    CATEGORY_ADDED: "\u2728",  # ✨
    CATEGORY_FIXED: "\U0001FA79",  # 🩹
    CATEGORY_CHANGED: "\U0001F504",  # 🔄
}


@dataclass(frozen=True)
class ChangelogEntry:
    version: str
    date: str  # ISO date string, e.g. "2026-08-10"
    changes: list[str]

    def categorized(self) -> dict[str, list[str]]:
        """Buckets this entry's bullets into Added/Fixed/Changed for the
        collapsible, grouped "What's new" dialog.

        Existing entries were written before categorization existed, as a
        flat `changes` list -- rather than hand-tagging ~90 historical
        bullets (and risking silently mis-tagging old wording no one is
        re-reading), each bullet is classified here from its own text,
        deterministically and at render time, so `changes` stays the one
        source of truth and nothing about past entries needs to change to
        support this. New entries can write plain sentences exactly as
        before; the same rule classifies them.
        """
        buckets: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
        for change in self.changes:
            buckets[_classify_change(change)].append(change)
        return buckets


def _classify_change(text: str) -> str:
    """Best-effort classification of a single changelog bullet by its
    leading wording -- "Fixed a bug where..." -> Fixed, "Added X" ->
    Added, everything else (reworded/simplified/renamed/moved/improved
    behavior that isn't a new capability or a bug fix) -> Changed.

    Bullets may start with a leading emoji (e.g. "🛠️ Fixed ..."), so any
    non-letter characters at the start are skipped before checking the
    leading word.
    """
    stripped = text.strip().lower()
    # Skip past a leading emoji/symbol run to reach the first word.
    start = 0
    while start < len(stripped) and not stripped[start].isalpha():
        start += 1
    lowered = stripped[start:]
    if lowered.startswith(("fixed", "fix ")):
        return CATEGORY_FIXED
    if lowered.startswith(("added", "add ")):
        return CATEGORY_ADDED
    return CATEGORY_CHANGED


# Product decision: changelog entries never call out the audit-export
# feature specifically (no "audit report", "audit trail", "audit record"
# line item) -- the feature itself remains fully intact in the app
# (File > Save audit report..., core/audit.py), only its own dedicated
# changelog bullets are excluded going forward.


CHANGELOG: list[ChangelogEntry] = [
    ChangelogEntry(
        version="2.2",
        date="2026-08-19",
        changes=[
            "Added: a new \"Select all (incl. review)\" button in the "
            "Duplicates tab that checks every currently visible group, "
            "including low-confidence \"needs review\" matches. Large "
            "libraries with hundreds or thousands of review-tier groups "
            "no longer require scrolling through and clicking each one "
            "by hand. The existing \"Select all (exact + high "
            "confidence)\" checkbox is unchanged and still leaves "
            "review-tier rows unchecked by default, so the safer default "
            "behavior is preserved -- this is an additional, explicitly "
            "opt-in control, not a change to what \"Select all\" already "
            "did.",
            "Improved: Library.xml loading and duplicate-group table "
            "population were re-profiled against large (30,000+ song) "
            "libraries. The streaming plist parser, fuzzy-match "
            "bucketing/time-box, and batched table population "
            "introduced in earlier releases already covered the "
            "hot paths; this release adds test coverage confirming "
            "those paths behave correctly at large scale and did not "
            "reveal further hot spots worth changing without a larger "
            "architectural change (see core/plist_stream.py and "
            "core/duplicate_detector.py docstrings for the existing "
            "optimizations this builds on).",
        ],
    ),
    ChangelogEntry(
        version="2.1",
        date="2026-08-16",
        changes=[
            "Added: when a duplicate song's track belongs to an album "
            "copy that looks incomplete — and a complete copy of that "
            "same album exists elsewhere in your library — its checkbox "
            "in the Duplicates tab is now pre-checked for you, with a "
            "\U0001F4BF note in the reason column. Completeness is judged "
            "from the album's \"Track Count\" tag when available, or by "
            "comparing how many of that album's tracks each copy "
            "actually has otherwise. This only pre-checks rows you could "
            "already check yourself — nothing is removed until you click "
            "Apply, and low-confidence \"possible duplicate\" rows are "
            "never auto-checked by this, same as everywhere else.",
            "Fixed a bug in the same completeness comparison (caught "
            "during this release's testing, never shipped) where, if "
            "neither album copy had a \"Track Count\" tag, the larger "
            "copy could be left unclassified instead of being recognized "
            "as the complete one — which meant the smaller copy's "
            "overlapping tracks were silently skipped instead of being "
            "pre-checked.",
        ],
    ),
    ChangelogEntry(
        version="2.0",
        date="2026-08-16",
        changes=[
            "Fixed a bug where two copies of the exact same song (same "
            "artist, same title) could be missed by duplicate detection "
            "entirely whenever their lengths differed by more than a few "
            "seconds — for example a radio edit next to an album version, "
            "or a re-imported copy tagged with a slightly different Total "
            "Time. Previously, an artist+title match was only kept if "
            "every copy's length also landed within a few seconds of each "
            "other; copies outside that window were silently dropped by "
            "both the exact and the near-miss (\"fuzzy\") passes, so a "
            "library could show zero duplicates for a song you could see "
            "listed twice in iTunes. These are now always surfaced — "
            "labeled \"Same title — different length\" in the duplicates "
            "list — for you to review, the same way a near-miss match "
            "already was, and are never auto-selected for cleanup without "
            "you looking at them first.",
            "Fixed duplicate detection silently skipping any song whose "
            "title is made up entirely of symbols, like Ty Dolla $ign's "
            "\"$\" — the title-matching step stripped it down to nothing "
            "internally and treated that as \"no title at all,\" so two "
            "real duplicate copies of a symbol-titled song were never "
            "matched by either the exact or the near-miss pass, and "
            "iTunes could still show them as duplicates after a \"cleaned\" "
            "run. These now match correctly, the same as any other "
            "same-artist, same-title duplicate.",
            "Added 8 new theme palettes — Paper, Slate, Sand, and Mint "
            "(light), and Midnight, Charcoal, Espresso, and Forest (dark) "
            "— in Settings → General, as a new \"Theme\" option alongside "
            "the existing Appearance (Match Windows/Light/Dark) and "
            "Accent color choices. Each gives the whole app a different "
            "background/surface/text color treatment (not just a "
            "different accent highlight), and can be paired with any of "
            "the 10 existing accent colors. Previewed live before "
            "confirming, same as the existing appearance/accent settings; "
            "\"No override\" (the default) keeps the original Light/Dark "
            "look exactly as before.",
            "Fixed the Paper, Slate, Sand, and Mint theme palettes not "
            "actually applying when selected in Settings — the app-wide "
            "stylesheet and this window's stylesheet could get out of "
            "sync, leaving the plain Light look showing through instead "
            "of the chosen palette. All 8 theme palettes now apply "
            "correctly and stay in sync everywhere.",
            "Fixed the duplicate-group detail panel having no way to "
            "close it once expanded, other than clicking the same table "
            "row again. Added a \u2715 Close button to the panel itself, "
            "and pressing Escape now closes it too.",
            "Added keyboard shortcuts: Ctrl+F to jump to the search box, "
            "and Escape to close an expanded duplicate-group detail "
            "panel, alongside the existing Ctrl+A (select all), Ctrl+Z "
            "(undo last rebuild), and Ctrl+Enter (delete duplicates) "
            "shortcuts.",
        ],
    ),
    ChangelogEntry(
        version="1.7",
        date="2026-08-16",
        changes=[
            "Fixed the duplicate-group detail panel being able to grow "
            "so tall (on a group with many copies) that the window's "
            "titlebar/close button could become unreachable. The table "
            "and the expanded row are now split by a draggable handle — "
            "click and hold the border at the top of the expanded row "
            "to make it bigger or smaller — and the expanded row starts "
            "at a sensible height instead of growing to fit however "
            "many copies are in the group.",
            "Added a volume slider and mute button to each duplicate "
            "copy's inline audio preview player, and shrank the "
            "preview player's play button, seek bar, and time label "
            "so it takes up less room in the expanded row.",
            "Rebuild library now only keeps the single most recent "
            "\"iTunes Library.itl.bak_…\" (and matching .xml) backup in "
            "your iTunes folder instead of accumulating one per rebuild "
            "— older backups are deleted automatically once a new one "
            "is made, to save disk space. Backup filenames now use a "
            "day/month/year, 24-hour-time stamp (e.g. "
            "\"iTunes Library.itl.bak_16-08-2026_143005\") instead of "
            "the previous year-first stamp.",
        ],
    ),
    ChangelogEntry(
        version="1.6",
        date="2026-08-16",
        changes=[
            "Fixed buttons, table headers, and the songs list not "
            "responding to clicks in most of the window -- only the "
            "top toolbar (Restore backup, Save restore point, etc.) "
            "still worked. Re-verified the notification-overlay fix "
            "from the last update and hardened it further so this "
            "can't come back.",
            "The \"What's new\" screen now uses simpler, shorter "
            "wording, and each version's changes are grouped under an "
            "emoji so you can spot new features, fixes, and other "
            "changes at a glance.",
        ],
    ),
    ChangelogEntry(
        version="1.5",
        date="2026-08-16",
        changes=[
            "Added a \"What changed since last export\" summary shown "
            "automatically when re-opening a Library.xml that's newer "
            "than the last time this app saw it -- lists tracks added, "
            "removed, or with changed metadata (name/artist/album/"
            "rating/play count) and any playlist count change since "
            "then, with a few concrete examples. Only appears once "
            "there's a previous export on record for that file to "
            "compare against; the very first time a library is opened, "
            "nothing is shown. A background \"check for new duplicates "
            "weekly\" re-scan still gets its existing toast summary "
            "instead, so it isn't interrupted by a dialog for something "
            "that ran unprompted.",
            "Fixed every button in the window -- \"Open Library.xml…\", "
            "\"Restore backup…\", \"Select all exact\", \"Select all "
            "high-confidence\", \"Exclude reviewed-out permanently\", "
            "and \"Clean up duplicates…\" -- becoming completely "
            "unpressable, while dragging a Library.xml file onto the "
            "window to open it still worked. The always-on-top toast-"
            "notification overlay that floats over the whole window was "
            "built to let clicks pass through to whatever's underneath "
            "it except its own notification banners, but was "
            "accidentally configured the opposite way, so it silently "
            "absorbed every click anywhere in the window instead -- "
            "drag-and-drop was unaffected because it's handled by the "
            "window itself, not routed through this overlay. Clicking "
            "is back to normal everywhere; toast notifications "
            "(including their own close buttons) still work exactly as "
            "before.",
            "Fixed building the consolidation plan (the \"Building "
            "consolidation plan...\" step at 92% on Open) becoming very "
            "slow, and appearing to hang, on large libraries with many "
            "duplicate groups -- it was re-scanning every playlist's "
            "full track list from scratch for each duplicate group found; "
            "it's now a single indexing pass over all playlists up "
            "front, so the time this step takes no longer multiplies "
            "with how many duplicates and playlists a library has.",
            "Fixed the app appearing to freeze right at 100% after "
            "opening a large library -- opening a library was silently "
            "rebuilding the consolidation plan a second time on the "
            "main window (to apply any permanently-excluded groups) "
            "using the same slow path above; now that plan-building "
            "itself is fast, this second pass no longer blocks the "
            "window.",
            "Fixed the duplicates list taking a long time to finish "
            "appearing after a scan found a very large number of "
            "possible duplicates (4000+) -- same root cause as the two "
            "fixes above: the list can only be drawn once plan-building "
            "finishes, so a slow plan made the list look slow too even "
            "though drawing the rows themselves was already fast.",
            "Fixed \"Clean up duplicates\" sometimes staying "
            "greyed-out/unclickable after opening a large library -- it "
            "only becomes clickable once the duplicates list has "
            "finished populating, which the fixes above were delaying "
            "far longer than intended on big libraries.",
            "Fixed the built app showing a \"module not found\"-style "
            "error popup when iTunesLibraryConsolidator.exe was run from "
            "the project root (or after build.bat/install.bat finished) "
            "instead of from inside the dist\\iTunesLibraryConsolidator "
            "folder -- the step that copies the freshly built app into "
            "the project root wasn't copying the folder of DLLs/"
            "libraries PyInstaller places alongside the exe, only the "
            "exe itself, so the root copy was missing files it needs to "
            "actually run. build.bat, build_windows.bat, and "
            "install.bat all copy the complete build output now.",
            "Fixed build.bat sometimes failing at step [3/4] with "
            "\"The system cannot find the batch label specified - "
            "unlock_dist\" and aborting the build -- an unescaped \"&\" "
            "inside the PyInstaller PowerShell command line could throw "
            "off how the relaunched (minimized) copy of build.bat reads "
            "its own script, causing it to lose track of an unrelated "
            "step later in the file. The PowerShell command is now "
            "passed in a way that avoids the ambiguity entirely.",
            "Fixed build.bat leaving a broken .venv folder behind after "
            "a failed build (e.g. dependency install interrupted, wrong "
            "Python on PATH), which then got silently reused -- and kept "
            "failing -- on every following build attempt. build.bat now "
            "deletes .venv whenever a build fails, so the next run "
            "always starts from a clean environment.",
            "Fixed \"Clean up duplicates\" still sometimes staying "
            "greyed-out/unclickable after a library finished loading, "
            "even after the earlier plan-building speed fix above -- "
            "the button's enabled state was computed right at the start "
            "of finishing the load, from data that hadn't been set yet, "
            "and was only ever corrected afterward as a side effect of "
            "populating the duplicates list. If anything else in "
            "between raised an error, that correction never ran and the "
            "button was left disabled with no error shown. It's now "
            "always set once, at the very end of finishing a load, and "
            "that now happens even if something in between fails.",
        ],
    ),
    ChangelogEntry(
        version="1.0",
        date="2026-08-16",
        changes=[
            "Added \U0001F4C2 \"Find missing files in folder\u2026\" to "
            "the Library Health tab, next to the existing \"Locate "
            "missing file\u2026\" list: pick one root folder and every "
            "track currently showing missing/broken (the same tracks "
            "iTunes/Apple Music marks with a \"!\") is searched for by "
            "filename under that folder at once, instead of relinking "
            "one at a time. Useful after moving playlists/music into a "
            "different subfolder layout inside the iTunes folder. Shows "
            "matches for review before relinking anything -- nothing is "
            "changed automatically.",
            "This is the first full release: v1.0. Every earlier build "
            "was a pre-release; those are now numbered sequentially as "
            "\"0.1(pre)\" through \"0.50(pre)\" (oldest to newest) below "
            "instead of their original version numbers, so the "
            "pre-release history reads as a straightforward run-up to "
            "this release. Nothing about what changed in each of those "
            "versions was altered -- only how they're numbered.",
        ],
    ),
    ChangelogEntry(
        version="0.50(pre)",
        date="2026-08-16",
        changes=[
            "Fixed the Windows installer (dist_config/setup.iss) not "
            "resolving \"Failed to load Python DLL ... LoadLibrary: The "
            "specified module could not be found\" for anyone missing "
            "the Microsoft Visual C++ Redistributable (x64) -- the "
            "v1.10.2 UPX fix only addressed the case where that error "
            "came from a UPX-mangled DLL; a genuinely missing "
            "redistributable on the machine produces the identical "
            "error message pointing at the same DLL. The installer now "
            "silently installs the redistributable during setup (a "
            "no-op, adding about a second, on the many machines that "
            "already have a compatible copy). Anyone installing the "
            "plain iTunesLibraryConsolidator.exe without the installer "
            "still needs to install it manually -- see the new "
            "troubleshooting note in dist_config/installer_README.md.",
        ],
    ),
    ChangelogEntry(
        version="0.49(pre)",
        date="2026-08-16",
        changes=[
            "Fixed the built .exe sometimes failing to start with "
            "\"Failed to load Python DLL ... LoadLibrary: The specified "
            "module could not be found.\" The build was UPX-compressing "
            "the bundled Python DLL (and a few other core runtime/Qt "
            "DLLs), which can silently produce a copy Windows' loader "
            "refuses to load even though the build itself reports "
            "success. Those specific files are now left uncompressed; "
            "UPX still compresses everything else, so the built app is "
            "unaffected in size for anyone not hitting this.",
            "Added test fixtures covering malformed and truncated "
            "Library.xml, non-ASCII (CJK, accented, and emoji) track "
            "and playlist names, and playlist folders with nested "
            "child playlists, so the parser's handling of these is now "
            "verified by the automated test suite instead of only the "
            "single synthetic fixture used before.",
        ],
    ),
    ChangelogEntry(
        version="0.48(pre)",
        date="2026-08-16",
        changes=[
            "Added \U0001F517 \"Merge tracks...\" to the toolbar: manually "
            "merge any two tracks the automatic scan didn't group "
            "together at all (different enough tags that even the fuzzy "
            "pass never caught them), by picking both from a searchable "
            "list. Shows up in the table tagged \"Manually merged\" and "
            "can be reviewed, unchecked, or undone like any other group. "
            "This is separate from the existing \"Keep this one "
            "instead\", which only re-picks the canonical track within a "
            "group already detected -- that control is unchanged.",
            "Added a \"Check for new duplicates automatically\" option "
            "(Settings \u2192 General): once per launch, if it's been at "
            "least a set number of days (default weekly) since your "
            "most recently opened library was last scanned, it's "
            "re-scanned in the background and a notification reports "
            "what was found. Off by default. Built entirely from scan "
            "history this app already recorded for the growth timeline "
            "-- nothing new is stored just for this.",
        ],
    ),
    ChangelogEntry(
        version="0.47(pre)",
        date="2026-08-16",
        changes=[
            "Added a telemetry-free local crash reporter: an unexpected "
            "error now also saves a self-contained crash dump file "
            "(traceback, app/OS/Qt versions, and a short trail of recent "
            "actions) to disk, viewable under Settings → Diagnostics → "
            "Crash dumps. Nothing is ever sent anywhere automatically — "
            "it's a local file you can choose to attach to a bug report. "
            "The existing rolling error log is unchanged and still works "
            "exactly as before.",
            "Added a duplicate-count trend comparison: the summary bar "
            "and \U0001F4C8 \"View growth timeline...\" now note how this "
            "scan compares to the same library's last recorded scan "
            "(e.g. \"12 fewer duplicates than last scan\"), built from "
            "the same scan history already used for the growth timeline "
            "chart.",
            "Added \U0001F4CC \"Save restore point...\" to the toolbar: "
            "save a backup of the current library with your own label "
            "(e.g. \"before spring cleaning\") any time, on top of the "
            "existing automatic per-load/per-apply backups. Named "
            "restore points show up alongside automatic ones in \u23EA "
            "\"Restore backup...\", marked with \U0001F4CC so they're "
            "easy to tell apart at a glance.",
        ],
    ),
    ChangelogEntry(
        version="0.46(pre)",
        date="2026-08-16",
        changes=[
            "Added a pluggable duplicate-detection strategy layer "
            "(core/duplicate_strategies.py): the exact and fuzzy matching "
            "passes can now be composed and independently tested as "
            "interchangeable strategies instead of two hardcoded passes, "
            "and a new metadata fingerprint strategy (matching on iTunes' "
            "Persistent ID, or file size + duration as a fallback) can "
            "catch duplicates whose title/artist tags were edited too "
            "heavily for fuzzy matching to still recognize. Purely "
            "additive under the hood \u2014 the default exact-then-fuzzy "
            "scan behavior everywhere in the app is unchanged.",
            "Changed: QSS spacing, corner-radius, and font-size values "
            "used throughout the app's stylesheet are now defined once "
            "in a shared design-token module (ui/design_tokens.py) "
            "instead of being repeated as literals across the light and "
            "dark themes. No visual change \u2014 every screen renders "
            "pixel-identical to before.",
        ],
    ),
    ChangelogEntry(
        version="0.45(pre)",
        date="2026-08-16",
        changes=[
            "\U0001F512 Fixed: backup snapshots (auto-backup-on-load and "
            "pre-consolidation backups) are now checksummed when saved "
            "and that checksum is verified before \u23EA \"Restore backup\" "
            "hands the data back. A corrupted snapshot (partial write, "
            "disk bit-rot, a hand-edited cache file) now fails loudly "
            "with a clear \"Backup snapshot corrupted\" message instead "
            "of silently restoring bad data. Snapshots saved by earlier "
            "versions have no checksum to check against and continue to "
            "restore exactly as before \u2014 this doesn't make any "
            "existing backup unrestorable.",
            "\U0001F3A7 Added Spotify import: \U0001F3A7 Import Spotify "
            "library\u2026 on the toolbar reads a Spotify data export "
            "(the .zip from Settings \u2192 Account \u2192 Privacy \u2192 "
            "\"Download your data\", or the folder it's extracted into) "
            "and reports how many tracks and playlists it found, plus "
            "how many of those tracks already appear to be in your "
            "currently loaded library. Entirely offline and read-only "
            "\u2014 no account sign-in, no network access, and nothing "
            "about your library or the export is changed. Built on the "
            "provider plugin architecture added in v1.8.0.",
        ],
    ),
    ChangelogEntry(
        version="0.44(pre)",
        date="2026-08-16",
        changes=[
            "\U0001F3A8 Added 10 accent color themes (Blue, Purple, Pink, "
            "Red, Orange, Yellow, Green, Teal, Graphite, Indigo) in "
            "Settings \u2192 General, each recoloring buttons, tabs, "
            "progress bars, and other accented text/UI app-wide. Pick "
            "any accent alongside the existing Light/Dark/Match Windows "
            "appearance mode, and preview it live before confirming.",
            "\U0001F50C Added an internal provider plugin architecture "
            "(core/providers/) laying the groundwork for future "
            "streaming-service integrations such as the Apple Music API "
            "and Spotify library exports. Not user-facing yet in this "
            "release \u2014 no external service is connected \u2014 this "
            "adds the interface future import/export support will plug "
            "into.",
        ],
    ),
    ChangelogEntry(
        version="0.43(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added keyboard shortcuts for common actions: Ctrl+O opens "
            "a library, Ctrl+Enter cleans up the currently checked "
            "duplicates, Ctrl+A selects all exact + high-confidence "
            "groups, and Ctrl+Z undoes the most recent library rebuild.",
            "✨ Added a \"Recent…\" toolbar menu listing recently opened "
            "Library.xml files, so reopening one is a single click "
            "instead of browsing for it again.",
            "✨ Added audio preview playback in the duplicate-review "
            "detail panel: play/pause and seek each copy in a group "
            "right there, to manually confirm true duplicates by ear "
            "before deciding what to keep.",
            "✨ The duplicates table's column order and widths are now "
            "remembered between sessions — drag a column to a new "
            "position or resize it, and it stays that way next time you "
            "open the app.",
        ],
    ),
    ChangelogEntry(
        version="0.42(pre)",
        date="2026-08-16",
        changes=[
            "🛠️ Changed: the fuzzy \"possible duplicate\" scan now spends "
            "a time-boxed budget instead of a fixed total-comparison "
            "count, and shows a live \"Still scanning for possible "
            "duplicates... (N% of scan time budget used)\" status message "
            "while it runs — very large or unevenly-organized libraries "
            "now get a predictable wait with visible progress instead of "
            "an invisible reduction in how thorough the scan was.",
            "✨ Added embedded-artwork reading for FLAC files (the same "
            "cover-art preview already shown for MP3/MP4/M4A now also "
            "works for .flac tracks). Apple Lossless (ALAC) artwork was "
            "already covered, since ALAC audio is packaged inside the "
            "same .m4a container this app already reads.",
        ],
    ),
    ChangelogEntry(
        version="0.41(pre)",
        date="2026-08-16",
        changes=[
            "🛠️ Changed: the Windows build (build.bat/build_windows.bat/"
            "install.bat) now produces a standalone-folder app instead of "
            "a single-file .exe, and copies the built "
            "iTunesLibraryConsolidator.exe (with its dependent files) "
            "straight into the project root on a successful build — no "
            "more digging through the \"dist\" folder to find it.",
            "✨ Added: build.bat now brings the freshly built app's window "
            "to the foreground when it auto-launches after a successful "
            "build, instead of leaving it to open behind whatever else "
            "is on screen.",
        ],
    ),
    ChangelogEntry(
        version="0.40(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added a \"Backups\" tab to Settings (During cleanup) to "
            "manage the automatic backup snapshots saved to the local "
            "SQLite cache: set how many recent backups to keep (default "
            "100, or Unlimited), see how many are currently stored, and "
            "delete the oldest ones on demand. The cap is also applied "
            "automatically right after every new backup is saved, so the "
            "cache file no longer grows without limit by default.",
            "🛠️ Changed: the duplicate-confidence tier labels and colored "
            "badges (Exact match / High confidence / Possible duplicate) "
            "are now driven from a single enum-backed table instead of "
            "two separately hand-maintained lookups, so they can no "
            "longer drift out of sync with each other. No visible change "
            "in behavior or appearance.",
        ],
    ),
    ChangelogEntry(
        version="0.39(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added \"Locate missing file…\" to the Library Health tab: "
            "songs with a missing or broken file link now get a button "
            "right there to browse to where the file actually is and "
            "relink it, instead of only ever showing a count with "
            "nothing to click.",
            "✨ Added \"Fix missing artwork…\" to the Library Health tab. "
            "This app doesn't fetch artwork from the internet, so it "
            "looks for another local copy of the same song already in "
            "your library that has embedded cover art and offers to use "
            "that copy's art — and says plainly when no local copy with "
            "art can be found, rather than pretending to search further.",
            "✨ Added a \"View growth timeline…\" chart to the Library "
            "Health tab, plotting total tracks and duplicate tracks "
            "found each time this app has scanned your library over "
            "time, so you can see accumulation trends instead of only "
            "a single point-in-time count.",
            "🛠️ Fixed: several confirmations (like \"N group(s) will now "
            "be skipped permanently\") previously only ever flashed "
            "through the status bar — a single line of text that's also "
            "overwritten by load/clean-up progress messages, and easy to "
            "miss entirely. These now show as a non-blocking toast "
            "notification in the corner of the window that stays visible "
            "for a few seconds (or until dismissed) independent of "
            "whatever else the status bar is doing.",
        ],
    ),
    ChangelogEntry(
        version="0.38(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added a small annotated picture of iTunes's own \"Choose "
            "Library...\" prompt to the \"Library rebuilt\" success dialog, "
            "with that button circled — so there's something to look for "
            "on screen when iTunes reopens, not just a paragraph of "
            "instructions that's easy to skim past.",
            "✨ Added a pre-flight check (free disk space, write "
            "permission on the iTunes folder, whether iTunes is already "
            "running) to \"Rebuild library now…\", run before any part of "
            "the quit/backup/copy/relaunch sequence starts. A blocking "
            "problem is now caught up front, before iTunes is closed or "
            "any existing library file is touched, instead of surfacing "
            "midway through.",
        ],
    ),
    ChangelogEntry(
        version="0.37(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added auto-detect for your iTunes folder on first launch: "
            "the app now scans common drive letters for a folder that "
            "already looks like a real iTunes data folder (containing "
            "iTunes Library.itl) and offers it for confirmation, instead "
            "of only ever asking you to browse for it blind. You can "
            "still browse manually, and the detected/entered folder can "
            "now also be set or changed any time from Settings → General "
            "→ iTunes folder, not just from the first-launch prompt or "
            "\"Rebuild library now…\".",
            "✨ Added tooltips to the \"Backups kept\" list shown after a "
            "rebuild, explaining what the \".bak_<timestamp>\" files are "
            "(an automatic safety copy made before that rebuild, with "
            "when it was made) and that they're safe to leave in place — "
            "hover any listed backup to see it.",
            "🛠️ Error and warning dialogs no longer show raw technical "
            "detail (WinError/errno codes, COM error tuples, Python "
            "exception class names) — those popups now describe what "
            "happened in plain language, with the \"what to try\" "
            "guidance unchanged. The full technical detail is still "
            "recorded in the app's error log (Settings → Diagnostics) "
            "exactly as before, for anyone who needs it to troubleshoot "
            "or report a problem.",
        ],
    ),
    ChangelogEntry(
        version="0.36(pre)",
        date="2026-08-16",
        changes=[
            "✨ Added a one-click \"Undo last rebuild\" (toolbar, and also "
            "offered right after a rebuild finishes): restores the most "
            "recent iTunes Library.itl/.xml backup pair that \"Rebuild "
            "library now…\" made automatically, instead of having to find "
            "and rename those timestamped backup files by hand.",
            "✨ Added \"Remove duplicate files from disk…\", offered after a "
            "rebuild completes: permanently deletes the actual audio "
            "files for the copies just removed from your library (not "
            "the copy you kept), with an itemized confirmation first and "
            "a full success/failure summary after — nothing is deleted "
            "silently or automatically.",
            "🎨 Error/warning/info dialogs are now colour-coded by "
            "severity (blocking errors in red, warnings in amber, "
            "routine notices in blue) via a coloured accent strip, so a "
            "real problem no longer looks the same weight as a routine "
            "confirmation.",
        ],
    ),
    ChangelogEntry(
        version="0.35(pre)",
        date="2026-08-15",
        changes=[
            "✨ Added a real step tracker (Quitting iTunes → Backing up → "
            "Copying → Relaunching) to \"Rebuild library now…\", instead "
            "of a single spinner with no indication of which part of the "
            "sequence is currently happening. The rebuild also now runs "
            "off the main thread, so the window stays responsive while "
            "it works.",
            "✏️ Settings is now grouped by workflow stage — \"Before you "
            "scan\" (General, Accessibility), \"During cleanup\" (Duplicate "
            "Detection, Diagnostics), and \"Reference\" (Changelog) — "
            "instead of a flat alphabetical tab list, so the setting "
            "you're after is easier to find at the point you'd actually "
            "want it. Every individual settings page, tooltip, and saved "
            "value is unchanged; only how they're grouped changed.",
            "🧹 Removed the old standalone .bat rebuild-script generator "
            "and its dead code path (its own \"Generate rebuild script…\" "
            "button was already removed back in v1.3.19 -- see \"What's "
            "new in v1.3.19\" in the README). The in-app \"Rebuild library "
            "now…\" button already does the same quit/backup/copy/relaunch "
            "sequence more safely, with checks the .bat version never had "
            "(verified copy sizes, confirmed process exit, stray-.xml "
            "cleanup), so keeping both implementations around only risked "
            "them drifting apart.",
        ],
    ),
    ChangelogEntry(
        version="0.34(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed the app sometimes staying open in Task Manager after "
            "closing the window with the titlebar's X button, with no "
            "window visible on screen. Window shutdown now always finishes "
            "closing (and quits the app) even if something during cleanup "
            "went wrong, instead of potentially leaving the process behind.",
            "✨ Added a persistent status strip, visible on every tab, "
            "showing exactly which iTunes folder is currently set for "
            "\"Rebuild library now…\" — no more guessing or reopening the "
            "folder picker just to check.",
            "⚡ Large libraries now populate the duplicates table noticeably "
            "faster, with less UI stutter while it fills in.",
            "🧹 Removed the old \"live COM import\" code path (and its "
            "explanatory comments) that always failed on classic Windows "
            "iTunes — confirmed impossible on every real machine, see "
            "\"What's new in v1.6.1\" below. \"Rebuild library now…\" "
            "already went straight to the working file-swap method after "
            "that fix; this just deletes the dead code and stub function "
            "that fix left behind, and the still-working \"Live iTunes "
            "sync\" feature (see the README) is unaffected — that's a "
            "separate, working feature that mirrors removed duplicate "
            "tracks into a running iTunes and was never part of this dead "
            "path.",
        ],
    ),
    ChangelogEntry(
        version="0.33(pre)",
        date="2026-08-15",
        changes=[
            "✏️ Simplified the wording on the \"Library rebuilt\" success "
            "dialog and dropped the confusing technical explanation of "
            "why live import isn't possible. It now just tells you "
            "plainly to click \"Choose Library...\", pick the folder, and "
            "manually import the deduped XML -- that last click still "
            "can't be automated (classic Windows iTunes has no "
            "supported way to script it), but the message no longer "
            "makes it sound like something went wrong.",
        ],
    ),
    ChangelogEntry(
        version="0.32(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed \"Rebuild library now…\" failing with \"Could not "
            "copy the cleaned XML into the iTunes folder: [WinError 2]\" "
            "when the cleaned/deduplicated XML had been saved directly "
            "inside the iTunes folder itself. The step that clears out "
            "other stray .xml files before relaunch was matching by "
            "filename only, so it didn't recognize the cleaned XML as "
            "the file this same rebuild was about to use -- it backed it "
            "up and removed it a moment before trying to copy it, which "
            "surfaced as a confusing \"file not found\" error even though "
            "nothing had actually been moved or deleted by the user. The "
            "cleaned XML is now always excluded from that cleanup step "
            "by its real path, and the copy step re-checks the source "
            "file exists immediately before running, with a clearer "
            "message if it's genuinely missing.",
        ],
    ),
    ChangelogEntry(
        version="0.31(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed \"Rebuild library now…\" occasionally leaving iTunes "
            "with a blank rebuilt library instead of your cleaned one, if "
            "copying the cleaned XML into the iTunes folder was "
            "interrupted partway (e.g. antivirus or a sync tool briefly "
            "grabbing the file). The copy now goes to a temp file first, "
            "is verified to match the source exactly, and is only then "
            "atomically put in place as iTunes Library.xml -- so iTunes "
            "is never relaunched against a missing or half-written file, "
            "and \"Choose Library...\" now reliably rebuilds the .itl "
            "from your actual cleaned library every time.",
        ],
    ),
    ChangelogEntry(
        version="0.30(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed \"Rebuild library now…\" sometimes not showing "
            "iTunes's \"Choose Library...\" prompt on relaunch when other "
            "stray .xml files were sitting in the iTunes folder alongside "
            "iTunes Library.xml -- those are now backed up (never "
            "deleted) and cleared out of the folder before the cleaned "
            "XML is copied in and iTunes is relaunched, the same way the "
            "old iTunes Library.itl already was.",
            "✨ Added a one-time prompt on startup (Windows only) asking "
            "you to locate your real iTunes data folder, instead of only "
            "asking the first time you click \"Rebuild library now…\" -- "
            "useful since that folder isn't always the default "
            "Music\\iTunes path (e.g. an external drive or a "
            "OneDrive-redirected Music folder). Skippable, and only asked "
            "again if you haven't confirmed a folder before.",
        ],
    ),
    ChangelogEntry(
        version="0.29(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed a bug where \"Rebuild library now…\" always reported "
            "\"iTunes rejected the XML import\" before falling back to the "
            "file-swap-and-relaunch method. The live import step was "
            "calling a COM method classic Windows iTunes doesn't actually "
            "have, so it failed every single time, on every machine, no "
            "matter what was in the library -- it also launched iTunes "
            "unnecessarily first when it wasn't already open, only to "
            "quit it again moments later for the real relaunch. The "
            "file-swap rebuild itself (backup, swap, relaunch, \"Choose "
            "Library...\") was never affected and continues to work "
            "exactly as before -- this only removes the always-failing "
            "shortcut attempt in front of it, so rebuilding is faster and "
            "no longer shows a confusing rejection message first.",
        ],
    ),
    ChangelogEntry(
        version="0.28(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ build.bat now also finds, unlocks, and removes any old "
            "installed copy of the app it finds registered on this "
            "machine (from a previous install.bat run, possibly in a "
            "different folder) before building, so Apps & features stops "
            "pointing at a stale install. This project's own current "
            "dist/build output was already handled before this change; "
            "only the separate old-install case is new.",
            "✨ Added a \"Jump to version...\" dropdown above the "
            "changelog in both Help → What's new… and Settings → "
            "Changelog, so a specific release's notes can be found "
            "directly instead of scrolling and expanding sections one "
            "at a time. Both dropdowns share the same list, so they can "
            "never drift apart.",
            "✨ Added two more one-click batch selections next to "
            "\"Select all (exact + high confidence)\": \"Select all "
            "exact\" and \"Select all high-confidence\" each select "
            "precisely that tier and nothing else.",
            "✨ Added \"Exclude reviewed-out permanently\": remembers "
            "every group you've marked as not duplicates so it's "
            "automatically skipped on every future library you open, "
            "not just for the current session.",
            "🔀 Refactored the main window's widget-building code into "
            "smaller, reusable widget classes (toolbar, header, filter "
            "row, table, empty state). No visible or behavioral change -- "
            "purely an internal code-organization cleanup.",
        ],
    ),
    ChangelogEntry(
        version="0.27(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed a build-script issue where a failed build window "
            "could stay minimized in the taskbar with no visible error, "
            "making it look like the build had silently closed. A failed "
            "build now restores its window automatically so the error "
            "and \"press any key\" prompt are actually visible.",
            "🛠️ Folded the separate unlock_dist.bat helper directly into "
            "build.bat (same lock-clearing logic, now one script instead "
            "of two) so there's nothing extra to keep alongside it.",
        ],
    ),
    ChangelogEntry(
        version="0.26(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed \"Rebuild library now\" sometimes leaving iTunes with "
            "a blank library instead of your cleaned-up one: it now tries "
            "importing the cleaned library straight into iTunes while "
            "it's running, so the Library/Music screen updates right "
            "away with nothing left to click. The previous close-and-"
            "reopen method (which relied on a \"Choose Library...\" "
            "prompt that couldn't be shown automatically) is now only "
            "used as a fallback if the direct import isn't possible on "
            "your machine.",
        ],
    ),
    ChangelogEntry(
        version="0.25(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed a mix-up in the \"Duplicates deleted\" screen: there "
            "were two buttons that did almost the same thing. We removed "
            "the extra one, so now there's just one clear \"Rebuild "
            "library now\" button.",
            "🛠️ Fixed the after-cleanup instructions on Windows showing "
            "extra manual steps you didn't need, since the \"Rebuild "
            "library now\" button already does them for you. Those steps "
            "still show up on other setups where you do need to do them "
            "by hand.",
            "✨ The \"What's new\" list in Settings now looks and works the "
            "same as the one under Help, with sections you can open and "
            "close.",
            "🔀 Settings tabs are now always in the same order: "
            "Accessibility, Changelog, Diagnostics, Duplicate Detection, "
            "General.",
            "🎨 Added small icons next to many buttons and tab names "
            "around the app, just to make them easier to spot at a "
            "glance. Nothing about how they work has changed.",
        ],
    ),
    ChangelogEntry(
        version="0.24(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed the app slowing down when loading a lot of album "
            "art at once. Artwork now loads more efficiently in the "
            "background.",
            "🛠️ Fixed the duplicates list looking empty for a moment "
            "while a big library was loading. It now shows a loading "
            "placeholder so you know it's working.",
            "✨ Added a heads-up for smart playlists: if cleaning up "
            "duplicates might change something that affects one of your "
            "smart playlists, you'll now see a warning so you can double-"
            "check that playlist afterward.",
            "✨ The \"What's new\" screen is now organized into sections "
            "you can open and close, instead of one long list.",
        ],
    ),
    ChangelogEntry(
        version="0.23(pre)",
        date="2026-08-15",
        changes=[
            "🛠️ Fixed album art not showing up at all after loading your "
            "library. This was caused by a small formatting bug that's "
            "now fixed, and it also fixes the same missing-artwork issue "
            "in the Library Health tab.",
            "🛠️ Fixed a risk of corrupting your library file if it was "
            "accidentally opened in two windows at once. The app now "
            "shows a clear message instead of letting that happen.",
            "🎨 Replaced the old-style menu bar with a proper toolbar, so "
            "the main buttons (Open, Restore backup, Save summary, "
            "Settings, What's new) are easier to find and use.",
            "✨ Added a new duplicate check for whole albums: Library "
            "Health can now spot albums that seem to have been added to "
            "your library more than once (for example, after re-ripping "
            "them at better quality). This works alongside the existing "
            "song-by-song duplicate check, not instead of it.",
        ],
    ),
    ChangelogEntry(
        version="0.22(pre)",
        date="2026-08-14",
        changes=[
            "🛠️ Fixed a crash that could happen when opening up a "
            "duplicate group to see more detail.",
            "✨ Opening a duplicate group now shows exactly which "
            "playlists each copy belongs to, not just how many.",
            "✨ The confirmation screen before cleaning up duplicates now "
            "explains, in plain language, what \"keep\" and \"remove\" "
            "mean — and makes clear that nothing happens until you click "
            "Continue.",
            "✏️ Simplified the wording used throughout the app and its "
            "tooltips to be easier to understand.",
        ],
    ),
    ChangelogEntry(
        version="0.21(pre)",
        date="2026-08-14",
        changes=[
            "⚙️ You can now fine-tune how strict duplicate matching is, "
            "under Settings → Duplicate Detection, with a button to reset "
            "back to the defaults.",
            "🚀 Scanning for duplicates is now faster on very large "
            "libraries.",
            "🛠️ If iTunes is open on Windows, the app now tries again a "
            "few times when removing a song, in case iTunes doesn't "
            "respond right away.",
            "✨ Added helpful tooltips to every button and control that "
            "didn't already have one, so it's clearer what each one does.",
        ],
    ),
    ChangelogEntry(
        version="0.20(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed a bug where restoring a backup could quietly change "
            "a song's \"Date Added\" to the wrong value. This could have "
            "caused an error later on if that restored library was "
            "cleaned up again.",
        ],
    ),
    ChangelogEntry(
        version="0.19(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed the build process failing for anyone building the "
            "app from source, caused by an outdated dependency that's no "
            "longer available. It now uses a current one instead.",
            "✨ The build progress window now shows a running timer and "
            "moves smoothly through each step, instead of appearing to "
            "freeze partway through.",
        ],
    ),
    ChangelogEntry(
        version="0.18(pre)",
        date="2026-08-11",
        changes=[
            "✨ Changing the app's appearance in Settings now only saves "
            "your choice once you click OK — clicking Cancel or closing "
            "the window puts things back the way they were.",
            "🎨 Match confidence (how sure the app is that two songs are "
            "duplicates) now shows as a colored badge, making it easier "
            "to tell the three levels apart at a glance.",
            "✨ Added a \"Why flagged\" note to each duplicate, explaining "
            "in plain language why those songs were matched.",
            "✨ You can now click a column header to sort the duplicates "
            "list, and select multiple rows at once to review them "
            "together.",
            "✨ Before cleaning up duplicates, you'll now see an exact "
            "preview of what will be kept, what will be removed, and "
            "which playlists will be updated — not just a summary count.",
            "✨ You can now drag a library file straight onto the window "
            "to open it, instead of using the Open menu.",
        ],
    ),
    ChangelogEntry(
        version="0.17(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed a rare issue where the app's internal error log "
            "could get corrupted, and made error logging faster and more "
            "efficient overall.",
            "🛠️ Fixed error messages sometimes suggesting you re-export "
            "your library file when that wasn't actually the problem.",
        ],
    ),
    ChangelogEntry(
        version="0.16(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed the app's error log occasionally growing larger "
            "than it should, when errors included non-English text (like "
            "certain song or artist names).",
            "🛠️ Fixed error messages sometimes suggesting you re-export "
            "your library file for problems that had nothing to do with "
            "your library file.",
        ],
    ),
    ChangelogEntry(
        version="0.15(pre)",
        date="2026-08-11",
        changes=[
            "⚙️ Added a Settings screen (File → Settings) with four tabs: "
            "General (choose Light or Dark appearance), Accessibility "
            "(larger text option), Diagnostics (view or clear the error "
            "log), and Changelog (the same release notes shown under "
            "Help → What's new).",
            "🛠️ Fixed the installer showing the wrong version number "
            "under Apps & Features. It now always shows the version that "
            "was actually installed.",
        ],
    ),
    ChangelogEntry(
        version="0.14(pre)",
        date="2026-08-11",
        changes=[
            "✨ Added live iTunes sync for Windows: if iTunes is open "
            "while you clean up duplicates, the app now removes those "
            "same songs directly from iTunes too, so you don't have to "
            "quit and reopen it. If iTunes isn't open, nothing changes — "
            "you'll follow the same steps as before.",
        ],
    ),
    ChangelogEntry(
        version="0.13(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed the build progress window closing itself too early "
            "during a build. It now stays open for the whole process.",
        ],
    ),
    ChangelogEntry(
        version="0.12(pre)",
        date="2026-08-11",
        changes=[
            "✨ Building the app from source now has an easier, guided "
            "option with a simple menu and progress screen.",
        ],
    ),
    ChangelogEntry(
        version="0.11(pre)",
        date="2026-08-11",
        changes=[
            "🚀 Opening a large library now uses less memory and runs "
            "more efficiently.",
            "✨ The loading progress bar now actually moves while your "
            "library file is being read, instead of sitting frozen.",
        ],
    ),
    ChangelogEntry(
        version="0.10(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Fixed opening a library sometimes failing with a "
            "database error on certain computers.",
            "🛠️ Fixed closing the app while it was mid-task sometimes "
            "interrupting that task. The app now waits for it to finish, "
            "or lets you cancel closing.",
            "🛠️ Fixed cover art previews briefly freezing the window "
            "while loading, especially for songs stored on a network "
            "drive.",
            "🛠️ Fixed the Library Health scan risking a stall on very "
            "large libraries with lots of offline or network files.",
            "🎨 The app now uses a cleaner, more Apple-like font where "
            "available, and falls back to the normal Windows font "
            "otherwise.",
        ],
    ),
    ChangelogEntry(
        version="0.9(pre)",
        date="2026-08-11",
        changes=[
            "🛠️ Added better error logging: if something goes wrong "
            "while starting up or using the app, it's now recorded in a "
            "small log file, in addition to the usual on-screen message.",
            "✨ The installer's \"unblock\" step now finishes on its own "
            "and closes automatically, instead of leaving a window open "
            "waiting for a key press.",
        ],
    ),
    ChangelogEntry(
        version="0.8(pre)",
        date="2026-08-11",
        changes=[
            "🔀 Every version is now labeled as a pre-release (like "
            "\"1.3.2-pre\") until we decide it's ready for a full 1.0 "
            "release.",
            "✨ The app now remembers your window size, position, and "
            "search filters between sessions, so it opens back up the "
            "way you left it.",
            "✨ Long tasks like opening or cleaning up a library now show "
            "which step is currently happening, not just a percentage.",
            "✨ Added a summary near the top of the window showing how "
            "many duplicates were found and how much space you could "
            "save.",
        ],
    ),
    ChangelogEntry(
        version="0.7(pre)",
        date="2026-08-10",
        changes=[
            "🔍 Added search and filtering for duplicates: find songs by "
            "artist, title, or how confident the app is that they're "
            "duplicates.",
            "↩️ Added Undo: after cleaning up duplicates, you can now "
            "undo the change and restore your library to how it was "
            "right before.",
            "✨ \"Restore backup\" now shows a full list of every saved "
            "backup, with the date each one was made, so you can pick "
            "exactly which one to restore.",
            "🎨 Improved how the app shows loading, empty, and error "
            "states throughout, so it's always clear what's happening.",
            "🎨 Improved the layout so it resizes properly across "
            "different screen sizes.",
        ],
    ),
    ChangelogEntry(
        version="0.6(pre)",
        date="2026-08-10",
        changes=[
            "🎨 The app now has a proper icon, shown in File Explorer, "
            "the taskbar, and the window title.",
            "🌗 Added light and dark appearance that automatically "
            "matches your Windows settings.",
            "✨ Error messages now include a helpful suggestion for what "
            "to try next, instead of just showing raw error text.",
            "🖼️ Added artwork previews: opening a duplicate group now "
            "shows each copy's cover art alongside its details.",
            "📦 Added an optional Windows installer with a Start Menu "
            "shortcut and a proper uninstaller.",
        ],
    ),
    ChangelogEntry(
        version="0.5(pre)",
        date="2026-08-10",
        changes=[
            "🛠️ Fixed a bug that could cause a song's unique internal ID "
            "to be copied incorrectly when cleaning up duplicates.",
        ],
    ),
    ChangelogEntry(
        version="0.4(pre)",
        date="2026-08-10",
        changes=[
            "🛠️ Fixed a bug where marking a group as \"not duplicates\" "
            "could cause a later action to accidentally apply to the "
            "wrong song. Actions now always apply to the exact song "
            "group you clicked.",
            "🛠️ Fixed duplicate detection sometimes grouping songs "
            "together that weren't actually close enough in length to "
            "count as duplicates.",
            "🧹 Minor behind-the-scenes cleanup, no visible changes.",
        ],
    ),
    ChangelogEntry(
        version="0.3(pre)",
        date="2026-08-10",
        changes=[
            "✨ Added manual review for duplicates: click any group to "
            "see why it was matched, choose a different copy to keep, or "
            "mark the group as \"not duplicates\" to skip it.",
            "✨ Opening a duplicate group now shows more detail for each "
            "copy: bitrate, album, and which playlists it's in.",
            "📊 Added a new Library Health tab showing duplicate counts, "
            "missing artwork, missing song info, low-quality files, "
            "broken file links, and how much space you could save.",
        ],
    ),
    ChangelogEntry(
        version="0.2(pre)",
        date="2026-08-10",
        changes=[
            "🔍 Added fuzzy duplicate matching: the app now catches "
            "near-matches too (like typos or small differences), not "
            "just exact duplicates.",
            "✅ Near-matches are shown separately and are never selected "
            "for cleanup automatically — you always decide first.",
            "✨ Progress bars now show a real percentage instead of just "
            "spinning.",
            "📂 The app now automatically finds your iTunes/Apple Music "
            "library file when you open it, if it can.",
            "💾 Added the option to save your cleaned-up library "
            "directly over the original file, with step-by-step guidance "
            "for reopening iTunes/Apple Music afterward.",
            "📋 Moved the changelog into the app itself, under Help → "
            "What's new.",
        ],
    ),
    ChangelogEntry(
        version="0.1(pre)",
        date="2026-06-01",
        changes=[
            "🎉 First release: finds exact duplicate songs, lets you "
            "preview changes before applying them, keeps playlists "
            "pointed at the right songs, merges play counts and "
            "ratings, and automatically backs up your library so you "
            "can restore it if needed.",
        ],
    ),
]


def changelog_text() -> str:
    """Plain-text rendering used by the in-app 'What's new' dialog."""
    lines: list[str] = []
    for entry in CHANGELOG:
        lines.append(f"Version {entry.version} — {entry.date}")
        for change in entry.changes:
            lines.append(f"  • {change}")
        lines.append("")
    return "\n".join(lines).rstrip()
