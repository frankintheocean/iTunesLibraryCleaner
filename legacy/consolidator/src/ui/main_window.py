from __future__ import annotations

import datetime
import re
import time
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtCore import QObject, QRunnable, QThread, QThreadPool, pyqtSignal

from .. import crash_reporter, error_log
from ..changelog import APP_VERSION, CATEGORY_ORDER, CHANGELOG
from ..core.artwork import file_uri_to_path, read_embedded_artwork
from ..core.consolidator import ConsolidationPlan, build_plan
from ..core.duplicate_detector import (
    TIER_DURATION_MISMATCH,
    TIER_EXACT,
    TIER_HIGH_CONFIDENCE,
    TIER_MANUAL,
    TIER_NEEDS_REVIEW,
    Tier,
    make_manual_merge_group,
    normalize,
)
from ..core.health_actions import (
    apply_artwork_from_source,
    find_artwork_source,
    find_missing_files_in_root,
    relink_track_location,
)
from ..core.itunes_xml import (
    Library,
    REOPEN_INSTRUCTIONS,
    REOPEN_STEPS_AUTOMATED,
    detect_default_library_xml,
)
from ..core.library_diff import LibraryDiff, build_fingerprint, diff_against_fingerprint
from ..core.library_health import analyze_library
from ..core.library_lock import LibraryAlreadyOpenError, LibraryLock
from ..core.itunes_com_sync import is_windows
from ..core.rebuild_script import (
    REBUILD_STEPS,
    PreflightResult,
    RebuildResult,
    UndoResult,
    autodetect_itunes_dir,
    default_itunes_dir,
    find_latest_rebuild_backup_pair,
    preflight_check_rebuild,
)
from ..core.workers import ApplyPlanWorker, LoadLibraryWorker, RebuildLibraryWorker, UndoRebuildWorker
from ..data.cache_db import CacheDB, SnapshotIntegrityError
from ..errors import with_recovery_guidance
from ..resources import app_icon_path
from .health_panel import HealthPanel
from .settings_dialog import (
    AUTO_RESCAN_ENABLED_SETTING_KEY,
    AUTO_RESCAN_INTERVAL_DAYS_DEFAULT,
    AUTO_RESCAN_INTERVAL_DAYS_MAX,
    AUTO_RESCAN_INTERVAL_DAYS_MIN,
    AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY,
    ChangelogVersionSection,
    SettingsDialog,
    apply_font_scale,
    build_changelog_version_jump,
    load_large_text_preference,
    load_qss_preference,
)
from .theme import accent_color, current_qss
from .widgets import (
    AudioPreviewPlayer,
    DuplicatesTable,
    EmptyStateLabel,
    FilterRow,
    HeaderSection,
    ChooseLibraryCalloutLabel,
    ItunesFolderStrip,
    LibraryActionRow,
    MainToolbar,
    MergeTracksDialog,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    GrowthTimelineChart,
    SummaryBar,
    ToastManager,
    TOAST_SUCCESS,
    _apply_severity_style,
    _SEVERITY_ACCENTS,
    show_critical,
    show_info,
    show_warning,
)

APP_DATA_DIR = Path.home() / "AppData" / "Local" / "iTunesConsolidator" if Path.home().joinpath("AppData").exists() else Path.home() / ".itunes_consolidator"

# CacheDB.get_setting/set_setting key for the set of group identities the
# user has chosen to exclude permanently, via "Exclude all reviewed-out
# groups permanently" (see MainWindow._on_exclude_reviewed_out_permanently
# and _apply_permanent_exclusions). Stored as a flat sorted list of
# "norm_artist\x1fnorm_title" strings (DuplicateGroup.key joined, since
# JSON only round-trips list/dict/str/etc, not tuples-as-dict-keys) rather
# than as raw tuples, so it survives the JSON encode/decode round trip in
# CacheDB unambiguously. This is a separate top-level key from "ui_state"
# for the same reason those are already split out from each other: a
# future change to one schema's version should never have to touch the
# other's.
PERMANENT_EXCLUSIONS_SETTING_KEY = "permanently_excluded_group_keys"
_GROUP_KEY_SEP = "\x1f"

# CacheDB.get_setting/set_setting key for the recently-opened-libraries
# list shown under the toolbar's "Recent..." menu (see
# _refresh_recent_files_menu / _remember_recent_file). Stored as a flat
# list of path strings, most-recently-opened first -- a separate
# top-level key from "ui_state"/PERMANENT_EXCLUSIONS_SETTING_KEY for the
# same reason those are already split from each other: a future change
# to one schema never has to touch the others.
RECENT_FILES_SETTING_KEY = "recent_library_files"
# Cap on how many entries are remembered -- a short, genuinely "recent"
# list is more useful than an ever-growing one, and keeps the menu itself
# a manageable size.
_RECENT_FILES_MAX = 10


def _encode_group_key(key: tuple[str, str]) -> str:
    return _GROUP_KEY_SEP.join(key)

# Sentinel distinguishing "not looked up yet" from "looked up, confirmed
# no artwork" (which caches as None) in the artwork cache.
_NOT_CACHED = object()


class _ArtworkLoadSignals(QObject):
    """QRunnable itself can't emit Qt signals (it isn't a QObject), so this
    small relay object is what _ArtworkLoadTask actually emits through --
    one instance per task, connected by the caller before the task is
    handed to the pool."""
    loaded = pyqtSignal(int, object)  # track_id, image_bytes-or-None


class _ArtworkLoadTask(QRunnable):
    """Background load of a single track's embedded artwork bytes, run on
    MainWindow's shared _artwork_pool (QThreadPool) instead of spinning up
    a dedicated QThread per row.

    Bug fix: expanding a group with many tracks previously started one
    brand-new QThread per row (_ArtworkLoadThread), each paying full OS
    thread-creation/teardown cost for what is typically a few-KB disk
    read -- on a group with a couple dozen copies (or quickly expanding/
    collapsing several groups in a row) this could momentarily spin up
    dozens of OS threads at once, competing with the UI thread for
    scheduling and making artwork feel *slower* to appear than doing it
    serially would have. QThreadPool queues tasks onto a small set of
    worker threads it creates once and reuses for every subsequent task,
    so thread count now stays bounded regardless of how many artwork
    loads are requested."""

    def __init__(self, track_id: int, location: str | None):
        super().__init__()
        self.track_id = track_id
        self.location = location
        self.signals = _ArtworkLoadSignals()

    def run(self) -> None:
        image_bytes = None
        path = file_uri_to_path(self.location) if self.location else None
        if path is not None:
            image_bytes = read_embedded_artwork(path)
        self.signals.loaded.emit(self.track_id, image_bytes)

# Single enum-driven source of truth for how each confidence tier is
# presented in the UI -- one entry per Tier member, instead of two
# separately-maintained dicts (label text, QSS badge objectName) that
# could silently drift out of sync with each other or with Tier itself
# (e.g. a new tier added to the enum but forgotten in one of the dicts).
# NamedTuple keeps this a plain, ordered pair of attributes rather than
# introducing a new dependency for what's still just a lookup table.
class _TierDisplay(NamedTuple):
    label: str
    badge_object_name: str  # QSS objectName for the colored badge, see ui/theme.py


_TIER_DISPLAY = {
    Tier.EXACT: _TierDisplay("Exact match", "tierBadgeExact"),
    Tier.HIGH_CONFIDENCE: _TierDisplay("High confidence", "tierBadgeHigh"),
    Tier.NEEDS_REVIEW: _TierDisplay("Possible duplicate — review", "tierBadgeReview"),
    Tier.MANUAL: _TierDisplay("Manually merged", "tierBadgeManual"),
    # v2.0: same artist+title, but the copies' lengths differ enough that
    # they weren't auto-grouped -- see Tier.DURATION_MISMATCH. Reuses the
    # "review" badge style (same "needs a human look" meaning), just with
    # its own label so the reason is clear at a glance.
    Tier.DURATION_MISMATCH: _TierDisplay("Same title — different length", "tierBadgeReview"),
}
_DEFAULT_TIER_DISPLAY = _TierDisplay("Possible duplicate — review", "tierBadgeReview")


def _tier_display(tier) -> "_TierDisplay":
    """Looks up the label/badge pair for `tier`, falling back to the
    review-tier presentation for anything not in _TIER_DISPLAY (e.g. a
    corrupt/future value read back from a restored snapshot or audit
    JSON) -- matches the previous dict.get(..., "tierBadgeReview")
    fallback behavior exactly, just from one table instead of two."""
    try:
        return _TIER_DISPLAY[Tier(tier)]
    except ValueError:
        return _DEFAULT_TIER_DISPLAY


# Matches both the current day/month/year_24hr-time backup stamp (see
# core.rebuild_script._BACKUP_STAMP_FORMAT, "DD-MM-YYYY_HHMMSS") and the
# older "%Y%m%d_%H%M%S" stamp so a backup left over from before this
# format change still gets a proper "made on <date>" tooltip instead of
# just the generic fallback.
_BAK_TIMESTAMP_RE = re.compile(r"\.bak_(\d{2}-\d{2}-\d{4}_\d{6}|\d{8}_\d{6})$")
_BAK_TIMESTAMP_FORMATS = ("%d-%m-%Y_%H%M%S", "%Y%m%d_%H%M%S")

# Bug fix: default/minimum sizing for the expandable duplicate-group
# detail panel (see MainWindow._build_duplicates_tab / detail_scroll_area
# above). A group with many copies could previously grow tall enough to
# push the window's footer and titlebar out of reach -- table_detail_
# splitter now starts each newly-expanded row at this default height
# (via setSizes() in _on_row_clicked) instead of letting it grow
# unbounded, and _DETAIL_PANEL_MIN_HEIGHT keeps the splitter from being
# dragged down to nothing. The user can still drag the splitter handle
# to any size in between (or beyond the default) -- these are just the
# starting point and floor, not a hard ceiling.
_DETAIL_PANEL_DEFAULT_MAX_HEIGHT = 260
_DETAIL_PANEL_MIN_HEIGHT = 120


def _bak_timestamp_tooltip(filename: str) -> str:
    """Explains what a ".bak_<timestamp>" file is and when it was made,
    for the per-item tooltips on the "Backups kept" list in the rebuild-
    finished dialog (see MainWindow._on_rebuild_finished) -- people who've
    never seen these files before have no way to know, just from the
    filename, that they're an automatic safety copy rather than something
    left behind by mistake. Falls back to a generic explanation (still
    naming the pattern) if the timestamp can't be parsed out of this
    particular filename, since the tooltip is still useful without it."""
    match = _BAK_TIMESTAMP_RE.search(filename)
    if match:
        when_text = None
        for fmt in _BAK_TIMESTAMP_FORMATS:
            try:
                when = datetime.datetime.strptime(match.group(1), fmt)
                when_text = when.strftime("%Y-%m-%d %H:%M:%S")
                break
            except ValueError:
                continue
        if when_text is not None:
            return (
                f"Automatic backup made {when_text}, before this rebuild "
                "replaced the file. Safe to leave in place — use \u21A9\uFE0F "
                "\"Undo this change\u2026\" to restore from it, or delete it "
                "yourself once you've confirmed the rebuild worked."
            )
    return (
        "Automatic backup made before this rebuild replaced the file "
        "(the \".bak_<timestamp>\" in the name marks when). Safe to leave "
        "in place — use \u21A9\uFE0F \"Undo this change\u2026\" to restore from "
        "it, or delete it yourself once you've confirmed the rebuild "
        "worked."
    )


def _match_reason_text(action) -> str:
    """Short, human-readable explanation of *why* this group was flagged
    as a duplicate, derived entirely from data the action already carries
    (tier/similarity) -- no core/matching changes needed. Shown inline in
    the table row and repeated in the detail panel."""
    if action.tier == TIER_EXACT:
        return "Same artist and song title"
    if action.tier == TIER_HIGH_CONFIDENCE:
        return f"Very similar artist/title ({action.similarity:.0%} match)"
    if action.tier == TIER_MANUAL:
        return "You manually merged these tracks"
    if action.tier == TIER_DURATION_MISMATCH:
        return "Same artist and song title, but lengths differ — worth a look"
    return f"Somewhat similar artist/title ({action.similarity:.0%} match) — worth a look"



