"""
Settings dialog: General, Duplicate Detection, Accessibility, Diagnostics,
and Changelog pages, grouped into workflow-stage tabs (Before you scan /
During cleanup / Reference -- see SettingsDialog's docstring) rather than
a single flat alphabetical tab list.

Everything here is additive on top of existing, already-working
machinery -- no existing behavior is changed by simply opening this
dialog:
  - General's theme choice writes to the same CacheDB.get_setting/
    set_setting key/value store already used for window geometry and
    filter state (data/cache_db.py), and is read by main.py/MainWindow
    at startup the same way the OS-follow theme always was.
  - Duplicate Detection's thresholds are read by workers.py (LoadLibrary-
    Worker) at the start of each scan via load_fuzzy_thresholds() below,
    the same CacheDB the rest of this dialog already uses. Nothing
    reaches into core/duplicate_detector.py's module-level constants
    directly from the UI; those constants remain the defaults used
    whenever no override has been saved yet (see clamp_threshold there).
  - Accessibility's "larger text" option only adjusts QApplication's
    base font point size; it never touches ui/theme.py's stylesheet
    strings, so existing QSS (colors, borders, spacing) is unaffected.
  - Diagnostics is a read-only view over the existing error_log module
    (already populated by main.py's excepthook and startup-failure
    handling) -- opening/using this tab cannot itself produce errors
    for itself to show.
  - Changelog re-renders the same collapsible, grouped CHANGELOG data
    (via the shared ChangelogVersionSection widget below) already shown
    by Help > What's new..., so the two can never drift out of sync
    with each other.

Nothing in this module is wired to run automatically; it's only shown
when the user opens Settings, mirroring how the existing "What's new"
dialog works. Duplicate Detection thresholds are the one exception to
"nothing persists until OK is pressed" (see General's live theme
preview) -- they're saved immediately as the user adjusts them, same as
Accessibility's "larger text" toggle, since there's no live preview to
protect and re-running the scan is an explicit separate action (re-
opening the library or hitting the existing rescan path) rather than
something this dialog triggers itself.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import crash_reporter, error_log
from ..changelog import APP_VERSION, CATEGORY_EMOJI, CATEGORY_ORDER, CHANGELOG
from ..core.duplicate_detector import (
    FUZZY_HIGH_CONFIDENCE,
    FUZZY_LOW_CONFIDENCE,
    FUZZY_THRESHOLD_MAX,
    FUZZY_THRESHOLD_MIN,
    clamp_threshold,
)
from ..core.itunes_com_sync import is_windows
from ..core.rebuild_script import autodetect_itunes_dir, default_itunes_dir
from .theme import base_palette_choices, theme_choices


class ChangelogVersionSection(QWidget):
    """One collapsible "What's new" section for a single changelog
    version: a click-to-toggle header (version + date) and, when
    expanded, its bullets grouped under Added/Fixed/Changed subheadings
    (categories with no bullets for this version are simply omitted).
    Built from plain QWidgets (a QToolButton for the disclosure arrow +
    a body QWidget whose visibility toggles) rather than a third-party
    collapsible-panel widget, since Qt's built-ins cover this exactly.
    Shared by the toolbar's Help > What's new... dialog (main_window.py)
    and Settings > Changelog below, so the two never drift apart."""

    def __init__(self, entry, expanded: bool = False, parent=None):
        super().__init__(parent)
        # Kept accessible (not just consumed in __init__) so the "Jump to
        # version..." dropdown (build_changelog_version_jump below) can
        # label each entry in the combo box from the same section objects
        # it's given, rather than needing a second, separately-ordered
        # copy of CHANGELOG passed alongside them.
        self.entry = entry
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toggle = QToolButton()
        self._toggle.setText(f"Version {entry.version} — {entry.date}")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; }")
        self._toggle.clicked.connect(self._on_toggled)
        outer.addWidget(self._toggle)

        self._body = QWidget()
        self._body.setVisible(expanded)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(24, 2, 4, 8)
        body_layout.setSpacing(6)

        categorized = entry.categorized()
        for category in CATEGORY_ORDER:
            bullets = categorized.get(category, [])
            if not bullets:
                continue
            heading = QLabel(f"{CATEGORY_EMOJI.get(category, '')} {category}".strip())
            heading.setObjectName("sectionHeading")
            body_layout.addWidget(heading)
            for bullet in bullets:
                bullet_label = QLabel(f"•  {bullet}")
                bullet_label.setObjectName("subtitle")
                bullet_label.setWordWrap(True)
                body_layout.addWidget(bullet_label)

        outer.addWidget(self._body)

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

    def expand(self) -> None:
        """Opens this section (used by the "Jump to version" dropdown
        below) without affecting any other section's state."""
        if not self._toggle.isChecked():
            self._toggle.setChecked(True)
            self._on_toggled(True)


def build_changelog_version_jump(scroll: QScrollArea, sections: list["ChangelogVersionSection"]) -> QComboBox:
    """Builds the "Jump to version..." dropdown shown above the
    collapsible changelog sections, in both Help > What's new... and
    Settings > Changelog (see main_window._on_show_changelog and
    _build_changelog_tab below) -- one shared helper so the two dropdowns
    always list the same versions in the same order and behave
    identically.

    Selecting an entry expands that version's section (leaving every
    other section's expanded/collapsed state untouched) and scrolls it
    into view. Purely a navigation aid over the existing collapsible
    sections -- it doesn't change what CHANGELOG data is shown or add a
    second copy of the release notes.
    """
    combo = QComboBox()
    combo.addItem("Jump to version\u2026", userData=None)
    for section in sections:
        combo.addItem(f"Version {section.entry.version} — {section.entry.date}", userData=section)

    def _on_jump(index: int) -> None:
        target = combo.itemData(index)
        if target is None:
            return
        target.expand()
        scroll.ensureWidgetVisible(target, 0, 0)
        # Reset back to the placeholder afterward so re-selecting the same
        # entry twice in a row still fires currentIndexChanged (and so the
        # box doesn't look "stuck" on one version after jumping).
        combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    combo.currentIndexChanged.connect(_on_jump)
    return combo


