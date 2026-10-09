"""
Small composable widget-builder classes factored out of
MainWindow._build_ui, which had grown into one long procedural method
covering the toolbar, header, filter row, table, and footer all at once.

Each class here builds one self-contained visual chunk and exposes the
individual widgets MainWindow needs to keep a reference to (to wire
signals, enable/disable, or update at runtime) as plain attributes.
Nothing here changes behavior, wording, tooltips, object names, or
layout -- this is a structural extraction only. MainWindow still owns
all signal wiring and business logic; these classes only assemble
widgets and layouts.
"""

from __future__ import annotations

import datetime

from PyQt6.QtCore import QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QTableWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# QtMultimedia (QMediaPlayer/QAudioOutput) ships as part of the same PyQt6
# wheel already pinned in requirements.txt -- not a new dependency, just a
# different submodule of the one already-required package. Imported
# defensively: some minimal PyQt6 installs/environments omit the
# multimedia plugin backends (e.g. a stripped-down Linux CI image with no
# system audio backend available), and audio preview is a nice-to-have,
# not something that should ever prevent the rest of the app -- which has
# no other dependency on audio playback -- from starting. See
# AudioPreviewPlayer.is_available().
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA_IMPORT_ERROR: Exception | None = None
except Exception as _exc:  # pragma: no cover - environment-dependent
    QAudioOutput = None  # type: ignore[assignment]
    QMediaPlayer = None  # type: ignore[assignment]
    _MULTIMEDIA_IMPORT_ERROR = _exc


class MainToolbar:
    """Builds the top toolbar (Open, Recent, Restore backup, Save audit
    report, Settings, What's new) and hands back the QToolBar plus the
    actions/menu MainWindow needs to enable/disable or populate later
    (restore_action, recent_menu) -- callers connect each action's
    `triggered` signal themselves, same as the original inline code."""

    def __init__(self, window) -> None:
        style = window.style()
        toolbar = QToolBar("Main toolbar", window)
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.open_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "\U0001F4C2 Open Library.xml\u2026",
        )
        # Standard "Open" shortcut (Ctrl+O / Cmd+O), applied at the
        # QMainWindow level via the action itself (not a separate
        # QShortcut) so it's automatically listed in the action's own
        # tooltip below and can never fire while the action is disabled
        # (e.g. mid-load -- see MainWindow._set_busy) the way a bare
        # QShortcut would.
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setToolTip(
            "Choose an iTunes Library.xml file to scan for duplicates. "
            f"({self.open_action.shortcut().toString()})"
        )

        # Recent-files dropdown: a small toolbar button (not a QAction, so
        # it can host its own popup QMenu of recently opened libraries)
        # placed right next to Open. Populated/refreshed by MainWindow
        # (see _refresh_recent_files_menu) from persisted recent-files
        # state -- this class only builds the empty menu shell and exposes
        # it, so it never needs to know about CacheDB itself.
        self.recent_menu = QMenu("Recent libraries", toolbar)
        self.recent_button = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "\U0001F553 Recent\u2026",
        )
        self.recent_button.setToolTip("Reopen a recently used Library.xml file.")
        self.recent_button.setMenu(self.recent_menu)
        # Clicking the action itself (not just the dropdown arrow) also
        # pops the menu -- QToolButton normally requires the small arrow
        # to be clicked for InstantPopup-style menus, which is easy to
        # miss on a small icon+text action like this one.
        recent_button_widget = toolbar.widgetForAction(self.recent_button)
        if isinstance(recent_button_widget, QToolButton):
            recent_button_widget.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.restore_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "\u23EA Restore backup\u2026",
        )
        self.restore_action.setToolTip(
            "Roll back to an earlier automatic backup snapshot of this library."
        )
        self.restore_action.setEnabled(False)

        # Named restore points: same underlying snapshot mechanism as the
        # automatic backups above (see cache_db.CacheDB.save_snapshot,
        # which already accepted a `label`), just triggered on demand
        # with a user-chosen note ("before spring cleaning") instead of
        # only ever being taken automatically on load/apply. Enabled
        # alongside restore_action, for the same reason -- both need a
        # loaded library's current raw state to snapshot/restore.
        self.save_restore_point_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "\U0001F4CC Save restore point\u2026",
        )
        self.save_restore_point_action.setToolTip(
            "Save a labeled backup of the current library right now, so "
            "you can find and restore it later by name."
        )
        self.save_restore_point_action.setEnabled(False)

        self.undo_rebuild_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            "\u21A9\uFE0F Undo last rebuild\u2026",
        )
        # "Undo" here specifically means undoing the most recent in-app
        # library rebuild (see MainWindow._on_undo_last_rebuild) -- the
        # closest analog this app has to a general Ctrl+Z, and the one
        # already always-available action (not gated on this session
        # having run anything) that "undo" could safely mean without
        # ambiguity. Reviewing/undoing an individual manual-review edit
        # already has its own dedicated controls (see the detail panel's
        # "Mark this group as not duplicates" / "Keep this one instead"),
        # so Ctrl+Z is not overloaded onto those per-row actions.
        self.undo_rebuild_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_rebuild_action.setToolTip(
            "Restore the most recent iTunes Library.itl/.xml backup pair "
            "made by \"Rebuild library now...\", undoing that rebuild. "
            f"({self.undo_rebuild_action.shortcut().toString()})"
        )

        toolbar.addSeparator()

        self.save_audit_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "\U0001F4C4 Save audit report\u2026",
        )
        self.save_audit_action.setToolTip("Save a summary of what was cleaned up.")

        self.settings_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "\u2699\uFE0F Settings\u2026",
        )
        self.settings_action.setToolTip(
            "Change how the app looks and how duplicates are matched."
        )

        # Read-only: reads a Spotify data export (.zip or the extracted
        # folder) and reports how many of its tracks already appear in
        # the currently loaded library (see core/providers/
        # spotify_export.py and MainWindow._on_import_spotify_library).
        # Never enabled/disabled based on whether a library is loaded --
        # unlike the actions above, reading the export itself doesn't
        # require one; the comparison step just notes when there's
        # nothing loaded to compare against yet.
        self.import_spotify_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            "\U0001F3A7 Import Spotify library\u2026",
        )
        self.import_spotify_action.setToolTip(
            "Read a Spotify data export (.zip or extracted folder) and "
            "see how many of its tracks already appear in your currently "
            "loaded library."
        )

        # Manual merge override: lets the user pick any two tracks in the
        # currently loaded library and merge them, even if exact/fuzzy
        # detection never grouped them at all (as opposed to
        # canonical_override_id, which only re-picks which track survives
        # *within* an already-detected group -- see
        # MainWindow._on_merge_tracks_clicked /
        # core/duplicate_detector.make_manual_merge_group). Enabled only
        # once a library is loaded (there's nothing to pick from
        # otherwise), same gating as restore_action.
        self.merge_tracks_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton),
            "\U0001F517 Merge tracks\u2026",
        )
        self.merge_tracks_action.setToolTip(
            "Manually merge two tracks the automatic scan didn't group "
            "together at all, e.g. very differently tagged copies of the "
            "same song."
        )
        self.merge_tracks_action.setEnabled(False)

        # Spacer pushes What's new to the right edge of the toolbar.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.whats_new_action = toolbar.addAction(
            style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
            "\u2728 What's new\u2026",
        )
        self.whats_new_action.setToolTip("See what changed in this update.")

        self.toolbar = toolbar