class MainWindow(QMainWindow):
    # Cap on how many groups the consolidation confirmation dialog
    # itemizes in full (see _duplicate_removal_preview_text) -- keeps that
    # dialog responsive to build/render even when the user selects
    # thousands of groups via "select all" on a very large library.
    _PREVIEW_MAX_GROUPS = 200

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"🎵 iTunes Duplicate Cleaner v{APP_VERSION}")
        self.resize(980, 640)
        # Keeps the header, action row, and table usable rather than
        # overlapping/clipping if the window is resized small -- covers
        # common Windows laptop/tiled-window sizes down to a modest floor,
        # without constraining how large the window can be maximized.
        self.setMinimumSize(720, 480)
        # CacheDB construction is moved up here (was previously right
        # after self.plan = None) since the saved theme/font preferences
        # it holds are needed for the very first stylesheet application,
        # not a second throwaway DB open -- matching the rest of
        # _restore_ui_state()'s "never block startup on a missing/corrupt
        # saved value" behavior.
        self.cache = CacheDB(APP_DATA_DIR / "cache.sqlite3")
        self._theme_preference = load_qss_preference(self.cache)
        self._apply_theme_stylesheet(self._theme_preference)
        apply_font_scale(load_large_text_preference(self.cache))

        icon_path = app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        # Drag-and-drop: lets a Library.xml be dropped onto the window
        # instead of always going through File > Open. Purely an
        # alternative entry point into the existing _load_library() --
        # every validation/loading/error-handling path is unchanged.
        self.setAcceptDrops(True)

        self.library: Library | None = None
        self.plan: ConsolidationPlan | None = None
        # Set once initial UI state (filter text/tier) has been restored
        # from the previous session, so the filter-changed handler wired up
        # during _build_ui() doesn't immediately re-save the just-restored
        # values (harmless, but pointless) or, worse, save a transient
        # empty value that fires before restoration runs.
        self._restoring_ui_state = False
        self._load_worker: LoadLibraryWorker | None = None
        self._apply_worker: ApplyPlanWorker | None = None
        self._write_back_mode: bool = False
        # Duplicate groups behind the current plan, kept around (rather than
        # only the flattened MergeAction list) so manual review actions
        # (mark not-duplicate / change canonical) can mutate a group and
        # have the plan rebuilt from it.
        self._groups: list = []
        self._expanded_row: int | None = None
        self._last_audit_record = None
        self._last_pre_consolidation_snapshot_id: int | None = None
        self._last_output_path: Path | None = None
        # On-disk audio file paths (resolved via core/artwork.
        # file_uri_to_path) for the tracks removed by the most recent
        # "Clean up duplicates" run -- see _removed_track_file_paths and
        # "Remove duplicate files from disk...". Reset to empty whenever
        # a fresh apply runs, so this can never offer to delete files
        # from a stale, already-acted-on run.
        self._last_removed_track_paths: list[Path] = []
        # Holds the advisory lock on the currently-open Library.xml (see
        # core/library_lock.py), so a second window/instance can't also
        # write back to the same file concurrently. Released whenever a
        # different library is opened (see _load_library) and on close.
        self._library_lock: LibraryLock | None = None
        # See _maybe_run_scheduled_rescan/_load_library's `scheduled` arg.
        self._pending_scheduled_rescan: bool = False
        self._scheduled_rescan_path: Path | None = None
        # Set inside _on_library_loaded, then consumed/cleared right after
        # -- see _diff_against_last_export/_show_library_diff_dialog
        # ("What changed since last export").
        self._pending_library_diff: "LibraryDiff | None" = None

        self._build_ui()
        self._restore_ui_state()
        self._refresh_itunes_folder_strip()
        self._confirm_itunes_dir_on_launch()
        self._refresh_itunes_folder_strip()
        if not self._maybe_run_scheduled_rescan():
            self._offer_default_library()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        # Real in-app toolbar, replacing the old plain Help/File menu bar
        # (product decision). Actions are unchanged -- Open, Restore
        # backup, Save audit report, Settings, and What's new -- only how
        # they're presented changes, so every existing handler/tooltip/
        # keyboard path below is reused as-is. Icons come from Qt's own
        # QStyle standard-icon set (no new asset/dependency needed) so
        # this looks native on Windows and follows the current theme.
        self.menuBar().setVisible(False)
        toolbar_builder = MainToolbar(self)
        self.addToolBar(toolbar_builder.toolbar)
        self.toolbar_open_action = toolbar_builder.open_action
        self.toolbar_open_action.triggered.connect(self._on_open_clicked)
        self.recent_files_menu = toolbar_builder.recent_menu
        self.toolbar_restore_action = toolbar_builder.restore_action
        self.toolbar_restore_action.triggered.connect(self._on_restore_clicked)
        self.toolbar_save_restore_point_action = toolbar_builder.save_restore_point_action
        self.toolbar_save_restore_point_action.triggered.connect(self._on_save_named_restore_point)
        self.toolbar_undo_rebuild_action = toolbar_builder.undo_rebuild_action
        self.toolbar_undo_rebuild_action.triggered.connect(self._on_undo_last_rebuild)
        toolbar_builder.save_audit_action.triggered.connect(self._on_save_audit_report)
        toolbar_builder.settings_action.triggered.connect(self._on_show_settings)
        toolbar_builder.import_spotify_action.triggered.connect(self._on_import_spotify_library)
        self.toolbar_merge_tracks_action = toolbar_builder.merge_tracks_action
        self.toolbar_merge_tracks_action.triggered.connect(self._on_merge_tracks_clicked)
        toolbar_builder.whats_new_action.triggered.connect(self._on_show_changelog)
        self._refresh_recent_files_menu()

        # Additional keyboard shortcuts beyond the ones already attached
        # directly to toolbar QActions (Open/Undo last rebuild -- see
        # MainToolbar, which sets those via QAction.setShortcut so they
        # respect each action's own enabled state automatically). These
        # two apply to plain QPushButtons/QCheckBoxes rather than
        # QActions, so they're set up here as window-scoped QShortcuts
        # instead. Ambiguous with nothing else in this window (no menu
        # bar is shown -- see setVisible(False) above -- so there's no
        # competing action using the same sequence).
        self._apply_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._apply_shortcut.activated.connect(self._on_apply_shortcut)
        self._apply_shortcut_enter = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self._apply_shortcut_enter.activated.connect(self._on_apply_shortcut)

        self._select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        self._select_all_shortcut.activated.connect(self._on_select_all_shortcut)

        # Ctrl+F: focuses the existing artist/song search box (filter_row.
        # filter_edit) instead of adding a new, separate search UI --
        # matches the standard "find" shortcut users expect, and reuses
        # the filtering this window already had.
        self._find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._find_shortcut.activated.connect(self._on_find_shortcut)

        # Escape: closes the expanded duplicate-group detail panel, if one
        # is open -- the same action as clicking its Close button or
        # clicking the already-expanded row again (see
        # _collapse_detail_panel). Does nothing if no row is expanded, so
        # it never interferes with any other widget's own Escape handling
        # (e.g. a QDialog closing itself) elsewhere in the app.
        self._collapse_detail_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._collapse_detail_shortcut.activated.connect(self._on_escape_shortcut)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        # Header
        root.addWidget(HeaderSection())

        # Persistent iTunes-folder status strip: shows exactly which
        # folder "Rebuild library now..." will use, everywhere that
        # matters, instead of the user having to reopen that dialog to
        # check. Kept in sync via _refresh_itunes_folder_strip(), called
        # on startup and after every place the setting can change (see
        # _confirm_itunes_dir_on_launch, _prompt_for_itunes_dir).
        self.itunes_folder_strip = ItunesFolderStrip()
        self.itunes_folder_strip_label = self.itunes_folder_strip.folder_label
        root.addWidget(self.itunes_folder_strip)

        # Action row
        action_row = LibraryActionRow()
        self.open_btn = action_row.open_btn
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.status_label = action_row.status_label
        self.restore_btn = action_row.restore_btn
        self.restore_btn.clicked.connect(self._on_restore_clicked)
        root.addWidget(action_row)

        # Always-visible duplicates/savings summary bar. Previously this
        # figure only existed inside the Library Health tab, so switching
        # to the Duplicates tab (the default view) hid it entirely. This
        # bar is updated in lockstep with the Health tab from the same
        # HealthReport (see _refresh_health) so the two never disagree,
        # and is visible regardless of which tab is active.
        self.summary_bar = SummaryBar()
        self.summary_bar_label = self.summary_bar.summary_bar_label
        root.addWidget(self.summary_bar)

        # Progress — determinate (0-100) so large-library operations show
        # real percentage-complete instead of an indeterminate spinner, plus
        # a short phase label (Parsing / Exact matching / Fuzzy matching /
        # Writing, etc.) so a flat percentage doesn't leave the user
        # guessing what's actually happening at, say, 40% complete.
        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.phase_label = QLabel("")
        self.phase_label.setObjectName("phaseLabel")
        self.phase_label.setVisible(False)
        self.phase_label.setMinimumWidth(140)
        progress_row.addWidget(self.phase_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        progress_row.addWidget(self.progress, stretch=1)
        root.addLayout(progress_row)

        # Tabs: the original duplicate-review workflow, plus Library Health.
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        duplicates_tab = QWidget()
        dup_layout = QVBoxLayout(duplicates_tab)
        dup_layout.setContentsMargins(0, 12, 0, 0)
        dup_layout.setSpacing(10)

        hint = QLabel(
            "Click a row to expand it — see every copy's bitrate, album, and which "
            "playlists it's in, why that copy was picked to keep, and to mark "
            "a group as not actually duplicates or pick a different track to keep."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        dup_layout.addWidget(hint)

        # Search/filter row: narrows the table below by artist/song text
        # match and/or confidence tier. Purely a view-level filter over the
        # current plan's actions -- it never mutates self.plan, so "select
        # all" / apply / manual review actions are unaffected by whatever
        # is currently filtered in or out.
        filter_row = FilterRow(
            {tier: display.label for tier, display in _TIER_DISPLAY.items()},
            TIER_EXACT, TIER_HIGH_CONFIDENCE, TIER_NEEDS_REVIEW,
            TIER_DURATION_MISMATCH,
        )
        self.filter_edit = filter_row.filter_edit
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.filter_tier_combo = filter_row.filter_tier_combo
        self.filter_tier_combo.currentIndexChanged.connect(self._on_filter_changed)
        dup_layout.addWidget(filter_row)

        # Duplicate table (dry-run preview)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # Bug fix: the table and the expandable detail panel below used to
        # be stacked in a plain QVBoxLayout with no cap on the detail
        # panel's height. A group with many duplicate copies (each with an
        # artwork thumbnail + inline audio preview player) could grow tall
        # enough to push the window's footer/titlebar interaction area off
        # screen -- on some window managers this left no visible way to
        # close the window at all while a large group was expanded. A
        # QSplitter fixes both halves of that: it caps how much of the
        # window the detail panel can occupy by default, and its handle
        # (dragged from the border between the table and the detail panel,
        # i.e. the top edge of the expanded row) lets the user resize that
        # split themselves if they want to see more or less of it.
        self.table_detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.table_detail_splitter.setObjectName("tableDetailSplitter")
        self.table_detail_splitter.setChildrenCollapsible(False)
        self.table_detail_splitter.setHandleWidth(8)

        self.table = DuplicatesTable()
        self.table.cellClicked.connect(self._on_row_clicked)
        self.table_detail_splitter.addWidget(self.table)

        # Empty-state placeholder shown in place of the table when there's
        # nothing to display for one of three distinct reasons (no library
        # loaded / library has no duplicates / current filter matches
        # nothing) -- each gets its own message rather than a blank table,
        # so it's never ambiguous whether something went wrong or there's
        # simply nothing to show.
        self.empty_state_label = EmptyStateLabel()
        card_layout.addWidget(self.empty_state_label)

        # Expandable detail panel for the currently-selected row: per-track
        # bitrate/album/playlists plus manual review controls. Hidden until
        # a row is clicked; rebuilt each time (cheap — a handful of widgets).
        # Wrapped in a QScrollArea so a group with many copies scrolls
        # internally instead of forcing the panel itself to keep growing --
        # combined with the splitter above, this is what keeps an expanded
        # row from ever taking over the whole app window.
        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("detailPanel")
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(16, 12, 16, 14)

        self.detail_scroll_area = QScrollArea()
        self.detail_scroll_area.setObjectName("detailScrollArea")
        self.detail_scroll_area.setWidgetResizable(True)
        self.detail_scroll_area.setWidget(self.detail_panel)
        self.detail_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # Minimum only -- no maximum. A hard maximum would stop the
        # splitter handle below from ever letting the user drag the panel
        # taller, which defeats the whole point of adding it. The sensible
        # default height instead comes from table_detail_splitter.setSizes()
        # once both widgets exist (see _on_row_clicked), and the user can
        # freely resize past it in either direction from there.
        self.detail_scroll_area.setMinimumHeight(_DETAIL_PANEL_MIN_HEIGHT)
        self.detail_scroll_area.setVisible(False)
        self.table_detail_splitter.addWidget(self.detail_scroll_area)

        # Give the table the lion's share of space by default; the detail
        # panel only grows into its cap above (or further, if the user
        # drags the handle) once it's actually shown.
        self.table_detail_splitter.setStretchFactor(0, 1)
        self.table_detail_splitter.setStretchFactor(1, 0)

        card_layout.addWidget(self.table_detail_splitter)

        dup_layout.addWidget(card, stretch=1)

        # Footer / confirm row -- split into two stacked rows (options, then
        # summary+action) instead of one long horizontal row, so it degrades
        # to a narrow window without checkboxes, the summary text, and the
        # primary button all competing for the same line and clipping each
        # other. self.summary_label wraps too, since result text length
        # varies with how many groups were found/filtered.
        footer = QVBoxLayout()
        footer.setSpacing(8)

        options_row = QHBoxLayout()
        self.select_all_cb = QCheckBox("Select all (exact + high confidence)")
        self.select_all_cb.setToolTip(
            "Selects the confident matches only. Anything marked 'needs "
            "review' is left unchecked so you can look it over first."
        )
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        self.select_all_cb.setEnabled(False)
        options_row.addWidget(self.select_all_cb)

        # Additional one-click batch selections beyond "select all
        # (exact + high confidence)" above -- each is precise (it also
        # unchecks whatever doesn't match) rather than additive, so
        # clicking one always gives the same, predictable selection.
        self.select_all_exact_btn = QPushButton("Select all exact")
        self.select_all_exact_btn.setToolTip(
            "Checks only exact-match groups (identical artist and title) "
            "and unchecks everything else currently visible."
        )
        self.select_all_exact_btn.setEnabled(False)
        self.select_all_exact_btn.clicked.connect(self._on_select_all_exact)
        options_row.addWidget(self.select_all_exact_btn)

        self.select_all_high_conf_btn = QPushButton("Select all high-confidence")
        self.select_all_high_conf_btn.setToolTip(
            "Checks only high-confidence fuzzy-match groups and unchecks "
            "everything else currently visible."
        )
        self.select_all_high_conf_btn.setEnabled(False)
        self.select_all_high_conf_btn.clicked.connect(self._on_select_all_high_confidence)
        options_row.addWidget(self.select_all_high_conf_btn)

        # True "select every visible row" -- unlike select_all_cb above,
        # this deliberately includes 'needs review' groups too, so users
        # with hundreds/thousands of review-tier groups aren't forced to
        # scroll and click each one by hand. It's a separate, explicitly-
        # named control (not a change to select_all_cb's behavior) so the
        # existing "confident matches only" default stays the safe default.
        self.select_all_everything_btn = QPushButton("Select all (incl. review)")
        self.select_all_everything_btn.setToolTip(
            "Checks every currently visible group, including 'needs "
            "review' matches. Review the selection before applying --"
            " low-confidence groups are included this time."
        )
        self.select_all_everything_btn.setEnabled(False)
        self.select_all_everything_btn.clicked.connect(self._on_select_all_everything)
        options_row.addWidget(self.select_all_everything_btn)

        self.exclude_reviewed_out_btn = QPushButton("\U0001F512 Exclude reviewed-out permanently")
        self.exclude_reviewed_out_btn.setToolTip(
            "Remembers every group currently marked as not duplicates so "
            "it's automatically skipped on every future library you open "
            "too, not just this session."
        )
        self.exclude_reviewed_out_btn.setEnabled(False)
        self.exclude_reviewed_out_btn.clicked.connect(self._on_exclude_reviewed_out_permanently)
        options_row.addWidget(self.exclude_reviewed_out_btn)

        self.write_back_cb = QCheckBox("Save over the original file")
        self.write_back_cb.setToolTip(
            "Saves the cleaned-up library over the file you opened, "
            "instead of asking where to save a new copy."
        )
        self.write_back_cb.setEnabled(False)
        options_row.addWidget(self.write_back_cb)
        options_row.addStretch(1)
        footer.addLayout(options_row)

        confirm_row = QHBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("subtitle")
        self.summary_label.setWordWrap(True)
        confirm_row.addWidget(self.summary_label, stretch=1)

        self.apply_btn = QPushButton("\U0001F5D1\uFE0F Delete duplicates…")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setToolTip(
            "Removes the checked duplicates and keeps one copy of each "
            "song. A backup is saved first, and you'll be asked to "
            "confirm."
        )
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        confirm_row.addWidget(self.apply_btn)
        footer.addLayout(confirm_row)

        dup_layout.addLayout(footer)

        self.tabs.addTab(duplicates_tab, "\U0001F3B5 Duplicates")

        self.health_panel = HealthPanel()
        self.health_panel.locate_file_requested.connect(self._on_locate_missing_file)
        self.health_panel.fix_artwork_requested.connect(self._on_fix_missing_artwork)
        self.health_panel.find_missing_in_folder_requested.connect(
            self._on_find_missing_files_in_folder
        )
        self.health_panel.growth_timeline_requested.connect(self._on_show_growth_timeline)
        self.tabs.addTab(self.health_panel, "\U0001FA7A Library Health")

        self.statusBar().showMessage("Ready.")

        # Non-blocking toast overlay, anchored to this window's bottom-right
        # corner (see widgets.ToastManager). Created last in _build_ui so it
        # sits on top of every other child widget in stacking order; kept
        # positioned via resizeEvent/showEvent below rather than a fixed
        # geometry, since the window is resizable.
        self._toast_manager = ToastManager(central)
        self._toast_manager.reposition()

    def _toast(
        self,
        message: str,
        severity: str = SEVERITY_INFO,
    ) -> None:
        """Shows a transient, non-blocking notification banner instead of
        (or in addition to) a status-bar message. Use this for one-off
        confirmations that previously only ever flashed through
        statusBar().showMessage() -- e.g. "Backup restored" or "5 group(s)
        excluded" -- which were easy to miss entirely since the status bar
        shows only one line of text at a time and is also the same target
        LoadLibraryWorker/ApplyPlanWorker write their live progress
        messages to. The status bar itself is unchanged and still used for
        that ongoing progress text; toasts are for events, not progress."""
        self._toast_manager.show_toast(message, severity)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        toast_manager = getattr(self, "_toast_manager", None)
        if toast_manager is not None:
            toast_manager.reposition()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        toast_manager = getattr(self, "_toast_manager", None)
        if toast_manager is not None:
            toast_manager.reposition()

    # ------------------------------------------------------------- actions

    def _confirm_itunes_dir_on_launch(self) -> None:
        """On startup (Windows only), asks the user to locate their real
        iTunes data folder (the one containing iTunes Library.itl) via a
        folder-browse prompt, rather than silently assuming it's at the
        standard default Music\\iTunes path -- that assumption breaks for
        anyone with their library on an external drive or a
        OneDrive/redirected Music folder, and previously was only ever
        checked the first time "Rebuild library now..." was clicked, long
        after duplicates had already been cleaned up. Only asked once a
        session's worth of runs -- if a folder has already been confirmed
        in a previous run (remembered via CacheDB), that choice is reused
        silently and this does not prompt again every launch. Cancelling
        leaves the remembered/default value untouched and never blocks
        opening or working with a Library.xml -- this only affects what
        folder "Rebuild library now..." offers/defaults to later."""
        if not is_windows():
            return
        if self.cache.get_setting("itunes_library_dir"):
            return
        # Scan common drive letters for a folder that already looks like a
        # real iTunes data folder (see core.rebuild_script.
        # autodetect_itunes_dir) before asking the user to browse blind --
        # this is the common case for anyone whose library sits at a
        # standard-ish path, even one on a different drive than the OS
        # user profile. A find here is only ever offered for confirmation,
        # never applied silently: it still goes through the same "Locate
        # your iTunes folder" prompt below, pre-filled with the detected
        # path instead of the plain Music\iTunes default, and the user can
        # always browse to a different folder instead (or set one later in
        # Settings -- see settings_dialog._build_general_tab).
        detected = autodetect_itunes_dir()
        if detected is not None:
            confirm = QMessageBox.question(
                self,
                "🎵 iTunes folder found",
                f"This looks like your iTunes data folder:\n\n{detected}\n\n"
                "Use this folder? (You can change it any time in "
                "Settings.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.cache.set_setting("itunes_library_dir", str(detected))
                self._refresh_itunes_folder_strip()
                return
            # "No" falls through to the manual browse-to-confirm flow
            # below instead of assuming the user wants to be asked again
            # next launch -- they've already said this guess is wrong, so
            # letting them pick the right folder now (rather than a second
            # separate prompt) is the more useful next step.
            self._prompt_for_itunes_dir()
            return

        confirm = QMessageBox.question(
            self,
            "🎵 Locate your iTunes folder",
            "To rebuild your iTunes library after cleaning up duplicates, "
            "this app needs to know where your real iTunes data folder is "
            "(the one containing iTunes Library.itl). It couldn't be "
            "found automatically.\n\n"
            "This isn't always the default Music\\iTunes folder -- for "
            "example, it could be on an external drive or a "
            "OneDrive-redirected Music folder.\n\n"
            "Locate it now? (You can also set this later in Settings.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._prompt_for_itunes_dir()

    def _offer_default_library(self) -> None:
        """On startup, if a Library.xml exists at a known default location,
        offer to open it directly instead of making the user browse for it."""
        default_path = detect_default_library_xml()
        if default_path is None:
            return
        confirm = QMessageBox.question(
            self,
            "🎵 iTunes library found",
            f"Found an iTunes/Apple Music library at:\n{default_path}\n\n"
            "Open it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._load_library(default_path)

    def _maybe_run_scheduled_rescan(self) -> bool:
        """Startup check for "check for new duplicates weekly" (see
        AUTO_RESCAN_ENABLED_SETTING_KEY, added to Settings \u2192 General).
        For someone who keeps re-importing tracks into the same library,
        this silently re-scans it in the background once it's been at
        least AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY days since that
        library's last recorded scan, instead of relying on them to
        remember to reopen the app and rescan by hand.

        Off by default, and a strict no-op unless every one of these
        holds:
          - the setting is enabled;
          - there's a most-recently-opened library on record (see
            RECENT_FILES_SETTING_KEY) and the file still exists;
          - that library has at least one prior recorded scan (see
            cache_db.list_health_snapshots) and it's old enough.
        Returns True if a background rescan was started (in which case
        the caller skips the normal _offer_default_library prompt, so
        the user isn't asked twice about the same file), False
        otherwise -- including when a rescan isn't due, so the ordinary
        startup flow continues exactly as before for everyone who hasn't
        opted into this.
        """
        try:
            enabled = bool(self.cache.get_setting(AUTO_RESCAN_ENABLED_SETTING_KEY, default=False))
        except Exception:
            enabled = False
        if not enabled:
            return False

        recent = self.cache.get_setting(RECENT_FILES_SETTING_KEY, default=[])
        if not isinstance(recent, list) or not recent:
            return False
        path_str = next((p for p in recent if isinstance(p, str)), None)
        if not path_str:
            return False
        path = Path(path_str)
        if not path.exists():
            return False  # moved/deleted since last opened; nothing to auto-rescan

        try:
            interval_days = int(
                self.cache.get_setting(
                    AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY,
                    default=AUTO_RESCAN_INTERVAL_DAYS_DEFAULT,
                )
            )
        except (TypeError, ValueError):
            interval_days = AUTO_RESCAN_INTERVAL_DAYS_DEFAULT
        interval_days = min(max(interval_days, AUTO_RESCAN_INTERVAL_DAYS_MIN), AUTO_RESCAN_INTERVAL_DAYS_MAX)

        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        points = [p for p in self.cache.list_health_snapshots() if p["source_path"] == resolved]
        if not points:
            return False  # never scanned before; nothing to compare "due" against
        last_scanned_at = points[-1]["created_at"]
        due_at = last_scanned_at + (interval_days * 86400)
        if time.time() < due_at:
            return False

        crash_reporter.record_action(f"Scheduled re-scan: {path.name}")
        self._scheduled_rescan_path = path
        self._load_library(path, scheduled=True)
        return True

    def _on_open_clicked(self) -> None:
        default_path = detect_default_library_xml()
        start_dir = str(default_path.parent) if default_path else ""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open iTunes Library.xml", start_dir, "iTunes Library (*.xml);;All files (*.*)"
        )
        if not path_str:
            return
        self._load_library(Path(path_str))

    # ------------------------------------------------------------ recent files

    def _remember_recent_file(self, path: Path) -> None:
        """Adds `path` to the front of the persisted recent-files list
        (see RECENT_FILES_SETTING_KEY), de-duplicating any existing
        entry for the same path (case-insensitively resolved, so opening
        the same file via two differently-cased/relative paths on
        Windows still counts as one entry) and capping the list at
        _RECENT_FILES_MAX. Called from _load_library so every successful
        load attempt (Open dialog, drag-and-drop, default-library offer,
        or reopening from this very menu) is remembered the same way --
        a single call site rather than duplicating this at each entry
        point. Best-effort: a failed save never blocks opening the
        library it's trying to remember, matching every other setting
        write in this class."""
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        existing = self.cache.get_setting(RECENT_FILES_SETTING_KEY, default=[])
        if not isinstance(existing, list):
            existing = []
        deduped = [p for p in existing if isinstance(p, str) and p.lower() != resolved.lower()]
        deduped.insert(0, resolved)
        del deduped[_RECENT_FILES_MAX:]
        try:
            self.cache.set_setting(RECENT_FILES_SETTING_KEY, deduped)
        except Exception:
            pass  # best-effort, same as every other setting save in this class
        self._refresh_recent_files_menu()

    def _refresh_recent_files_menu(self) -> None:
        """Rebuilds the toolbar's "Recent..." popup menu from the
        persisted list. Called on startup and after every
        _remember_recent_file so the menu never goes stale mid-session.
        Entries whose file no longer exists on disk are still listed
        (clicking one surfaces the normal load-failure path below,
        rather than this menu silently pretending the entry was never
        there) but are visually marked so a missing file is obvious
        before clicking it."""
        menu = self.recent_files_menu
        menu.clear()
        entries = self.cache.get_setting(RECENT_FILES_SETTING_KEY, default=[])
        if not isinstance(entries, list) or not entries:
            empty_action = menu.addAction("No recent libraries yet")
            empty_action.setEnabled(False)
            return
        for entry in entries:
            if not isinstance(entry, str):
                continue
            entry_path = Path(entry)
            label = entry_path.name or entry
            exists = entry_path.exists()
            if not exists:
                label += "  (not found)"
            action = menu.addAction(label)
            action.setToolTip(entry)
            action.triggered.connect(
                lambda _checked=False, p=entry_path: self._on_recent_file_selected(p)
            )
        menu.addSeparator()
        clear_action = menu.addAction("Clear recent libraries")
        clear_action.triggered.connect(self._on_clear_recent_files)

    def _on_recent_file_selected(self, path: Path) -> None:
        if self._is_worker_busy():
            show_info(
                self,
                "One thing at a time",
                "Please wait for the current task to finish before "
                "opening another library.",
            )
            return
        self._load_library(path)

    def _on_clear_recent_files(self) -> None:
        try:
            self.cache.set_setting(RECENT_FILES_SETTING_KEY, [])
        except Exception:
            pass
        self._refresh_recent_files_menu()

    # ------------------------------------------------------------ shortcuts

    def _on_apply_shortcut(self) -> None:
        """Ctrl+Enter/Ctrl+Return keyboard shortcut for the primary
        "Delete duplicates..." action -- only fires the same click path
        the button itself already uses (_on_apply_clicked), and only
        when that button is actually enabled, so this can't trigger an
        apply with nothing loaded/selected or while a load/apply is
        already in progress any more than clicking the (disabled)
        button by hand could."""
        if self.apply_btn.isEnabled():
            self._on_apply_clicked()

    def _on_select_all_shortcut(self) -> None:
        """Ctrl+A: toggles the same "Select all (exact + high
        confidence)" checkbox the footer already exposes, rather than a
        separate/parallel selection path -- so keyboard and mouse users
        end up in the exact same selection state either way. Only acts
        when a plan with actions is actually loaded (mirrors the
        checkbox's own setEnabled state, see _set_busy/_populate_table_
        rows), and only checks it (never unchecks) to match "select
        all"'s usual one-directional meaning elsewhere in this app --
        unchecking is already one click away on the same checkbox."""
        if self.select_all_cb.isEnabled():
            self.select_all_cb.setChecked(True)

    def _on_find_shortcut(self) -> None:
        """Ctrl+F: focuses the artist/song filter box (and selects any
        existing text, so typing immediately replaces it) rather than
        opening a separate find UI. Only acts once the filter box is
        actually enabled/visible with a plan loaded, matching the same
        guard the other shortcuts above use."""
        if self.filter_edit.isEnabled():
            self.filter_edit.setFocus()
            self.filter_edit.selectAll()

    def _on_escape_shortcut(self) -> None:
        """Escape: closes the expanded duplicate-group detail panel, if
        one is currently open. A no-op otherwise, so it never steals
        Escape from any other widget (e.g. a modal dialog) that already
        handles it."""
        if self._expanded_row is not None:
            self._collapse_detail_panel()

    def _load_library(self, path: Path, scheduled: bool = False) -> None:
        # Take the per-file lock before doing anything else. If another
        # window/instance already holds it, refuse to load rather than
        # risk two processes both writing back to the same Library.xml
        # later (see core/library_lock.py). This intentionally happens
        # before releasing any lock this window already holds on a
        # *different* library, so a failed attempt to open a second,
        # already-locked file never loses this window's current library.
        new_lock = LibraryLock(APP_DATA_DIR / "locks", path)
        try:
            new_lock.acquire()
        except LibraryAlreadyOpenError as exc:
            # A scheduled background rescan silently backing off because
            # something else already has the file open is expected, not
            # an error worth interrupting startup with a dialog for --
            # only an explicit Open/drag-drop shows this warning.
            if scheduled:
                self._scheduled_rescan_path = None
                return
            show_warning(self, "Library already open", str(exc))
            return

        if self._library_lock is not None:
            self._library_lock.release()
        self._library_lock = new_lock

        self._remember_recent_file(path)
        # Tracked so _on_library_loaded/_on_load_failed know this run was
        # a background "check for new duplicates weekly" pass (see
        # _maybe_run_scheduled_rescan) rather than a normal user-
        # initiated Open, and show a toast summary instead of/alongside
        # the usual UI. Cleared as soon as it's consumed so a later
        # ordinary load is never mistaken for a scheduled one.
        self._pending_scheduled_rescan = scheduled
        action_verb = "Auto re-scanning" if scheduled else "Loading"
        crash_reporter.record_action(f"{action_verb} library: {path.name}")
        self._set_busy(True, f"{action_verb} {path.name}…")
        self._show_table_skeleton()
        self._load_worker = LoadLibraryWorker(path, self.cache)
        self._load_worker.progress.connect(self.statusBar().showMessage)
        self._load_worker.progress_pct.connect(self.progress.setValue)
        self._load_worker.phase.connect(self._on_phase_changed)
        self._load_worker.finished_ok.connect(self._on_library_loaded)
        self._load_worker.failed.connect(self._on_load_failed)
        self._load_worker.start()

    def _on_library_loaded(self, library: Library, plan: ConsolidationPlan) -> None:
        # Bug fix: _set_busy(False) used to run FIRST, before self.plan was
        # (re)assigned below -- it computes apply_btn's (and the other
        # plan-dependent buttons') enabled state from self.plan as it was
        # at that exact moment, which on a fresh load is still None/stale.
        # Nothing later in this method re-asserts that state except
        # _populate_table_rows()'s own apply_btn.setEnabled(has_actions) --
        # so if anything between here and that call raised (e.g. inside
        # _apply_permanent_exclusions, the second build_plan() call, or
        # _refresh_health), Delete/Clean up duplicates was left permanently
        # disabled with no error dialog shown (an exception inside a Qt
        # slot doesn't surface the normal error UI). Deferring _set_busy
        # to the end means it always runs after self.plan holds the real,
        # final plan, and it now runs even on that exception path via
        # try/finally so a mid-method failure can never leave the whole
        # toolbar stuck in its "still loading" disabled state.
        try:
            self.library = library
            self.plan = plan
            # Keep the actual DuplicateGroup objects each action was built
            # from (bug fix, v1.2.1: previously this reconstructed fresh
            # DuplicateGroup copies here and paired them with plan.actions
            # by row index elsewhere -- both the recreation and the
            # index-pairing were unsafe, since build_plan() can drop groups
            # and shift every later row out of alignment with a
            # separately-tracked list).
            self._groups = [a.source_group for a in plan.actions if a.source_group is not None]
            self._apply_permanent_exclusions(self._groups)
            self.plan = build_plan(library, self._groups)
            self._artwork_cache = {}
            self.restore_btn.setEnabled(True)
            self.toolbar_restore_action.setEnabled(True)
            self.toolbar_save_restore_point_action.setEnabled(True)
            self.toolbar_merge_tracks_action.setEnabled(True)
            self.write_back_cb.setEnabled(library.source_path is not None)
            self.status_label.setText(
                f"{len(library.tracks)} tracks · {len(library.user_playlists())} playlists · "
                f"{path_name(library)}"
            )
            self._expanded_row = None
            self._stop_detail_panel_previews()
            self.detail_scroll_area.setVisible(False)
            # Reset any filter left over from a previous library so the
            # newly loaded results aren't hidden by a stale search/tier
            # selection.
            self.filter_edit.blockSignals(True)
            self.filter_edit.clear()
            self.filter_edit.blockSignals(False)
            self.filter_tier_combo.blockSignals(True)
            self.filter_tier_combo.setCurrentIndex(0)
            self.filter_tier_combo.blockSignals(False)
            self._populate_table(self.plan)
            self._refresh_health()
            # "What changed since last export": compares this load against
            # the fingerprint recorded the last time a Library.xml from
            # this same source path was opened (see
            # _record_export_fingerprint/_diff_against_last_export in
            # core/library_diff.py). Computed here, inside the same
            # try/finally as everything else in this method, but never
            # allowed to affect whether the load itself succeeds --
            # wrapped in its own try/except so a fingerprinting problem
            # (e.g. a corrupt saved setting) can never leave the toolbar
            # stuck the way the bug fix above guards against for the rest
            # of this method.
            self._pending_library_diff = None
            try:
                self._pending_library_diff = self._diff_against_last_export(library)
                self._record_export_fingerprint(library)
            except Exception:
                pass
        finally:
            self._set_busy(False)

        # Shown after busy state clears (same ordering as the scheduled-
        # rescan toast below) and skipped for a scheduled background
        # rescan, which already gets its own toast summary instead of an
        # interactive dialog for something that ran unprompted.
        if not self._pending_scheduled_rescan and self._pending_library_diff is not None:
            self._show_library_diff_dialog(self._pending_library_diff)
        self._pending_library_diff = None

        if self._pending_scheduled_rescan:
            self._pending_scheduled_rescan = False
            self._scheduled_rescan_path = None
            review_count = len(self.plan.review_actions)
            found = len(self.plan.actions)
            if found:
                review_note = f" ({review_count} need review)" if review_count else ""
                message = (
                    f"\U0001F50D Scheduled re-scan: found {found} duplicate "
                    f"group(s){review_note} in {path_name(self.library)}."
                )
                severity = SEVERITY_WARNING if review_count else TOAST_SUCCESS
            else:
                message = (
                    f"\U0001F50D Scheduled re-scan: no duplicates found in "
                    f"{path_name(self.library)}."
                )
                severity = TOAST_SUCCESS
            self._toast(message, severity)

    def _on_load_failed(self, message: str) -> None:
        self._set_busy(False)
        self._clear_table_skeleton()
        was_scheduled = self._pending_scheduled_rescan
        self._pending_scheduled_rescan = False
        self._scheduled_rescan_path = None
        # The raw `message` (WinError codes, exception text, etc.) is kept
        # in the log file for troubleshooting; the dialog itself only ever
        # shows the sanitized, non-technical version -- see errors.py.
        error_log.log_error(f"Couldn't open library: {message}")
        if was_scheduled:
            # A background scheduled rescan failing shouldn't interrupt
            # startup with a blocking dialog the way an explicit Open
            # does -- the error is still recorded above (Settings ->
            # Diagnostics) for anyone who wants to know why, and a toast
            # is enough of a heads-up for something that ran unprompted.
            self._toast(
                "\U0001F50D Scheduled re-scan couldn't run — see the error "
                "log in Settings → Diagnostics.",
                SEVERITY_WARNING,
            )
            return
        show_critical(self, "Couldn't open library", with_recovery_guidance(message))

    # ---------------------------------------------------------- library diff

    # Prefix for the per-source-path CacheDB setting key each fingerprint
    # is stored under (see _record_export_fingerprint/
    # _diff_against_last_export) -- namespaced like the existing recent-
    # files/ui-state keys in this same ui_settings table, keyed by the
    # library's resolved source path so opening a *different* library
    # never gets compared against an unrelated one's last-seen state.
    _EXPORT_FINGERPRINT_KEY_PREFIX = "export_fingerprint::"

    def _export_fingerprint_setting_key(self, library: Library) -> str | None:
        if library.source_path is None:
            return None
        try:
            resolved = str(library.source_path.resolve())
        except OSError:
            resolved = str(library.source_path)
        return f"{self._EXPORT_FINGERPRINT_KEY_PREFIX}{resolved}"

    def _diff_against_last_export(self, library: Library) -> "LibraryDiff | None":
        """Returns a LibraryDiff comparing `library` against the
        fingerprint recorded the last time this same source path was
        opened, or None if there's nothing to compare against yet (first
        time this file has been opened, or the saved fingerprint predates
        this feature/is unreadable)."""
        key = self._export_fingerprint_setting_key(library)
        if key is None:
            return None
        previous = self.cache.get_setting(key, default=None)
        if previous is None:
            return None
        return diff_against_fingerprint(library, previous)

    def _record_export_fingerprint(self, library: Library) -> None:
        """Saves a compact fingerprint of `library`'s current state so the
        *next* time this same source path is opened, _diff_against_last_export
        has something to compare against. Best-effort: called from inside
        the same try/except as _diff_against_last_export above, so any
        failure here (e.g. disk full) is silently swallowed rather than
        affecting the load that's already succeeded."""
        key = self._export_fingerprint_setting_key(library)
        if key is None:
            return
        self.cache.set_setting(key, build_fingerprint(library))

    def _show_library_diff_dialog(self, diff: "LibraryDiff") -> None:
        """Shows a summary of what changed since the last time this
        library's source file was opened. Only called when there *is* a
        previous fingerprint to compare against (see
        _diff_against_last_export) -- the very first time a file is
        opened, there's nothing to show, so no dialog appears at all."""
        if not diff.has_changes:
            # Explicitly re-opened a newer export with nothing detectably
            # different (e.g. re-exported with no library edits since) --
            # a brief toast is enough; not worth an interruptive dialog.
            self._toast("\U0001F50D No changes detected since the last time this library was opened.", TOAST_SUCCESS)
            return

        lines: list[str] = []
        if diff.previous_export_date:
            lines.append(f"Since the export dated {diff.previous_export_date}:")
        else:
            lines.append("Since the last time this library was opened:")
        lines.append("")
        if diff.added_track_ids:
            lines.append(f"\u2795 {len(diff.added_track_ids)} track(s) added")
        if diff.removed_track_ids:
            lines.append(f"\u2796 {len(diff.removed_track_ids)} track(s) removed")
        if diff.modified:
            lines.append(f"\u270F\uFE0F {len(diff.modified)} track(s) with changed metadata")
        if diff.playlist_count_delta:
            direction = "more" if diff.playlist_count_delta > 0 else "fewer"
            lines.append(f"\U0001F4C1 {abs(diff.playlist_count_delta)} {direction} playlist(s)")

        # A handful of concrete examples beyond the summary counts above --
        # capped so this stays a quick skim even on a library with
        # thousands of changed tracks, not a full per-track changelog.
        _MAX_EXAMPLES = 10
        examples: list[str] = []
        for track_id in diff.added_track_ids[:_MAX_EXAMPLES]:
            track = self.library.tracks.get(track_id) if self.library else None
            if track is not None:
                examples.append(f"  + {track.artist or 'Unknown artist'} — {track.name or 'Unknown title'}")
        for track_id in diff.removed_track_ids[:_MAX_EXAMPLES]:
            examples.append(f"  \u2013 Track ID {track_id} (no longer in this library)")
        if examples:
            lines.append("")
            lines.append("Examples:")
            lines.extend(examples[:_MAX_EXAMPLES])
            total_listed = min(len(diff.added_track_ids), _MAX_EXAMPLES) + min(
                len(diff.removed_track_ids), _MAX_EXAMPLES
            )
            remaining = len(diff.added_track_ids) + len(diff.removed_track_ids) - total_listed
            if remaining > 0:
                lines.append(f"  \u2026and {remaining} more")

        box = QMessageBox(self)
        box.setWindowTitle("\U0001F50D What changed since last export")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("\n".join(lines))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # Row count for the placeholder skeleton shown while a library is
    # loading (see _show_table_skeleton) -- enough to fill a typical
    # window height without over-allocating widgets for a state that's
    # only ever visible briefly.
    _SKELETON_ROW_COUNT = 8

    def _show_table_skeleton(self) -> None:
        """Fills the (currently empty/stale) table with placeholder
        "skeleton" rows while a library loads, instead of leaving it
        blank or showing the previous library's rows frozen on screen.

        Bug fix: previously, clicking Open showed only the progress bar/
        status text -- the table itself stayed exactly as it was (empty
        on first load, or showing the *previous* library's rows on a
        second load) until the load finished and _populate_table() ran,
        which could read as "nothing is happening" during a slow parse of
        a very large library. These rows are inert (no checkboxes, no
        cell widgets, sorting/selection disabled) and are always replaced
        wholesale by _populate_table() once real data is ready -- they're
        never partially reused."""
        self.empty_state_label.setVisible(False)
        self.table.setVisible(True)
        self.table.setSortingEnabled(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setRowCount(self._SKELETON_ROW_COUNT)
        # Alternating placeholder widths so the skeleton reads as "rows of
        # text" rather than a uniform gray block, without needing any
        # animation/timer machinery for a state that's only ever shown for
        # a few seconds.
        width_fractions = (0.6, 0.4, 0.75)
        for row in range(self._SKELETON_ROW_COUNT):
            for col in range(self.table.columnCount()):
                bar = QLabel()
                bar.setFixedHeight(14)
                bar.setStyleSheet(
                    "background-color: rgba(127, 127, 127, 60); "
                    "border-radius: 4px;"
                )
                col_width = max(self.table.columnWidth(col), 40)
                fraction = width_fractions[(row + col) % len(width_fractions)]
                bar.setFixedWidth(max(int(col_width * fraction) - 20, 10))
                container = QWidget()
                bar_layout = QHBoxLayout(container)
                bar_layout.setContentsMargins(10, 6, 10, 6)
                bar_layout.addWidget(bar)
                bar_layout.addStretch(1)
                self.table.setCellWidget(row, col, container)
        self._skeleton_active = True

    def _clear_table_skeleton(self) -> None:
        """Removes any skeleton rows left over from _show_table_skeleton.
        Safe to call even if no skeleton is currently showing (e.g. a load
        that fails before any row was ever added)."""
        if getattr(self, "_skeleton_active", False):
            self.table.setRowCount(0)
            self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            self._skeleton_active = False

    def _populate_table(self, plan: ConsolidationPlan) -> None:
        self._clear_table_skeleton()
        # Sorting must be off while rows are being inserted/filled --
        # QTableWidget can reorder rows as items land when sorting is
        # live, which would scatter a row's checkbox/badge cell widgets
        # away from its QTableWidgetItems mid-populate. Re-enabled once
        # every row is fully built below.
        self.table.setSortingEnabled(False)
        # setUpdatesEnabled(False) suspends the table's repaint/layout
        # work for the duration of the populate loop below instead of
        # relayouting after every single setItem/setCellWidget call -- on
        # a very large library (many thousand duplicate-group rows), that
        # per-call repaint is what made bulk population visibly lag the
        # UI thread. Restored in the finally below (not just after the
        # call) so a malformed plan can't leave the table permanently
        # frozen mid-populate; batching every row's repaint into one when
        # updates come back on removes the lag without changing what ends
        # up in any cell.
        self.table.setUpdatesEnabled(False)
        try:
            self._populate_table_rows(plan)
        finally:
            self.table.setUpdatesEnabled(True)

    def _populate_table_rows(self, plan: ConsolidationPlan) -> None:
        self.table.setRowCount(len(plan.actions))
        for row, action in enumerate(plan.actions):
            cb = QCheckBox()
            # v2.1: when a complete copy of this album exists elsewhere in
            # the library and this group's duplicate track belongs to the
            # incomplete copy, pre-check it (and say so in the tooltip) so
            # cleaning up "album re-imported in full" cases doesn't
            # require re-checking every overlapping track by hand -- the
            # user still reviews the table and clicks Apply as normal,
            # nothing here removes anything by itself. Only ever turns a
            # row ON; a low-confidence fuzzy/review-tier row is never
            # auto-checked by this, same rule as every other pre-check
            # below (needs_review always wins).
            if action.incomplete_album_overlap and not action.needs_review:
                cb.setToolTip(
                    "Include this group when cleaning up duplicates.\n\n"
                    "Pre-checked: a complete copy of this album was found "
                    "elsewhere in your library, so this track looks "
                    "redundant. Still requires Apply."
                )
            else:
                cb.setToolTip("Include this group when cleaning up duplicates.")
            # Only pre-check exact and high-confidence matches. Low-confidence
            # "possible duplicate" matches always require the user to opt in
            # explicitly, so a shaky fuzzy match can never merge silently.
            cb.setChecked(not action.needs_review)
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.addWidget(cb)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.table.setCellWidget(row, 0, cb_container)

            name_item = QTableWidgetItem(action.canonical_name)
            # Stashes this row's original plan-index on the Song item so it
            # can still be resolved back to the right action after the user
            # sorts the table (sorting reorders visual rows but this data
            # travels with the item) -- see _action_for_row().
            name_item.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, QTableWidgetItem(action.canonical_artist))

            removed_item = QTableWidgetItem()
            removed_item.setData(Qt.ItemDataRole.DisplayRole, len(action.removed_ids))
            self.table.setItem(row, 3, removed_item)

            playlists_item = QTableWidgetItem()
            playlists_item.setData(Qt.ItemDataRole.DisplayRole, len(action.playlists_updated))
            self.table.setItem(row, 4, playlists_item)

            play_count_item = QTableWidgetItem()
            play_count_item.setData(Qt.ItemDataRole.DisplayRole, action.merged_play_count)
            self.table.setItem(row, 5, play_count_item)

            # Match confidence: a colored badge (see ui/theme.py's
            # tierBadge* objectNames) instead of plain colored text, so
            # the three tiers are distinguishable at a glance rather than
            # only by a subtle foreground-color difference. The invisible
            # QTableWidgetItem underneath still carries the sortable text
            # so header-click sorting on this column works.
            tier_display = _tier_display(action.tier)
            confidence_text = tier_display.label if action.tier == TIER_EXACT else (
                f"{tier_display.label} ({action.similarity:.0%})"
            )
            confidence_item = QTableWidgetItem(confidence_text)
            self.table.setItem(row, 6, confidence_item)
            badge = QLabel(confidence_text)
            badge.setObjectName(tier_display.badge_object_name)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_container = QWidget()
            badge_layout = QHBoxLayout(badge_container)
            badge_layout.addWidget(badge)
            badge_layout.setContentsMargins(6, 4, 6, 4)
            badge_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.table.setCellWidget(row, 6, badge_container)

            reason_text = _match_reason_text(action)
            if action.incomplete_album_overlap:
                reason_text += " \U0001F4BF complete album copy found elsewhere"
            if action.smart_playlist_warnings:
                reason_text += " ⚠️ may affect a smart playlist"
            reason_item = QTableWidgetItem(reason_text)
            tooltip = _match_reason_text(action)
            if action.incomplete_album_overlap:
                tooltip += (
                    "\n\nA complete copy of this album was found elsewhere "
                    "in your library — this track looks redundant."
                )
            if action.smart_playlist_warnings:
                tooltip += (
                    "\n\nMight affect: "
                    + ", ".join(action.smart_playlist_warnings)
                    + "\nWe can't be 100% sure, so it's worth a quick check "
                    "afterward."
                )
            reason_item.setToolTip(tooltip)
            self.table.setItem(row, 7, reason_item)

        self.table.setSortingEnabled(True)
        has_actions = len(plan.actions) > 0
        self.select_all_cb.setEnabled(has_actions)
        self.select_all_exact_btn.setEnabled(has_actions)
        self.select_all_high_conf_btn.setEnabled(has_actions)
        self.select_all_everything_btn.setEnabled(has_actions)
        self.exclude_reviewed_out_btn.setEnabled(has_actions)
        self.select_all_cb.setChecked(has_actions and len(plan.review_actions) < len(plan.actions))
        self.apply_btn.setEnabled(has_actions)

        if has_actions:
            review_count = len(plan.review_actions)
            review_note = f" ({review_count} need your review first)" if review_count else ""
            self._base_summary_text = (
                f"Found {len(plan.actions)} duplicate group(s) — "
                f"{plan.total_duplicates_removed} song(s) would be removed{review_note}. "
                "Nothing has changed yet."
            )
        else:
            self._base_summary_text = "🎉 No duplicates found. Your library is already clean."

        # Re-apply the current search/filter text and tier over the newly
        # populated rows (e.g. after a manual review action rebuilds the
        # plan) so an active filter doesn't silently reset itself.
        self._apply_filter()

    def _action_for_row(self, row: int):
        """Resolves a *visual* table row back to its ConsolidationAction,
        independent of the table's current sort order. Column 1 (Song)
        carries the row's original self.plan.actions index in UserRole
        data (set in _populate_table) precisely so this lookup keeps
        working after the user sorts by clicking a header -- without it,
        every row-index-based lookup in this class (detail panel, manual
        review actions, selection) would silently point at the wrong
        group post-sort."""
        if not self.plan:
            return None
        item = self.table.item(row, 1)
        if item is None:
            return None
        plan_index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(plan_index, int) or not (0 <= plan_index < len(self.plan.actions)):
            return None
        return self.plan.actions[plan_index]

    def _on_filter_changed(self, *_args) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Hides table rows that don't match the current search text
        (matched against artist or song name, case-insensitive) and/or the
        selected confidence tier. Row *visibility* is toggled by visual
        row, and each row's action is resolved via _action_for_row (not a
        plan.actions[row] index) so this keeps working regardless of the
        table's current sort order -- selection, the detail panel, and
        manual review actions all keep working unmodified on whatever
        rows happen to be visible."""
        if not self.plan:
            self.table.setVisible(False)
            self.empty_state_label.setVisible(True)
            self.empty_state_label.setText("🎵 Open a library to find duplicates. You can also drag a file onto this window.")
            return

        query = self.filter_edit.text().strip().lower()
        tier_filter = self.filter_tier_combo.currentData()

        # Iterate by *visual* table row (not self.plan.actions order) and
        # resolve each row's action via _action_for_row -- with sorting
        # enabled (see _populate_table), a visual row's position no longer
        # matches its index in self.plan.actions, so the two must be
        # looked up independently rather than assumed to line up.
        visible_count = 0
        for row in range(self.table.rowCount()):
            action = self._action_for_row(row)
            if action is None:
                continue
            matches_text = (
                not query
                or query in action.canonical_name.lower()
                or query in action.canonical_artist.lower()
            )
            matches_tier = tier_filter is None or action.tier == tier_filter
            row_visible = matches_text and matches_tier
            self.table.setRowHidden(row, not row_visible)
            if row_visible:
                visible_count += 1

        has_any_actions = len(self.plan.actions) > 0
        has_filter_active = bool(query) or tier_filter is not None
        if not has_any_actions:
            self.table.setVisible(False)
            self.empty_state_label.setVisible(True)
            self.empty_state_label.setText("🎉 No duplicates found. Your library is already clean.")
        elif visible_count == 0 and has_filter_active:
            self.table.setVisible(False)
            self.empty_state_label.setVisible(True)
            self.empty_state_label.setText(
                "🔍 Nothing matches your filter. Try a different search "
                "or confidence level."
            )
        else:
            self.table.setVisible(True)
            self.empty_state_label.setVisible(False)

        # "Select all" and the results summary should reflect what's
        # actually visible under the current filter, not the whole plan --
        # otherwise checking "select all" while filtered could silently
        # select rows the user can't currently see. When no filter is
        # active, always fall back to the unfiltered base summary (set in
        # _populate_table) rather than leaving stale filtered text behind
        # from before the filter was cleared.
        if has_filter_active and has_any_actions:
            visible_review = 0
            for row in range(self.table.rowCount()):
                if self.table.isRowHidden(row):
                    continue
                a = self._action_for_row(row)
                if a is not None and a.needs_review:
                    visible_review += 1
            review_note = f" ({visible_review} need your review)" if visible_review else ""
            self.summary_label.setText(
                f"Showing {visible_count} of {len(self.plan.actions)} duplicate group(s){review_note}."
            )
        else:
            self.summary_label.setText(getattr(self, "_base_summary_text", ""))

    def _refresh_health(self) -> None:
        if not self.library:
            self.summary_bar_label.setText("📊 Open a library to see duplicate and savings totals.")
            return
        report = analyze_library(self.library, duplicate_groups=self._groups)
        self.health_panel.set_report(report, library=self.library)
        trend_suffix = self._trend_summary_suffix(report.duplicate_track_count)
        self.summary_bar_label.setText(
            f"{report.duplicate_track_count} duplicate(s) found, "
            f"{report.estimated_storage_savings_human()} potential savings"
            f"{trend_suffix}"
        )
        self._record_health_snapshot_stats(report)

    def _trend_summary_suffix(self, current_duplicate_count: int) -> str:
        """Short trailing clause comparing this scan's duplicate count to
        this same library's previous recorded scan (e.g. " — 12 fewer
        duplicates than last scan"), or "" if there's no prior scan of
        this library to compare against yet. Reads from the same
        health_snapshot_stats history already recorded for the growth
        timeline (see _record_health_snapshot_stats/cache_db.
        list_health_snapshots) -- purely a different view of that same
        data, nothing new is stored for this."""
        if not self.library:
            return ""
        source = str(self.library.source_path) if self.library.source_path else "(unsaved)"
        try:
            previous = self._previous_health_snapshot_for_source(source)
        except Exception as exc:
            error_log.log_error("Couldn't compute duplicate trend", exc)
            return ""
        if previous is None:
            return ""
        delta = current_duplicate_count - previous["duplicate_track_count"]
        when = datetime.datetime.fromtimestamp(previous["created_at"]).strftime("%Y-%m-%d")
        if delta == 0:
            return f" — same as last scan ({when})"
        direction = "fewer" if delta < 0 else "more"
        return f" — {abs(delta)} {direction} duplicate(s) than last scan ({when})"

    def _previous_health_snapshot_for_source(self, source_path: str) -> dict | None:
        """Most recent recorded health-snapshot point for `source_path`
        strictly before the one _record_health_snapshot_stats is about to
        write/update for the current scan -- i.e. "last time", not "this
        time". Returns None if this library has no earlier recorded scan.
        """
        points = [p for p in self.cache.list_health_snapshots() if p["source_path"] == source_path]
        if len(points) < 2:
            # Only the current scan (or none yet) has been recorded for
            # this library -- nothing earlier to compare against. Also
            # covers the very first scan of a library, before
            # _record_health_snapshot_stats has written anything at all.
            return None
        # list_health_snapshots returns oldest-first; the second-to-last
        # entry is "last scan" relative to the one about to be recorded/
        # updated for the current call.
        return points[-2]

    def _record_health_snapshot_stats(self, report) -> None:
        """Records one point for the growth/duplicate-accumulation
        timeline (see cache_db.CacheDB.record_health_snapshot and
        _on_show_growth_timeline). Called from _refresh_health, so this
        runs on every load and every plan rebuild -- min_interval_seconds
        collapses rapid repeats (e.g. several manual-review edits back to
        back) into a single moving point instead of a dense cluster."""
        if not self.library:
            return
        source = str(self.library.source_path) if self.library.source_path else "(unsaved)"
        try:
            self.cache.record_health_snapshot(
                source,
                len(self.library.tracks),
                report.duplicate_track_count,
                min_interval_seconds=60.0,
            )
        except Exception as exc:
            # Purely a nice-to-have chart data point; never let a
            # recording failure interrupt the health refresh it's piggy-
            # backing on.
            error_log.log_error("Couldn't record health snapshot stats", exc)

    def _on_show_growth_timeline(self) -> None:
        """"Library growth" button on the Health tab: shows a small line
        chart of track count and duplicate count over time, built from
        every recorded health-snapshot point (see cache_db.
        list_health_snapshots) across every library this app has scanned
        on this machine. Hand-drawn with QPainter on a QWidget rather than
        pulling in a charting dependency (matplotlib etc.) for what is, at
        the scale this app's history table ever reaches (a few hundred
        points), a simple two-line plot -- consistent with this app's
        existing "no new dependency for a small, well-understood drawing
        task" choice in ui/widgets.py's choose_library_annotated_pixmap."""
        points = self.cache.list_health_snapshots()
        dialog = QDialog(self)
        dialog.setWindowTitle("\U0001F4C8 Library growth over time")
        dialog.resize(680, 460)
        layout = QVBoxLayout(dialog)

        if len(points) < 2:
            empty = QLabel(
                "Not enough history yet. This chart fills in as you open "
                "and review libraries over time — come back after a few "
                "more sessions."
            )
            empty.setObjectName("subtitle")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        else:
            intro = QLabel(
                "Total tracks and duplicate tracks found, each time this "
                "app scanned a library. Multiple libraries share this "
                "timeline if you've opened more than one."
            )
            intro.setObjectName("subtitle")
            intro.setWordWrap(True)
            layout.addWidget(intro)

            trend_text = self._latest_vs_previous_trend_text(points)
            if trend_text:
                trend_label = QLabel(trend_text)
                trend_label.setObjectName("subtitle")
                trend_label.setWordWrap(True)
                layout.addWidget(trend_label)

            layout.addWidget(
                GrowthTimelineChart(points, track_color=accent_color(self._theme_preference)),
                stretch=1,
            )

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()

    def _latest_vs_previous_trend_text(self, points: list[dict]) -> str:
        """Headline comparison sentence for the growth timeline dialog,
        e.g. "This scan: 12 fewer duplicates and 340 more tracks than
        last scan (2026-08-09)." Compares the two most recent points that
        share the same source_path as the very latest point, so a
        multi-library history doesn't compare one library's count against
        a different library's. `points` is already oldest-first (see
        cache_db.list_health_snapshots)."""
        if len(points) < 2:
            return ""
        latest = points[-1]
        same_source = [p for p in points if p["source_path"] == latest["source_path"]]
        if len(same_source) < 2:
            return ""
        previous = same_source[-2]
        track_delta = latest["track_count"] - previous["track_count"]
        dup_delta = latest["duplicate_track_count"] - previous["duplicate_track_count"]
        when = datetime.datetime.fromtimestamp(previous["created_at"]).strftime("%Y-%m-%d")

        def _phrase(delta: int, noun: str) -> str:
            if delta == 0:
                return f"the same {noun}"
            direction = "fewer" if delta < 0 else "more"
            return f"{abs(delta)} {direction} {noun}"

        return (
            f"This scan: {_phrase(dup_delta, 'duplicates')} and "
            f"{_phrase(track_delta, 'tracks')} than last scan ({when})."
        )

    def _on_locate_missing_file(self, track_id: int) -> None:
        """Handles HealthPanel.locate_file_requested: lets the user browse
        to where a track's audio file actually is and relinks the track's
        Location to it (core.health_actions.relink_track_location).
        In-memory only -- like any other edit in this app (manual review,
        consolidation), it's picked up by the normal save/write-back flow
        the next time the user saves, not written to disk immediately."""
        if not self.library:
            return
        track = self.library.tracks.get(track_id)
        if track is None:
            return
        start_dir = ""
        existing_path = file_uri_to_path(track.location) if track.location else None
        if existing_path is not None:
            start_dir = str(existing_path.parent)
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            f"Locate '{track.name or 'this track'}'",
            start_dir,
            "Audio files (*.mp3 *.m4a *.m4p *.mp4 *.flac *.wav *.aac);;All files (*.*)",
        )
        if not path_str:
            return
        result = relink_track_location(track, Path(path_str))
        if not result.ok:
            show_warning(self, "Couldn't relink file", result.message)
            return
        self.cache.rebuild_track_index(self.library.tracks.values(), normalize)
        self._toast(f"'{track.name or 'Track'}' relinked.", TOAST_SUCCESS)
        self._refresh_health()

    def _on_find_missing_files_in_folder(self) -> None:
        """Handles HealthPanel.find_missing_in_folder_requested: asks for
        one root folder and searches it (recursively) for every currently
        missing/broken-Location track's file by filename
        (core.health_actions.find_missing_files_in_root) -- for the case
        covered by "Locate missing file…" one at a time, just for many
        tracks at once after e.g. a whole music folder was moved or
        reorganized into different subfolders. Matches are shown for
        review before anything is relinked; only confirmed matches are
        applied, the same "review before write" shape as duplicate
        clean-up and every other action in this app."""
        if not self.library:
            return
        report = analyze_library(self.library.tracks.values())
        if not report.missing_or_broken_location:
            show_info(
                self, "Nothing to find",
                "No missing or broken files were found in this library.",
            )
            return

        remembered = self.cache.get_setting("missing_files_search_dir")
        start_dir = remembered or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select the folder to search for missing files",
            start_dir,
        )
        if not chosen:
            return
        root_folder = Path(chosen)
        self.cache.set_setting("missing_files_search_dir", str(root_folder))

        crash_reporter.record_action(f"Searching for missing files under {root_folder}")
        matches = find_missing_files_in_root(
            self.library, root_folder, report.missing_or_broken_location
        )
        if not matches:
            show_info(
                self, "No matches found",
                f"None of the {len(report.missing_or_broken_location)} missing/"
                f"broken track(s) had a matching filename anywhere under:\n\n"
                f"{root_folder}",
            )
            return

        preview_lines = [m.display_name for m in matches[:20]]
        preview = "\n".join(f"\u2022 {line}" for line in preview_lines)
        if len(matches) > len(preview_lines):
            preview += f"\n...and {len(matches) - len(preview_lines)} more."
        confirm = QMessageBox.question(
            self, "Relink found files?",
            f"Found matching files for {len(matches)} of "
            f"{len(report.missing_or_broken_location)} missing/broken track(s) "
            f"under:\n{root_folder}\n\n{preview}\n\n"
            "Relink these tracks to the files found? Nothing else about "
            "them (name, artist, playlists) changes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        relinked = 0
        failed: list[str] = []
        for match in matches:
            track = self.library.tracks.get(match.track_id)
            if track is None:
                continue
            result = relink_track_location(track, match.found_path)
            if result.ok:
                relinked += 1
            else:
                failed.append(f"{match.display_name}: {result.message}")

        if relinked:
            self.cache.rebuild_track_index(self.library.tracks.values(), normalize)
            self._toast(f"Relinked {relinked} track(s).", TOAST_SUCCESS)
        if failed:
            show_warning(
                self, "Some files couldn't be relinked", "\n".join(failed)
            )
        self._refresh_health()

    def _on_fix_missing_artwork(self, track_id: int) -> None:
        """Handles HealthPanel.fix_artwork_requested: looks for another
        local copy of the same song that already has embedded artwork
        (core.health_actions.find_artwork_source) and, if found, records
        it as an available artwork source for this track. This app has no
        network access and does not fetch artwork online — see
        core/health_actions.py's module docstring for why — so when no
        local copy with art exists, this says so plainly instead of
        pretending to look further."""
        if not self.library:
            return
        track = self.library.tracks.get(track_id)
        if track is None:
            return
        candidates = find_artwork_source(self.library, track, max_candidates=1)
        if not candidates:
            show_info(
                self,
                "No artwork found",
                f"'{track.name or 'This track'}' has no other local copy in "
                "this library with readable embedded artwork to copy from. "
                "This app doesn't fetch artwork from the internet — you can "
                "add art with iTunes/Apple Music or a tag editor, then "
                "reopen this library to pick it up.",
            )
            return
        result = apply_artwork_from_source(self.library, track, candidates[0])
        if not result.ok:
            show_warning(self, "Couldn't use that artwork", result.message)
            return
        show_info(self, "Artwork source found", result.message)
        self._toast(f"Artwork source found for '{track.name or 'track'}'.", TOAST_SUCCESS)
        self._refresh_health()

    def _rebuild_plan_from_groups(self) -> None:
        """Re-derives the ConsolidationPlan from the current (possibly
        user-edited) self._groups list — used after a manual review action
        changes a group's canonical pick or not-duplicate flag."""
        if not self.library:
            return
        self.plan = build_plan(self.library, self._groups)
        self._expanded_row = None
        self._stop_detail_panel_previews()
        self.detail_scroll_area.setVisible(False)
        self._populate_table(self.plan)
        self._refresh_health()

    def _collapse_detail_panel(self) -> None:
        """Collapses the expanded detail panel, if one is open. Shared by
        clicking the already-expanded row again and by the panel's own
        Close button (see _populate_detail_panel)."""
        self._expanded_row = None
        self._stop_detail_panel_previews()
        self.detail_scroll_area.setVisible(False)

    def _on_row_clicked(self, row: int, _column: int) -> None:
        if not self.plan or self._action_for_row(row) is None:
            return
        if self._expanded_row == row:
            self._collapse_detail_panel()
            return
        self._expanded_row = row
        self._populate_detail_panel(row)
        self.detail_scroll_area.setVisible(True)
        # Bug fix: give the newly-expanded row a sensible starting height
        # via the splitter (see table_detail_splitter/_DETAIL_PANEL_
        # DEFAULT_MAX_HEIGHT) instead of letting it grow to fit however
        # many copies this group has -- a group with many copies could
        # previously take over most of the window, leaving no visible way
        # to reach the titlebar/close button. Only applied the first time
        # a row is expanded in this splitter's lifetime (i.e. while the
        # detail pane's current height is still 0) -- if the user has
        # already dragged the handle to a size they prefer, re-expanding a
        # different row keeps that size instead of resetting it every
        # click.
        sizes = self.table_detail_splitter.sizes()
        if len(sizes) == 2 and sizes[1] == 0:
            total = sum(sizes) or self.table_detail_splitter.height()
            detail_height = min(_DETAIL_PANEL_DEFAULT_MAX_HEIGHT, max(total - _DETAIL_PANEL_MIN_HEIGHT, _DETAIL_PANEL_MIN_HEIGHT))
            self.table_detail_splitter.setSizes([max(total - detail_height, _DETAIL_PANEL_MIN_HEIGHT), detail_height])

    def _stop_detail_panel_previews(self) -> None:
        """Stops any audio preview currently playing in the detail
        panel before it's rebuilt/hidden (collapsing a row, expanding a
        different one, or a full table repopulate after a manual review
        edit) -- otherwise a preview started on one group could keep
        playing silently in the background after the row that started
        it is gone. Safe to call even when nothing is playing."""
        for player in self.detail_panel.findChildren(AudioPreviewPlayer):
            player.stop()

    def _populate_detail_panel(self, row: int) -> None:
        self._stop_detail_panel_previews()
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        action = self._action_for_row(row)
        if action is None:
            return

        # Bug fix: the expanded detail panel could previously only be
        # collapsed by clicking the same table row again -- with no visible
        # close control on the panel itself, a user who scrolled the table
        # (or simply didn't realize the row was the toggle) had no obvious
        # way to close it, even though the splitter handle let them resize
        # it freely. This explicit close button gives the panel its own
        # affordance, independent of the resize handle.
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("\u2715 Close")
        close_button.setObjectName("detailPanelCloseButton")
        close_button.setToolTip("Collapse this duplicate group's detail panel.")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self._collapse_detail_panel)
        close_row.addWidget(close_button)
        self.detail_layout.addLayout(close_row)

        match_reason = QLabel("Why it's a duplicate: " + _match_reason_text(action))
        match_reason.setObjectName("subtitle")
        match_reason.setWordWrap(True)
        self.detail_layout.addWidget(match_reason)

        reason = QLabel(action.canonical_reason or "Chosen automatically.")
        reason.setObjectName("sectionHeading")
        reason.setWordWrap(True)
        self.detail_layout.addWidget(reason)

        for track in action.group_tracks:
            is_canonical = track.track_id == action.canonical_id
            row_frame = QFrame()
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(4, 6, 4, 6)

            artwork_label = QLabel()
            artwork_label.setFixedSize(40, 40)
            artwork_label.setScaledContents(True)
            cached = self._cached_artwork_pixmap_for(track)
            # Bug fix: _cached_artwork_pixmap_for returns the _NOT_CACHED
            # sentinel (not None) when this track's artwork hasn't been
            # looked up yet -- "not looked up" and "looked up, confirmed
            # no artwork" (which caches as an actual None) are different
            # states and must be handled differently. The previous `is not
            # None` check treated the sentinel itself as a real pixmap and
            # passed it straight to setPixmap(), which raised
            # "TypeError: argument 1 has unexpected type 'object'" every
            # time a not-yet-cached row was expanded (see Diagnostics log).
            if cached is _NOT_CACHED:
                artwork_label.setText("♪")
                artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                artwork_label.setObjectName("subtitle")
                # Bug fix: previously read_embedded_artwork() ran inline
                # here, on the GUI thread -- opening/parsing the track's
                # real audio file. A file on a slow or currently-
                # unreachable network/offline path could stall the whole
                # UI for as long as the OS file-open call takes to give
                # up. Load it off-thread instead; the ♪ placeholder above
                # shows immediately and is swapped for the real artwork
                # if/when it arrives.
                self._start_artwork_load(track, artwork_label)
            elif cached is not None:
                artwork_label.setPixmap(cached)
            else:
                # cached is exactly None: already looked up this session
                # and confirmed this track has no embedded artwork. Leave
                # the ♪ placeholder as-is -- no need to load again.
                artwork_label.setText("♪")
                artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                artwork_label.setObjectName("subtitle")
            row_layout.addWidget(artwork_label)

            marker = "★ Keep" if is_canonical else "Remove"
            track_playlists = _playlists_for_track(self.library, track.track_id)
            if track_playlists:
                playlists_text = "in " + ", ".join(track_playlists)
            else:
                playlists_text = "not in any playlist"
            label = QLabel(
                f"{marker} — #{track.track_id} · {track.album or 'Unknown album'} · "
                f"{track.bitrate or '?'} kbps · {playlists_text}"
            )
            label.setObjectName("subtitle")
            label.setWordWrap(True)
            row_layout.addWidget(label, stretch=1)

            if not is_canonical:
                pick_btn = QPushButton("\u2705 Keep this one instead")
                pick_btn.clicked.connect(
                    lambda _checked=False, r=row, tid=track.track_id: self._on_set_canonical(r, tid)
                )
                row_layout.addWidget(pick_btn)

            self.detail_layout.addWidget(row_frame)

            # Inline audio preview: lets the user actually listen to
            # this specific copy to manually confirm it's a true
            # duplicate (rather than a same-titled remix/live version
            # fuzzy-matched together) before deciding whether to keep
            # it. Resolved the same way embedded-artwork lookup already
            # resolves a playable path (core.artwork.file_uri_to_path);
            # tracks with no resolvable local file degrade to a disabled
            # control (see AudioPreviewPlayer) rather than being hidden.
            preview_path = file_uri_to_path(track.location) if track.location else None
            preview_player = AudioPreviewPlayer(preview_path)
            self.detail_layout.addWidget(preview_player)

        playlist_names = ", ".join(action.playlists_updated) if action.playlists_updated else "None"
        playlists_label = QLabel(f"Playlists that reference this group: {playlist_names}")
        playlists_label.setObjectName("subtitle")
        playlists_label.setWordWrap(True)
        self.detail_layout.addWidget(playlists_label)

        if action.smart_playlist_warnings:
            smart_label = QLabel(
                "⚠️ Might affect: "
                + ", ".join(action.smart_playlist_warnings)
                + ". We can't be 100% sure, so it's worth a quick check "
                "afterward."
            )
            smart_label.setObjectName("subtitle")
            smart_label.setWordWrap(True)
            self.detail_layout.addWidget(smart_label)

        controls_row = QHBoxLayout()
        not_dup_btn = QPushButton("\U0001F6AB Mark this group as not duplicates")
        not_dup_btn.setObjectName("danger")
        not_dup_btn.clicked.connect(lambda _checked=False, r=row: self._on_mark_not_duplicate(r))
        controls_row.addWidget(not_dup_btn)
        controls_row.addStretch(1)
        controls_frame = QWidget()
        controls_frame.setLayout(controls_row)
        self.detail_layout.addWidget(controls_frame)

    def _cached_artwork_pixmap_for(self, track):
        """Cache-only lookup -- never touches disk. Returns the cached
        pixmap (or None-for-'known no artwork') if this track's artwork
        was already loaded this session, or the sentinel _NOT_CACHED if
        it hasn't been looked up yet, so the caller knows whether to kick
        off a background load."""
        if not hasattr(self, "_artwork_cache"):
            self._artwork_cache: dict[int, object] = {}
        return self._artwork_cache.get(track.track_id, _NOT_CACHED)

    def _artwork_thread_pool(self) -> QThreadPool:
        """Shared pool for artwork-load tasks, created once and reused for
        the lifetime of this window (see _ArtworkLoadTask). Capped at a
        small fixed size -- artwork reads are disk-bound, not CPU-bound,
        so more threads than this mostly just contend for the same disk
        rather than finishing faster, and it keeps the pool well clear of
        Qt's global default pool sizing (used elsewhere for other work)."""
        if not hasattr(self, "_artwork_pool") or self._artwork_pool is None:
            self._artwork_pool = QThreadPool(self)
            self._artwork_pool.setMaxThreadCount(4)
        return self._artwork_pool

    def _start_artwork_load(self, track, label: QLabel) -> None:
        """Loads one track's embedded artwork off the GUI thread (see bug
        fix note at the call site) and applies it to `label` if/when it
        finishes -- unless the label has since been deleted (row
        collapsed/re-expanded/table repopulated), which the RuntimeError
        guard below covers, since PyQt deletes the underlying C++ object
        on deleteLater() and any later access raises rather than silently
        no-op-ing.

        Runs on the shared _artwork_thread_pool (QThreadPool) rather than
        a one-off thread per call -- see _ArtworkLoadTask for why."""
        if not hasattr(self, "_artwork_cache"):
            self._artwork_cache: dict[int, object] = {}
        if not hasattr(self, "_artwork_pending"):
            # Tracks in-flight track_ids only (not thread objects -- the
            # pool owns the actual worker threads now) so closeEvent can
            # still tell whether anything is still outstanding.
            self._artwork_pending: set[int] = set()

        task = _ArtworkLoadTask(track.track_id, track.location)
        self._artwork_pending.add(track.track_id)

        def _on_loaded(track_id: int, image_bytes: object) -> None:
            pixmap = None
            if image_bytes:
                candidate = QPixmap()
                if candidate.loadFromData(image_bytes):
                    pixmap = candidate
            self._artwork_cache[track_id] = pixmap
            try:
                if pixmap is not None:
                    label.setPixmap(pixmap)
            except RuntimeError:
                pass  # label's row was collapsed/rebuilt before this returned
            self._artwork_pending.discard(track_id)

        # Qt.ConnectionType default (AutoConnection) correctly marshals
        # this back onto the GUI thread even though the signal is emitted
        # from a pool worker thread, same as the old per-row QThread did.
        task.signals.loaded.connect(_on_loaded)
        self._artwork_thread_pool().start(task)

    def _on_set_canonical(self, row: int, track_id: int) -> None:
        # Bug fix (v1.2.1): resolve the group via the action's own
        # source_group reference, not self._groups[row] -- see the note in
        # _populate_detail_panel for why row-index lookup into a separately
        # -filtered list is unsafe. Also resolved via _action_for_row (not
        # a raw plan.actions[row] index) so this still points at the right
        # group after the table has been sorted. _action_for_row already
        # returns None when self.plan is unset, so no separate guard is
        # needed here (it was previously duplicated at every call site).
        action = self._action_for_row(row)
        if action is None:
            return
        group = action.source_group
        if group is None:
            return
        group.canonical_override_id = track_id
        self._rebuild_plan_from_groups()

    def _on_mark_not_duplicate(self, row: int) -> None:
        action = self._action_for_row(row)
        if action is None:
            return
        group = action.source_group
        if group is None:
            return
        confirm = QMessageBox.question(
            self,
            "Mark as not duplicates",
            "This group will be skipped — nothing in it will be changed. "
            "You can undo this by reloading the library. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        group.marked_not_duplicate = True
        self._rebuild_plan_from_groups()

    def _on_select_all(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            # Rows hidden by the current search/filter are left as-is --
            # "select all" only acts on what's currently visible, so it
            # never silently selects a group the user has filtered out.
            if self.table.isRowHidden(row):
                continue
            container = self.table.cellWidget(row, 0)
            if not container or not self.plan:
                continue
            cb = container.findChild(QCheckBox)
            if not cb:
                continue
            action = self._action_for_row(row)
            if action is None:
                continue
            # "Select all" only covers exact/high-confidence rows; possible
            # duplicates stay opt-in even when this box is checked, matching
            # the label ("Select all (exact + high confidence)").
            if checked and action.needs_review:
                continue
            cb.setChecked(checked)

    def _set_row_checkboxes_by_tier(self, tiers: set[str]) -> None:
        """Shared implementation for the "Select all exact" / "Select all
        high-confidence" batch buttons: checks every currently-visible row
        whose tier is in `tiers` and unchecks every other currently-
        visible row, so each button gives a precise, repeatable selection
        rather than only ever adding to whatever was already checked.
        Rows hidden by the current search/filter are left untouched, same
        rule as the existing "Select all" checkbox above."""
        if not self.plan:
            return
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            container = self.table.cellWidget(row, 0)
            cb = container.findChild(QCheckBox) if container else None
            action = self._action_for_row(row)
            if not cb or action is None:
                continue
            cb.setChecked(action.tier in tiers)

    def _on_select_all_exact(self) -> None:
        self._set_row_checkboxes_by_tier({TIER_EXACT})

    def _on_select_all_high_confidence(self) -> None:
        self._set_row_checkboxes_by_tier({TIER_HIGH_CONFIDENCE})

    def _on_select_all_everything(self) -> None:
        """Checks every currently-visible row regardless of tier,
        including 'needs review' groups. See select_all_everything_btn
        setup comment above for why this exists as a separate control."""
        if not self.plan:
            return
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            container = self.table.cellWidget(row, 0)
            cb = container.findChild(QCheckBox) if container else None
            action = self._action_for_row(row)
            if not cb or action is None:
                continue
            cb.setChecked(True)

    # ------------------------------------------------- permanent exclusions

    def _permanently_excluded_keys(self) -> set[tuple[str, str]]:
        """Reads the persisted set of group identities excluded via
        "Exclude all reviewed-out groups permanently", decoded back into
        the (norm_artist, norm_title) tuples DuplicateGroup.key uses.
        Falls back to an empty set on anything unexpected (missing,
        corrupt, wrong shape) -- a bad/missing saved value should never
        block loading a library, only fall back to "nothing excluded"."""
        raw = self.cache.get_setting(PERMANENT_EXCLUSIONS_SETTING_KEY, default=[])
        if not isinstance(raw, list):
            return set()
        decoded: set[tuple[str, str]] = set()
        for item in raw:
            if not isinstance(item, str):
                continue
            parts = item.split(_GROUP_KEY_SEP)
            if len(parts) == 2:
                decoded.add((parts[0], parts[1]))
        return decoded

    def _save_permanently_excluded_keys(self, keys: set[tuple[str, str]]) -> None:
        try:
            self.cache.set_setting(
                PERMANENT_EXCLUSIONS_SETTING_KEY,
                sorted(_encode_group_key(k) for k in keys),
            )
        except Exception:
            # Best-effort, matching every other setting save in this class
            # -- a failed write shouldn't block using the exclusions for
            # the rest of this session.
            pass

    def _apply_permanent_exclusions(self, groups: list) -> None:
        """Marks every group in `groups` whose key is in the persisted
        permanent-exclusion set as not-duplicate, the same flag the
        existing per-group "Mark as not duplicates" button sets (see
        core/duplicate_detector.DuplicateGroup.marked_not_duplicate and
        core/consolidator.build_plan, which already skips flagged groups).
        Called wherever a fresh group list is derived for a library
        (initial load and the post-apply rescan) so a permanent exclusion
        keeps applying across reloads and sessions, not just for the
        session it was set in."""
        excluded = self._permanently_excluded_keys()
        if not excluded:
            return
        for group in groups:
            if group.key in excluded:
                group.marked_not_duplicate = True

    def _on_exclude_reviewed_out_permanently(self) -> None:
        """"Exclude all reviewed-out groups permanently": takes every
        group already marked not-duplicate in the current session
        (whether just now or from an earlier reload of this same
        permanent-exclusion set) and persists its identity so it's
        auto-excluded on every future load of any library too, not just
        skipped in this plan. Reviewed-out groups the user hasn't
        touched this session are unaffected -- this only makes existing
        not-duplicate decisions permanent, it doesn't mark anything new."""
        if not self._groups:
            return
        reviewed_out = [g for g in self._groups if g.marked_not_duplicate]
        if not reviewed_out:
            show_info(
                self,
                "Nothing to exclude",
                "No groups are currently marked as not duplicates. Use "
                "\"Mark this group as not duplicates\" on a group first, "
                "then come back to this to make it permanent.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Exclude permanently?",
            f"{len(reviewed_out)} group(s) marked as not duplicates will "
            "be remembered and automatically skipped every time you open "
            "any library from now on, not just this session. You can "
            "still undo this later by clearing the app's saved settings. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        excluded = self._permanently_excluded_keys()
        excluded.update(g.key for g in reviewed_out)
        self._save_permanently_excluded_keys(excluded)
        # Fix: this confirmation previously only ever flashed through the
        # status bar (statusBar().showMessage(..., 5000)) -- easy to miss
        # since it's the same one-line target the load/apply workers'
        # live progress text also writes to, and it would be silently
        # overwritten by the very next status update. A toast is
        # non-blocking (no click-to-dismiss required, unlike a
        # QMessageBox) but persists on screen independently of whatever
        # else is happening in the status bar.
        self._toast(
            f"{len(reviewed_out)} group(s) will now be skipped permanently.",
            TOAST_SUCCESS,
        )

    def _selected_actions(self):
        if not self.plan:
            return []
        selected = []
        for row in range(self.table.rowCount()):
            action = self._action_for_row(row)
            if action is None:
                continue
            container = self.table.cellWidget(row, 0)
            cb = container.findChild(QCheckBox) if container else None
            if cb and cb.isChecked():
                selected.append(action)
        return selected

    def _confirm_duplicate_removal_preview(self, selected) -> bool:
        """Confirmation dialog showing the exact tracks and playlists this
        consolidation will affect, not just aggregate counts -- so the
        user can see precisely what's being removed/repointed before
        committing, matching the same Yes/Continue-or-cancel gate the
        previous plain QMessageBox.question provided. Returns True to
        proceed, False to cancel; nothing here writes any data."""
        review_selected = [a for a in selected if a.needs_review]
        removed_count = sum(len(a.removed_ids) for a in selected)
        review_note = (
            f"\n\n📝 {len(review_selected)} of these are matches you checked "
            "yourself, not sure matches — take a last look below before "
            "continuing." if review_selected else ""
        )
        smart_warned = [a for a in selected if a.smart_playlist_warnings]
        smart_playlist_note = ""
        if smart_warned:
            affected_names = sorted({
                name for a in smart_warned for name in a.smart_playlist_warnings
            })
            smart_playlist_note = (
                f"\n\n⚠️ {len(smart_warned)} of these might affect a smart "
                "playlist: " + ", ".join(affected_names) + ". We can't be "
                "100% sure, so it's worth a quick check afterward if that "
                "playlist matters to you."
            )

        dialog = QDialog(self)
        dialog.setWindowTitle("Confirm cleanup")
        dialog.resize(560, 480)
        layout = QVBoxLayout(dialog)

        summary = QLabel(
            f"This will clean up {len(selected)} duplicate group(s), removing "
            f"{removed_count} extra song entries. Your playlists will still "
            "point to the song you're keeping.\n\n"
            "A backup is saved automatically before anything changes."
            f"{review_note}{smart_playlist_note}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        detail_label = QLabel("Exactly what will change:")
        detail_label.setObjectName("sectionHeading")
        layout.addWidget(detail_label)

        # Plain-language explainer for the list below. Added because the
        # KEEP/REMOVE list was reported as confusing on its own -- it
        # wasn't obvious that "REMOVE" means removing a duplicate entry
        # from the library file (not deleting the song, and not deleting
        # any audio file), or that nothing below has actually happened
        # yet. This doesn't change what the list shows, only adds context
        # above it.
        how_to_read = QLabel(
            "For each song: KEEP is the copy that stays. REMOVE lists the "
            "extra copies that will be taken out. This doesn't delete any "
            "music file — it just removes the duplicate entry, and any "
            "playlist that had it will now point to the KEEP copy instead. "
            "Nothing happens until you click Continue below."
        )
        how_to_read.setObjectName("subtitle")
        how_to_read.setWordWrap(True)
        layout.addWidget(how_to_read)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(self._duplicate_removal_preview_text(selected))
        layout.addWidget(preview, stretch=1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        button_box.button(QDialogButtonBox.StandardButton.Yes).setText("Continue")
        button_box.button(QDialogButtonBox.StandardButton.No).setText("Cancel")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _duplicate_removal_preview_text(self, selected) -> str:
        """Plain-text, per-group breakdown of exactly which track entries
        are kept/removed and which playlists get repointed -- built purely
        from data the selected actions already carry (removed_ids,
        group_tracks, playlists_updated), no new lookups needed.

        Capped at _PREVIEW_MAX_GROUPS groups: for a very large library
        (thousands of duplicate groups selected via "select all"),
        building and then rendering an uncapped plain-text dump into a
        QTextEdit on the GUI thread was a real freeze/memory risk with no
        way for the user to back out quickly. The aggregate counts in the
        dialog's summary label above already cover the true totals, so
        the itemized list only needs to show enough to actually verify
        the plan, not literally every group.
        """
        lines: list[str] = []
        for action in selected[: self._PREVIEW_MAX_GROUPS]:
            lines.append(f"{action.canonical_artist} — {action.canonical_name}")
            # O(1) lookup per track instead of a linear scan of
            # group_tracks per removed_id -- group_tracks can legitimately
            # be large for a library with many copies of the same song, so
            # the previous next(...) inside this loop was quadratic per
            # group for no reason; the data doesn't change mid-loop.
            tracks_by_id = {t.track_id: t for t in action.group_tracks}
            for track in action.group_tracks:
                if track.track_id == action.canonical_id:
                    lines.append(f"    KEEP    #{track.track_id}  ({track.album or 'Unknown album'})")
            for removed_id in action.removed_ids:
                removed_track = tracks_by_id.get(removed_id)
                album = removed_track.album if removed_track and removed_track.album else "Unknown album"
                lines.append(f"    REMOVE  #{removed_id}  ({album})")
            if action.playlists_updated:
                lines.append("    Playlists updated: " + ", ".join(action.playlists_updated))
            else:
                lines.append("    Playlists updated: none")
            if action.smart_playlist_warnings:
                lines.append(
                    "    ⚠ May affect smart playlist(s): "
                    + ", ".join(action.smart_playlist_warnings)
                )
            lines.append("")

        remaining = len(selected) - self._PREVIEW_MAX_GROUPS
        if remaining > 0:
            lines.append(
                f"…and {remaining} more group(s) not shown here — "
                "see the summary above for exact totals."
            )
        return "\n".join(lines).rstrip()

    def _removed_track_file_paths(self, selected) -> list[Path]:
        """Resolves the on-disk audio file path for every track that
        `selected` (a list of MergeAction) is about to remove, via each
        action's group_tracks (the full pre-merge Track objects, still
        intact at call time -- see _on_apply_clicked). Tracks whose
        Location isn't a resolvable local file:// path (streamed, cloud,
        already missing) are skipped, same as artwork lookup does
        elsewhere -- this list is only ever used to offer deletion, never
        assumed complete."""
        from ..core.artwork import file_uri_to_path

        paths: list[Path] = []
        for action in selected:
            removed_id_set = set(action.removed_ids)
            for track in action.group_tracks:
                if track.track_id not in removed_id_set:
                    continue
                location = track.raw.get("Location")
                if not location:
                    continue
                resolved = file_uri_to_path(location)
                if resolved is not None:
                    paths.append(resolved)
        return paths

    def _on_apply_clicked(self) -> None:
        if not self.library or not self.plan:
            return
        selected = self._selected_actions()
        if not selected:
            show_info(self, "Nothing selected", "Select at least one duplicate group to clean up.")
            return

        crash_reporter.record_action(f"Cleaning up {len(selected)} duplicate group(s)")
        if not self._confirm_duplicate_removal_preview(selected):
            return

        write_back = self.write_back_cb.isChecked() and self.library.source_path is not None
        if write_back:
            output_path = self.library.source_path
            confirm_overwrite = QMessageBox.question(
                self,
                "Replace your original file?",
                f"This will replace:\n{output_path}\n\n"
                "A backup is still saved automatically first. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm_overwrite != QMessageBox.StandardButton.Yes:
                return
        else:
            save_path_str, _ = QFileDialog.getSaveFileName(
                self, "Save cleaned library as", "Library_Deduplicated.xml",
                "iTunes Library (*.xml)"
            )
            if not save_path_str:
                return
            output_path = Path(save_path_str)

        self._write_back_mode = write_back
        scoped_plan = ConsolidationPlan(actions=selected)
        # Captured now (before ApplyPlanWorker/apply_plan mutates
        # self.library.tracks) so "Remove duplicate files from disk..."
        # can offer to delete the on-disk audio files for exactly the
        # tracks this run is about to remove from the library, once the
        # user has rebuilt/reopened iTunes and confirmed they're happy
        # with the result. Only local file:// Locations resolve to a
        # path (see core/artwork.file_uri_to_path) -- streamed/cloud/
        # remote tracks are silently skipped here, same as artwork
        # lookup already does elsewhere in this app.
        self._last_removed_track_paths = self._removed_track_file_paths(selected)
        self._set_busy(True, "Cleaning up duplicates…")
        self._apply_worker = ApplyPlanWorker(self.library, scoped_plan, output_path, self.cache)
        self._apply_worker.progress.connect(self.statusBar().showMessage)
        self._apply_worker.progress_pct.connect(self.progress.setValue)
        self._apply_worker.phase.connect(self._on_phase_changed)
        self._apply_worker.finished_ok.connect(self._on_apply_done)
        self._apply_worker.failed.connect(self._on_apply_failed)
        self._apply_worker.start()

    def _on_apply_done(self, library: Library, output_path: str, audit_record,
                        pre_snapshot_id: int | None, com_sync_result=None) -> None:
        self._set_busy(False)
        self._last_audit_record = audit_record
        self._last_pre_consolidation_snapshot_id = pre_snapshot_id
        self._last_output_path = Path(output_path)
        if self._write_back_mode:
            target_desc = "your original library file"
        else:
            target_desc = (
                "a new file (not your original — iTunes/Apple Music will still "
                "show the duplicates until this new file replaces it, see below)"
            )

        # If the running iTunes was updated live via COM, the reopen/
        # re-import steps are no longer necessary for that already-open
        # instance -- so lead with that instead of steps the user doesn't
        # need to follow. Any other case (iTunes wasn't running, wasn't
        # responsive, isn't on this platform, or the sync hit errors)
        # falls back to showing the existing reopen instructions exactly
        # as before -- this branch is purely additive.
        needs_reopen_steps = True
        if com_sync_result is not None and com_sync_result.succeeded_fully:
            needs_reopen_steps = False
            sync_section = (
                "Your open iTunes was already updated for you -- "
                f"{com_sync_result.summary_text()} No need to quit or reopen "
                "anything.\n\n"
                "(A copy of the change was also saved to the file below, in "
                "case you want it as a backup or for another computer.)"
            )
        elif com_sync_result is not None and com_sync_result.attempted and com_sync_result.itunes_available:
            # iTunes was running and reachable, but some tracks couldn't be
            # removed live -- still worth telling the user what happened,
            # but the exported file is the authoritative fallback either way.
            reopen_steps = (
                REOPEN_STEPS_AUTOMATED if is_windows() else REOPEN_INSTRUCTIONS
            )
            sync_section = (
                f"{com_sync_result.summary_text()}\n\n"
                "To see the change in iTunes/Apple Music:\n\n"
                f"{reopen_steps}"
            )
        else:
            reopen_steps = (
                REOPEN_STEPS_AUTOMATED if is_windows() else REOPEN_INSTRUCTIONS
            )
            sync_section = (
                "To see the change in iTunes/Apple Music:\n\n"
                f"{reopen_steps}"
            )

        box = QMessageBox(self)
        _apply_severity_style(box, SEVERITY_INFO)
        box.setWindowTitle("✅ Duplicates cleaned up")
        box.setText(
            f"Saved your cleaned-up library to {target_desc}:\n{output_path}\n\n"
            f"{sync_section}"
        )
        save_audit_btn = box.addButton("\U0001F4C4 Save summary\u2026", QMessageBox.ButtonRole.ActionRole)
        rebuild_now_btn = None
        if needs_reopen_steps and is_windows():
            # Classic Windows iTunes keeps its real working database in a
            # binary "iTunes Library.itl" file, not the XML -- editing or
            # replacing Library.xml alone does nothing on its own. "Rebuild
            # now" handles this for you: it quits iTunes, backs up the
            # existing library files, swaps the cleaned XML in, and
            # relaunches iTunes (see core/rebuild_script.
            # rebuild_library_in_app) -- the "Choose Library..." click
            # afterward is the one step that can't be automated, since
            # classic iTunes has no COM-scriptable way to import a
            # Library.xml into a running app directly (see
            # core/itunes_com_sync.py's module docstring).
            # (The separate .bat-generating button previously offered here
            # was removed since this button already runs that same swap
            # in-app, with nothing left to hand-run.)
            rebuild_now_btn = box.addButton(
                "\U0001F504 Rebuild library now\u2026", QMessageBox.ButtonRole.ActionRole
            )
        undo_btn = None
        if pre_snapshot_id is not None:
            undo_btn = box.addButton("\u21A9\uFE0F Undo this change\u2026", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_audit_btn:
            self._on_save_audit_report()
        elif rebuild_now_btn is not None and clicked is rebuild_now_btn:
            self._on_rebuild_library_in_app()
        elif undo_btn is not None and clicked is undo_btn:
            self._restore_snapshot_by_id(pre_snapshot_id)
            return
        # Refresh view against the now-modified in-memory library (no more duplicates
        # among the merged groups).
        from ..core.duplicate_detector import find_all_candidate_groups
        groups = find_all_candidate_groups(library)
        self._groups = groups
        self._apply_permanent_exclusions(self._groups)
        self.plan = build_plan(library, groups)
        self._expanded_row = None
        self._stop_detail_panel_previews()
        self.detail_scroll_area.setVisible(False)
        self._populate_table(self.plan)
        self._refresh_health()

    def _refresh_itunes_folder_strip(self) -> None:
        """Updates the persistent iTunes-folder status strip (see
        ItunesFolderStrip) from the currently-remembered setting. Called
        on startup and after every place _prompt_for_itunes_dir can change
        that setting, so the strip never goes stale or requires reopening
        the folder-picker just to check what's set."""
        remembered = self.cache.get_setting("itunes_library_dir")
        if remembered:
            self.itunes_folder_strip_label.setText(f"iTunes folder: {remembered}")
            self.itunes_folder_strip_label.setToolTip(remembered)
        elif is_windows():
            self.itunes_folder_strip_label.setText(
                "iTunes folder: not set yet — used when you rebuild your library after cleanup"
            )
            self.itunes_folder_strip_label.setToolTip("")
        else:
            self.itunes_folder_strip_label.setText(
                "iTunes folder: not applicable on this platform"
            )
            self.itunes_folder_strip_label.setToolTip("")

    def _prompt_for_itunes_dir(self) -> Path | None:
        """Asks the user to confirm/choose the folder containing their real
        iTunes Library.itl -- can't be assumed to be the default Windows
        Music\\iTunes path, since the library may live on an external
        drive or a redirected folder. Remembers the last-confirmed choice
        (via CacheDB) and pre-fills it next time; falls back to the
        standard default location only the first time it's ever asked.
        Returns None if the user cancels."""
        remembered = self.cache.get_setting("itunes_library_dir")
        start_dir = Path(remembered) if remembered else default_itunes_dir()
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select your iTunes folder (containing iTunes Library.itl)",
            str(start_dir),
        )
        if not chosen:
            return None
        chosen_path = Path(chosen)
        self.cache.set_setting("itunes_library_dir", str(chosen_path))
        self._refresh_itunes_folder_strip()
        return chosen_path

    def _on_rebuild_library_in_app(self) -> None:
        """Runs the in-app rebuild directly (see core/rebuild_script.
        rebuild_library_in_app): quits iTunes, backs up the existing
        iTunes Library.itl/.xml, copies the cleaned XML into the iTunes
        folder, and relaunches iTunes. Confirms first since -- unlike
        every other action in this app -- this quits another running
        program and writes into a folder outside anything the user chose
        as an output location."""
        output_path = getattr(self, "_last_output_path", None)
        if output_path is None:
            show_info(
                self, "Nothing to rebuild yet",
                "Clean up duplicates first — this needs the file that step produces."
            )
            return

        itunes_dir = self._prompt_for_itunes_dir()
        if itunes_dir is None:
            return

        crash_reporter.record_action(f"Rebuilding library in {itunes_dir}")

        # Pre-flight check (disk space, write permission, iTunes-running
        # status) runs before *anything* in the rebuild sequence starts --
        # including before the confirmation prompt below -- so a blocking
        # problem (e.g. no free space) is caught while it's still safe to
        # simply not proceed, instead of surfacing midway through after
        # iTunes has already been quit and the existing library files
        # backed up. See core/rebuild_script.preflight_check_rebuild.
        preflight = preflight_check_rebuild(output_path, itunes_dir)
        if not preflight.ok:
            show_critical(
                self, "Can't rebuild right now",
                "Before starting, this check found a problem:\n\n"
                + "\n\n".join(preflight.problems),
            )
            return

        confirm_text = (
            "This will:\n\n"
            "  1. Close iTunes if it's open\n"
            "  2. Back up your current library files (kept, never deleted)\n"
            "  3. Copy in the cleaned-up version\n"
            "  4. Reopen iTunes\n\n"
            "iTunes will then ask you to choose a library — click "
            "\"Choose Library...\" and select the folder below yourself; "
            "that one step can't be automated (classic iTunes has no way "
            "to script a Library.xml import into a running app).\n\n"
            f"iTunes folder:\n{itunes_dir}"
        )
        if preflight.warnings:
            confirm_text += "\n\n" + "\n".join(f"\u2022 {w}" for w in preflight.warnings)
        confirm_text += "\n\nContinue?"

        confirm = QMessageBox.question(
            self, "Rebuild iTunes library now?",
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Runs off the UI thread (see core/workers.RebuildLibraryWorker)
        # and reports which step of the quit/backup/copy/relaunch
        # sequence is currently running via the same progress/phase
        # widgets used elsewhere, instead of blocking the window with no
        # indication of what's happening or how far along it is.
        self._set_busy(True, "Rebuilding iTunes library…")
        self.progress.setRange(0, len(REBUILD_STEPS))
        self._rebuild_worker = RebuildLibraryWorker(output_path, itunes_dir)
        self._rebuild_worker.step.connect(self._on_rebuild_step)
        self._rebuild_worker.finished_ok.connect(self._on_rebuild_finished)
        self._rebuild_worker.start()

    def _on_rebuild_step(self, step_name: str, step_index: int, total_steps: int) -> None:
        self.phase_label.setText(step_name)
        self.progress.setValue(step_index)
        self.progress.setFormat(f"Step {step_index}/{total_steps}: {step_name}")
        self.statusBar().showMessage(f"Rebuilding iTunes library… ({step_name})")

    def _on_rebuild_finished(self, result: RebuildResult) -> None:
        # Restores the progress bar's normal 0-100 percentage mode (see
        # _on_rebuild_library_in_app, which switches it to a 0-len(steps)
        # range for the step tracker above) before _set_busy hides it, so
        # the next load/apply run starts from its usual state.
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self._set_busy(False)

        if not result.ok:
            error_log.log_error(f"Couldn't rebuild library: {result.message}")
            show_critical(self, "Couldn't rebuild library", with_recovery_guidance(result.message))
            return

        text = result.message
        if result.warnings:
            text += "\n\n" + "\n".join(f"\u2022 {w}" for w in result.warnings)
        # (backup path, tooltip explaining that specific file) pairs --
        # kept separate rather than folded into `text` above so each one
        # can carry its own hover tooltip explaining the ".bak_<timestamp>"
        # naming (see the QListWidget below): people who've never seen
        # these files before have no way to know they're safe-to-ignore
        # backups rather than something the app left behind by mistake.
        backups: list[tuple[str, str]] = []
        if result.itl_backup_path is not None:
            backups.append((
                str(result.itl_backup_path),
                _bak_timestamp_tooltip(result.itl_backup_path.name),
            ))
        if result.xml_backup_path is not None:
            backups.append((
                str(result.xml_backup_path),
                _bak_timestamp_tooltip(result.xml_backup_path.name),
            ))
        for original, backup in result.extra_xml_backups.items():
            backups.append((
                f"{backup} (was: {original.name})",
                _bak_timestamp_tooltip(backup.name),
            ))

        box = QDialog(self)
        # _apply_severity_style (widgets.py) targets QMessageBox
        # specifically (it calls setIcon(), which QDialog doesn't have,
        # and its stylesheet selector is "QMessageBox {...}") -- this
        # needed a real QDialog instead of a QMessageBox so a QListWidget
        # (for the per-backup tooltips below) could be added to it, so the
        # same blue "info" accent strip is applied directly here rather
        # than reusing that QMessageBox-only helper.
        info_accent = _SEVERITY_ACCENTS[SEVERITY_INFO][0]
        box.setStyleSheet(f"QDialog {{ border-top: 4px solid {info_accent}; }}")
        box.setWindowTitle("✅ Library rebuilt")
        box_layout = QVBoxLayout(box)
        message_label = QLabel(text)
        message_label.setWordWrap(True)
        box_layout.addWidget(message_label)

        # Small annotated mockup of iTunes' own "Choose Library..." prompt,
        # so there's something to visually look for on relaunch rather than
        # only a paragraph of instructions that's easy to skim past while
        # iTunes' window is stealing focus at the same moment. Shown every
        # time this dialog appears -- the manual click it depicts is
        # required after every in-app rebuild, automated relaunch or not
        # (see the "not relaunched" text appended to `text` above for that
        # case, which this same visual still applies to).
        box_layout.addWidget(ChooseLibraryCalloutLabel(box))

        if backups:
            backups_heading = QLabel("Backups kept:")
            backups_heading.setObjectName("sectionHeading")
            box_layout.addWidget(backups_heading)
            backups_list = QListWidget()
            # Roughly enough rows to show without scrolling for the usual
            # 2-3 backups this produces, while still capping how much of
            # the dialog a long extra_xml_backups list can take over.
            backups_list.setMaximumHeight(120)
            for path_text, tooltip in backups:
                item = QListWidgetItem(path_text)
                item.setToolTip(tooltip)
                backups_list.addItem(item)
            box_layout.addWidget(backups_list)

        buttons = QDialogButtonBox()
        # Only offered once there's actually something to delete -- see
        # _removed_track_file_paths, populated by the "Clean up
        # duplicates" run that produced the file this rebuild just used.
        # Deliberately offered here (after the rebuild, not right after
        # cleanup) since only now has iTunes reopened with the deduped
        # library -- deleting the underlying audio files any earlier
        # would be irreversible before the user has had any chance to
        # confirm the rebuild itself actually went well.
        # QDialog (unlike QMessageBox) has no clickedButton() to tell which
        # button closed it afterward, so the "delete files" choice is
        # tracked explicitly here instead -- set immediately on click, read
        # once exec() returns below.
        delete_files_clicked = False

        def _mark_delete_files_clicked() -> None:
            nonlocal delete_files_clicked
            delete_files_clicked = True
            box.accept()

        delete_files_btn = None
        if getattr(self, "_last_removed_track_paths", None):
            delete_files_btn = buttons.addButton(
                "\U0001F5D1\uFE0F Remove duplicate files from disk\u2026",
                QDialogButtonBox.ButtonRole.DestructiveRole,
            )
            delete_files_btn.clicked.connect(_mark_delete_files_clicked)
        ok_btn = buttons.addButton(QDialogButtonBox.StandardButton.Ok)
        ok_btn.clicked.connect(box.accept)
        box_layout.addWidget(buttons)
        box.exec()
        if delete_files_clicked:
            self._on_remove_duplicate_files_from_disk()

    def _on_remove_duplicate_files_from_disk(self) -> None:
        """Deletes the on-disk audio files for the tracks the most recent
        "Clean up duplicates" run removed from the library (see
        _removed_track_file_paths) -- offered only once a rebuild has
        completed, so iTunes has already been pointed at the deduped
        library before anything irreversible happens on disk. Every
        attempted delete is tried independently (one missing/locked file
        never blocks the rest), and the user sees an exact count of what
        succeeded/failed before anything is removed, via the confirm
        dialog below."""
        paths = getattr(self, "_last_removed_track_paths", None) or []
        if not paths:
            show_info(
                self, "Nothing to remove",
                "No duplicate file paths were captured for the most recent "
                "cleanup run."
            )
            return

        # De-duplicate while preserving order -- the same on-disk file can
        # legitimately appear twice if two different duplicate groups both
        # happened to point at it (e.g. a manually-restored copy).
        seen: set[str] = set()
        unique_paths: list[Path] = []
        for p in paths:
            key = str(p)
            if key not in seen:
                seen.add(key)
                unique_paths.append(p)

        preview = "\n".join(str(p) for p in unique_paths[:20])
        if len(unique_paths) > 20:
            preview += f"\n\u2026and {len(unique_paths) - 20} more"

        confirm = QMessageBox.question(
            self, "Remove duplicate files from disk?",
            f"This will permanently delete {len(unique_paths)} audio "
            "file(s) from disk -- the copies already removed from your "
            "library, not the copy you kept. This cannot be undone by "
            "this app (there is no file-level backup of these).\n\n"
            f"{preview}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        deleted: list[Path] = []
        missing: list[Path] = []
        failed: list[tuple[Path, str]] = []
        for path in unique_paths:
            try:
                if not path.exists():
                    missing.append(path)
                    continue
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                failed.append((path, str(exc)))

        # Cleared either way once acted on -- offering to delete the same
        # files again from a stale list (e.g. after the user reruns
        # cleanup on a different selection) would be confusing and, for
        # the ones already gone, a no-op that only clutters the summary.
        self._last_removed_track_paths = []

        lines = [f"Deleted {len(deleted)} file(s)."]
        if missing:
            lines.append(f"{len(missing)} file(s) were already gone (skipped).")
        if failed:
            lines.append(f"{len(failed)} file(s) could not be deleted:")
            lines.extend(f"  \u2022 {p}: {err}" for p, err in failed[:10])
            if len(failed) > 10:
                lines.append(f"  \u2026and {len(failed) - 10} more")

        if failed:
            show_warning(self, "Some files could not be removed", "\n".join(lines))
        else:
            show_info(self, "✅ Files removed", "\n".join(lines))

    def _on_undo_last_rebuild(self) -> None:
        """One-click "undo last rebuild": restores the most recent iTunes
        Library.itl/.xml backup pair that "Rebuild library now..." made
        automatically (see core/rebuild_script.find_latest_rebuild_backup_
        pair / undo_last_rebuild), instead of the user having to find and
        rename those timestamped .bak_<stamp> files themselves. Always
        available from the toolbar (not gated on this session having run
        a rebuild) since the backup files themselves are what's being
        looked for on disk, not anything this app needs to remember."""
        remembered = self.cache.get_setting("itunes_library_dir")
        itunes_dir = Path(remembered) if remembered else default_itunes_dir()

        itl_backup, xml_backup, stamp = find_latest_rebuild_backup_pair(itunes_dir)
        if itl_backup is None and xml_backup is None:
            show_info(
                self, "No rebuild backup found",
                "No rebuild backup was found in:\n"
                f"{itunes_dir}\n\n"
                "\"Undo last rebuild\" only works after \"Rebuild library "
                "now...\" has run at least once in this folder."
            )
            return

        confirm = QMessageBox.question(
            self, "Undo last rebuild?",
            "This will:\n\n"
            "  1. Close iTunes if it's open\n"
            f"  2. Restore the backup made {stamp}\n"
            "  3. Reopen iTunes with the restored library\n\n"
            f"iTunes folder:\n{itunes_dir}\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, "Undoing last rebuild…")
        self.progress.setRange(0, len(REBUILD_STEPS))
        self._undo_rebuild_worker = UndoRebuildWorker(itunes_dir)
        self._undo_rebuild_worker.step.connect(self._on_rebuild_step)
        self._undo_rebuild_worker.finished_ok.connect(self._on_undo_rebuild_finished)
        self._undo_rebuild_worker.start()

    def _on_undo_rebuild_finished(self, result: UndoResult) -> None:
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self._set_busy(False)

        if not result.ok:
            error_log.log_error(f"Couldn't undo last rebuild: {result.message}")
            show_critical(self, "Couldn't undo last rebuild", with_recovery_guidance(result.message))
            return
        show_info(self, "✅ Rebuild undone", result.message)

    def _on_save_audit_report(self) -> None:
        """Exports the exact field-level changes from the most recent
        consolidation run (before/after values per canonical track,
        per-field backfills, and playlists repointed) as JSON."""
        record = getattr(self, "_last_audit_record", None)
        if record is None:
            show_info(
                self, "Nothing to save yet",
                "Clean up duplicates first — this covers the most recent run."
            )
            return
        save_path_str, _ = QFileDialog.getSaveFileName(
            self, "Save summary as", "cleanup_summary.json", "JSON (*.json)"
        )
        if not save_path_str:
            return
        try:
            record.save(Path(save_path_str))
        except OSError as exc:
            error_log.log_error("Couldn't save summary", exc)
            show_critical(
                self, "Couldn't save summary",
                with_recovery_guidance(f"Failed to save summary: {exc}"),
            )
            return
        show_info(self, "✅ Summary saved", f"Saved to:\n{save_path_str}")

    def _on_apply_failed(self, message: str) -> None:
        self._set_busy(False)
        error_log.log_error(f"Cleanup failed: {message}")
        show_critical(self, "Cleanup failed", with_recovery_guidance(message))

    def _on_import_spotify_library(self) -> None:
        """Reads a Spotify data-export bundle (see core/providers/
        spotify_export.py) and reports how many of its tracks already
        appear to be in the currently loaded library, using the same
        normalized artist+title comparison
        core/duplicate_detector.normalize already uses for in-library
        duplicates elsewhere in this app, so "already have this" means
        the same thing here as everywhere else.

        Purely read-only/informational: nothing about the loaded
        library, Library.xml, or the Spotify export itself is ever
        written to by this action. Works with no library loaded too --
        the export is still read and its own track/playlist counts
        shown -- just without a match count to report.
        """
        source_str, _ = QFileDialog.getOpenFileName(
            self, "Select your Spotify data export (.zip)", "",
            "Spotify export (*.zip);;All files (*)",
        )
        if not source_str:
            source_str = QFileDialog.getExistingDirectory(
                self, "Or select the folder you extracted your Spotify export into"
            )
        if not source_str:
            return

        from ..core.providers import get_provider
        from ..core.providers.base import ProviderError

        provider = get_provider("spotify_export")
        if provider is None:
            show_critical(
                self, "Spotify import unavailable",
                "The Spotify import provider isn't available in this build.",
            )
            return

        try:
            tracks = list(provider.import_tracks(source_str))
        except ProviderError as exc:
            error_log.log_error("Spotify import failed", exc)
            show_critical(
                self, "Couldn't read Spotify export", with_recovery_guidance(str(exc))
            )
            return

        try:
            playlists = list(provider.import_playlists(source_str))
        except ProviderError as exc:
            error_log.log_error("Spotify playlist import failed", exc)
            playlists = []

        if self.library is not None:
            existing_keys = {
                (normalize(t.artist), normalize(t.name))
                for t in self.library.tracks.values()
            }
            matched = sum(
                1 for t in tracks
                if (normalize(t.artist), normalize(t.name)) in existing_keys
            )
            library_note = (
                f"{matched} of those already appear to be in your currently "
                "loaded library."
            )
        else:
            library_note = "Open a Library.xml file to compare these against your library."

        show_info(
            self, "\u2705 Spotify export read",
            f"Found {len(tracks)} track(s) and {len(playlists)} playlist(s) "
            f"in that Spotify export. {library_note}",
        )

    def _on_merge_tracks_clicked(self) -> None:
        """Toolbar "\U0001F517 Merge tracks...": lets the user pick any two
        tracks in the currently loaded library and merge them, covering
        the gap manual review's existing "Keep this one instead" doesn't
        -- that control only re-picks the canonical track *within* a
        group exact/fuzzy detection already found. This is for the case
        detection found nothing at all: two copies of the same song
        tagged differently enough (different artist spelling, a
        translated title, etc.) that even the fuzzy pass's similarity
        score never crossed FUZZY_LOW_CONFIDENCE.

        Opens MergeTracksDialog to pick both tracks, then builds a
        synthetic DuplicateGroup via
        core/duplicate_detector.make_manual_merge_group and adds it to
        self._groups -- the exact same list _rebuild_plan_from_groups
        already re-derives self.plan from after every other manual
        review edit, so the merged pair shows up in the table (tagged
        "Manually merged") and behaves like any other group from there:
        it can be unchecked, expanded, re-picked, or marked not-
        duplicate again like anything else.
        """
        if not self.library:
            return
        dialog = MergeTracksDialog(self.library, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.selected_tracks()
        if len(picked) < 2:
            return
        already_grouped = {t.track_id for g in self._groups for t in g.tracks}
        if any(t.track_id in already_grouped for t in picked):
            confirm = QMessageBox.question(
                self,
                "Track already in a group",
                "One or both of these tracks are already part of another "
                "duplicate group. Merging them here will add a second, "
                "separate group for this pair — it won't remove them from "
                "the other group. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        try:
            group = make_manual_merge_group(picked)
        except ValueError as exc:
            show_warning(self, "Couldn't merge those tracks", str(exc))
            return
        self._groups.append(group)
        self._rebuild_plan_from_groups()
        self._toast(
            f"Merged '{picked[0].name or 'track'}' and "
            f"'{picked[1].name or 'track'}'. Review it in the table below.",
            TOAST_SUCCESS,
        )

    # Prefix used to mark a snapshot's `label` as one the user typed
    # themselves (see _on_save_named_restore_point), as opposed to the
    # fixed labels the app writes for its own automatic snapshots
    # ("auto-backup on load", "pre-consolidation backup" -- see
    # core/workers.py). Nothing about the underlying save_snapshot/
    # list_snapshots/load_snapshot/restore path changes for a named
    # point -- it's the exact same snapshot mechanism and the exact same
    # restore dialog below, just distinguished for display by this
    # prefix so a user-labeled point ("before spring cleaning") is easy
    # to pick out from the automatic ones at a glance.
    _NAMED_RESTORE_POINT_PREFIX = "user: "

    def _on_save_named_restore_point(self) -> None:
        """Saves a labeled backup of the current library on demand (see
        toolbar's "Save restore point..."), independent of the automatic
        per-load/per-apply snapshots -- so a point worth returning to on
        purpose ("before spring cleaning") can be found later by name
        instead of by guessing which automatic backup's timestamp is the
        right one."""
        if not self.library:
            return
        note, ok = QInputDialog.getText(
            self, "\U0001F4CC Save restore point",
            "Give this restore point a short name, so you can find it "
            "again later (e.g. \"before spring cleaning\"):",
        )
        if not ok:
            return
        note = note.strip()
        if not note:
            show_info(
                self, "Name needed",
                "Enter a short name for this restore point so it's easy "
                "to find again later.",
            )
            return
        source = str(self.library.source_path) if self.library.source_path else "(unsaved)"
        try:
            self.cache.save_snapshot(
                self.library.raw, source, label=f"{self._NAMED_RESTORE_POINT_PREFIX}{note}"
            )
        except Exception as exc:
            error_log.log_error("Couldn't save named restore point", exc)
            show_critical(
                self, "Couldn't save restore point",
                with_recovery_guidance(f"Failed to save this restore point: {exc}"),
            )
            return
        crash_reporter.record_action(f"Saved named restore point: {note}")
        self._toast(f"\U0001F4CC Restore point saved: \u201C{note}\u201D")

    def _on_restore_clicked(self) -> None:
        """Opens a browsable list of every saved backup snapshot --
        automatic (auto-backup-on-load, pre-consolidation backups) and
        user-named restore points (see _on_save_named_restore_point)
        alike -- so the user can pick exactly which point in time to
        restore, rather than always restoring only the most recent one."""
        snapshots = self.cache.list_snapshots()
        if not snapshots:
            show_info(self, "No backups yet", "No backups have been saved yet.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("⏪ Restore backup")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)

        intro = QLabel(
            "A backup is saved automatically every time you open a library "
            "or clean up duplicates, and you can save your own named "
            "restore point any time (\U0001F4CC \"Save restore point...\"). "
            "Pick one below to restore — you'll be asked where to save "
            "it, so nothing is overwritten automatically."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        list_widget = QListWidget()
        for snap in snapshots:
            when = datetime.datetime.fromtimestamp(snap["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            source_name = Path(snap["source_path"]).name if snap["source_path"] else "(unknown source)"
            raw_label = snap["label"] or "backup"
            if raw_label.startswith(self._NAMED_RESTORE_POINT_PREFIX):
                display_label = "\U0001F4CC " + raw_label[len(self._NAMED_RESTORE_POINT_PREFIX):]
            else:
                display_label = raw_label
            item = QListWidgetItem(f"{when}  \u2014  {display_label}  \u2014  {source_name}")
            item.setData(Qt.ItemDataRole.UserRole, snap["id"])
            list_widget.addItem(item)
        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        restore_btn = buttons.addButton("⏪ Restore selected\u2026", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        restore_btn.clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current_item = list_widget.currentItem()
        if current_item is None:
            return
        snapshot_id = current_item.data(Qt.ItemDataRole.UserRole)
        self._restore_snapshot_by_id(snapshot_id)

    def _restore_snapshot_by_id(self, snapshot_id: int) -> None:
        crash_reporter.record_action(f"Restoring backup snapshot #{snapshot_id}")
        confirm = QMessageBox.question(
            self, "Restore backup",
            "This saves the backup as a new file — your currently open "
            "library isn't touched. You'll be asked where to save it. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        save_path_str, _ = QFileDialog.getSaveFileName(
            self, "Save restored library as", "Library_Restored.xml", "iTunes Library (*.xml)"
        )
        if not save_path_str:
            return
        try:
            raw = self.cache.load_snapshot(snapshot_id)
        except KeyError as exc:
            error_log.log_error("Couldn't restore backup", exc)
            show_critical(
                self, "Couldn't restore backup",
                with_recovery_guidance(f"Backup snapshot no longer available: {exc}"),
            )
            return
        except SnapshotIntegrityError as exc:
            # Deliberately a separate branch from the KeyError one above:
            # this backup *does* exist but failed its checksum/parse
            # check (see CacheDB.load_snapshot), so the message says so
            # plainly instead of implying it simply isn't there -- and,
            # same as the KeyError case, nothing has been written to disk
            # at this point, so failing here can't leave a half-restored
            # file behind.
            error_log.log_error("Backup snapshot failed integrity check", exc)
            show_critical(
                self, "Backup snapshot corrupted",
                with_recovery_guidance(
                    f"{exc} If you have other backups listed, try restoring "
                    "a different one instead."
                ),
            )
            return
        library = Library(raw=raw, tracks={}, playlists=[])
        # Rehydrate via the same Tracks-dict-of-dicts conversion Library.load
        # uses, but from an in-memory snapshot dict rather than a file --
        # Library.tracks_from_raw() is the single shared implementation of
        # that conversion so this path and Library.load() can't drift apart.
        from ..core.itunes_xml import Playlist
        library.tracks = Library.tracks_from_raw(raw.get("Tracks"))
        library.playlists = [Playlist(raw=p) for p in (raw.get("Playlists") or [])]
        try:
            library.save(Path(save_path_str))
        except OSError as exc:
            error_log.log_error("Couldn't restore backup", exc)
            show_critical(
                self, "Couldn't restore backup",
                with_recovery_guidance(f"Failed to write restored library: {exc}"),
            )
            return
        show_info(self, "✅ Restored", f"Backup restored to:\n{save_path_str}")

    # -------------------------------------------------------- persisted UI state

    # Bump if the shape of what's saved under these keys ever changes
    # incompatibly, so an old value from a previous app version is never
    # mistaken for the new shape (get_setting()'s default already protects
    # against missing/corrupt values -- this protects against a
    # structurally different but validly-parsed old value).
    _UI_STATE_VERSION = 1

    def _restore_ui_state(self) -> None:
        """Restores window size/position, the last-used duplicates filter
        (search text + confidence tier), and the duplicates table's
        column order/widths from the previous session. Every read falls
        back silently to the current default (whatever _build_ui() already
        set up) if nothing was saved yet, the saved state is from an
        incompatible version, or a saved value no longer matches anything
        selectable -- a missing/corrupt saved setting must never prevent
        the window from opening."""
        self._restoring_ui_state = True
        try:
            state = self.cache.get_setting("ui_state", default=None)
            if not isinstance(state, dict) or state.get("version") != self._UI_STATE_VERSION:
                return

            geometry_hex = state.get("window_geometry")
            if isinstance(geometry_hex, str):
                try:
                    self.restoreGeometry(bytes.fromhex(geometry_hex))
                except (ValueError, TypeError):
                    pass  # corrupt hex; keep the default geometry already set

            filter_text = state.get("filter_text")
            if isinstance(filter_text, str):
                self.filter_edit.setText(filter_text)

            tier_value = state.get("filter_tier")
            # tier_value of None legitimately means "All confidence levels"
            # (index 0) -- only skip restoring on a genuinely missing key,
            # which get()'s default (also None) is indistinguishable from,
            # so we only attempt the lookup when the key was present at all.
            if "filter_tier" in state:
                idx = self.filter_tier_combo.findData(tier_value)
                if idx >= 0:
                    self.filter_tier_combo.setCurrentIndex(idx)

            # Column order/widths (see DuplicatesTable.restore_column_state):
            # an added, purely additive key -- a saved state written by an
            # older app version simply won't have it, in which case the
            # table just keeps its already-configured default layout, same
            # as any other never-restored-yet default in this method.
            column_state_hex = state.get("duplicates_table_columns")
            if isinstance(column_state_hex, str):
                self.table.restore_column_state(column_state_hex)
        finally:
            self._restoring_ui_state = False

    def _save_ui_state(self) -> None:
        """Persists window geometry, the current duplicates filter, and
        the duplicates table's column order/widths so the next session
        reopens the same way. Best-effort: any failure writing to the
        cache DB (e.g. disk full, permissions) is swallowed rather than
        blocking app shutdown -- losing a UI preference is never worth
        stopping the user from closing the app."""
        try:
            self.cache.set_setting(
                "ui_state",
                {
                    "version": self._UI_STATE_VERSION,
                    "window_geometry": bytes(self.saveGeometry()).hex(),
                    "filter_text": self.filter_edit.text(),
                    "filter_tier": self.filter_tier_combo.currentData(),
                    "duplicates_table_columns": self.table.save_column_state(),
                },
            )
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # Bug fix: previously this never checked for an in-flight
        # LoadLibraryWorker/ApplyPlanWorker before closing. Closing while
        # ApplyPlanWorker.run() is mid-write risks a torn write to the
        # user's actual library file, and the CacheDB connection was never
        # explicitly closed on shutdown either.
        busy_worker = None
        for worker in (self._load_worker, self._apply_worker):
            if worker is not None and worker.isRunning():
                busy_worker = worker
                break

        if busy_worker is not None:
            confirm = QMessageBox.question(
                self,
                "Still working…",
                "Something is still running. Closing now could leave the "
                "file incomplete.\n\n"
                "Wait for it to finish before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # User chose to close anyway: give the worker a bounded window
            # to finish/unwind cleanly rather than killing it mid-write.
            busy_worker.wait(5000)

        # Bug fix: closing via the titlebar X button was leaving the
        # process running in Task Manager. The cleanup steps below
        # (waiting on the artwork pool, releasing the library lock,
        # closing the cache DB) previously sat directly in closeEvent with
        # no guard -- if any one of them raised, super().closeEvent(event)
        # never ran, so Qt never considered the window actually closed and
        # app.exec() (see main.py) never returned, leaving the whole
        # process alive with no visible window. Wrapping cleanup in
        # try/finally guarantees super().closeEvent(event) always runs --
        # and therefore the window (and, once it's the last one, the
        # process) always actually closes -- regardless of whether cleanup
        # fully succeeded.
        try:
            self._save_ui_state()
            self._stop_detail_panel_previews()
            # Any still-running artwork-load background work (see
            # _start_artwork_load) was previously left unattended on
            # close -- Qt logs "QThread: Destroyed while thread is still
            # running" and can abort the process if one is still
            # executing when its C++ object is torn down with the window.
            # These are read-only, short-lived background reads, so a
            # bounded wait (no confirmation dialog needed, unlike the
            # write-risk case above) is enough to let them finish before
            # shutdown. Now backed by a QThreadPool (see
            # _artwork_thread_pool) -- waitForDone(ms) blocks until every
            # queued/running task in the pool finishes or the timeout
            # elapses, same bounded-wait contract as the old per-loader
            # .wait(2000).
            artwork_pool = getattr(self, "_artwork_pool", None)
            if artwork_pool is not None:
                artwork_pool.waitForDone(2000)
            if self._library_lock is not None:
                self._library_lock.release()
                self._library_lock = None
            self.cache.close()
        finally:
            super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # Accept the drag only if it's carrying exactly one local .xml
        # file -- anything else (multiple files, non-XML, non-local URLs
        # like a browser-dragged link) falls through to Qt's default
        # ignore() so the cursor shows the "not allowed" state instead of
        # silently accepting something _load_library can't handle.
        if self._droppable_library_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # Some platforms/window managers re-check acceptance on every move
        # tick rather than trusting dragEnterEvent's decision; mirror the
        # same check so the drop indicator doesn't flicker between
        # accepted/rejected while dragging over the window.
        if self._droppable_library_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        path = self._droppable_library_path(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        # Bug fix: unlike the Open button (disabled via _set_busy while a
        # load/apply worker is running), drag-and-drop had no equivalent
        # guard -- dropping a file mid-operation would spin up a second
        # LoadLibraryWorker concurrently with whichever worker is already
        # running, racing writes to self.library/self.plan. Reject the
        # drop the same way a disabled Open button would.
        if self._is_worker_busy():
            show_info(
                self,
                "One thing at a time",
                "Please wait for the current task to finish before "
                "opening another library.",
            )
            return
        # Reuses the exact same loading path as File > Open Library.xml...
        # (_on_open_clicked's QFileDialog result feeds into the same
        # _load_library call) -- drag-and-drop is purely an alternative
        # way to supply the path, every downstream load/parse/error-
        # handling behavior is unchanged.
        self._load_library(path)

    def _is_worker_busy(self) -> bool:
        """True if a LoadLibraryWorker or ApplyPlanWorker is currently
        running. Single source of truth shared by dropEvent's guard and
        closeEvent's existing in-flight check, instead of each
        reimplementing the same worker-scan loop."""
        for worker in (getattr(self, "_load_worker", None), getattr(self, "_apply_worker", None)):
            if worker is not None and worker.isRunning():
                return True
        return False

    @staticmethod
    def _droppable_library_path(mime_data) -> Path | None:
        """Returns the local filesystem Path if `mime_data` represents a
        single-file drop with a .xml extension, else None. Kept as one
        shared check used by both dragEnterEvent/dragMoveEvent (to decide
        whether to show the drop as allowed) and dropEvent (to decide
        whether to actually load it), so the two can never disagree about
        what's acceptable."""
        if not mime_data.hasUrls():
            return None
        urls = mime_data.urls()
        if len(urls) != 1:
            return None
        url = urls[0]
        if not url.isLocalFile():
            return None
        path = Path(url.toLocalFile())
        if path.suffix.lower() != ".xml":
            return None
        return path

    # -------------------------------------------------------------- helpers

    def _on_phase_changed(self, phase: str) -> None:
        self.phase_label.setText(phase)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress.setVisible(busy)
        self.phase_label.setVisible(busy)
        if busy:
            self.progress.setValue(0)
            self.phase_label.setText("")
        self.open_btn.setEnabled(not busy)
        self.toolbar_open_action.setEnabled(not busy)
        self.apply_btn.setEnabled(not busy and bool(self.plan and self.plan.actions))
        self.restore_btn.setEnabled(not busy and bool(self.library))
        self.toolbar_restore_action.setEnabled(not busy and bool(self.library))
        self.toolbar_save_restore_point_action.setEnabled(not busy and bool(self.library))
        self.write_back_cb.setEnabled(not busy and bool(self.library and self.library.source_path))
        # Filtering/searching and manual review controls act on data that a
        # background load/apply is actively replacing, so they're disabled
        # for the duration rather than left clickable against stale state.
        self.filter_edit.setEnabled(not busy)
        self.filter_tier_combo.setEnabled(not busy)
        self.select_all_cb.setEnabled(not busy and bool(self.plan and self.plan.actions))
        self.select_all_exact_btn.setEnabled(not busy and bool(self.plan and self.plan.actions))
        self.select_all_high_conf_btn.setEnabled(not busy and bool(self.plan and self.plan.actions))
        self.select_all_everything_btn.setEnabled(not busy and bool(self.plan and self.plan.actions))
        self.exclude_reviewed_out_btn.setEnabled(not busy and bool(self.plan and self.plan.actions))
        if busy:
            self._stop_detail_panel_previews()
            self.detail_scroll_area.setVisible(False)
        if message:
            self.statusBar().showMessage(message)

    def _apply_theme_stylesheet(self, preference: str) -> None:
        """Applies `preference`'s stylesheet to both this window and the
        QApplication instance.

        Bug fix: main.py's startup app.setStyleSheet(current_qss()) call
        (with no preference argument, i.e. always the plain Blue accent
        with no base palette) and this window's own
        setStyleSheet(current_qss(self._theme_preference)) used to be two
        separate, independently-applied stylesheets -- one on the
        QApplication, one on MainWindow. Both are full, broad stylesheets
        that target the same selectors (QMainWindow, QWidget#centralWidget,
        *, etc.) with the same literal hex colors as their starting point,
        so for any of the 8 named base palettes (all of which reuse
        QSS_LIGHT/QSS_DARK's structure -- see ui/theme.BASE_PALETTES) the
        unpaletted app-level stylesheet's rules could still end up applied
        instead of this window's palette-recolored ones, since Qt applies
        both an app-level and a widget-level stylesheet rather than the
        widget-level one fully replacing the app-level one. Paper/Slate/
        Sand/Mint (the four *light*-family palettes) were the ones users
        actually saw fail to apply, because "auto" mode on most dev/user
        machines resolves to the *light* QSS_LIGHT base already, so the
        app-level sheet's plain-light rules blended in almost invisibly
        with a light-family palette's very similar layout -- whereas a
        mismatched family (e.g. a dark palette while the app-level sheet
        is light) would have been obviously broken and caught immediately.
        Setting the identical stylesheet on the QApplication instance too
        (whenever this window's own stylesheet changes -- both at startup
        and on a live preference change from Settings) keeps both in sync
        so no unpaletted rule is left to compete with the chosen palette.
        """
        qss = current_qss(preference)
        self.setStyleSheet(qss)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)

    def _on_theme_preference_changed(self, preference: str) -> None:
        """Called live from SettingsDialog when the user picks a different
        Appearance option, so the change is visible immediately instead of
        requiring an app restart. Restyles both this window and the
        QApplication instance (see _apply_theme_stylesheet) so child
        top-level windows -- e.g. the "What's new" dialog -- also pick up
        the change immediately instead of only on next launch."""
        self._theme_preference = preference
        self._apply_theme_stylesheet(preference)

    def _on_show_settings(self) -> None:
        dialog = SettingsDialog(self.cache, self._on_theme_preference_changed, self)
        dialog.exec()
        # The General tab's iTunes-folder field (see settings_dialog.
        # _build_general_tab) can change the same "itunes_library_dir"
        # setting the status strip reads -- refresh it regardless of how
        # the dialog was closed (OK, Cancel, Esc) since that field, unlike
        # the theme preview, saves as it's edited rather than only on OK.
        self._refresh_itunes_folder_strip()

    def _on_show_changelog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"✨ What's new — v{APP_VERSION}")
        dialog.resize(560, 560)
        layout = QVBoxLayout(dialog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)

        # One collapsible section per version, newest first (CHANGELOG's
        # existing order). Only the newest version starts expanded --
        # older versions are usually just being checked for "did I miss
        # anything", not re-read in full every time this dialog opens.
        sections = []
        for index, entry in enumerate(CHANGELOG):
            section = ChangelogVersionSection(entry, expanded=(index == 0))
            content_layout.addWidget(section)
            sections.append(section)
        content_layout.addStretch(1)

        scroll.setWidget(content)

        # "Jump to version..." dropdown -- same shared helper as
        # Settings > Changelog, so both changelog views navigate
        # identically (see settings_dialog.build_changelog_version_jump).
        jump_combo = build_changelog_version_jump(scroll, sections)
        layout.addWidget(jump_combo)
        layout.addWidget(scroll, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()


def path_name(library: Library) -> str:
    return library.source_path.name if library.source_path else "(unsaved)"


def _playlists_for_track(library: Library | None, track_id: int) -> list[str]:
    if library is None:
        return []
    return [p.name for p in library.playlists if track_id in p.track_ids()]