# ---------------------------------------------------------------- settings keys
#
# Stored via CacheDB.get_setting/set_setting (the same generic key/value
# store already used for "ui_state"). Kept as their own top-level keys
# rather than folded into "ui_state" so a future change to one schema's
# version never has to touch the other's.
THEME_SETTING_KEY = "theme_preference"       # "auto" | "light" | "dark"
ACCENT_THEME_SETTING_KEY = "accent_theme_id"  # one of ui.theme.THEME_ORDER,
                                               # e.g. "teal" -- kept as its own
                                               # setting (rather than folded
                                               # into THEME_SETTING_KEY) so a
                                               # value saved before accent
                                               # theming existed still parses
                                               # as a plain "auto"/"light"/
                                               # "dark" mode with no migration
                                               # needed.
LARGE_TEXT_SETTING_KEY = "accessibility_large_text"  # bool
# v2.0: one of ui.theme.BASE_PALETTE_ORDER (e.g. "midnight"), or "" for
# "no override" (the original Light/Dark surface look). Kept as its own
# setting, same reasoning as ACCENT_THEME_SETTING_KEY above -- a value
# saved before base palettes existed still parses as a plain mode/accent
# preference with no migration needed.
BASE_PALETTE_SETTING_KEY = "base_palette_id"
FUZZY_LOW_SETTING_KEY = "fuzzy_low_confidence_threshold"    # float, 0.5-0.99
FUZZY_HIGH_SETTING_KEY = "fuzzy_high_confidence_threshold"  # float, 0.5-0.99
SNAPSHOT_RETENTION_SETTING_KEY = "snapshot_retention_count"  # int, 0 = unlimited

# Scheduled/automatic re-scan ("check for new duplicates weekly" -- see
# MainWindow._maybe_run_scheduled_rescan, which reads these at startup).
# Defined here (rather than in main_window.py, where the feature actually
# runs) so this dialog's General tab and that startup check share one
# source of truth for the key names/defaults/bounds, the same pattern
# already used for every other General-tab setting in this file.
AUTO_RESCAN_ENABLED_SETTING_KEY = "auto_rescan_enabled"          # bool
AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY = "auto_rescan_interval_days"  # int, 1-90
AUTO_RESCAN_INTERVAL_DAYS_DEFAULT = 7
AUTO_RESCAN_INTERVAL_DAYS_MIN = 1
AUTO_RESCAN_INTERVAL_DAYS_MAX = 90

_THEME_CHOICES = [
    ("Match Windows (recommended)", "auto"),
    ("Light", "light"),
    ("Dark", "dark"),
]

# Snapshots keep growing (see backup section below); this default caps the
# SQLite cache at a reasonable number of restore points without deleting
# anything a normal, occasional user would ever notice missing (every load
# and every apply writes one, so this is dozens of app-uses' worth, not a
# handful). 0 disables pruning entirely ("unlimited", matching the pre-
# existing/original behavior for anyone who upgrades and never opens this
# setting).
SNAPSHOT_RETENTION_DEFAULT = 100
# Hard bounds for the user-configurable value -- 0 is the explicit
# "unlimited" sentinel (see above) and is allowed through unclamped;
# everything else is kept in a sane range so a fat-fingered value can't
# silently disable backups (too low) or make the spinner unusable (too
# high).
SNAPSHOT_RETENTION_MIN = 5
SNAPSHOT_RETENTION_MAX = 2000


def clamp_snapshot_retention(value) -> int:
    """Clamps a user-supplied retention count into the valid range,
    falling back to the default for anything not interpretable as an
    int. 0 always passes through unchanged (unlimited), matching
    CacheDB.prune_snapshots' own "keep <= 0 means unlimited" contract."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return SNAPSHOT_RETENTION_DEFAULT
    if value == 0:
        return 0
    return min(max(value, SNAPSHOT_RETENTION_MIN), SNAPSHOT_RETENTION_MAX)


def _clamp_rescan_interval(value) -> int:
    """Clamps a user-supplied/stored scheduled-rescan interval (days)
    into AUTO_RESCAN_INTERVAL_DAYS_MIN..MAX, falling back to the default
    for anything not interpretable as an int -- same defend-against-a-
    corrupt-or-out-of-range-stored-value shape as clamp_threshold/
    clamp_snapshot_retention above."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return AUTO_RESCAN_INTERVAL_DAYS_DEFAULT
    return min(max(value, AUTO_RESCAN_INTERVAL_DAYS_MIN), AUTO_RESCAN_INTERVAL_DAYS_MAX)

# QApplication's default base point size before any "larger text" scaling
# is applied. Captured the first time it's needed (see apply_font_scale)
# rather than hardcoded, since the platform default varies by OS/DPI --
# this way "off" always means "back to whatever it already was", not a
# guessed fixed number.
_base_point_size: float | None = None