class HeaderSection(QWidget):
    """Static eyebrow/title/subtitle header shown at the top of the
    window. Purely presentational -- no widgets here are ever referenced
    again after _build_ui, matching the original inline layout exactly."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        eyebrow = QLabel("ITUNES LIBRARY")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Duplicate Tracks")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Keep one copy of each song. Your playlists, ratings, and play "
            "history all stay safe."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)


class LibraryActionRow(QWidget):
    """Open/status/restore row directly under the header. Exposes
    open_btn, status_label, and restore_btn as attributes so MainWindow
    can wire their signals and update status_label's text at runtime,
    exactly as it did when these were built inline."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.open_btn = QPushButton("\U0001F4C2 Open Library.xml…")
        self.open_btn.setToolTip(
            "Choose an iTunes Library.xml file to scan for duplicates. You "
            "can also drag a Library.xml file onto this window."
        )
        layout.addWidget(self.open_btn)

        self.status_label = QLabel("No library loaded.")
        self.status_label.setObjectName("subtitle")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label, stretch=1)

        self.restore_btn = QPushButton("\u23EA Restore backup…")
        self.restore_btn.setToolTip(
            "Roll back to an earlier automatic backup snapshot of this "
            "library (taken on load and before each duplicate removal)."
        )
        self.restore_btn.setEnabled(False)
        layout.addWidget(self.restore_btn)


class SummaryBar(QFrame):
    """Always-visible duplicates/savings summary bar, visible regardless
    of which tab is active. Exposes summary_bar_label for MainWindow's
    _refresh_health to update."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.summary_bar_label = QLabel("Open a library to see duplicate and savings totals.")
        self.summary_bar_label.setObjectName("summaryBarLabel")
        self.summary_bar_label.setWordWrap(True)
        layout.addWidget(self.summary_bar_label, stretch=1)


class ItunesFolderStrip(QFrame):
    """Persistent, always-visible strip showing which iTunes data folder
    (the one containing iTunes Library.itl) is currently set -- so the
    user never has to guess or reopen the "Select your iTunes folder..."
    dialog just to check. Exposes folder_label for MainWindow to update
    whenever the setting changes (on launch, after _prompt_for_itunes_dir,
    and before any rebuild)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("itunesFolderStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        icon = QLabel("\U0001F4C1")
        layout.addWidget(icon)
        self.folder_label = QLabel("iTunes folder: not set")
        self.folder_label.setObjectName("itunesFolderStripLabel")
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.folder_label, stretch=1)


class FilterRow(QWidget):
    """Search text + confidence-tier filter row above the duplicates
    table. Exposes filter_edit and filter_tier_combo for MainWindow to
    wire signals and restore/save state, same widgets/tooltips/order as
    the original inline construction."""

    def __init__(
        self,
        tier_labels: dict,
        tier_exact,
        tier_high_confidence,
        tier_needs_review,
        tier_duration_mismatch=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filter_label = QLabel("Filter:")
        filter_label.setObjectName("subtitle")
        layout.addWidget(filter_label)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search by artist or song\u2026")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.filter_edit.setToolTip(
            "Only shows matching rows. It doesn't change what's selected."
        )
        layout.addWidget(self.filter_edit, stretch=2)

        self.filter_tier_combo = QComboBox()
        self.filter_tier_combo.addItem("All confidence levels", userData=None)
        self.filter_tier_combo.addItem(tier_labels[tier_exact], userData=tier_exact)
        self.filter_tier_combo.addItem(tier_labels[tier_high_confidence], userData=tier_high_confidence)
        self.filter_tier_combo.addItem(tier_labels[tier_needs_review], userData=tier_needs_review)
        # v2.0: optional -- omitted (None) by any caller still using the
        # old 4-arg signature, so this stays purely additive.
        if tier_duration_mismatch is not None and tier_duration_mismatch in tier_labels:
            self.filter_tier_combo.addItem(
                tier_labels[tier_duration_mismatch], userData=tier_duration_mismatch
            )
        self.filter_tier_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.filter_tier_combo.setToolTip(
            "Shows only groups that match this well. Exact means an "
            "identical artist and title; the others are close matches, "
            "like a typo. You can adjust this in Settings."
        )
        layout.addWidget(self.filter_tier_combo, stretch=1)


