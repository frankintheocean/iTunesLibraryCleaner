"""
Metadata-based duplicate detection.

v1 scope (per product decision): duplicates are identified by normalized
Artist + Title + Duration proximity. No audio fingerprinting, no file
access required — this only reads the fields already present in the XML
library, so it works even when Location paths are unavailable/offline.

v1.1: exact normalized-key matches are still grouped and auto-planned as
before (no behavior change, existing tests keep passing). On top of that,
near-miss groups (e.g. a typo'd artist or title) are now surfaced as
*fuzzy* candidates with a similarity score and a confidence tier, so
likely-but-uncertain duplicates are shown for manual review instead of
being silently missed OR silently auto-merged.

v1.3.15: the fuzzy thresholds below are still the defaults used
everywhere no explicit value is passed (every existing call site/test is
therefore unaffected), but find_fuzzy_candidate_groups()/
find_all_candidate_groups() now also accept optional high/low overrides
so the Settings dialog can expose them to the user (see
ui/settings_dialog.py's "Duplicate Detection" tab and
data/cache_db.py's FUZZY_*_THRESHOLD_KEY-keyed settings). Also new: the
fuzzy pass's per-bucket comparison batches can optionally run in a
process pool instead of sequentially, for large libraries where the
pairwise comparison work is the dominant cost (see
find_fuzzy_candidate_groups' `parallel`/`max_workers` args and
_compare_batch below) -- single-threaded behavior/results are unchanged
when parallel execution isn't requested or isn't available.

v1.7.6: the fuzzy pass's comparison budget is now time-boxed
(FUZZY_SCAN_TIME_BUDGET_SECONDS) instead of splitting one fixed total
comparison count (FUZZY_MAX_COMPARISONS) evenly across every bucketed
batch. The old per-batch split meant a library with many small buckets
got an arbitrarily strict -- and invisible -- per-batch allowance, so
recall silently degraded in a way that varied with how titles happened
to cluster, while wall-clock time still varied with per-comparison cost.
Bounding by elapsed time instead gives the same "never hangs" guarantee
but ties the ceiling to what the user actually experiences (a bounded
wait), and find_fuzzy_candidate_groups()'s new `progress_callback` arg
lets a caller (see workers.py) surface a live "still scanning, N% of
scan time budget used" indicator instead of the scan disappearing into
one silent blocking call. FUZZY_MAX_COMPARISONS remains as a
defense-in-depth backstop (see _compare_batch/find_fuzzy_candidate_groups
below), not the primary control. Every existing call site/test that
doesn't pass the new args keeps the same default budget and result
shape as before.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed as _as_completed
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Callable

from .itunes_xml import Library, Track

# Tracks within this many milliseconds are considered the "same length"
# for matching purposes. Encodes/tags can shave a second or two off.
DURATION_TOLERANCE_MS = 3000

# Fuzzy-matching thresholds (0.0-1.0 similarity, combined artist+title score).
# Below LOW threshold: not considered a candidate at all (too likely unrelated).
# Between LOW and HIGH: "possible duplicate" — needs manual review before merge.
# At/above HIGH: "high confidence" — still shown for review, but pre-checked.
FUZZY_HIGH_CONFIDENCE = 0.92
FUZZY_LOW_CONFIDENCE = 0.80

# Hard bounds for user-configurable overrides of the thresholds above (see
# Settings > Duplicate Detection). Kept well inside (0, 1) -- 0 or 1 exactly
# would turn the fuzzy pass into "match everything"/"match nothing", which
# isn't a useful configuration and isn't worth special-casing elsewhere.
FUZZY_THRESHOLD_MIN = 0.50
FUZZY_THRESHOLD_MAX = 0.99


def clamp_threshold(value: float, default: float) -> float:
    """Clamps a user-supplied threshold into the valid range, falling back
    to `default` for anything not interpretable as a number. Shared by the
    Settings dialog (validating what the user typed/dragged) and the
    detector itself (defending against a corrupt/out-of-range stored
    setting) so the two never disagree about what counts as valid."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    return min(max(value, FUZZY_THRESHOLD_MIN), FUZZY_THRESHOLD_MAX)

# The fuzzy pass compares remaining tracks pairwise since it needs to catch
# near-miss typos that no exact key would surface — a proper fingerprint/
# index-based fuzzy matcher is future work, not something to add as a new
# dependency here. To keep this bounded at 100k+ scale regardless of how
# titles happen to cluster, candidates are bucketed by normalized title's
# first character AND any bucket larger than FUZZY_MAX_BUCKET_SIZE is
# further split into fixed-size chunks compared only within themselves.
# This trades a small amount of recall (a match whose two tracks land in
# different chunks of an oversized bucket is missed) for a hard, predictable
# runtime ceiling instead of a worst-case O(n^2) hang.
FUZZY_BUCKET_BY_FIRST_CHAR = True
FUZZY_MAX_BUCKET_SIZE = 40

# Adaptive, time-boxed ceiling on how long the fuzzy pass is allowed to run
# (see module docstring, v1.7.6). Chosen generously enough that typical/
# mid-size libraries finish the whole fuzzy pass well before hitting it --
# this is a worst-case ceiling for very large or adversarially-clustered
# libraries, not a target duration. `find_fuzzy_candidate_groups`'s
# `time_budget_seconds` arg overrides this per-call (e.g. for tests that
# want a tighter deadline) without touching the module default.
FUZZY_SCAN_TIME_BUDGET_SECONDS = 30.0

# Defense-in-depth backstop on the total number of pairwise comparisons
# performed across the entire fuzzy pass, independent of elapsed time.
# Each comparison is cheap (a couple of SequenceMatcher.ratio() calls on
# short strings), so hitting this before the time budget expires would
# mean something is comparing far more pairs per second than expected --
# kept as a sanity ceiling, not the primary control (see
# FUZZY_SCAN_TIME_BUDGET_SECONDS above).
FUZZY_MAX_COMPARISONS = 2_000_000

