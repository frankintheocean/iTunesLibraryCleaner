"""
Library Health tab.

Dashboard summarizing library-wide issues (duplicates, missing artwork/
metadata, inconsistent tags, low-quality/corrupt files, and the storage
that consolidating current duplicates would recover), built from a
HealthReport (core.library_health.analyze_library()). The stat-card grid
and breakdown sections below are purely informational and never mutate
the library themselves.

Two categories -- missing cover art and missing/broken file locations --
additionally get a short actionable list with a per-track fix button
("Fix missing artwork\u2026" / "Locate missing file\u2026"), instead of
only ever showing a count with nothing to do about it from here. Clicking
one of these buttons does not itself change anything; HealthPanel only
emits a signal (fix_artwork_requested / locate_file_requested) carrying
the track id, and MainWindow (which owns the loaded Library, the file
dialogs, and the save/write-back flow) does the actual work -- keeping
this panel's own responsibility limited to rendering the report and
routing button clicks, the same separation core.health_actions already
assumes.

The missing/broken files section also gets one section-level button,
"Find missing files in folder\u2026" (find_missing_in_folder_requested),
alongside its per-track "Locate missing file\u2026" rows -- for
relocating many/all of them at once by pointing at one root folder
(e.g. after moving a whole music folder to a new subfolder layout)
instead of browsing to each file individually. Same routing: this panel
only emits the signal, MainWindow does the folder picker and the actual
search/relink (core.health_actions.find_missing_files_in_root).
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.library_health import HealthReport


class _StatCard(QFrame):
    def __init__(self, title: str, value: str, tone: str = "neutral", parent=None):
        super().__init__(parent)
        self.setObjectName("healthCard")
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        value_label = QLabel(value)
        value_label.setObjectName("healthCardValue")
        title_label = QLabel(title)
        title_label.setObjectName("healthCardTitle")
        title_label.setWordWrap(True)

        layout.addWidget(value_label)
        layout.addWidget(title_label)


class HealthPanel(QWidget):
    """Scrollable grid of stat cards, one per health category, plus a
    short "what to do about it" note. Rebuilt each time set_report() is
    called (cheap — a handful of labels), so no incremental-update logic
    is needed."""

    # Emitted when the user clicks "Fix missing artwork…" / "Locate
    # missing file…" next to a specific track in one of the actionable
    # lists below. Carries only the track id -- MainWindow looks the
    # Track up on its own Library and does the actual work (see
    # core.health_actions), then calls set_report() again with a
    # refreshed HealthReport so the list reflects the result.
    fix_artwork_requested = pyqtSignal(int)  # track_id
    locate_file_requested = pyqtSignal(int)  # track_id

    # Emitted when the user clicks "Find missing files in folder…" above
    # the missing/broken-files list. Carries no data -- unlike the two
    # signals above, this isn't about one specific track; MainWindow asks
    # for a root folder and searches every currently missing/broken track
    # under it in one pass (see core.health_actions.find_missing_files_in_root).
    find_missing_in_folder_requested = pyqtSignal()

    # Emitted when the user clicks "View growth timeline…" in this
    # panel's header. Carries no data -- MainWindow owns the CacheDB
    # history read and shows widgets.GrowthTimelineChart in a dialog
    # (see MainWindow._on_show_growth_timeline), same routing pattern as
    # the two signals above.
    growth_timeline_requested = pyqtSignal()

    # Cap on how many per-track rows each actionable list renders, so a
    # library with thousands of missing-artwork/broken-location tracks
    # doesn't build thousands of QWidgets into a QVBoxLayout at once (the
    # same concern _StatCard's parent grid doesn't have, since that's
    # always exactly 8 cards). The stat card above each list already
    # shows the true total; the list itself is "here's where to start",
    # not an exhaustive one-row-per-track browser.
    _MAX_ACTIONABLE_ROWS = 25

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self._content = QWidget()
        scroll.setWidget(self._content)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(16)

        self._empty_label = QLabel("📊 Open a library to see its health report.")
        self._empty_label.setObjectName("subtitle")
        self._layout.addWidget(self._empty_label)
        self._layout.addStretch(1)

        # Set alongside each set_report() call so the actionable rows can
        # look up a track's display name/artist -- HealthReport itself
        # only carries track ids (see library_health.py), not full Track
        # objects, so this panel needs the Library too to show anything
        # more useful than a bare id.
        self._library = None

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_actionable_list(
        self,
        title: str,
        track_ids: list[int],
        button_text: str,
        signal: pyqtSignal,
        empty_note: str,
        section_button: Optional[tuple[str, pyqtSignal]] = None,
    ) -> QFrame:
        """One "<title>" section: a short list of affected tracks, each
        with a fix button that re-emits `signal` carrying that track's
        id. Shared by the missing-artwork and missing/broken-location
        sections below since both are the same shape (a list of track
        ids from HealthReport, one action per row).

        `section_button`, if given, is an optional (button_text, signal)
        pair rendered once in the heading row (not per-track) that
        re-emits `signal` with no arguments when clicked -- for an action
        that applies to the whole list at once rather than one track,
        e.g. "Find missing files in folder…" alongside the per-track
        "Locate missing file…" rows. Only shown when there's at least one
        track in the list, since there's nothing to search for otherwise."""
        section = QFrame()
        section.setObjectName("card")
        layout = QVBoxLayout(section)

        heading_row = QWidget()
        heading_row_layout = QHBoxLayout(heading_row)
        heading_row_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title)
        heading.setObjectName("sectionHeading")
        heading_row_layout.addWidget(heading, stretch=1)
        if section_button is not None and track_ids:
            section_button_text, section_signal = section_button
            section_btn = QPushButton(section_button_text)
            section_btn.clicked.connect(section_signal.emit)
            heading_row_layout.addWidget(section_btn)
        layout.addWidget(heading_row)

        if not track_ids:
            none_label = QLabel(empty_note)
            none_label.setObjectName("subtitle")
            layout.addWidget(none_label)
            return section

        library = self._library
        shown = track_ids[: self._MAX_ACTIONABLE_ROWS]
        for track_id in shown:
            track = library.tracks.get(track_id) if library else None
            if track is not None:
                name = track.name or "(untitled)"
                artist = track.artist or "Unknown artist"
                row_text = f"{artist} — {name}"
            else:
                row_text = f"Track {track_id}"

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)

            row_label = QLabel(row_text)
            row_label.setObjectName("subtitle")
            row_label.setWordWrap(True)
            row_layout.addWidget(row_label, stretch=1)

            fix_btn = QPushButton(button_text)
            fix_btn.setProperty("track_id", track_id)
            fix_btn.clicked.connect(
                lambda _checked=False, tid=track_id: signal.emit(tid)
            )
            row_layout.addWidget(fix_btn)

            layout.addWidget(row)

        if len(track_ids) > len(shown):
            more_label = QLabel(
                f"...and {len(track_ids) - len(shown)} more. Showing the "
                "first {0} — the count above reflects all of them.".format(
                    len(shown)
                )
            )
            more_label.setObjectName("subtitle")
            layout.addWidget(more_label)

        return section

    def set_report(self, report: HealthReport, library=None) -> None:
        self._library = library
        self.clear()

        header_row = QWidget()
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("\U0001FA7A Library Health")
        header.setObjectName("pageTitle")
        header_row_layout.addWidget(header, stretch=1)
        timeline_btn = QPushButton("\U0001F4C8 View growth timeline\u2026")
        timeline_btn.setToolTip(
            "See how your library's track count and duplicate count have "
            "changed each time this app has scanned it."
        )
        timeline_btn.clicked.connect(self.growth_timeline_requested.emit)
        header_row_layout.addWidget(timeline_btn)
        self._layout.addWidget(header_row)

        subtitle = QLabel(
            f"Scanned {report.total_tracks} song(s) and found "
            f"{report.issues_total} thing(s) worth a look below."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        self._layout.addWidget(subtitle)

        grid_frame = QFrame()
        grid = QGridLayout(grid_frame)
        grid.setSpacing(12)

        cards = [
            (
                "Duplicate songs",
                str(report.duplicate_track_count),
                "warning" if report.duplicate_track_count else "good",
            ),
            (
                "Missing cover art",
                str(len(report.missing_artwork)),
                "warning" if report.missing_artwork else "good",
            ),
            (
                "Missing or incomplete info",
                str(len(report.inconsistent_tags)),
                "warning" if report.inconsistent_tags else "good",
            ),
            (
                "Low-quality files",
                str(len(report.low_quality)),
                "danger" if report.low_quality else "good",
            ),
            (
                "Missing or broken files",
                str(len(report.missing_or_broken_location)),
                "danger" if report.missing_or_broken_location else "good",
            ),
            (
                "Unknown quality",
                str(len(report.unknown_quality)),
                "neutral",
            ),
            (
                "Space you could save",
                report.estimated_storage_savings_human(),
                "good" if report.estimated_duplicate_storage_bytes else "neutral",
            ),
            (
                "Albums added more than once",
                str(len(report.album_duplicate_groups)),
                "warning" if report.album_duplicate_groups else "good",
            ),
        ]
        for i, (title, value, tone) in enumerate(cards):
            grid.addWidget(_StatCard(title, value, tone), i // 3, i % 3)

        self._layout.addWidget(grid_frame)

        # Actionable lists: turn the "Missing cover art" and "Missing or
        # broken files" counts above into something to actually click,
        # not just read. Each row's fix button re-emits this panel's
        # fix_artwork_requested/locate_file_requested signal with that
        # track's id -- MainWindow does the real work (see
        # core.health_actions) and calls set_report() again afterward.
        self._layout.addWidget(
            self._build_actionable_list(
                "Missing or broken files — locate them",
                report.missing_or_broken_location,
                "\U0001F4C1 Locate missing file\u2026",
                self.locate_file_requested,
                "No missing or broken files found. \U0001F389",
                section_button=(
                    "\U0001F4C2 Find missing files in folder\u2026",
                    self.find_missing_in_folder_requested,
                ),
            )
        )
        self._layout.addWidget(
            self._build_actionable_list(
                "Missing cover art — fix them",
                report.missing_artwork,
                "\U0001F5BC\uFE0F Fix missing artwork\u2026",
                self.fix_artwork_requested,
                "Every song has cover art. \U0001F389",
            )
        )

        # Per-field missing-metadata breakdown, since "inconsistent tags"
        # alone doesn't say which fields are the problem.
        if any(report.missing_metadata.values()):
            breakdown_title = QLabel("What's missing, by type")
            breakdown_title.setObjectName("sectionHeading")
            self._layout.addWidget(breakdown_title)

            breakdown_frame = QFrame()
            breakdown_frame.setObjectName("card")
            breakdown_layout = QVBoxLayout(breakdown_frame)
            for field_name, ids in report.missing_metadata.items():
                if not ids:
                    continue
                row = QLabel(f"{field_name}: missing on {len(ids)} song(s)")
                row.setObjectName("subtitle")
                breakdown_layout.addWidget(row)
            self._layout.addWidget(breakdown_frame)

        # Album-level duplicate breakdown: which whole albums showed up at
        # more than one bitrate, and what bitrates. Purely informational
        # (see core/library_health.HealthReport.album_duplicate_groups) --
        # the individual duplicate tracks underneath are already covered
        # by the "Duplicate tracks" card above and reviewed/merged the
        # normal way from the Duplicates tab.
        if report.album_duplicate_groups:
            album_dup_title = QLabel("Albums that look like they were added twice")
            album_dup_title.setObjectName("sectionHeading")
            self._layout.addWidget(album_dup_title)

            album_dup_frame = QFrame()
            album_dup_frame.setObjectName("card")
            album_dup_layout = QVBoxLayout(album_dup_frame)
            for group in report.album_duplicate_groups[:20]:
                bitrate_text = ", ".join(
                    f"{b} kbps" if b else "unknown quality" for b in group.bitrates
                )
                row = QLabel(
                    f"{group.album_artist or 'Unknown artist'} — {group.album}: "
                    f"found at {bitrate_text} "
                    f"({len(group.duplicated_track_titles)} shared song(s), "
                    f"{group.duplicate_track_count} could be removed)"
                )
                row.setObjectName("subtitle")
                row.setWordWrap(True)
                album_dup_layout.addWidget(row)
            if len(report.album_duplicate_groups) > 20:
                more_row = QLabel(
                    f"...and {len(report.album_duplicate_groups) - 20} more."
                )
                more_row.setObjectName("subtitle")
                album_dup_layout.addWidget(more_row)
            self._layout.addWidget(album_dup_frame)

        note = QLabel(
            "You can review and clean up duplicates from the Duplicates "
            "tab, and fix missing artwork or relink missing files directly "
            "above. Everything else here is just for your information — "
            "this app doesn't edit song info or re-encode audio files."
        )
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        self._layout.addWidget(note)

        self._layout.addStretch(1)