class DuplicatesTable(QTableWidget):
    """The duplicates dry-run preview table, with its column setup
    (resize modes, sortability, selection mode) applied once at
    construction -- identical configuration to the original inline
    QTableWidget, just moved into its own class so _build_ui doesn't
    have to lay it all out inline.

    Column order is user-movable (header.setSectionsMovable) and the
    resulting order/widths can be saved/restored across sessions via
    save_column_state()/restore_column_state() (see MainWindow's
    persisted-UI-state handling in ui/main_window.py) -- purely a
    convenience layered on top of the existing resize-mode setup below,
    which is otherwise unchanged: Song/Artist/Why-flagged still stretch
    to fill available space and the narrow numeric columns still size to
    their contents by default, exactly as before, unless/until the user
    (or a restored session) actually resizes/reorders something."""

    def __init__(self, parent=None) -> None:
        super().__init__(0, 8, parent)
        self.setHorizontalHeaderLabels(
            ["", "Song", "Artist", "Duplicates removed", "Playlists updated",
             "Play count merged", "Match confidence", "Why flagged"]
        )
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 36)
        header_item = self.horizontalHeaderItem(0)
        if header_item is not None:
            header_item.setToolTip("Check the groups you want to clean up.")
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in (3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        # Lets the user drag column headers into a different order (e.g.
        # move "Match confidence" next to "Song"). Purely visual/ordering
        # -- every lookup elsewhere in this app resolves a row's data via
        # _action_for_row's UserRole index (see ui/main_window.py), never
        # by a fixed column position, so reordering columns can't point
        # any existing feature at the wrong data.
        header.setSectionsMovable(True)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ---------------------------------------------------- persisted layout

    def save_column_state(self) -> str:
        """Serializes the header's current section order/widths/sort
        indicator via Qt's own QHeaderView.saveState(), as a hex string
        so it round-trips cleanly through CacheDB's JSON value store
        (see data/cache_db.py's get_setting/set_setting) the same way
        MainWindow._save_ui_state already hex-encodes window geometry."""
        return bytes(self.horizontalHeader().saveState()).hex()

    def restore_column_state(self, state_hex: str) -> bool:
        """Restores a previously-saved header state. Returns False (and
        changes nothing) on any malformed/incompatible input -- e.g. a
        value saved by a future/different app version -- so a bad saved
        value can never leave the table's header in a broken state;
        Qt's own restoreState() already returns False in that case
        rather than raising, matching QMainWindow.restoreGeometry's
        failure contract used elsewhere in this app."""
        try:
            raw = bytes.fromhex(state_hex)
        except (ValueError, TypeError):
            return False
        return self.horizontalHeader().restoreState(raw)


class AudioPreviewPlayer(QFrame):
    """Small inline media-playback control (play/pause, seek slider,
    elapsed/total time, volume) for previewing one track's audio file, so
    a user reviewing a possible-duplicate group can listen to confirm two
    entries really are the same recording before deciding what to do
    with them -- rather than only comparing the text metadata already
    shown (artist/title/album/bitrate) in the detail panel.

    Backed by QMediaPlayer/QAudioOutput (see the QtMultimedia import
    above), not any new third-party dependency. One instance is created
    per group-row's per-track entry in the detail panel (see
    MainWindow._populate_detail_panel) and only ever plays the single
    file it was constructed with -- there is no shared/singleton player,
    so expanding a different row and stopping this one doesn't require
    any extra bookkeeping: the whole row (and this widget with it) is
    just deleted, which QMediaPlayer's own destructor already stops
    cleanly.

    Sized compactly (see _CONTROL_HEIGHT/_CONTROL_WIDTH below) since a
    detail panel can show several of these stacked at once, one per
    duplicate copy -- keeping each one short leaves more of the panel
    for the metadata it sits next to instead of the transport controls
    dominating the row.

    Read-only preview only: nothing here ever writes to the audio file,
    matching every other read-only preview already in this app (embedded
    artwork -- see core/artwork.py)."""

    # Compact sizing shared by the play button and volume button so the
    # whole control reads as one small unit rather than the play/pause
    # button dominating the row the way a default-sized QPushButton would.
    _CONTROL_HEIGHT = 24
    _CONTROL_WIDTH = 26
    # Remembered across every AudioPreviewPlayer instance in the process
    # (not just this row) -- QAudioOutput's own volume always starts back
    # at 1.0 for a brand new player, so without this, expanding a
    # different duplicate group after turning the volume down would jump
    # back to full volume on the very first preview played there. 0.0-1.0,
    # matching QAudioOutput.setVolume()'s own range.
    _last_volume = 0.5

    def __init__(self, path, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("audioPreviewPlayer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(4)

        self._player = None
        self._audio_output = None
        self._volume_before_mute = AudioPreviewPlayer._last_volume

        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(self._CONTROL_WIDTH, self._CONTROL_HEIGHT)
        self.play_btn.setToolTip("Play a preview of this file.")
        layout.addWidget(self.play_btn)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setFixedHeight(self._CONTROL_HEIGHT)
        self.position_slider.setToolTip("Seek within the preview.")
        layout.addWidget(self.position_slider, stretch=1)

        self.time_label = QLabel("--:-- / --:--")
        self.time_label.setObjectName("subtitle")
        self.time_label.setMinimumWidth(78)
        layout.addWidget(self.time_label)

        # Volume controls: a mute-toggle button plus a small slider, both
        # matching the play button's compact height. Previously there was
        # no way to adjust (or mute) preview playback volume at all short
        # of the OS/system mixer.
        self.volume_btn = QPushButton()
        self.volume_btn.setFixedSize(self._CONTROL_WIDTH, self._CONTROL_HEIGHT)
        self.volume_btn.setToolTip("Mute the preview.")
        layout.addWidget(self.volume_btn)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self._volume_before_mute * 100)))
        self.volume_slider.setFixedSize(60, self._CONTROL_HEIGHT)
        self.volume_slider.setToolTip("Preview volume.")
        layout.addWidget(self.volume_slider)

        style = self.style()
        self._play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self._pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self._volume_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        self._muted_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolumeMuted)

        if not self.is_available() or path is None:
            # No local audio backend available, or this track has no
            # resolvable local file (streamed/cloud/missing -- same
            # cases artwork lookup already treats as "nothing to show",
            # see core/artwork.file_uri_to_path). Shown disabled with an
            # explanatory tooltip rather than hidden entirely, so it's
            # clear this is "can't preview this one" and not a layout
            # glitch.
            self.play_btn.setIcon(self._play_icon)
            self.play_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            self.volume_btn.setIcon(self._volume_icon)
            self.volume_btn.setEnabled(False)
            self.volume_slider.setEnabled(False)
            reason = (
                "This copy's file couldn't be located on disk."
                if path is None else
                "Audio preview isn't available in this build."
            )
            self.setToolTip(reason)
            return

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(self._volume_before_mute)
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile(str(path)))

        self.play_btn.setIcon(self._play_icon)
        self.play_btn.clicked.connect(self._toggle_playback)
        self.volume_btn.setIcon(self._volume_icon)
        self.volume_btn.clicked.connect(self._toggle_mute)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.errorOccurred.connect(self._on_error)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)

    @staticmethod
    def is_available() -> bool:
        """True if QtMultimedia's playback classes imported successfully
        in this environment. Checked once at import time (see the
        try/except above this class) rather than re-attempted per
        instance, since a missing multimedia backend is an environment
        property that can't change mid-session."""
        return QMediaPlayer is not None and QAudioOutput is not None

    def _toggle_playback(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _toggle_mute(self) -> None:
        """Mutes/unmutes this preview, remembering the volume level it
        was at so unmuting restores it rather than jumping to some fixed
        default. Mirrors the slider position so the two controls never
        disagree about the current state."""
        if self._audio_output is None:
            return
        if self._audio_output.volume() > 0:
            self._volume_before_mute = self._audio_output.volume()
            self.volume_slider.setValue(0)
        else:
            restored = self._volume_before_mute if self._volume_before_mute > 0 else 0.5
            self.volume_slider.setValue(int(round(restored * 100)))

    def _on_volume_slider_changed(self, value: int) -> None:
        """Applies the slider's 0-100 position to QAudioOutput's 0.0-1.0
        volume, updates the mute-button icon to match, and remembers the
        level (AudioPreviewPlayer._last_volume) so the next preview
        opened -- in this row or any other -- starts at the same volume
        instead of resetting to full each time."""
        if self._audio_output is None:
            return
        volume = value / 100.0
        self._audio_output.setVolume(volume)
        AudioPreviewPlayer._last_volume = volume
        if value > 0:
            self._volume_before_mute = volume
        self.volume_btn.setIcon(self._muted_icon if value == 0 else self._volume_icon)
        self.volume_btn.setToolTip("Unmute the preview." if value == 0 else "Mute the preview.")

    def _on_playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(self._pause_icon if playing else self._play_icon)
        self.play_btn.setToolTip("Pause the preview." if playing else "Play a preview of this file.")

    def _on_position_changed(self, position_ms: int) -> None:
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position_ms)
        self._update_time_label(position_ms, self._player.duration() if self._player else 0)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.position_slider.setRange(0, max(duration_ms, 0))
        self._update_time_label(self._player.position() if self._player else 0, duration_ms)

    def _on_slider_moved(self, position_ms: int) -> None:
        if self._player is not None:
            self._player.setPosition(position_ms)

    def _on_error(self, _error, error_string: str) -> None:
        # A file that can't actually be decoded (corrupt/unsupported
        # codec/moved since the library was scanned) degrades to a
        # disabled control with the player's own error text, rather than
        # raising or silently doing nothing when Play is clicked --
        # matches this app's existing pattern of never letting a preview
        # feature's failure interrupt the surrounding review workflow.
        self.play_btn.setEnabled(False)
        self.position_slider.setEnabled(False)
        self.setToolTip(f"Couldn't preview this file: {error_string}" if error_string else "Couldn't preview this file.")

    @staticmethod
    def _format_ms(ms: int) -> str:
        total_seconds = max(ms, 0) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        self.time_label.setText(
            f"{self._format_ms(position_ms)} / {self._format_ms(duration_ms)}"
        )

    def stop(self) -> None:
        """Stops playback -- called before this widget's row is torn
        down (e.g. collapsing/re-expanding a group, or repopulating the
        table after a manual review edit) so audio doesn't keep playing
        for a row that's no longer visible. Safe to call even if
        playback was never available/started."""
        if self._player is not None:
            self._player.stop()