# Confidence tier labels used throughout the UI/plan.
#
# `str, Enum` rather than a plain `class ... (Enum)`: every existing call
# site (DuplicateGroup.tier, MergeAction.tier, TrackChangeRecord.tier,
# CacheDB's JSON-serialized raw/audit blobs) was already written against
# these being plain strings -- compared with `==`/`!=`, used as dict keys,
# passed straight to json.dumps(), and round-tripped through json.loads()
# on restore. A `str` mixin keeps every one of those working unchanged
# (Tier.EXACT == "exact" is True, json.dumps(Tier.EXACT) emits "exact",
# {Tier.EXACT: ...}["exact"] hits the same entry) while still giving a
# single enum-driven source of truth for "what are the valid tiers" that
# UI code can map from, instead of hand-keeping parallel label/style
# dicts in sync with these constants by convention alone.
class Tier(str, Enum):
    EXACT = "exact"            # normalized key matched exactly
    HIGH_CONFIDENCE = "high"   # fuzzy score >= FUZZY_HIGH_CONFIDENCE
    NEEDS_REVIEW = "review"    # fuzzy score in [LOW, HIGH)
    MANUAL = "manual"          # user explicitly merged tracks the algorithm never grouped
    # v2.0: normalized artist+title matched exactly (same as TIER_EXACT),
    # but the tracks' durations differ by more than DURATION_TOLERANCE_MS --
    # e.g. a radio edit vs. album version, or a re-imported copy with a
    # different Total Time tag. Previously these were split into separate
    # single-track clusters by _split_by_duration() and then silently
    # dropped (a singleton cluster is never a group), AND the fuzzy pass
    # explicitly skips same-key pairs (that's "our job", per the comment
    # in _compare_batch), so a real, obvious duplicate -- same artist, same
    # title -- could vanish from both passes entirely whenever its two
    # copies happened to differ in length. This tier surfaces that case for
    # manual review instead of losing it silently. Never auto-selected by
    # "select all (exact + high confidence)", same as NEEDS_REVIEW, since a
    # large duration gap can also mean a genuinely different edit that
    # shouldn't be auto-merged.
    DURATION_MISMATCH = "duration_mismatch"

    def __str__(self) -> str:  # keep str(tier) == tier.value, not "Tier.EXACT"
        return self.value


# Module-level aliases: every pre-existing call site (this module, plus
# core/consolidator.py, core/audit.py, ui/main_window.py, ui/widgets.py,
# tests/test_consolidation.py) imports/uses TIER_EXACT etc. by name and
# compares/stores them as bare strings. Keeping these names bound to the
# enum members is the minimal change that gets every one of those sites
# onto the enum without touching their code.
TIER_EXACT = Tier.EXACT
TIER_HIGH_CONFIDENCE = Tier.HIGH_CONFIDENCE
TIER_NEEDS_REVIEW = Tier.NEEDS_REVIEW
# v1.10.1: tracks the user manually merged via "Merge these tracks..." --
# see make_manual_merge_group() below. Never produced by the automatic
# exact/fuzzy passes; only ever constructed from an explicit user action in
# the review UI. Treated like TIER_EXACT/TIER_HIGH_CONFIDENCE everywhere a
# tier is checked against TIER_NEEDS_REVIEW (pre-selected for cleanup,
# included in "select all"), since the user has already confirmed these two
# tracks are duplicates by choosing them individually -- there is nothing
# left to "review" the way an algorithm-guessed fuzzy match still needs.
TIER_MANUAL = Tier.MANUAL
# v2.0: see Tier.DURATION_MISMATCH above.
TIER_DURATION_MISMATCH = Tier.DURATION_MISMATCH

# Prefix on the synthetic group key used for manually-merged groups (see
# make_manual_merge_group), so a manual group's key can never collide with
# a real (normalized artist, normalized title) key produced by the exact/
# fuzzy passes -- both here (this module never emits keys starting with
# this) and in ui/main_window.py's permanent-exclusion set (which stores/
# compares raw DuplicateGroup.key tuples; a manual merge's key is
# effectively unique to the specific tracks involved, so it can never be
# accidentally excluded by a permanent-exclusion entry meant for a
# different, real artist/title pair).
_MANUAL_KEY_PREFIX = "__manual__"

_FEAT_PATTERN = re.compile(
    r"\s*[\(\[]?\s*(feat\.?|featuring|ft\.?)\s+.*?[\)\]]?\s*$", re.IGNORECASE
)
_REMASTER_PATTERN = re.compile(
    r"\s*[\(\[]\s*(remaster(ed)?|live|mono|stereo|explicit|clean|single version|"
    r"album version|radio edit|deluxe(\s+edition)?)\s*.*?[\)\]]\s*", re.IGNORECASE
)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_MULTI_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip accents/punctuation, and remove common noise tokens
    (feat., remaster tags, etc.) so trivially-different tags of the same
    song match."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _FEAT_PATTERN.sub("", text)
    text = _REMASTER_PATTERN.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text