# Multiplier applied to the base font size when "larger text" is on.
# Modest and readable rather than dramatic, consistent with this being an
# accessibility nicety layered on top of the existing design, not a
# redesign of it.
_LARGE_TEXT_SCALE = 1.15


def apply_font_scale(large_text: bool) -> None:
    """Applies (or reverts) the Accessibility "larger text" setting to the
    running QApplication. Safe to call multiple times/idempotently --
    always scales from the recorded original base size, never compounds."""
    global _base_point_size
    app = QApplication.instance()
    if app is None:
        return
    font = app.font()
    if _base_point_size is None:
        # PointSizeF is used (not integer PointSize) so the multiplier
        # doesn't lose precision or drift on repeated toggles.
        _base_point_size = font.pointSizeF()
        if _base_point_size <= 0:
            # Some platforms report -1 (pixel-size-based font instead of
            # point-size-based); scaling isn't meaningful there, so treat
            # "larger text" as a no-op rather than producing a nonsensical
            # size.
            return
    font.setPointSizeF(_base_point_size * _LARGE_TEXT_SCALE if large_text else _base_point_size)
    app.setFont(font)


def load_theme_preference(cache) -> str:
    """Reads the saved theme preference, defaulting to 'auto' (the
    original, always-on behavior) if nothing was saved yet or the saved
    value isn't one of the recognized choices."""
    value = cache.get_setting(THEME_SETTING_KEY, default="auto")
    valid = {choice for _, choice in _THEME_CHOICES}
    return value if value in valid else "auto"


def load_accent_theme_id(cache) -> str:
    """Reads the saved accent color theme id, defaulting to 'blue' (the
    app's original/only accent) if nothing was saved yet or the saved
    value isn't one of the ten recognized theme ids."""
    value = cache.get_setting(ACCENT_THEME_SETTING_KEY, default="blue")
    valid = {theme_id for _, theme_id in theme_choices()}
    return value if value in valid else "blue"


def load_base_palette_id(cache) -> str:
    """Reads the saved base-palette id (v2.0), defaulting to "" (no
    override -- the original Light/Dark surface look) if nothing was
    saved yet or the saved value isn't one of the 8 recognized palette
    ids."""
    value = cache.get_setting(BASE_PALETTE_SETTING_KEY, default="")
    valid = {palette_id for _, palette_id in base_palette_choices()}
    return value if value in valid else ""


def load_qss_preference(cache) -> str:
    """Combines the saved appearance mode, accent theme, and (v2.0) base
    palette into the single string ui.theme.current_qss()/accent_color()
    expect (e.g. "dark:teal:midnight"). This is the one function
    MainWindow/main.py should call to get the currently-effective full
    theme preference; none of them need to know the three settings are
    stored separately."""
    palette_id = load_base_palette_id(cache)
    suffix = f":{palette_id}" if palette_id else ""
    return f"{load_theme_preference(cache)}:{load_accent_theme_id(cache)}{suffix}"


def load_large_text_preference(cache) -> bool:
    value = cache.get_setting(LARGE_TEXT_SETTING_KEY, default=False)
    return bool(value)


def load_fuzzy_thresholds(cache) -> tuple[float, float]:
    """Returns (low_confidence, high_confidence), each clamped into the
    valid range and falling back to the module defaults if nothing was
    saved yet or the stored value is corrupt/out of range. Low is also
    never allowed to end up >= high (a saved combination that would make
    the "review" tier disappear or invert) -- if that happens the low
    value is pulled back down to just under high instead of raising or
    silently producing an unusable tier split.

    This is the one function workers.py needs to call to get the
    currently-effective thresholds; it never reads CacheDB directly."""
    low = clamp_threshold(cache.get_setting(FUZZY_LOW_SETTING_KEY, default=FUZZY_LOW_CONFIDENCE), FUZZY_LOW_CONFIDENCE)
    high = clamp_threshold(cache.get_setting(FUZZY_HIGH_SETTING_KEY, default=FUZZY_HIGH_CONFIDENCE), FUZZY_HIGH_CONFIDENCE)
    if low >= high:
        low = max(FUZZY_THRESHOLD_MIN, round(high - 0.01, 2))
    return low, high


def load_snapshot_retention(cache) -> int:
    """Returns the currently-effective snapshot retention count (0 =
    unlimited), clamped/defaulted the same way load_fuzzy_thresholds()
    handles its settings. This is the one function workers.py/MainWindow
    need to call to prune after a new snapshot is saved; neither reads
    CacheDB's raw setting directly."""
    return clamp_snapshot_retention(
        cache.get_setting(SNAPSHOT_RETENTION_SETTING_KEY, default=SNAPSHOT_RETENTION_DEFAULT)
    )


