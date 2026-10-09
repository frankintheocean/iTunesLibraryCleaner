"""
Consolidation engine.

Given duplicate groups, produces a ConsolidationPlan (pure data, no
mutation) that can be previewed (dry-run) and then applied to a Library.

Guarantees:
  - Exactly one canonical Track ID survives per duplicate group.
  - Every playlist that referenced ANY track in the group ends up
    referencing the canonical track instead (deduplicated within the
    playlist so it isn't added twice if the playlist somehow had both).
  - Play Count = sum across duplicates (total listening history preserved).
  - Rating = highest rating across duplicates (assume the higher rating
    reflects the user's real opinion, never silently discard a rating).
  - Date Added = earliest across duplicates (oldest library membership wins).
  - Artwork/other metadata fields: canonical track's own fields are kept;
    any field that is empty on the canonical track but populated on a
    duplicate is backfilled from the duplicate (never lose metadata that
    only exists on the copy being removed).
  - Removed tracks are only ever dropped from the Tracks dict during
    apply(); nothing is touched until the plan is explicitly applied.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .duplicate_detector import (
    DuplicateGroup,
    TIER_DURATION_MISMATCH,
    TIER_EXACT,
    TIER_NEEDS_REVIEW,
    find_incomplete_album_overlap_track_ids,
)

# v2.0: tiers that should never be pre-selected/auto-merged without a human
# looking at the group first -- fuzzy "possible duplicate" matches, and
# same-artist/same-title groups whose durations diverge too much to be
# confidently auto-grouped (see duplicate_detector.Tier.DURATION_MISMATCH).
# Kept as one tuple so MergeAction.needs_review and
# ConsolidationPlan.exact_actions/review_actions can't drift out of sync
# with each other about which tiers count as "needs a human look".
_REVIEW_TIERS = (TIER_NEEDS_REVIEW, TIER_DURATION_MISMATCH)
from .itunes_xml import Library, Playlist, Track

# Fields we actively merge with special rules; everything else is simple
# "fill if empty" backfill from duplicates onto the canonical track.
_SUMMED_FIELDS = ("Play Count",)
_MAX_FIELDS = ("Rating",)
_MIN_DATE_FIELDS = ("Date Added",)
# Identity fields belong to the specific track entry they're on and must
# never be copied from a removed duplicate onto the surviving canonical
# track, even if the canonical's own value happens to be empty/falsy.
# "Persistent ID" in particular is Apple's own stable per-track identity,
# used by iTunes/Music.app itself (e.g. iCloud Music Library matching) --
# backfilling a removed duplicate's Persistent ID onto the track that
# actually survives would make the surviving track wear an identity that
# was never really its own. "Track ID" is included for the same reason,
# even though it is effectively never empty on a loaded track.
_IDENTITY_FIELDS = ("Track ID", "Persistent ID")
_NEVER_BACKFILLED = _SUMMED_FIELDS + _MAX_FIELDS + _MIN_DATE_FIELDS + _IDENTITY_FIELDS

# Fields commonly used as smart-playlist match criteria in iTunes/Music.app
# (Genre is X, Rating is greater than Y, Play Count is Z, Date Added is in
# the last N days, etc.). Library.xml's "Smart Criteria" key is an opaque,
# undocumented binary-plist blob -- Apple's own internal encoding for the
# rule tree -- so this app cannot read or evaluate the *actual* rules of
# any given smart playlist. What it CAN do, safely, is notice when a merge
# is about to change one of the fields smart playlists are commonly built
# on, for a track that belongs to at least one smart playlist, and flag
# that as worth a manual check -- without claiming to know whether that
# specific playlist's rules actually reference the changed field.
SMART_PLAYLIST_SENSITIVE_FIELDS = (
    "Genre",
    "Rating",
    "Play Count",
    "Play Date UTC",
    "Date Added",
    "Year",
    "Album",
    "Artist",
    "Album Artist",
    "Bit Rate",
    "Comments",
    "Kind",
    "Loved",
    "Disliked",
)


@dataclass
class MergeAction:
    group_key: tuple[str, str]
    canonical_id: int
    removed_ids: list[int]
    canonical_name: str
    canonical_artist: str
    playlists_updated: list[str] = field(default_factory=list)
    merged_play_count: int = 0
    merged_rating: int = 0
    backfilled_fields: list[str] = field(default_factory=list)
    # Confidence tier from the DuplicateGroup this action was built from:
    # "exact" or "high" are pre-checked/actionable by default; "review"
    # groups are still built (so the UI can show them) but never
    # pre-selected, since a low-confidence fuzzy match should never be
    # merged without a human looking at it first.
    tier: str = TIER_EXACT
    similarity: float = 1.0
    # All tracks in the source group (canonical + removed), kept for the
    # UI's expandable row detail (per-track bitrate/album/playlists) and
    # for re-deriving the plan if the user changes the canonical pick.
    group_tracks: list[Track] = field(default_factory=list)
    canonical_reason: str = ""
    # Names of smart playlists that reference a track in this group AND
    # whose membership *could* be affected by this merge, because the
    # merge changes a field (see SMART_PLAYLIST_SENSITIVE_FIELDS) commonly
    # used in smart-playlist criteria. This is a heads-up, not a guarantee
    # -- see build_plan/_smart_playlist_merge_warnings for exactly what it
    # does and doesn't know. Empty when no smart playlist references any
    # track in the group, or when none of the changed fields are on the
    # sensitive list.
    smart_playlist_warnings: list[str] = field(default_factory=list)
    # The exact DuplicateGroup object this action was built from (identity,
    # not a copy). Bug fix (v1.2.1): the UI used to look up the "matching"
    # group by row index into a separately-maintained list, which drifts
    # out of sync with plan.actions as soon as build_plan() drops a group
    # (e.g. one marked not-duplicate) -- silently repointing manual-review
    # edits (canonical override / not-duplicate) onto the wrong song.
    # Carrying the real object here means the UI never needs to guess.
    source_group: "DuplicateGroup | None" = None
    # v2.1: True when at least one of this group's duplicate (non-
    # canonical) tracks belongs to an album copy that a complete copy of
    # the same album elsewhere in the library makes redundant -- see
    # core/duplicate_detector.find_incomplete_album_overlap_track_ids.
    # Purely a UI pre-selection hint (see ui/main_window._populate_table_rows):
    # never changes what removed_ids/canonical_id are, and never bypasses
    # the normal Apply confirmation.
    incomplete_album_overlap: bool = False

    @property
    def needs_review(self) -> bool:
        return self.tier in _REVIEW_TIERS


@dataclass
class ConsolidationPlan:
    actions: list[MergeAction]

    @property
    def total_duplicates_removed(self) -> int:
        return sum(len(a.removed_ids) for a in self.actions)

    def summary_lines(self) -> list[str]:
        lines = []
        for a in self.actions:
            line = (
                f"{a.canonical_artist} — {a.canonical_name}: "
                f"keep #{a.canonical_id}, remove {a.removed_ids} "
                f"(play count -> {a.merged_play_count}, rating -> {a.merged_rating}, "
                f"{len(a.playlists_updated)} playlist(s) repointed)"
            )
            if a.smart_playlist_warnings:
                line += (
                    f" -- may affect smart playlist(s): "
                    f"{', '.join(a.smart_playlist_warnings)}"
                )
            lines.append(line)
        return lines

    @property
    def smart_playlist_warning_count(self) -> int:
        """Number of actions with at least one smart-playlist compatibility
        warning -- used by the UI to decide whether to surface anything at
        all (most plans will have zero)."""
        return sum(1 for a in self.actions if a.smart_playlist_warnings)

    @property
    def exact_actions(self) -> list["MergeAction"]:
        return [a for a in self.actions if a.tier not in _REVIEW_TIERS]

    @property
    def review_actions(self) -> list["MergeAction"]:
        """Possible-duplicate matches -- fuzzy candidates, and (v2.0)
        same-artist/same-title duration-mismatch groups -- that should be
        shown to the user but never pre-selected for merge."""
        return [a for a in self.actions if a.tier in _REVIEW_TIERS]


def _build_track_to_playlists_index(library: Library) -> dict[int, list[Playlist]]:
    """Maps every track id to the list of Playlist objects that reference
    it, built once in a single pass over all playlists.

    Perf fix (v1.5): build_plan() used to re-scan every playlist's full
    track list (calling Playlist.track_ids(), which rebuilds a fresh list
    from the raw "Playlist Items" every time it's called) once PER
    duplicate group, for both the "which playlists does this merge touch"
    check and (separately, again) inside _smart_playlist_merge_warnings.
    That's O(groups * playlists * items-per-playlist) -- on a large
    library with thousands of duplicate groups this is what made the
    "Building consolidation plan..." step (92%) hang, and, since
    ui/main_window.py re-runs build_plan() synchronously on the UI thread
    right after load to apply permanent exclusions, made the window
    appear frozen at 100% right after too, delaying the point where the
    Delete/Apply button gets re-enabled.

    Building this index costs one pass over all playlists
    (O(playlists * items)) up front; every group's lookup afterward is
    then just a dict get + list extend, independent of playlist count or
    size. Results are identical to the old per-group scan -- this only
    changes how the same membership facts are computed, not what they are.
    """
    index: dict[int, list[Playlist]] = defaultdict(list)
    for playlist in library.playlists:
        for tid in playlist.track_ids():
            index[tid].append(playlist)
    return index


def build_plan(library: Library, groups: list[DuplicateGroup]) -> ConsolidationPlan:
    """Pure/read-only: computes what WOULD happen. Does not touch library."""
    actions: list[MergeAction] = []
    track_to_playlists = _build_track_to_playlists_index(library)
    # v2.1: computed once up front over every group (not per-action inside
    # the loop below), same reasoning as _build_track_to_playlists_index
    # above -- a single pass over the whole plan instead of O(actions)
    # separate scans. Best-effort: a failure here should never block
    # building the rest of the plan, since this only affects which rows
    # get pre-checked, not what the plan itself contains.
    try:
        incomplete_overlap_ids = find_incomplete_album_overlap_track_ids(library, groups)
    except Exception:
        incomplete_overlap_ids = set()
    for group in groups:
        if group.marked_not_duplicate:
            # User explicitly reviewed this group and confirmed it's not a
            # real duplicate; never plan a merge for it.
            continue
        canonical = group.canonical()
        duplicates = group.duplicates()
        if not duplicates:
            continue

        merged_play_count = canonical.play_count + sum(d.play_count for d in duplicates)
        merged_rating = max([canonical.rating] + [d.rating for d in duplicates])

        backfilled = []
        for d in duplicates:
            for k, v in d.raw.items():
                if k in _NEVER_BACKFILLED:
                    continue
                if not canonical.raw.get(k) and v:
                    backfilled.append(k)

        group_track_ids = (canonical.track_id, *[d.track_id for d in duplicates])
        referencing_playlists: list[Playlist] = []
        seen_playlist_ids: set[int] = set()
        for tid in group_track_ids:
            for p in track_to_playlists.get(tid, ()):
                if id(p) not in seen_playlist_ids:
                    seen_playlist_ids.add(id(p))
                    referencing_playlists.append(p)
        affected_playlists = [p.name for p in referencing_playlists]

        smart_playlist_warnings = _smart_playlist_merge_warnings(
            referencing_playlists=referencing_playlists,
            canonical=canonical,
            duplicates=duplicates,
            merged_play_count=merged_play_count,
            merged_rating=merged_rating,
            backfilled_fields=backfilled,
        )

        actions.append(
            MergeAction(
                group_key=group.key,
                canonical_id=canonical.track_id,
                removed_ids=[d.track_id for d in duplicates],
                canonical_name=canonical.name,
                canonical_artist=canonical.artist,
                playlists_updated=affected_playlists,
                merged_play_count=merged_play_count,
                merged_rating=merged_rating,
                backfilled_fields=sorted(set(backfilled)),
                tier=group.tier,
                similarity=group.similarity,
                group_tracks=list(group.tracks),
                canonical_reason=group.canonical_reason(),
                smart_playlist_warnings=smart_playlist_warnings,
                source_group=group,
                incomplete_album_overlap=any(
                    d.track_id in incomplete_overlap_ids for d in duplicates
                ),
            )
        )
    return ConsolidationPlan(actions=actions)


def _smart_playlist_merge_warnings(
    referencing_playlists: list[Playlist],
    canonical: Track,
    duplicates: list[Track],
    merged_play_count: int,
    merged_rating: int,
    backfilled_fields: list[str],
) -> list[str]:
    """Names of smart playlists that reference any track in this group and
    that *could* have their membership affected by this merge -- see
    SMART_PLAYLIST_SENSITIVE_FIELDS for exactly what "could" means here.

    This deliberately does not try to read or evaluate a playlist's actual
    "Smart Criteria" rules (an opaque, undocumented binary-plist blob) --
    it only checks (a) does a merge-changed field intersect the list of
    fields smart playlists commonly key on, and (b) does a smart playlist
    actually reference one of the tracks being merged. Both being true is
    a reason to double-check, not proof the playlist's membership will
    actually change.

    Perf fix (v1.5): takes the group's already-computed `referencing_playlists`
    (see build_plan/_build_track_to_playlists_index) instead of re-scanning
    every playlist in the library and re-deriving its track ids again here --
    same playlists this group's plain "affected playlists" list was built
    from, just filtered down to the smart ones.
    """
    referencing_smart_playlists = [p for p in referencing_playlists if p.is_smart]
    if not referencing_smart_playlists:
        return []

    changed_fields: set[str] = set(backfilled_fields)
    if merged_play_count != canonical.play_count:
        changed_fields.add("Play Count")
    if merged_rating and merged_rating != canonical.rating:
        changed_fields.add("Rating")
    # Date Added always changes to the earliest across the group when any
    # duplicate's date differs from the canonical's.
    other_dates = [d.date_added for d in duplicates if d.date_added]
    if other_dates and canonical.date_added and min(other_dates) < canonical.date_added:
        changed_fields.add("Date Added")
    elif other_dates and not canonical.date_added:
        changed_fields.add("Date Added")

    if not changed_fields.intersection(SMART_PLAYLIST_SENSITIVE_FIELDS):
        return []

    return sorted(p.name for p in referencing_smart_playlists)


def apply_plan(library: Library, plan: ConsolidationPlan) -> None:
    """Mutates the given Library in place according to the plan.
    Call this only after the user has confirmed the dry-run preview.
    """
    # Map every removed id -> canonical id, across ALL actions, so playlist
    # rewriting is a single pass regardless of how many groups a playlist touches.
    id_redirect: dict[int, int] = {}
    for action in plan.actions:
        for removed_id in action.removed_ids:
            id_redirect[removed_id] = action.canonical_id

    # 1. Merge metadata/play count/rating/date onto canonical tracks.
    for action in plan.actions:
        canonical = library.tracks.get(action.canonical_id)
        if canonical is None:
            continue
        removed_tracks = [library.tracks[rid] for rid in action.removed_ids if rid in library.tracks]

        canonical.raw["Play Count"] = action.merged_play_count
        if action.merged_rating:
            canonical.raw["Rating"] = action.merged_rating

        dates = [canonical.date_added] + [t.date_added for t in removed_tracks]
        dates = [d for d in dates if d]
        if dates:
            canonical.raw["Date Added"] = min(dates)

        for t in removed_tracks:
            for k, v in t.raw.items():
                if k in _NEVER_BACKFILLED:
                    continue
                if not canonical.raw.get(k) and v:
                    canonical.raw[k] = v

    # 2. Repoint every playlist's track references, de-duplicating so a
    #    playlist that (rarely) had two duplicate copies doesn't end up
    #    with the canonical track listed twice.
    for playlist in library.playlists:
        original_ids = playlist.track_ids()
        if not original_ids:
            continue
        new_ids: list[int] = []
        seen: set[int] = set()
        changed = False
        for tid in original_ids:
            resolved = id_redirect.get(tid, tid)
            if resolved != tid:
                changed = True
            if resolved not in seen:
                new_ids.append(resolved)
                seen.add(resolved)
            else:
                changed = True  # dropped a now-duplicate reference
        if changed:
            playlist.set_track_ids(new_ids)

    # 3. Remove the duplicate Track entries themselves. Canonical tracks
    #    (and any track not part of any action) are left untouched.
    for action in plan.actions:
        for removed_id in action.removed_ids:
            library.tracks.pop(removed_id, None)