@dataclass
class DuplicateGroup:
    key: tuple[str, str]  # (normalized artist, normalized title)
    tracks: list[Track]
    # Confidence tier for this group: "exact" (normalized-key match, same as
    # v1 behavior) or "high"/"review" for fuzzy-matched groups. Defaults to
    # "exact" so every existing call site/test that builds a DuplicateGroup
    # without passing this keeps its old meaning.
    tier: str = TIER_EXACT
    # Similarity score in [0, 1] for fuzzy groups; 1.0 for exact groups.
    similarity: float = 1.0
    # Manual review state, set by the user in the UI (never inferred
    # automatically). When set, this overrides the auto-picked canonical
    # track id for this group. None means "use the automatic choice".
    canonical_override_id: int | None = None
    # When True, the user has explicitly marked this group as NOT actually
    # duplicates (e.g. two different live/remix versions that happened to
    # match). The plan builder skips groups with this flag set.
    marked_not_duplicate: bool = False

    def canonical(self) -> Track:
        """Track to keep. Uses the user's manual override if one was set
        via the review UI; otherwise falls back to the automatic choice —
        most complete metadata / highest quality, ties broken by lowest
        Track ID for determinism."""
        if self.canonical_override_id is not None:
            for t in self.tracks:
                if t.track_id == self.canonical_override_id:
                    return t
        return max(self.tracks, key=lambda t: (t.completeness_score(), -t.track_id))

    def canonical_reason(self) -> str:
        """Short human-readable explanation of why the current canonical
        track was chosen, for display in the expanded review row."""
        if self.canonical_override_id is not None:
            return "Manually selected by you"
        canon = self.canonical()
        reasons: list[str] = []
        others = [t for t in self.tracks if t.track_id != canon.track_id]
        if canon.bitrate and others and canon.bitrate >= max((t.bitrate for t in others), default=0):
            reasons.append(f"highest bitrate ({canon.bitrate} kbps)")
        if canon.raw.get("Artwork Count", 0) and not any(t.raw.get("Artwork Count", 0) for t in others):
            reasons.append("has artwork")
        filled = sum(1 for k in ("Album", "Genre", "Year", "Composer", "Album Artist") if canon.raw.get(k))
        if filled:
            reasons.append(f"{filled} metadata field(s) filled")
        if canon.play_count and others and canon.play_count >= max((t.play_count for t in others), default=0):
            reasons.append(f"most plays ({canon.play_count})")
        if not reasons:
            reasons.append("most complete entry overall")
        return "Chosen for: " + ", ".join(reasons)

    def duplicates(self) -> list[Track]:
        canon = self.canonical()
        return [t for t in self.tracks if t.track_id != canon.track_id]

    @property
    def needs_review(self) -> bool:
        """Fuzzy 'possible duplicate' groups, and same-title/artist groups
        with a duration mismatch (v2.0, see Tier.DURATION_MISMATCH), should
        never be auto-merged without the user looking at them first."""
        return self.tier in (TIER_NEEDS_REVIEW, TIER_DURATION_MISMATCH)

    @property
    def is_manual(self) -> bool:
        """True for a group created via make_manual_merge_group() -- the
        user's own "Merge these tracks..." override, as opposed to
        anything the exact/fuzzy passes found on their own."""
        return self.tier == TIER_MANUAL


def find_duplicate_groups(library: Library) -> list[DuplicateGroup]:
    """Groups tracks by normalized (artist, title), then splits any group
    further by duration when members' lengths differ by more than the
    tolerance (covers same-name-different-song edge cases).

    Exact normalized-key matches whose durations all cluster together are
    returned tagged tier="exact", same as v1.

    v2.0 bug fix: previously, when an exact-key bucket's durations didn't
    all cluster together (see _split_by_duration), each resulting duration
    sub-cluster was only kept if it *itself* had 2+ tracks -- any duration
    sub-cluster that ended up with just one track (e.g. two same-artist,
    same-title copies whose lengths differ by more than
    DURATION_TOLERANCE_MS, so each lands alone in its own duration
    cluster) was silently discarded. Combined with the fuzzy pass
    deliberately skipping exact-key pairs (see _compare_batch: "exact
    matches are the exact-tier's job, not ours"), this meant an obvious
    same-artist/same-title duplicate could be missed by *both* passes
    whenever its copies' durations happened to diverge -- a common case
    for a radio edit vs. album version, a remaster with different
    trimming, or a re-imported copy with a slightly different Total Time
    tag. Now, whenever a bucket's tracks don't all fit in one duration
    cluster, every track in that bucket is still returned as a single
    group tagged tier="duration_mismatch" (see Tier.DURATION_MISMATCH)
    instead of being fragmented and dropped -- surfaced for manual review
    rather than auto-merged, since a large duration gap can also mean a
    genuinely different edit. Buckets whose durations *do* all cluster
    together keep the exact v1 behavior (tier="exact", no change).

    Use find_all_candidate_groups() to additionally get fuzzy "possible
    duplicate" candidates for manual review.
    """
    buckets: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for track in library.tracks.values():
        # Bug fix: this used to skip any track whose *normalized* title
        # came out empty (`if not key[1]`), intending to skip tracks with
        # no title at all. But normalize() strips everything that isn't a
        # letter/digit/space (see _NON_ALNUM), so a track whose raw title
        # is made up entirely of symbols -- e.g. "$" (Ty Dolla $ign),
        # "?", "!!!" -- has a real, non-empty title but normalizes to ""
        # and was silently treated as titleless, excluding it from
        # exact-match grouping even against an identically-named,
        # identically-symbol-titled duplicate. The guard now checks the
        # raw title instead, so it only skips tracks that are genuinely
        # untitled; two tracks that both normalize to "" (both all-
        # symbol titles) still bucket together and can match, the same
        # as any other shared normalized key.
        if not (track.name or "").strip():
            continue  # no title at all; nothing meaningful to match on
        key = (normalize(track.artist), normalize(track.name))
        buckets[key].append(track)

    groups: list[DuplicateGroup] = []
    for key, tracks in buckets.items():
        if len(tracks) < 2:
            continue
        duration_clusters = [sub for sub in _split_by_duration(tracks) if len(sub) >= 2]
        covered_ids = {t.track_id for sub in duration_clusters for t in sub}
        if len(covered_ids) == len(tracks):
            # Every track landed in a same-duration cluster of size >= 2:
            # identical to v1 behavior, tier="exact".
            for sub in duration_clusters:
                groups.append(DuplicateGroup(key=key, tracks=sub, tier=TIER_EXACT, similarity=1.0))
        else:
            # At least one track was left as a duration-cluster singleton
            # -- same artist+title, but a duration gap wide enough that it
            # couldn't be confidently auto-grouped. Keep the whole bucket
            # together as one review-tier group rather than losing the
            # singleton(s) entirely.
            groups.append(
                DuplicateGroup(key=key, tracks=list(tracks), tier=TIER_DURATION_MISMATCH, similarity=1.0)
            )
    return groups