class SettingsDialog(QDialog):
    """Settings grouped by workflow stage instead of a flat alphabetical
    tab list, so the setting you need is easier to find at the point in
    the workflow where you'd actually want it, rather than requiring you
    to already know which of five unrelated-sounding tab names it's
    filed under:

      - Before you scan: appearance/version (General) and readability
        (Accessibility) -- things worth checking before opening a
        library at all.
      - During cleanup: how strict duplicate matching is (Duplicate
        Detection) and the error log (Diagnostics) -- things you'd
        reach for while actively reviewing/adjusting a scan.
      - Reference: What's new (Changelog) -- not tied to any workflow
        stage, kept as its own top-level group rather than forced under
        one of the above.

    Each original tab keeps its existing builder method, tooltips,
    settings keys, and save behavior unchanged -- this only changes how
    they're grouped/labeled in the QTabWidget(s).

    `cache` is the same CacheDB instance MainWindow already owns (for
    ui_state); `on_theme_changed` is called with the new preference string
    immediately when the user picks a different theme, so the running app
    restyles without needing to reopen this dialog or restart the app.
    """

    def __init__(self, cache, on_theme_changed, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._on_theme_changed = on_theme_changed
        # The theme preference in effect when this dialog was opened --
        # used to live-preview appearance changes as the user browses the
        # combo box without persisting anything until they confirm, and to
        # restore the original look if they cancel/close the dialog any
        # other way (Esc, the titlebar X, etc.). Persisting on every combo
        # change (the old behavior) meant there was no way to "try" a
        # theme and back out of it. Combined mode+accent string (see
        # load_qss_preference) so reverting restores both the light/dark/
        # auto mode and the accent color together in one call.
        self._original_theme_preference = load_qss_preference(self._cache)
        self._theme_committed = False

        self.setWindowTitle("Settings")
        self.resize(560, 480)
        layout = QVBoxLayout(self)

        # Top-level tabs are workflow stages; each stage's sub-tab widget
        # holds the existing settings pages relevant to that stage, in
        # the same left-to-right order they used to appear in the old
        # flat list. See class docstring for how each page was assigned.
        stage_tabs = QTabWidget()

        before_scan = QTabWidget()
        before_scan.addTab(self._build_general_tab(), "\u2699\uFE0F General")
        before_scan.addTab(self._build_accessibility_tab(), "\u267F Accessibility")
        stage_tabs.addTab(before_scan, "1\uFE0F\u20E3 Before you scan")

        during_cleanup = QTabWidget()
        during_cleanup.addTab(self._build_duplicate_detection_tab(), "\U0001F50D Duplicate Detection")
        during_cleanup.addTab(self._build_backups_tab(), "\U0001F5C4\uFE0F Backups")
        during_cleanup.addTab(self._build_diagnostics_tab(), "\U0001FA7A Diagnostics")
        stage_tabs.addTab(during_cleanup, "2\uFE0F\u20E3 During cleanup")

        reference = QTabWidget()
        reference.addTab(self._build_changelog_tab(), "\U0001F4DC Changelog")
        stage_tabs.addTab(reference, "\U0001F4D6 Reference")

        layout.addWidget(stage_tabs, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        close_row.addWidget(cancel_btn)
        close_btn = QPushButton("OK")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def accept(self) -> None:
        self._commit_theme()
        super().accept()

    def reject(self) -> None:
        self._revert_theme_preview()
        super().reject()

    def done(self, result: int) -> None:  # noqa: N802 (Qt override)
        # Covers every way the dialog can close besides the OK/Cancel
        # buttons above (Esc key, the titlebar close box) so a previewed-
        # but-not-confirmed theme is never left applied/saved just because
        # the user dismissed the dialog a different way.
        if result != QDialog.DialogCode.Accepted:
            self._revert_theme_preview()
        super().done(result)

    def _commit_theme(self) -> None:
        if self._theme_committed:
            return
        self._theme_committed = True
        mode_value = self.theme_combo.currentData()
        accent_value = self.accent_combo.currentData()
        palette_value = self.base_palette_combo.currentData()
        try:
            self._cache.set_setting(THEME_SETTING_KEY, mode_value)
            self._cache.set_setting(ACCENT_THEME_SETTING_KEY, accent_value)
            self._cache.set_setting(BASE_PALETTE_SETTING_KEY, palette_value or "")
        except Exception:
            # Best-effort, matching every other UI-state save in this app
            # (see MainWindow._save_ui_state) -- a failed preference write
            # should never block using the preference for the rest of
            # this session.
            pass

    def _revert_theme_preview(self) -> None:
        if self._theme_committed:
            return
        if self._on_theme_changed is not None:
            self._on_theme_changed(self._original_theme_preference)

    # ------------------------------------------------------------- General

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        intro = QLabel(
            "These settings are saved on this computer and apply right "
            "away, and again next time you open the app."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        form.addRow(intro)

        self.theme_combo = QComboBox()
        for label, value in _THEME_CHOICES:
            self.theme_combo.addItem(label, userData=value)
        current = load_theme_preference(self._cache)
        idx = self.theme_combo.findData(current)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        form.addRow("Appearance:", self.theme_combo)

        # Accent color theme -- independent of the light/dark/auto mode
        # above (any of the ten accents can be paired with any mode). The
        # accent recolors buttons, tabs, progress bars, links, and other
        # accent-tinted text/UI app-wide via ui/theme.py's per-theme QSS.
        self.accent_combo = QComboBox()
        for label, theme_id in theme_choices():
            self.accent_combo.addItem(label, userData=theme_id)
        current_accent = load_accent_theme_id(self._cache)
        accent_idx = self.accent_combo.findData(current_accent)
        if accent_idx >= 0:
            self.accent_combo.setCurrentIndex(accent_idx)
        self.accent_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        form.addRow("Accent color:", self.accent_combo)

        # Base palette (v2.0) -- a further surface/text color treatment,
        # independent of both the mode above and the accent color above
        # it (any of the 8 palettes can be paired with any mode/accent,
        # though a palette only takes effect while its own "family"
        # matches the active mode -- see ui/theme._recolor_base). The
        # first entry is always "no override", so upgrading users keep
        # the exact original Light/Dark look until they opt in.
        self.base_palette_combo = QComboBox()
        self.base_palette_combo.addItem("No override (original Light/Dark)", userData="")
        for label, palette_id in base_palette_choices():
            self.base_palette_combo.addItem(label, userData=palette_id)
        current_palette = load_base_palette_id(self._cache)
        palette_idx = self.base_palette_combo.findData(current_palette)
        if palette_idx >= 0:
            self.base_palette_combo.setCurrentIndex(palette_idx)
        self.base_palette_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        self.base_palette_combo.setToolTip(
            "An additional surface color treatment on top of Appearance/"
            "Accent color -- only visible while Appearance matches the "
            "palette's own light or dark family."
        )
        form.addRow("Theme:", self.base_palette_combo)

        # Scheduled/automatic re-scan: for people who keep re-importing
        # tracks into the same library, checks once per launch (see
        # MainWindow._maybe_run_scheduled_rescan) whether it's been long
        # enough since the last recorded scan of the most-recently-opened
        # library, and if so, re-scans it in the background and reports
        # the result via toast. Off by default -- saved immediately as
        # it's changed (no live preview to protect, matching Duplicate
        # Detection's thresholds/Accessibility's large-text toggle
        # elsewhere in this dialog), not deferred to OK.
        self.auto_rescan_checkbox = QCheckBox("Check for new duplicates automatically")
        self.auto_rescan_checkbox.setChecked(
            bool(self._cache.get_setting(AUTO_RESCAN_ENABLED_SETTING_KEY, default=False))
        )
        self.auto_rescan_checkbox.setToolTip(
            "Once per launch, re-scans your most recently opened library "
            "in the background if it's been at least this many days "
            "since its last scan, and shows a notification with what it "
            "found. Useful if you keep re-importing new tracks."
        )
        self.auto_rescan_checkbox.stateChanged.connect(self._on_auto_rescan_toggled)
        form.addRow(self.auto_rescan_checkbox)

        self.auto_rescan_interval_spin = QSpinBox()
        self.auto_rescan_interval_spin.setRange(
            AUTO_RESCAN_INTERVAL_DAYS_MIN, AUTO_RESCAN_INTERVAL_DAYS_MAX
        )
        self.auto_rescan_interval_spin.setSuffix(" day(s)")
        self.auto_rescan_interval_spin.setValue(
            _clamp_rescan_interval(
                self._cache.get_setting(
                    AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY,
                    default=AUTO_RESCAN_INTERVAL_DAYS_DEFAULT,
                )
            )
        )
        self.auto_rescan_interval_spin.setEnabled(self.auto_rescan_checkbox.isChecked())
        self.auto_rescan_interval_spin.setToolTip(
            "How often to check, e.g. 7 for weekly."
        )
        self.auto_rescan_interval_spin.valueChanged.connect(self._on_auto_rescan_interval_changed)
        form.addRow("Check every:", self.auto_rescan_interval_spin)

        if is_windows():
            # Manual override for the iTunes data folder (the one
            # containing iTunes Library.itl) used by "Rebuild library
            # now..."/"Undo last rebuild". This is normally set via the
            # auto-detect-then-confirm prompt on first launch (see
            # main_window._confirm_itunes_dir_on_launch) or by browsing
            # the first time a rebuild is run (_prompt_for_itunes_dir) --
            # this field is the same "itunes_library_dir" CacheDB setting,
            # just editable directly for anyone who wants to change it
            # (a new drive, a moved library) without waiting to be asked.
            itunes_row = QHBoxLayout()
            self.itunes_dir_edit = QLineEdit()
            self.itunes_dir_edit.setText(self._cache.get_setting("itunes_library_dir") or "")
            self.itunes_dir_edit.setPlaceholderText(str(default_itunes_dir()))
            self.itunes_dir_edit.setToolTip(
                "The folder containing your real iTunes data file "
                "(iTunes Library.itl) -- used when rebuilding your "
                "library after cleanup. This isn't always the default "
                "Music\\iTunes folder; it can be on another drive or a "
                "OneDrive-redirected Music folder."
            )
            self.itunes_dir_edit.editingFinished.connect(self._on_itunes_dir_edited)
            itunes_row.addWidget(self.itunes_dir_edit, stretch=1)

            browse_btn = QPushButton("Browse\u2026")
            browse_btn.setToolTip("Pick the folder yourself.")
            browse_btn.clicked.connect(self._on_browse_itunes_dir)
            itunes_row.addWidget(browse_btn)

            autodetect_btn = QPushButton("Auto-detect")
            autodetect_btn.setToolTip(
                "Scan common drive letters for a folder that already "
                "looks like an iTunes data folder."
            )
            autodetect_btn.clicked.connect(self._on_autodetect_itunes_dir)
            itunes_row.addWidget(autodetect_btn)

            form.addRow("iTunes folder:", itunes_row)

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("subtitle")
        form.addRow("Version:", version_label)

        return tab

    def _on_auto_rescan_toggled(self, _state: int) -> None:
        checked = self.auto_rescan_checkbox.isChecked()
        self.auto_rescan_interval_spin.setEnabled(checked)
        try:
            self._cache.set_setting(AUTO_RESCAN_ENABLED_SETTING_KEY, checked)
        except Exception:
            # Best-effort, matching every other setting save in this
            # dialog -- a failed write shouldn't block using the value
            # for the rest of this session.
            pass

    def _on_auto_rescan_interval_changed(self, value: int) -> None:
        try:
            self._cache.set_setting(
                AUTO_RESCAN_INTERVAL_DAYS_SETTING_KEY, _clamp_rescan_interval(value)
            )
        except Exception:
            pass

    def _on_itunes_dir_edited(self) -> None:
        # Typed/pasted directly into the field, rather than picked via
        # Browse/Auto-detect below -- saved as-is (matching how every
        # other field on this tab persists immediately, see class
        # docstring) without validating the path here, since a folder
        # that doesn't exist yet or doesn't currently contain iTunes
        # Library.itl isn't necessarily wrong (e.g. iTunes hasn't been
        # opened there yet) -- the rebuild step itself already checks and
        # reports clearly if the folder turns out not to be usable.
        value = self.itunes_dir_edit.text().strip()
        try:
            self._cache.set_setting("itunes_library_dir", value)
        except Exception:
            pass

    def _on_browse_itunes_dir(self) -> None:
        start_dir = self.itunes_dir_edit.text().strip() or str(default_itunes_dir())
        chosen = QFileDialog.getExistingDirectory(
            self, "Select your iTunes folder (containing iTunes Library.itl)", start_dir,
        )
        if not chosen:
            return
        self.itunes_dir_edit.setText(chosen)
        self._on_itunes_dir_edited()

    def _on_autodetect_itunes_dir(self) -> None:
        detected = autodetect_itunes_dir()
        if detected is None:
            QMessageBox.information(
                self, "Nothing found",
                "Couldn't find an iTunes folder automatically on any "
                "drive. Use Browse\u2026 to pick it yourself.",
            )
            return
        self.itunes_dir_edit.setText(str(detected))
        self._on_itunes_dir_edited()

    def _on_theme_combo_changed(self, _index: int) -> None:
        # Live preview only -- the window restyles immediately so the user
        # can see the effect, but nothing is written to the cache until OK
        # is pressed (see accept()/_commit_theme()). Cancel/Esc/closing the
        # dialog restores whatever preference was active before it opened.
        # Shared by all three combos (Appearance/Accent color/Theme --
        # any one changing needs to recombine with the other two's current
        # values).
        mode_value = self.theme_combo.currentData()
        accent_value = self.accent_combo.currentData()
        palette_value = self.base_palette_combo.currentData()
        suffix = f":{palette_value}" if palette_value else ""
        if self._on_theme_changed is not None:
            self._on_theme_changed(f"{mode_value}:{accent_value}{suffix}")

    # ---------------------------------------------------- Duplicate Detection

    def _build_duplicate_detection_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        intro = QLabel(
            "Controls how strict the app is when catching near-miss "
            "duplicates (like a typo). Exact matches are always found, no "
            "matter what these are set to. Changes apply the next time a "
            "library is opened or rescanned."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        form.addRow(intro)

        saved_low, saved_high = load_fuzzy_thresholds(self._cache)

        self.fuzzy_low_spin = QDoubleSpinBox()
        self.fuzzy_low_spin.setRange(FUZZY_THRESHOLD_MIN, FUZZY_THRESHOLD_MAX)
        self.fuzzy_low_spin.setSingleStep(0.01)
        self.fuzzy_low_spin.setDecimals(2)
        self.fuzzy_low_spin.setValue(saved_low)
        self.fuzzy_low_spin.setToolTip(
            "How similar two songs need to be before they're shown as a "
            "'possible duplicate' at all. Lower catches more near-misses "
            "(like typos) but may also flag unrelated songs. Below this, "
            "songs are never linked."
        )
        self.fuzzy_low_spin.valueChanged.connect(self._on_fuzzy_thresholds_changed)
        form.addRow("Possible-duplicate threshold:", self.fuzzy_low_spin)

        self.fuzzy_high_spin = QDoubleSpinBox()
        self.fuzzy_high_spin.setRange(FUZZY_THRESHOLD_MIN, FUZZY_THRESHOLD_MAX)
        self.fuzzy_high_spin.setSingleStep(0.01)
        self.fuzzy_high_spin.setDecimals(2)
        self.fuzzy_high_spin.setValue(saved_high)
        self.fuzzy_high_spin.setToolTip(
            "How similar two songs need to be before they're pre-checked "
            "as 'high confidence' instead of 'needs review'. Must be "
            "higher than the possible-duplicate setting above. Either "
            "way, nothing is ever merged without your OK."
        )
        self.fuzzy_high_spin.valueChanged.connect(self._on_fuzzy_thresholds_changed)
        form.addRow("High-confidence threshold:", self.fuzzy_high_spin)

        self.fuzzy_reset_btn = QPushButton("↩️ Reset to defaults")
        self.fuzzy_reset_btn.setToolTip(
            f"Put both settings back to their original values "
            f"({FUZZY_LOW_CONFIDENCE:.2f} and {FUZZY_HIGH_CONFIDENCE:.2f})."
        )
        self.fuzzy_reset_btn.clicked.connect(self._on_fuzzy_thresholds_reset)
        form.addRow("", self.fuzzy_reset_btn)

        return tab

    def _on_fuzzy_thresholds_changed(self, _value: float) -> None:
        # Keep low strictly below high in the widgets themselves (not just
        # at load time) so the user can't leave the dialog with an
        # inverted/equal pair that would silently make the "review" tier
        # disappear -- nudging the spin box that was NOT just edited is
        # less surprising than rejecting the edit outright.
        low = self.fuzzy_low_spin.value()
        high = self.fuzzy_high_spin.value()
        if low >= high:
            sender = self.sender()
            if sender is self.fuzzy_high_spin:
                self.fuzzy_low_spin.blockSignals(True)
                self.fuzzy_low_spin.setValue(max(FUZZY_THRESHOLD_MIN, round(high - 0.01, 2)))
                self.fuzzy_low_spin.blockSignals(False)
            else:
                self.fuzzy_high_spin.blockSignals(True)
                self.fuzzy_high_spin.setValue(min(FUZZY_THRESHOLD_MAX, round(low + 0.01, 2)))
                self.fuzzy_high_spin.blockSignals(False)
        try:
            self._cache.set_setting(FUZZY_LOW_SETTING_KEY, self.fuzzy_low_spin.value())
            self._cache.set_setting(FUZZY_HIGH_SETTING_KEY, self.fuzzy_high_spin.value())
        except Exception:
            # Best-effort, matching every other setting save in this
            # dialog -- a failed write shouldn't block using the value for
            # the rest of this session.
            pass

    def _on_fuzzy_thresholds_reset(self) -> None:
        self.fuzzy_low_spin.setValue(FUZZY_LOW_CONFIDENCE)
        self.fuzzy_high_spin.setValue(FUZZY_HIGH_CONFIDENCE)

    # ------------------------------------------------------------- Backups

    def _build_backups_tab(self) -> QWidget:
        """Retention policy for the automatic backup snapshots saved to
        the local SQLite cache (data/cache_db.py's `snapshots` table) --
        one is written before every library load and before every apply,
        so left unmanaged this grows without bound. This tab lets the
        cap be changed and shows/lets the user prune to it on demand;
        the cap is also applied automatically right after every new
        snapshot is saved (see MainWindow._prune_snapshots_if_needed),
        so normal use never requires opening this tab at all."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "A backup snapshot is saved automatically every time you open "
            "a library or clean up duplicates, so you can always restore "
            "an earlier point in time (see \u23EA Restore backup\u2026). "
            "These build up over time — set how many to keep below."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(12)

        saved_keep = load_snapshot_retention(self._cache)
        self.snapshot_retention_spin = QSpinBox()
        self.snapshot_retention_spin.setRange(0, SNAPSHOT_RETENTION_MAX)
        self.snapshot_retention_spin.setSpecialValueText("Unlimited (not recommended)")
        self.snapshot_retention_spin.setValue(saved_keep)
        self.snapshot_retention_spin.setToolTip(
            "How many recent backup snapshots to keep. Once you go over "
            "this, the oldest ones are deleted automatically right after "
            "the next backup is saved. Set to 0 for unlimited (the cache "
            "file will keep growing)."
        )
        self.snapshot_retention_spin.valueChanged.connect(self._on_snapshot_retention_changed)
        form.addRow("Keep this many backups:", self.snapshot_retention_spin)
        layout.addLayout(form)

        self.snapshot_count_label = QLabel()
        self.snapshot_count_label.setObjectName("subtitle")
        layout.addWidget(self.snapshot_count_label)
        self._refresh_snapshot_count_label()

        btn_row = QHBoxLayout()
        prune_btn = QPushButton("\U0001F9F9 Delete old backups now")
        prune_btn.setToolTip(
            "Applies the setting above right now instead of waiting for "
            "the next backup — deletes the oldest snapshots beyond the "
            "number to keep."
        )
        prune_btn.clicked.connect(self._on_prune_snapshots_clicked)
        btn_row.addWidget(prune_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        return tab

    def _refresh_snapshot_count_label(self) -> None:
        try:
            count = self._cache.snapshot_count()
        except Exception:
            self.snapshot_count_label.setText("")
            return
        noun = "backup" if count == 1 else "backups"
        self.snapshot_count_label.setText(f"Currently stored: {count} {noun}.")

    def _on_snapshot_retention_changed(self, value: int) -> None:
        try:
            self._cache.set_setting(SNAPSHOT_RETENTION_SETTING_KEY, value)
        except Exception:
            # Best-effort, matching every other setting save in this
            # dialog -- a failed write shouldn't block using the value
            # for the rest of this session.
            pass

    def _on_prune_snapshots_clicked(self) -> None:
        keep = clamp_snapshot_retention(self.snapshot_retention_spin.value())
        if keep <= 0:
            QMessageBox.information(
                self, "Unlimited backups",
                "Retention is set to Unlimited, so there's nothing to "
                "delete. Set a number above first.",
            )
            return
        try:
            deleted = self._cache.prune_snapshots(keep)
        except Exception as exc:
            error_log.log_error("Couldn't prune backup snapshots", exc)
            QMessageBox.critical(
                self, "Couldn't delete old backups",
                f"Something went wrong while deleting old backups: {exc}",
            )
            return
        self._refresh_snapshot_count_label()
        if deleted:
            QMessageBox.information(
                self, "Old backups deleted",
                f"Deleted {deleted} old backup{'s' if deleted != 1 else ''}. "
                f"Kept the {keep} most recent.",
            )
        else:
            QMessageBox.information(
                self, "Nothing to delete",
                f"You already have {keep} or fewer backups saved.",
            )

    # ------------------------------------------------------- Accessibility

    def _build_accessibility_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Options to make the app easier to read and use. These don't "
            "change how your library is scanned or cleaned up — just how "
            "the app looks."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.large_text_cb = QCheckBox("Use larger text")
        self.large_text_cb.setChecked(load_large_text_preference(self._cache))
        self.large_text_cb.stateChanged.connect(self._on_large_text_changed)
        layout.addWidget(self.large_text_cb)

        contrast_note = QLabel(
            "The Dark option under General also boosts contrast for "
            "low-light viewing — see the General tab."
        )
        contrast_note.setObjectName("subtitle")
        contrast_note.setWordWrap(True)
        layout.addWidget(contrast_note)

        layout.addStretch(1)
        return tab

    def _on_large_text_changed(self, _state: int) -> None:
        checked = self.large_text_cb.isChecked()
        try:
            self._cache.set_setting(LARGE_TEXT_SETTING_KEY, checked)
        except Exception:
            pass
        apply_font_scale(checked)

    # --------------------------------------------------------- Diagnostics

    def _build_diagnostics_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        intro = QLabel(
            "A record of recent errors, newest first. Handy if you need "
            "to report a problem."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.diagnostics_text = QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        layout.addWidget(self.diagnostics_text, stretch=1)
        self._refresh_diagnostics()

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_diagnostics)
        btn_row.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑️ Clear log")
        clear_btn.clicked.connect(self._on_clear_diagnostics)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Crash dumps: a separate, richer artifact from the rolling
        # error.log above -- one self-contained file per crash (full
        # traceback + repro context), written locally only (see
        # crash_reporter.py). Shown here so a saved dump is easy to find
        # without hunting through the app-data folder by hand.
        dumps_heading = QLabel("Crash dumps")
        dumps_heading.setObjectName("sectionHeading")
        layout.addWidget(dumps_heading)

        dumps_intro = QLabel(
            "A local crash dump is saved automatically when the app hits "
            "an unexpected error, so it can be diagnosed without needing "
            "to reproduce it live. Saved to this computer only -- nothing "
            "here is sent anywhere. Attach a dump manually if you're "
            "reporting a problem."
        )
        dumps_intro.setObjectName("subtitle")
        dumps_intro.setWordWrap(True)
        layout.addWidget(dumps_intro)

        self.crash_dumps_list = QListWidget()
        self.crash_dumps_list.setMaximumHeight(120)
        layout.addWidget(self.crash_dumps_list)
        self._refresh_crash_dumps()

        dumps_btn_row = QHBoxLayout()
        refresh_dumps_btn = QPushButton("🔄 Refresh")
        refresh_dumps_btn.clicked.connect(self._refresh_crash_dumps)
        dumps_btn_row.addWidget(refresh_dumps_btn)

        open_dump_btn = QPushButton("📄 View selected dump")
        open_dump_btn.clicked.connect(self._on_view_crash_dump)
        dumps_btn_row.addWidget(open_dump_btn)
        dumps_btn_row.addStretch(1)
        layout.addLayout(dumps_btn_row)

        return tab

    def _refresh_diagnostics(self) -> None:
        entries = error_log.recent_entries()
        if not entries:
            self.diagnostics_text.setPlainText("No errors recorded.")
            return
        self.diagnostics_text.setPlainText("\n\n".join(entries))

    def _on_clear_diagnostics(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear the error log?",
            "This only clears the app's own error log. Your iTunes "
            "library and backups aren't touched. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        error_log.clear()
        self._refresh_diagnostics()

    def _refresh_crash_dumps(self) -> None:
        self.crash_dumps_list.clear()
        dumps = crash_reporter.list_crash_dumps()
        if not dumps:
            item = QListWidgetItem("No crash dumps saved.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.crash_dumps_list.addItem(item)
            return
        for dump_path in dumps:
            item = QListWidgetItem(dump_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(dump_path))
            self.crash_dumps_list.addItem(item)

    def _on_view_crash_dump(self) -> None:
        current = self.crash_dumps_list.currentItem()
        if current is None:
            return
        dump_path_str = current.data(Qt.ItemDataRole.UserRole)
        if not dump_path_str:
            return
        try:
            text = Path(dump_path_str).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            QMessageBox.critical(
                self, "Couldn't open crash dump",
                f"Couldn't read this crash dump file: {exc}",
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Crash dump \u2014 {Path(dump_path_str).name}")
        dialog.resize(640, 500)
        dialog_layout = QVBoxLayout(dialog)
        text_view = QTextEdit()
        text_view.setReadOnly(True)
        text_view.setPlainText(text)
        dialog_layout.addWidget(text_view, stretch=1)
        location_label = QLabel(f"Saved at: {dump_path_str}")
        location_label.setObjectName("subtitle")
        location_label.setWordWrap(True)
        dialog_layout.addWidget(location_label)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        dialog_layout.addLayout(btn_row)
        dialog.exec()

    # ----------------------------------------------------------- Changelog

    def _build_changelog_tab(self) -> QWidget:
        # Same collapsible, grouped "What's new" presentation as the
        # toolbar's What's new... dialog (see ChangelogVersionSection above
        # and main_window._on_show_changelog) -- built from the same
        # CHANGELOG data, so this tab can never show different release
        # notes than that dialog does. Replaces the old flat changelog_text()
        # QTextEdit dump with the same per-version dropdown sections.
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)

        sections = []
        for index, entry in enumerate(CHANGELOG):
            section = ChangelogVersionSection(entry, expanded=(index == 0))
            content_layout.addWidget(section)
            sections.append(section)
        content_layout.addStretch(1)

        scroll.setWidget(content)

        # "Jump to version..." dropdown, same as Help > What's new... --
        # lets a long changelog be navigated directly by version instead
        # of only scrolling/expanding sections one at a time.
        jump_combo = build_changelog_version_jump(scroll, sections)
        layout.addWidget(jump_combo)
        layout.addWidget(scroll, stretch=1)

        return tab