class EmptyStateLabel(QLabel):
    """Placeholder shown in place of the table when there's nothing to
    display. Text is swapped at runtime by MainWindow._apply_filter for
    each of the three distinct empty reasons; this class only sets up
    the widget itself with its original default text/styling."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            "🎵 Open a library to find duplicates. You can also drag a file onto this window.",
            parent,
        )
        self.setObjectName("subtitle")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(24, 32, 24, 32)
        self.setVisible(False)


# ---------------------------------------------------------- Severity dialogs

# Every plain QMessageBox.information/.warning/.critical in this app looked
# identical in weight (same grey title bar, same small icon) regardless of
# whether it was a routine confirmation ("Summary saved") or a real failure
# ("Couldn't rebuild library") -- so a genuine problem didn't visually stand
# out from a heads-up notice. These constants/helpers give each severity a
# distinct colored accent strip (matching the app's own Success/Warning/
# Danger design tokens from theme.py) across the top of the dialog, on top
# of the existing native icon/buttons/behavior -- nothing about *when* each
# severity is used, what buttons are offered, or what text is shown
# changes; this only makes the existing severity visually unmistakable.
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# (accent color, icon) per severity, light-mode-safe on both themes since
# these are saturated enough to read on the light/dark title strip either
# way -- same accent hues as QFrame#healthCard's tone strip in theme.py, so
# "danger" here means the same thing visually as "danger" elsewhere.
_SEVERITY_ACCENTS: dict[str, tuple[str, "QMessageBox.Icon"]] = {
    SEVERITY_INFO: ("#0A84FF", QMessageBox.Icon.Information),
    SEVERITY_WARNING: ("#FF9F0A", QMessageBox.Icon.Warning),
    SEVERITY_CRITICAL: ("#FF453A", QMessageBox.Icon.Critical),
}


def _apply_severity_style(box: QMessageBox, severity: str) -> None:
    accent, icon = _SEVERITY_ACCENTS.get(severity, _SEVERITY_ACCENTS[SEVERITY_INFO])
    box.setIcon(icon)
    # A colored top border on the dialog frame itself -- the one part of a
    # QMessageBox's own chrome that a stylesheet can reliably target across
    # both the light and dark app themes (QMessageBox doesn't expose its
    # icon label as a styleable object name), so the accent shows regardless
    # of which theme.py stylesheet is currently applied.
    box.setStyleSheet(f"QMessageBox {{ border-top: 4px solid {accent}; }}")


def show_severity_message(
    parent,
    severity: str,
    title: str,
    text: str,
    buttons: "QMessageBox.StandardButton" = QMessageBox.StandardButton.Ok,
) -> "QMessageBox.StandardButton":
    """Severity-colour-coded replacement for QMessageBox.information/
    .warning/.critical -- same call shape (parent, title, text, buttons),
    same modal exec()-and-return-clicked-standard-button behavior, just
    with the correct accent colour/icon applied for the given severity so
    a blocking error doesn't look the same weight as a routine notice."""
    box = QMessageBox(parent)
    _apply_severity_style(box, severity)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    return box.exec()