def make_manual_merge_group(tracks: list[Track]) -> DuplicateGroup:
    """Builds a DuplicateGroup for tracks the user has explicitly chosen
    to merge via the review UI's "Merge these tracks..." picker --

    covering the case the automatic exact/fuzzy passes above don't: two
    (or more) tracks that were never grouped together *at all* (different
    enough artist/title text that even the fuzzy pass's similarity score
    fell below FUZZY_LOW_CONFIDENCE), but which the user can see, by
    listening or by other context, really are the same song. This is
    distinct from DuplicateGroup.canonical_override_id, which only lets
    the user re-pick which track survives *within* a group the algorithm
    already detected -- this function is what lets a group exist in the
    first place when detection found nothing.

    Requires at least 2 tracks (nothing to merge otherwise) and rejects
    duplicate track_ids in the input (a track can't be merged with
    itself). Tagged tier=TIER_MANUAL and similarity=1.0 (the user's own
    confirmation stands in for a similarity score -- there is no
    algorithmic score to report). The synthetic key is unique per call
    (keyed off the actual track ids involved, prefixed with
    _MANUAL_KEY_PREFIX) so it can never collide with a real normalized-
    key group or with another manual merge of different tracks.
    """
    if len(tracks) < 2:
        raise ValueError("A manual merge needs at least 2 tracks")
    ids = [t.track_id for t in tracks]
    if len(set(ids)) != len(ids):
        raise ValueError("Can't manually merge a track with itself")
    key = (_MANUAL_KEY_PREFIX, "+".join(str(i) for i in sorted(ids)))
    return DuplicateGroup(key=key, tracks=list(tracks), tier=TIER_MANUAL, similarity=1.0)


def similarity_score(a_artist: str, a_title: str, b_artist: str, b_title: str) -> float:
    """Combined 0-1 similarity between two normalized (artist, title) pairs.
    Title carries more weight than artist, since typo'd/edited artist tags
    are common but title is the stronger duplicate signal."""
    title_sim = SequenceMatcher(None, a_title, b_title).ratio()
    artist_sim = SequenceMatcher(None, a_artist, b_artist).ratio()
    return (title_sim * 0.7) + (artist_sim * 0.3)


# A batch item stripped down to exactly what a comparison needs (track_id,
# normalized artist, normalized title, duration). Deliberately not the
# Track dataclass itself: Track carries the full raw metadata dict, which
# would multiply IPC/pickling cost across a process-pool worker boundary
# for no benefit to the comparison logic below, which never looks at
# anything but these four fields.
_BatchItem = tuple[int, str, str, int | None]


def _to_batch_item(entry: tuple[Track, str, str]) -> _BatchItem:
    t, a, n = entry
    return (t.track_id, a, n, t.total_time_ms)


# How many comparisons to perform between each check of the wall-clock
# deadline, inside a single batch. Batches are already small (at most
# FUZZY_MAX_BUCKET_SIZE^2/2 comparisons), so this is mostly about not
# paying a time.monotonic() call on every single comparison; it has no
# effect on which duplicates are found, only how promptly an expired
# deadline is noticed.
_DEADLINE_CHECK_STRIDE = 25


def _compare_batch(
    batch: list[_BatchItem],
    deadline: float,
    low_confidence: float,
    high_confidence: float,
) -> tuple[list[tuple[str, str, float, list[int]]], int]:
    """Runs the O(n^2) pairwise comparison for one bucket/chunk batch,
    exactly as find_fuzzy_candidate_groups did inline before this was
    split out. Returns (raw_group_specs, comparisons_used) where each
    raw_group_spec is (artist_key, title_key, best_score, [track_ids]) --
    plain, picklable data so this function can run in a worker process via
    ProcessPoolExecutor as well as in-process; the caller (which does have
    the full Track objects) turns these back into DuplicateGroup instances.

    `deadline` is an absolute time.monotonic() timestamp (v1.7.6, see
    module docstring): once it passes, remaining comparisons in this batch
    are skipped, the same "stop rather than error, return what's found so
    far" behavior the old comparisons_budget parameter had.

    This is a free function (not a closure/method) specifically so it is
    picklable for ProcessPoolExecutor -- a closure or bound method can't
    cross a process boundary.
    """
    used: set[int] = set()
    results: list[tuple[str, str, float, list[int]]] = []
    comparisons_used = 0
    expired = False
    for i in range(len(batch)):
        if expired:
            break
        id1, a1, n1, dur1 = batch[i]
        if id1 in used:
            continue
        cluster_ids = [id1]
        best_score = 0.0
        for j in range(i + 1, len(batch)):
            if comparisons_used % _DEADLINE_CHECK_STRIDE == 0 and time.monotonic() >= deadline:
                expired = True
                break
            id2, a2, n2, dur2 = batch[j]
            if id2 in used:
                continue
            if (a1, n1) == (a2, n2):
                continue  # exact matches are the exact-tier's job, not ours
            if dur1 and dur2 and abs(dur1 - dur2) > DURATION_TOLERANCE_MS * 4:
                continue  # wildly different lengths: unlikely to be the same song
            comparisons_used += 1
            score = similarity_score(a1, n1, a2, n2)
            if score < low_confidence:
                continue
            cluster_ids.append(id2)
            best_score = max(best_score, score)

        if len(cluster_ids) >= 2:
            used.update(cluster_ids)
            results.append((a1, n1, best_score, cluster_ids))
    return results, comparisons_used


# Signature for find_fuzzy_candidate_groups' progress_callback: called
# with (budget_used_fraction, batches_done, batches_total).
# budget_used_fraction is 0.0-1.0 (elapsed time / time_budget_seconds,
# clamped); batches_done/batches_total let a caller also show "N/M" if it
# wants to. Best-effort: exceptions raised by the callback are swallowed
# (see _report_progress) so a UI-side hiccup can never abort the scan.
FuzzyProgressCallback = Callable[[float, int, int], None]


def find_fuzzy_candidate_groups(
    library: Library,
    already_grouped_ids: set[int] | None = None,
    low_confidence: float = FUZZY_LOW_CONFIDENCE,
    high_confidence: float = FUZZY_HIGH_CONFIDENCE,
    parallel: bool = False,
    max_workers: int | None = None,
    time_budget_seconds: float = FUZZY_SCAN_TIME_BUDGET_SECONDS,
    progress_callback: FuzzyProgressCallback | None = None,
) -> list[DuplicateGroup]:
    """Finds near-miss duplicate candidates that the exact matcher above
    would miss (e.g. "Redbone" vs "Redbone " with a stray typo, or an
    artist tag with a small spelling difference). Tracks already covered
    by an exact group are skipped, since those are handled with full
    confidence already.

    This work is bounded by FUZZY_MAX_BUCKET_SIZE per comparison batch (see
    module docstring above) so runtime scales predictably even at 100k+
    tracks, at the cost of not comparing across chunk boundaries within an
    oversized same-first-letter bucket.

    `low_confidence`/`high_confidence` default to the module constants --
    every existing caller that doesn't pass them keeps the original
    behavior exactly. Values are expected to already be validated/clamped
    (see clamp_threshold) by whoever reads them from Settings; this
    function itself doesn't re-validate, so a caller passing raw user
    input should clamp first.

    `parallel`: when True, each bucketed comparison batch (already an
    independent unit of work -- see FUZZY_MAX_BUCKET_SIZE) is submitted to
    a ProcessPoolExecutor instead of processed sequentially in a plain
    loop. Grouping/results are identical either way (batches never share
    state), so this only affects wall-clock time on large libraries with
    many buckets/chunks, never which duplicates are found. Defaults to
    False so every existing call site's behavior (single-threaded, no new
    processes spawned) is completely unchanged unless a caller opts in
    (see workers.py, which opts in above a track-count threshold).
    `max_workers` defaults to os.cpu_count() when not given, same as
    ProcessPoolExecutor's own default.

    `time_budget_seconds` (v1.7.6, see module docstring): wall-clock
    ceiling for the whole fuzzy pass, replacing the old fixed
    FUZZY_MAX_COMPARISONS split evenly across batches. Defaults to
    FUZZY_SCAN_TIME_BUDGET_SECONDS -- every existing caller that doesn't
    pass this gets the same module-level default either way. Comparisons
    stop (batches simply aren't started/finished) once the budget is
    spent, same "return what's found so far" behavior as before.

    `progress_callback`, if given, is invoked periodically (roughly once
    per batch -- batches are small, so this is frequent) with the
    fraction of the time budget used so far and a (batches_done,
    batches_total) pair, so a caller can surface a live "still scanning,
    N% budget used" indicator instead of the whole scan happening inside
    one opaque blocking call. Never required for correctness -- omit it
    and the scan behaves exactly as before, just without a progress
    signal.
    """
    already_grouped_ids = already_grouped_ids or set()
    # Bug fix: same issue as find_duplicate_groups' bucket guard above --
    # this used to require normalize(t.name) to be truthy, which excludes
    # any track whose title is entirely symbols (normalizes to "") even
    # though it has a real raw title. Checking the raw title instead
    # keeps only-genuinely-untitled tracks out of the fuzzy candidate
    # pool, without also dropping something like "$" or "?!".
    candidates = [
        t for t in library.tracks.values()
        if t.track_id not in already_grouped_ids and (t.name or "").strip()
    ]

    by_id = {t.track_id: t for t in candidates}
    normed = [(t, normalize(t.artist), normalize(t.name)) for t in candidates]

    # Bucket by normalized title's first character before doing the O(n^2)
    # pairwise comparison. A typo severe enough to change the very first
    # character of a title is rare, and this keeps each comparison batch
    # bounded by (tracks starting with that letter) instead of the whole
    # library, which matters at 100k+ scale.
    if FUZZY_BUCKET_BY_FIRST_CHAR:
        first_char_buckets: dict[str, list[tuple[Track, str, str]]] = defaultdict(list)
        for item in normed:
            _, _, n = item
            first_char_buckets[n[0] if n else ""].append(item)
        bucketed_batches: list[list[_BatchItem]] = []
        for bucket_items in first_char_buckets.values():
            # Hard cap per comparison batch: split any oversized bucket into
            # fixed-size chunks so total comparisons stay bounded regardless
            # of how many tracks happen to share a first letter.
            for start in range(0, len(bucket_items), FUZZY_MAX_BUCKET_SIZE):
                chunk = bucket_items[start:start + FUZZY_MAX_BUCKET_SIZE]
                bucketed_batches.append([_to_batch_item(e) for e in chunk])
    else:
        bucketed_batches = [[_to_batch_item(e) for e in normed]]

    start_time = time.monotonic()
    deadline = start_time + max(time_budget_seconds, 0.0)
    total_batches = len(bucketed_batches)

    def _report_progress(batches_done: int) -> None:
        if progress_callback is None:
            return
        elapsed = time.monotonic() - start_time
        fraction = 0.0 if time_budget_seconds <= 0 else min(elapsed / time_budget_seconds, 1.0)
        try:
            progress_callback(fraction, batches_done, total_batches)
        except Exception:
            pass  # best-effort UI hook; must never abort the scan itself

    raw_results: list[tuple[str, str, float, list[int]]] = []
    total_comparisons_used = 0
    if parallel and len(bucketed_batches) > 1:
        workers = max_workers or os.cpu_count() or 1
        workers = min(workers, len(bucketed_batches))
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_compare_batch, batch, deadline, low_confidence, high_confidence): batch
                    for batch in bucketed_batches
                }
                batches_done = 0
                deadline_hit = False
                for future in _as_completed(futures):
                    if future.cancelled():
                        continue  # cancelled below after the deadline was hit
                    batch_results, used = future.result()
                    raw_results.extend(batch_results)
                    total_comparisons_used += used
                    batches_done += 1
                    _report_progress(batches_done)
                    if not deadline_hit and time.monotonic() >= deadline:
                        # Deadline reached: cancel whatever hasn't started
                        # yet rather than waiting for it. Already-running
                        # futures finish on their own (each batch is tiny,
                        # see FUZZY_MAX_BUCKET_SIZE) and their results are
                        # still collected above as they complete.
                        deadline_hit = True
                        for other in futures:
                            other.cancel()
        except Exception:
            # Process-pool startup can fail in restricted/frozen-exe
            # environments (no fork/spawn support, sandboxing, etc.) --
            # fall back to the exact same sequential path used when
            # parallel=False rather than losing the scan entirely. This
            # mirrors every other best-effort fallback in this module
            # (see FUZZY_BUCKET_BY_FIRST_CHAR's own comment).
            raw_results = []
            total_comparisons_used = 0
            for batches_done, batch in enumerate(bucketed_batches, start=1):
                if time.monotonic() >= deadline or total_comparisons_used >= FUZZY_MAX_COMPARISONS:
                    break
                batch_results, used = _compare_batch(batch, deadline, low_confidence, high_confidence)
                raw_results.extend(batch_results)
                total_comparisons_used += used
                _report_progress(batches_done)
    else:
        for batches_done, batch in enumerate(bucketed_batches, start=1):
            if time.monotonic() >= deadline or total_comparisons_used >= FUZZY_MAX_COMPARISONS:
                break
            batch_results, used = _compare_batch(batch, deadline, low_confidence, high_confidence)
            raw_results.extend(batch_results)
            total_comparisons_used += used
            _report_progress(batches_done)

    _report_progress(total_batches)  # unconditional final update for the caller

    # A track can only end up in one result cluster per batch (each batch
    # marks ids "used" internally), and no track appears in more than one
    # batch (bucketing partitions the candidate list), so no additional
    # cross-batch dedup is needed here.
    groups: list[DuplicateGroup] = []
    for a1, n1, best_score, track_ids in raw_results:
        tracks = [by_id[tid] for tid in track_ids if tid in by_id]
        if len(tracks) < 2:
            continue
        tier = TIER_HIGH_CONFIDENCE if best_score >= high_confidence else TIER_NEEDS_REVIEW
        groups.append(
            DuplicateGroup(key=(a1, n1), tracks=tracks, tier=tier, similarity=round(best_score, 3))
        )
    return groups