def show_info(parent, title: str, text: str) -> None:
    show_severity_message(parent, SEVERITY_INFO, title, text)


def show_warning(parent, title: str, text: str) -> None:
    show_severity_message(parent, SEVERITY_WARNING, title, text)


def show_critical(parent, title: str, text: str) -> None:
    show_severity_message(parent, SEVERITY_CRITICAL, title, text)


# ------------------------------------------------- Choose Library... visual

# The "Library rebuilt" success dialog (ui/main_window._on_rebuild_finished)
# tells the user in words to click iTunes's own "Choose Library..." button
# on relaunch -- the one step this app can't automate. Words alone are easy
# to skim past mid-relaunch, especially with iTunes' own window stealing
# focus at the same moment. This draws a small annotated mockup of that
# iTunes prompt (not a real screenshot -- no image asset to ship/maintain,
# and it can't go stale if iTunes' actual dialog styling changes) with the
# "Choose Library..." button circled, so there's something to *look for*
# on screen, not just read about.
_CHOOSE_LIBRARY_MOCKUP_SIZE = (360, 150)


def choose_library_annotated_pixmap() -> QPixmap:
    """Renders a small annotated mockup of the iTunes "choose a library"
    prompt with its "Choose Library..." button circled, for display
    alongside (not instead of) the existing text instructions. Pure
    QPainter on an in-memory QPixmap -- no bundled image asset, no new
    dependency."""
    width, height = _CHOOSE_LIBRARY_MOCKUP_SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Mock dialog chrome: a plain window body so the button below reads as
    # sitting inside a picker prompt, not floating in isolation.
    dialog_rect = QRectF(4, 4, width - 8, height - 8)
    painter.setPen(QPen(QColor("#8E8E93"), 1.5))
    painter.setBrush(QColor("#2C2C2E"))
    painter.drawRoundedRect(dialog_rect, 8, 8)

    title_font = QFont()
    title_font.setPointSize(9)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#E5E5EA"))
    painter.drawText(
        QRectF(dialog_rect.left() + 16, dialog_rect.top() + 12, dialog_rect.width() - 32, 20),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "iTunes",
    )

    body_font = QFont()
    body_font.setPointSize(8)
    painter.setFont(body_font)
    painter.setPen(QColor("#AEAEB2"))
    painter.drawText(
        QRectF(dialog_rect.left() + 16, dialog_rect.top() + 34, dialog_rect.width() - 32, 34),
        Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
        "iTunes needs a library to work with. Choose an existing "
        "library or create a new one.",
    )

    # The button this whole mockup exists to point at.
    button_rect = QRectF(dialog_rect.left() + 16, dialog_rect.bottom() - 44, 168, 30)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#3A3A3C"))
    painter.drawRoundedRect(button_rect, 5, 5)
    button_font = QFont()
    button_font.setPointSize(8)
    painter.setPen(QColor("#F2F2F7"))
    painter.setFont(button_font)
    painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, "Choose Library\u2026")

    # Callout: a red circle around the button plus a short caption, so the
    # button is the thing that visually jumps out rather than blending
    # into the rest of the mockup dialog.
    callout_color = QColor("#FF453A")
    circle_rect = button_rect.adjusted(-8, -8, 8, 8)
    painter.setPen(QPen(callout_color, 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(circle_rect, 10, 10)

    caption_font = QFont()
    caption_font.setPointSize(8)
    caption_font.setBold(True)
    painter.setFont(caption_font)
    painter.setPen(callout_color)
    painter.drawText(
        QRectF(circle_rect.right() + 10, circle_rect.top() - 4, dialog_rect.right() - circle_rect.right() - 18, circle_rect.height() + 8),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
        "\u2190 Click this when\niTunes reopens",
    )

    painter.end()
    return pixmap


class ChooseLibraryCalloutLabel(QLabel):
    """Displays choose_library_annotated_pixmap() at native size, with a
    caption underneath. A thin wrapper (rather than inlining this in
    main_window) so the same visual can be reused anywhere else this
    instruction appears without duplicating the QPainter code."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPixmap(choose_library_annotated_pixmap())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(0, 4, 0, 4)


# --------------------------------------------------------------- Toasts

# Non-blocking notification banners, shown floating over the bottom-right
# corner of the window and auto-dismissing after a few seconds, instead of
# text that only ever appeared in the status bar (easy to miss entirely,
# and immediately overwritten by the next status message -- see
# MainWindow._set_busy/_load_worker.progress, which both write to the same
# statusBar().showMessage() target a toast might otherwise race with).
# This does not replace the status bar's own use for live progress text
# during a long-running load/apply; it's for one-off, transient
# confirmations ("Backup restored", "5 group(s) will now be skipped") that
# previously only flashed through statusBar().showMessage() and were easy
# to miss if you weren't looking at that corner of the window at the right
# moment. Same severity vocabulary as show_info/show_warning/show_critical
# (SEVERITY_INFO/WARNING/CRITICAL) and the same accent colors, so a toast
# and a dialog for the same kind of event always look related.
TOAST_DEFAULT_DURATION_MS = 4000

# Toast-specific accents (kept separate from _SEVERITY_ACCENTS, which
# pairs a colour with a QMessageBox.Icon rather than a colour alone) plus
# a "success" tone that severity dialogs don't have a use for, since a
# blocking dialog is never shown just to say something worked.
TOAST_SUCCESS = "success"
_TOAST_ACCENTS: dict[str, str] = {
    SEVERITY_INFO: "#0A84FF",
    SEVERITY_WARNING: "#FF9F0A",
    SEVERITY_CRITICAL: "#FF453A",
    TOAST_SUCCESS: "#30D158",
}
_TOAST_ICONS: dict[str, str] = {
    SEVERITY_INFO: "\u2139\ufe0f",
    SEVERITY_WARNING: "\u26a0\ufe0f",
    SEVERITY_CRITICAL: "\u26d4",
    TOAST_SUCCESS: "\u2705",
}


class _ToastWidget(QFrame):
    """One floating notification banner. Fades in, sits for `duration_ms`,
    then fades out and deletes itself -- callers never need to manage its
    lifetime beyond construction. dismissed fires right before the widget
    schedules its own deleteLater(), so a ToastManager can drop its
    reference and reflow whichever toasts remain."""

    dismissed = pyqtSignal(object)  # self

    _FADE_MS = 180

    def __init__(self, message: str, severity: str, duration_ms: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        # Explicit (not just relying on Qt's default) so this toast's own
        # clicks -- its close button, mainly -- are never accidentally
        # affected by whatever attribute its ToastManager parent uses for
        # its own click-through behavior. Qt widget attributes aren't
        # inherited by children, so this was already true in practice;
        # setting it here removes any doubt and guards against a future
        # change to the parent ever silently taking this child with it.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        accent = _TOAST_ACCENTS.get(severity, _TOAST_ACCENTS[SEVERITY_INFO])
        icon = _TOAST_ICONS.get(severity, _TOAST_ICONS[SEVERITY_INFO])
        # Styled directly on the widget (rather than relying on theme.py's
        # app-wide stylesheet) so a toast reads the same in light and dark
        # mode without needing a QSS#toast rule duplicated in both palette
        # blocks -- this is a small, self-contained overlay, not a themed
        # chrome element.
        self.setStyleSheet(
            "QFrame#toast {"
            "  background-color: rgba(40, 40, 43, 235);"
            f"  border-left: 4px solid {accent};"
            "  border-radius: 8px;"
            "}"
            "QFrame#toast QLabel {"
            "  color: #F5F5F7;"
            "  background: transparent;"
            "}"
        )
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(10)

        icon_label = QLabel(icon)
        layout.addWidget(icon_label)

        text_label = QLabel(message)
        text_label.setWordWrap(True)
        layout.addWidget(text_label, stretch=1)

        close_btn = QPushButton("\u2715")
        close_btn.setFlat(True)
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { color: #AEAEB2; border: none; font-size: 11px; }"
            "QPushButton:hover { color: #F5F5F7; }"
        )
        close_btn.setToolTip("Dismiss")
        close_btn.clicked.connect(self._dismiss)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_in.setDuration(self._FADE_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_out.setDuration(self._FADE_MS)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self._on_faded_out)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._dismiss)

        self.adjustSize()
        self._fade_in.start()
        if duration_ms > 0:
            self._auto_close_timer.start(duration_ms)

    def _dismiss(self) -> None:
        if self._auto_close_timer.isActive():
            self._auto_close_timer.stop()
        # Guard against a double-dismiss (e.g. the close button clicked
        # right as the auto-close timer also fires) starting the fade-out
        # animation twice.
        if self._fade_out.state() != QPropertyAnimation.State.Running:
            self._fade_out.start()

    def _on_faded_out(self) -> None:
        self.dismissed.emit(self)
        self.deleteLater()


class ToastManager(QWidget):
    """Owns the stack of currently-visible toasts for one window and keeps
    them positioned in that window's bottom-right corner, newest at the
    bottom, stacking upward as more appear. Transparent, click-through
    except for the toast banners themselves (each toast is a real child
    widget with its own close button, not painted). One instance is
    created per MainWindow and kept as a raised, positioned overlay on
    top of the central widget -- call reposition() from the window's
    resizeEvent so toasts stay anchored to the corner as the window is
    resized."""

    _MARGIN = 16
    _SPACING = 8

    def __init__(self, parent) -> None:
        super().__init__(parent)
        # Bug fix: this was set to False, meaning the full-window overlay
        # (see reposition()'s setGeometry(parent.rect())) was NOT
        # click-through, contradicting this class's own docstring. Since
        # the overlay is raised on top of every other child widget in
        # stacking order and always covers the whole central widget --
        # even while no toast is visible -- every mouse click anywhere in
        # the window (Open Library.xml…, Restore backup…, Clean up
        # duplicates…, Select all, etc.) was being swallowed by this
        # transparent widget instead of reaching the real button
        # underneath it. Window-level drag-and-drop kept working because
        # MainWindow.dropEvent is handled on the top-level window itself,
        # not routed through this child widget's mouse-event handling.
        # True restores the intended click-through behavior; each
        # _ToastWidget child still receives its own mouse events (Qt
        # attributes aren't inherited by children), so toast close
        # buttons/interactions are unaffected.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._toasts: list[_ToastWidget] = []

    def show_toast(
        self,
        message: str,
        severity: str = SEVERITY_INFO,
        duration_ms: int = TOAST_DEFAULT_DURATION_MS,
    ) -> None:
        toast = _ToastWidget(message, severity, duration_ms, self)
        toast.dismissed.connect(self._on_toast_dismissed)
        toast.show()
        self._toasts.append(toast)
        self.raise_()
        self._reflow()

    def _on_toast_dismissed(self, toast: "_ToastWidget") -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reflow()

    def reposition(self) -> None:
        """Call whenever the parent window is resized/shown so this
        overlay (and thus every toast in it) tracks the parent's current
        size instead of a stale one captured at construction time."""
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self._reflow()

    def _reflow(self) -> None:
        """Stacks visible toasts bottom-up in the bottom-right corner of
        this overlay. Each toast keeps whatever size it already computed
        via adjustSize() in its own constructor -- this only positions
        them, it never resizes a toast."""
        y = self.height() - self._MARGIN
        for toast in reversed(self._toasts):
            y -= toast.height()
            x = self.width() - self._MARGIN - toast.width()
            toast.move(max(x, 0), max(y, 0))
            y -= self._SPACING


# ------------------------------------------------------- Growth timeline

class GrowthTimelineChart(QWidget):
    """Small hand-drawn line chart of library track count and duplicate
    count over time, from the points recorded in cache_db's
    health_snapshot_stats table (see MainWindow._record_health_snapshot_stats
    and _on_show_growth_timeline). QPainter on a plain QWidget, matching
    this app's existing no-charting-dependency approach for small,
    well-understood drawing (see choose_library_annotated_pixmap above) --
    the point counts this ever needs to plot (one per health refresh,
    coalesced to at most one per minute per library) stay small enough
    that a general-purpose charting library would be a lot of new surface
    area for very little gained over a direct paintEvent."""

    _MARGIN_LEFT = 48
    _MARGIN_RIGHT = 16
    _MARGIN_TOP = 20
    _MARGIN_BOTTOM = 36

    _TRACK_COLOR = QColor("#0A84FF")
    _DUPLICATE_COLOR = QColor("#FF453A")
    _GRID_COLOR = QColor(127, 127, 127, 60)
    _AXIS_LABEL_COLOR = QColor("#6E6E73")

    def __init__(self, points: list[dict], parent=None, track_color: "QColor | str | None" = None) -> None:
        super().__init__(parent)
        # Sorted defensively (list_health_snapshots already orders by
        # created_at ASC) so this never assumes its caller's ordering.
        self._points = sorted(points, key=lambda p: p["created_at"])
        # track_color lets a caller pass the app's current accent color
        # (see MainWindow._on_show_growth_timeline) so the chart's track-
        # count line matches whichever of the ten accent themes is active,
        # instead of always drawing the original hardcoded blue. Optional
        # and defaults to the original _TRACK_COLOR class attribute, so
        # any other/older call site that doesn't pass it keeps the exact
        # same appearance as before.
        self._track_color = QColor(track_color) if track_color is not None else self._TRACK_COLOR
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        plot_rect = QRectF(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            max(rect.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT, 1),
            max(rect.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM, 1),
        )

        if len(self._points) < 2:
            painter.end()
            return

        max_track = max(p["track_count"] for p in self._points) or 1
        # Track count and duplicate count share one y-axis scaled to the
        # larger series (almost always track_count) -- duplicates are a
        # subset of tracks by definition, so this never clips the
        # duplicate line, it just means that line often sits low in the
        # plot, which is itself an honest picture of the proportion.
        y_max = max_track * 1.1

        times = [p["created_at"] for p in self._points]
        t_min, t_max = times[0], times[-1]
        t_span = (t_max - t_min) or 1.0

        def x_for(t: float) -> float:
            return plot_rect.left() + (t - t_min) / t_span * plot_rect.width()

        def y_for(v: float) -> float:
            return plot_rect.bottom() - (v / y_max) * plot_rect.height()

        # Horizontal gridlines + y-axis labels (4 bands).
        painter.setPen(QPen(self._GRID_COLOR, 1))
        label_font = QFont()
        label_font.setPointSize(8)
        painter.setFont(label_font)
        for i in range(5):
            frac = i / 4
            y = plot_rect.bottom() - frac * plot_rect.height()
            painter.drawLine(QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y))
            painter.setPen(QPen(self._AXIS_LABEL_COLOR))
            value = int(y_max * frac)
            painter.drawText(
                QRectF(0, y - 8, self._MARGIN_LEFT - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(value),
            )
            painter.setPen(QPen(self._GRID_COLOR, 1))

        # X-axis: first and last scanned dates only, to avoid clutter --
        # this is a trend chart, not a precise date picker.
        painter.setPen(QPen(self._AXIS_LABEL_COLOR))
        for t, align in ((t_min, Qt.AlignmentFlag.AlignLeft), (t_max, Qt.AlignmentFlag.AlignRight)):
            when = datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
            x = x_for(t)
            width = 90
            x0 = x if align == Qt.AlignmentFlag.AlignLeft else x - width
            painter.drawText(
                QRectF(x0, plot_rect.bottom() + 6, width, 18),
                align,
                when,
            )

        def draw_series(key: str, color: QColor) -> None:
            path = QPainterPath()
            for i, p in enumerate(self._points):
                x = x_for(p["created_at"])
                y = y_for(p[key])
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(color, 2.2))
            painter.drawPath(path)
            # Small dot at each recorded point so individual scans are
            # still visible on top of the trend line, not just the line
            # itself.
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            for p in self._points:
                x = x_for(p["created_at"])
                y = y_for(p[key])
                painter.drawEllipse(QPointF(x, y), 2.5, 2.5)

        draw_series("track_count", self._track_color)
        draw_series("duplicate_track_count", self._DUPLICATE_COLOR)

        # Legend.
        legend_font = QFont()
        legend_font.setPointSize(9)
        painter.setFont(legend_font)
        legend_y = self._MARGIN_TOP - 6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track_color)
        painter.drawEllipse(QPointF(plot_rect.left() + 4, legend_y), 4, 4)
        painter.setPen(QPen(self._AXIS_LABEL_COLOR))
        painter.drawText(
            QRectF(plot_rect.left() + 12, legend_y - 8, 90, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Total tracks",
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._DUPLICATE_COLOR)
        painter.drawEllipse(QPointF(plot_rect.left() + 110, legend_y), 4, 4)
        painter.setPen(QPen(self._AXIS_LABEL_COLOR))
        painter.drawText(
            QRectF(plot_rect.left() + 118, legend_y - 8, 90, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Duplicates",
        )

        painter.end()


class _TrackPicker(QWidget):
    """One half of MergeTracksDialog: a search box plus a filtered list
    of tracks to pick exactly one from. Two of these are stacked
    side-by-side by MergeTracksDialog so the user can pick each half of
    the pair independently, searching each list separately (e.g. by two
    different spellings of the same artist)."""

    def __init__(self, library, label: str, parent=None) -> None:
        super().__init__(parent)
        self._library = library
        # Sorted once up front (by artist, then title) so the unfiltered
        # list has a stable, predictable order rather than raw dict-
        # insertion/track-id order.
        self._all_tracks = sorted(
            library.tracks.values(),
            key=lambda t: ((t.artist or "").lower(), (t.name or "").lower()),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        heading = QLabel(label)
        heading.setObjectName("subtitle")
        layout.addWidget(heading)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by title or artist\u2026")
        self.search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setToolTip("Select the track for this side of the merge.")
        layout.addWidget(self.list_widget, stretch=1)

        self._refresh_list("")

    def _refresh_list(self, query: str) -> None:
        # Keep whichever track is currently selected (by track_id)
        # highlighted again after the list is rebuilt, so typing a
        # narrower search term doesn't silently lose the current pick if
        # that track still matches.
        previously_selected = self.selected_track()
        query = query.strip().lower()
        self.list_widget.clear()
        for track in self._all_tracks:
            if query:
                haystack = f"{track.artist} {track.name} {track.album}".lower()
                if query not in haystack:
                    continue
            label = f"{track.name or '(no title)'} \u2014 {track.artist or 'Unknown artist'}"
            if track.album:
                label += f" \u00B7 {track.album}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, track.track_id)
            item.setToolTip(
                f"#{track.track_id} \u00B7 {track.bitrate or '?'} kbps"
                + (f" \u00B7 {track.album}" if track.album else "")
            )
            self.list_widget.addItem(item)
            if previously_selected is not None and track.track_id == previously_selected.track_id:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)

    def selected_track(self):
        """Returns the currently selected Track, or None if nothing is
        selected (or the search filtered the previous selection out)."""
        item = self.list_widget.currentItem()
        if item is None or not item.isSelected():
            return None
        track_id = item.data(Qt.ItemDataRole.UserRole)
        return self._library.tracks.get(track_id)


class MergeTracksDialog(QDialog):
    """"Merge tracks..." picker: lets the user choose any two tracks in
    the currently loaded library to manually merge, for the case
    automatic exact/fuzzy duplicate detection never grouped them
    together at all (see core/duplicate_detector.make_manual_merge_group
    and MainWindow._on_merge_tracks_clicked). Each side is searched and
    picked independently via two side-by-side _TrackPicker widgets; OK
    is only enabled once two *different* tracks are selected, so the
    same track can't accidentally be "merged" with itself."""

    def __init__(self, library, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("\U0001F517 Merge tracks\u2026")
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Pick two tracks to merge even though the automatic scan "
            "didn't group them together \u2014 useful when two copies of "
            "the same song are tagged too differently for matching to "
            "catch (a translated title, a very different artist "
            "spelling, and so on). You'll still be able to review and "
            "undo this like any other group before anything is applied."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        pickers_row = QHBoxLayout()
        self._picker_a = _TrackPicker(library, "First track:")
        self._picker_b = _TrackPicker(library, "Second track:")
        pickers_row.addWidget(self._picker_a, stretch=1)
        pickers_row.addWidget(self._picker_b, stretch=1)
        layout.addLayout(pickers_row, stretch=1)

        self._warning_label = QLabel("")
        self._warning_label.setObjectName("subtitle")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self._buttons)

        self._picker_a.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self._picker_b.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        track_a = self._picker_a.selected_track()
        track_b = self._picker_b.selected_track()
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if track_a is None or track_b is None:
            ok_button.setEnabled(False)
            self._warning_label.setText("")
            return
        if track_a.track_id == track_b.track_id:
            ok_button.setEnabled(False)
            self._warning_label.setText(
                "\u26A0\uFE0F Pick two different tracks \u2014 the same track is "
                "selected on both sides."
            )
            return
        ok_button.setEnabled(True)
        self._warning_label.setText("")

    def selected_tracks(self) -> list:
        """Returns the two selected Track objects in picker order (first,
        second). Only meaningful after the dialog is accepted -- callers
        should check exec() returned Accepted first."""
        tracks = [self._picker_a.selected_track(), self._picker_b.selected_track()]
        return [t for t in tracks if t is not None]