def find_all_candidate_groups(
    library: Library,
    low_confidence: float = FUZZY_LOW_CONFIDENCE,
    high_confidence: float = FUZZY_HIGH_CONFIDENCE,
    parallel: bool = False,
    max_workers: int | None = None,
    time_budget_seconds: float = FUZZY_SCAN_TIME_BUDGET_SECONDS,
    progress_callback: FuzzyProgressCallback | None = None,
) -> list[DuplicateGroup]:
    """Exact groups first (tier="exact", unchanged v1 behavior), then fuzzy
    candidates over whatever tracks weren't already claimed by an exact
    group (tier="high" or "review"). This is the entry point the app/UI
    should use; find_duplicate_groups() remains available standalone for
    callers/tests that only want the exact-match v1 behavior.

    `low_confidence`/`high_confidence`/`parallel`/`max_workers`/
    `time_budget_seconds`/`progress_callback` are passed straight through
    to find_fuzzy_candidate_groups() -- see its docstring. Every existing
    caller that doesn't pass them gets the original single-threaded,
    default-threshold, default-time-budget behavior unchanged."""
    exact_groups = find_duplicate_groups(library)
    exact_ids = {t.track_id for g in exact_groups for t in g.tracks}
    fuzzy_groups = find_fuzzy_candidate_groups(
        library,
        already_grouped_ids=exact_ids,
        low_confidence=low_confidence,
        high_confidence=high_confidence,
        parallel=parallel,
        max_workers=max_workers,
        time_budget_seconds=time_budget_seconds,
        progress_callback=progress_callback,
    )
    return exact_groups + fuzzy_groups


@dataclass
class AlbumDuplicateGroup:
    """One album (normalized Album Artist + Album) that appears to have
    been imported/re-imported more than once at different quality, e.g.
    a whole album re-ripped at a higher bitrate without removing the
    original copies first. This is informational only -- unlike
    DuplicateGroup, nothing here feeds build_plan()/apply_plan(); the
    per-track exact/fuzzy matching already merges the individual
    duplicate songs underneath it. This just gives the album-level
    picture (e.g. "this album exists at both 128kbps and 320kbps, here's
    which tracks are duplicated across the two") that a flat list of
    per-track duplicate rows doesn't surface on its own."""

    key: tuple[str, str]  # (normalized album artist, normalized album)
    album_artist: str
    album: str
    # One entry per bitrate this album was found at, each holding the
    # tracks recorded at that bitrate.
    tracks_by_bitrate: dict[int, list[Track]]
    # Track (title-normalized) present at more than one of the bitrates
    # above -- i.e. an actual re-imported duplicate, not just "this
    # album happens to have some tracks we only have once".
    duplicated_track_titles: list[str]

    @property
    def bitrates(self) -> list[int]:
        return sorted(self.tracks_by_bitrate.keys())

    @property
    def total_tracks(self) -> int:
        return sum(len(v) for v in self.tracks_by_bitrate.values())

    @property
    def duplicate_track_count(self) -> int:
        """How many individual track entries are part of the overlap
        across bitrates -- i.e. what a consolidation would actually
        remove for this album, not just the count of distinct titles."""
        count = 0
        for title in self.duplicated_track_titles:
            occurrences = sum(
                1
                for tracks in self.tracks_by_bitrate.values()
                for t in tracks
                if normalize(t.name) == title
            )
            if occurrences > 1:
                count += occurrences - 1
        return count


# Minimum number of tracks an album-at-one-bitrate group must have before
# it's considered for album-level duplicate detection. A "1-2 track
# overlap" between two albums that merely share a couple of song titles
# (e.g. a Greatest Hits set) is exactly what the per-track matcher above
# already handles; this is specifically meant to catch a *whole album*
# re-imported wholesale, so a real minimum bar avoids flagging coincidental
# small overlaps as if an entire album were duplicated.
ALBUM_DUPLICATE_MIN_SHARED_TRACKS = 3


def find_album_duplicate_groups(
    library: Library,
    min_shared_tracks: int = ALBUM_DUPLICATE_MIN_SHARED_TRACKS,
) -> list[AlbumDuplicateGroup]:
    """Finds whole albums that appear to exist more than once in the
    library at different bitrates -- e.g. an album ripped at 128kbps and
    later re-ripped/re-imported at 320kbps without the original being
    removed. Groups tracks by normalized (Album Artist or Artist, Album),
    then splits each album's tracks by bitrate; if the same normalized
    track title appears under two or more distinct bitrates for the same
    album, and at least `min_shared_tracks` titles overlap that way, the
    album is reported as a group.

    Read-only and purely additive: this does not change what
    find_duplicate_groups()/find_fuzzy_candidate_groups() return, and its
    output never feeds build_plan()/apply_plan() -- the individual
    duplicate tracks these albums are made of are still detected and
    merged exactly as before by the existing per-track matching. This
    only adds an album-level *view* over the same data, for
    Library Health.
    """
    # Bucket every track with a usable album name by (album artist or
    # artist, album). Album Artist is preferred over Artist when present
    # since it's the more reliable "belongs to this release" signal for
    # compilations/soundtracks where individual track Artists vary.
    buckets: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for track in library.tracks.values():
        album_key = normalize(track.album)
        if not album_key:
            continue
        artist_source = track.raw.get("Album Artist") or track.artist
        artist_key = normalize(artist_source)
        buckets[(artist_key, album_key)].append(track)

    groups: list[AlbumDuplicateGroup] = []
    for (artist_key, album_key), tracks in buckets.items():
        by_bitrate: dict[int, list[Track]] = defaultdict(list)
        for t in tracks:
            by_bitrate[t.bitrate].append(t)

        if len(by_bitrate) < 2:
            continue  # only one bitrate on record; nothing to compare

        # For each normalized track title, which bitrates it shows up
        # under -- a title under 2+ distinct bitrates is a duplicated
        # track within this album.
        titles_by_bitrate: dict[str, set[int]] = defaultdict(set)
        for bitrate, bucket_tracks in by_bitrate.items():
            for t in bucket_tracks:
                title = normalize(t.name)
                if title:
                    titles_by_bitrate[title].add(bitrate)

        duplicated_titles = sorted(
            title for title, bitrates in titles_by_bitrate.items() if len(bitrates) >= 2
        )
        if len(duplicated_titles) < min_shared_tracks:
            continue

        sample = tracks[0]
        groups.append(
            AlbumDuplicateGroup(
                key=(artist_key, album_key),
                album_artist=(sample.raw.get("Album Artist") or sample.artist or ""),
                album=sample.album,
                tracks_by_bitrate=dict(by_bitrate),
                duplicated_track_titles=duplicated_titles,
            )
        )

    groups.sort(key=lambda g: g.duplicate_track_count, reverse=True)
    return groups


def _split_by_duration(tracks: list[Track]) -> list[list[Track]]:
    """Cluster tracks whose durations are within tolerance of each other.
    Tracks with no duration recorded are treated as compatible with any
    cluster (can't rule them out) and attached to the largest cluster.

    Bug fix (v1.2.1): tolerance is measured against each cluster's first
    (anchor) member, not its most-recently-added member. Comparing only to
    the last-added track lets a chain of pairwise-close tracks drift
    arbitrarily far apart end-to-end (e.g. 0ms, 2900ms, 5800ms would all
    land in one cluster under a 3000ms tolerance, even though the first
    and last are 5800ms apart) -- comparing to a fixed anchor keeps every
    member of a cluster within tolerance of the same reference point."""
    with_time = sorted((t for t in tracks if t.total_time_ms), key=lambda t: t.total_time_ms)
    without_time = [t for t in tracks if not t.total_time_ms]

    clusters: list[list[Track]] = []
    for t in with_time:
        placed = False
        for cluster in clusters:
            if abs(cluster[0].total_time_ms - t.total_time_ms) <= DURATION_TOLERANCE_MS:
                cluster.append(t)
                placed = True
                break
        if not placed:
            clusters.append([t])

    if not clusters:
        return [without_time] if without_time else []

    clusters.sort(key=len, reverse=True)
    clusters[0].extend(without_time)
    return clusters


# ---------------------------------------------------------------------------
# v2.1: complete-album-replaces-incomplete-album track selection
# ---------------------------------------------------------------------------
#
# Minimum number of tracks an album "copy" (see _album_copies_by_bitrate)
# must have before it's considered at all -- mirrors
# ALBUM_DUPLICATE_MIN_SHARED_TRACKS's reasoning: a 1-2 track copy is too
# likely to be a coincidental overlap (a Greatest Hits set, a single loose
# track that happens to share an Album tag) rather than a real "whole
# album re-imported" case, and comparing its size against Track Count is
# noisy at that scale.
ALBUM_COMPLETENESS_MIN_TRACKS = 3


def _album_copies_by_bitrate(tracks: list[Track]) -> list[list[Track]]:
    """Splits one album's tracks (already bucketed by normalized album
    artist + album) into candidate "copies" -- distinct import instances
    -- using bitrate as the separating signal, same partition
    find_album_duplicate_groups() already uses for the same underlying
    idea (a whole album re-ripped/re-imported at a different quality
    without the original being removed first). Reusing that exact,
    already-tested partition here (rather than inventing a second way to
    say "these tracks came from the same import") keeps the two features
    from ever disagreeing about what counts as one "copy" of an album."""
    by_bitrate: dict[int, list[Track]] = defaultdict(list)
    for t in tracks:
        by_bitrate[t.bitrate].append(t)
    return list(by_bitrate.values())


def _album_copy_declared_track_count(copy_tracks: list[Track]) -> int | None:
    """The Track Count most of this copy's tracks agree on, or None if
    none of them have it set. A few outliers (a single mistagged track)
    don't override the majority -- takes the most common non-None value
    rather than e.g. the first track's, so one bad tag can't misclassify
    an otherwise-consistent copy."""
    from collections import Counter

    values = [t.track_count for t in copy_tracks if t.track_count is not None]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def find_incomplete_album_overlap_track_ids(
    library: Library,
    groups: list[DuplicateGroup],
    min_tracks: int = ALBUM_COMPLETENESS_MIN_TRACKS,
) -> set[int]:
    """Identifies which track ids, among the tracks already present in
    `groups` (the exact/fuzzy/duration-mismatch duplicate groups a normal
    scan already found), belong to the *incomplete* copy of an album that
    also has a *complete* copy elsewhere in the library -- e.g. an album
    re-imported in full after only a partial rip existed before, where
    the old partial copy's overlapping tracks are now redundant.

    This never invents new duplicate groups and never decides anything
    build_plan()/apply_plan() doesn't already know how to act on: it only
    flags, among the *duplicate tracks a group already contains*, which
    ones sit on the "incomplete" side of a complete/incomplete album
    pair, so a caller (see ui/main_window._populate_table_rows) can
    pre-check those rows for the user. Read-only -- nothing here mutates
    `library` or any group, and nothing is actually removed unless the
    user reviews and applies the plan as normal.

    Completeness is judged per album copy (see _album_copies_by_bitrate):
      1. If the copy's tracks agree on a "Track Count" tag (see
         Track.track_count / _album_copy_declared_track_count), the copy
         is "complete" when its actual track total meets or exceeds that
         declared count, "incomplete" when it falls short.
      2. If no Track Count is available for a copy, it falls back to
         comparing that copy's actual track total against the other
         copy's actual track total -- the copy with strictly more tracks
         is "complete" relative to the smaller one. With no signal at all
         to break a tie (equal counts, neither has Track Count), neither
         copy is classified and nothing is flagged for that album.

    Only albums with at least two copies, each with at least `min_tracks`
    tracks, are considered (same reasoning as
    ALBUM_DUPLICATE_MIN_SHARED_TRACKS: a couple of coincidentally-shared
    titles between two small track sets isn't "a whole album re-imported
    incomplete/complete", and Track Count comparisons are too noisy at
    that scale to trust here).
    """
    overlap_ids: set[int] = set()

    # Only tracks that are actually part of a duplicate group matter here
    # -- this never flags a track build_plan() wouldn't otherwise touch.
    grouped_track_ids: set[int] = {
        t.track_id for g in groups for t in g.tracks if not g.marked_not_duplicate
    }
    if not grouped_track_ids:
        return overlap_ids

    # track_id -> the (non-excluded) groups it belongs to, built once so
    # the per-album loop below doesn't re-scan every group for every
    # candidate track -- matters at 100k+ tracks / many groups scale.
    groups_by_track_id: dict[int, list[DuplicateGroup]] = defaultdict(list)
    for g in groups:
        if g.marked_not_duplicate:
            continue
        for t in g.tracks:
            groups_by_track_id[t.track_id].append(g)

    album_buckets: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for track in library.tracks.values():
        album_key = normalize(track.album)
        if not album_key:
            continue
        artist_source = track.raw.get("Album Artist") or track.artist
        album_buckets[(normalize(artist_source), album_key)].append(track)

    for _key, album_tracks in album_buckets.items():
        copies = [c for c in _album_copies_by_bitrate(album_tracks) if len(c) >= min_tracks]
        if len(copies) < 2:
            continue  # nothing to compare -- one copy, or every copy too small

        # Classify each copy complete/incomplete against its own declared
        # Track Count first; copies with no declared count are resolved
        # below by comparing directly against the other copies' actual
        # totals.
        declared = [_album_copy_declared_track_count(c) for c in copies]
        actual_totals = [len(c) for c in copies]

        complete_idx: set[int] = set()
        incomplete_idx: set[int] = set()
        for i, (copy_tracks, decl, total) in enumerate(zip(copies, declared, actual_totals)):
            if decl is not None:
                if total >= decl:
                    complete_idx.add(i)
                else:
                    incomplete_idx.add(i)

        # Fallback for copies with no Track Count at all: compare their
        # actual total directly against the best-known complete copy's
        # total (if any), or -- if no copy has a declared count -- against
        # the largest actual total among the undecided copies themselves.
        # A strictly smaller copy is treated as incomplete relative to
        # that reference; the copy(ies) at the reference total are
        # treated as complete; an outright tie across every undecided
        # copy (nothing bigger to compare against) leaves all of them
        # unclassified -- no signal to break it.
        undecided_idx = [i for i in range(len(copies)) if i not in complete_idx and i not in incomplete_idx]
        if undecided_idx:
            if complete_idx:
                reference_total = max(actual_totals[i] for i in complete_idx)
            else:
                reference_total = max(actual_totals[i] for i in undecided_idx)
            for i in undecided_idx:
                if actual_totals[i] < reference_total:
                    incomplete_idx.add(i)
                elif actual_totals[i] == reference_total and not complete_idx:
                    # No copy was already known complete via its declared
                    # Track Count -- the largest undecided copy(ies)
                    # become the complete reference. If every undecided
                    # copy ties at this total, all end up here and none
                    # in incomplete_idx, which correctly yields "nothing
                    # to flag" for that album below.
                    complete_idx.add(i)

        if not complete_idx or not incomplete_idx:
            continue  # no usable complete/incomplete pairing for this album

        complete_track_ids = {t.track_id for i in complete_idx for t in copies[i]}
        for i in incomplete_idx:
            for t in copies[i]:
                if t.track_id not in grouped_track_ids:
                    continue  # not part of any detected duplicate group
                # Only flag it if its *specific* duplicate group actually
                # has a counterpart on the complete side -- otherwise this
                # track's duplicate is some unrelated track elsewhere in
                # the library, not this complete album copy.
                for g in groups_by_track_id.get(t.track_id, ()):
                    if any(gt.track_id in complete_track_ids for gt in g.tracks):
                        overlap_ids.add(t.track_id)
                        break

    return overlap_ids
