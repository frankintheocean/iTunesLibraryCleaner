"""
Pluggable duplicate-detection strategies (v1.9.1).

duplicate_detector.py's exact/fuzzy passes (find_duplicate_groups /
find_fuzzy_candidate_groups) are proven, individually tested, and used by
several existing call sites (workers.py, library_health.py,
main_window.py) exactly as they are -- this module does not touch any of
that logic. What it adds is a thin, composable layer on top: a common
`DuplicateStrategy` interface (matching the shape of
core/providers/base.py's `LibraryProvider` -- a class attribute
`strategy_id`, one required `find_groups()` method, an ABC) so exact,
fuzzy, and fingerprint matching can each be tested and reasoned about in
isolation, then composed by a caller instead of being three hardcoded,
separately-invoked functions.

Why add this now: find_all_candidate_groups() already does "exact, then
fuzzy over what's left" as a hardcoded two-step pipeline. That's fine as
a default and is left completely alone (nothing here changes it or what
it returns). But a caller that wants, say, only fingerprint matching, or
fuzzy-then-fingerprint, or wants to unit-test "does the fingerprint
matcher alone behave correctly" without also running the O(n^2) fuzzy
pass, previously had no way to do that -- the passes weren't separable
units. `DuplicateStrategy` subclasses make each pass an independently
constructible, independently callable object; `CompositeDuplicateStrategy`
composes any ordered list of them exactly the way find_all_candidate_groups
composes exact+fuzzy today (each strategy only sees tracks not already
claimed by an earlier one in the list), but with the list itself now a
parameter instead of two fixed function calls.

New in this module (not just a wrapper): FingerprintDuplicateStrategy.
"Fingerprint" here means a metadata fingerprint, not audio-content
fingerprinting -- consistent with this app's existing "reads Library.xml
fields only, never opens the audio file" scope (see duplicate_detector.py's
own module docstring). It groups tracks that share the same iTunes
"Persistent ID" (a stable identifier iTunes itself assigns and that
survives re-imports in some workflows) or, failing that, the same
(file size, total time) pair recorded in the XML -- signals no existing
pass uses, so it can catch a duplicate the normalized-key exact matcher
would miss (e.g. two entries with differently-cased or reformatted title
tags) without paying fuzzy matching's O(n^2) comparison cost.

Backward compatibility: nothing in duplicate_detector.py changes, no
existing call site is modified, and no existing test is touched. This
module is purely additive and safe to leave unused by the rest of the
app; adopting it anywhere is optional follow-up work, not part of this
change.
"""

from __future__ import annotations

import abc
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from .duplicate_detector import (
    DuplicateGroup,
    FUZZY_HIGH_CONFIDENCE,
    FUZZY_LOW_CONFIDENCE,
    FUZZY_SCAN_TIME_BUDGET_SECONDS,
    FuzzyProgressCallback,
    find_duplicate_groups,
    find_fuzzy_candidate_groups,
)
from .itunes_xml import Library, Track

# Confidence tier used for fingerprint-matched groups. Distinct from
# TIER_EXACT (normalized artist/title key) and the fuzzy tiers (score-based)
# since a fingerprint match is neither -- it's an identity match on a
# different field entirely. Callers that only know about the three
# existing tiers (see ui/widgets.py's tier badge lookup) should treat an
# unrecognized tier defensively rather than assuming exhaustiveness; the
# existing three tiers are completely unaffected by this addition.
TIER_FINGERPRINT = "fingerprint"


class DuplicateStrategy(abc.ABC):
    """Base class every duplicate-detection pass implements.

    Same shape as core/providers/base.LibraryProvider: a stable
    `strategy_id` class attribute plus one method a caller invokes
    without needing to know which concrete strategy it's holding. Kept
    intentionally minimal (one method) since, unlike providers, every
    strategy here does exactly one thing -- take a library (and the set
    of track ids an earlier strategy in a composed pipeline already
    claimed) and return duplicate groups.
    """

    #: Stable machine identifier, e.g. "exact", "fuzzy", "fingerprint".
    #: Used for logging/display and as a dict key by callers that want to
    #: look up or configure a specific strategy by name.
    strategy_id: str = ""

    @abc.abstractmethod
    def find_groups(
        self,
        library: Library,
        already_grouped_ids: Optional[set[int]] = None,
    ) -> list[DuplicateGroup]:
        """Returns duplicate groups found by this strategy alone, skipping
        any track whose id is in `already_grouped_ids` (so a strategy
        composed after another doesn't re-claim tracks the earlier one
        already grouped -- same convention find_all_candidate_groups()
        already uses between its exact and fuzzy passes)."""
        raise NotImplementedError


@dataclass
class ExactDuplicateStrategy(DuplicateStrategy):
    """Wraps find_duplicate_groups() -- normalized (artist, title) key
    match, split by duration tolerance. No new logic: this is the exact
    matcher itself, made independently constructible/callable so it can
    be composed with other strategies or tested standalone.

    `already_grouped_ids` is honored by filtering find_duplicate_groups()'s
    output rather than by changing find_duplicate_groups() itself (it has
    no such parameter, and every existing caller of it relies on that) --
    so behavior for direct callers of find_duplicate_groups() is
    completely unaffected by this class existing.
    """

    strategy_id: str = "exact"

    def find_groups(
        self,
        library: Library,
        already_grouped_ids: Optional[set[int]] = None,
    ) -> list[DuplicateGroup]:
        already_grouped_ids = already_grouped_ids or set()
        groups = find_duplicate_groups(library)
        if not already_grouped_ids:
            return groups
        filtered: list[DuplicateGroup] = []
        for group in groups:
            remaining = [t for t in group.tracks if t.track_id not in already_grouped_ids]
            if len(remaining) >= 2:
                filtered.append(
                    DuplicateGroup(key=group.key, tracks=remaining, tier=group.tier, similarity=group.similarity)
                )
        return filtered


@dataclass
class FuzzyDuplicateStrategy(DuplicateStrategy):
    """Wraps find_fuzzy_candidate_groups() -- near-miss similarity match
    over whatever tracks weren't already claimed. No new matching logic;
    this is a thin adapter so the fuzzy pass can be composed/tested like
    any other strategy. All of find_fuzzy_candidate_groups' tuning knobs
    (thresholds, parallel execution, time budget, progress reporting) are
    exposed unchanged as constructor fields, defaulting to the same
    module-level defaults duplicate_detector.py itself uses, so a
    FuzzyDuplicateStrategy() with no arguments behaves identically to
    calling find_fuzzy_candidate_groups() directly.
    """

    strategy_id: str = "fuzzy"
    low_confidence: float = FUZZY_LOW_CONFIDENCE
    high_confidence: float = FUZZY_HIGH_CONFIDENCE
    parallel: bool = False
    max_workers: Optional[int] = None
    time_budget_seconds: float = FUZZY_SCAN_TIME_BUDGET_SECONDS
    progress_callback: Optional[FuzzyProgressCallback] = None

    def find_groups(
        self,
        library: Library,
        already_grouped_ids: Optional[set[int]] = None,
    ) -> list[DuplicateGroup]:
        return find_fuzzy_candidate_groups(
            library,
            already_grouped_ids=already_grouped_ids,
            low_confidence=self.low_confidence,
            high_confidence=self.high_confidence,
            parallel=self.parallel,
            max_workers=self.max_workers,
            time_budget_seconds=self.time_budget_seconds,
            progress_callback=self.progress_callback,
        )


@dataclass
class FingerprintDuplicateStrategy(DuplicateStrategy):
    """Groups tracks sharing a stable per-file identity signal instead of
    a normalized text key or a similarity score: iTunes' own "Persistent
    ID" field when present (the most reliable signal -- iTunes assigns it
    per media item), falling back to the (file size, total time) pair
    recorded in the XML when Persistent ID is absent or the whole library
    lacks it. Both are metadata already present in Library.xml -- this
    reads no audio data, matching every other pass in this app.

    This complements rather than replaces the exact/fuzzy passes: a track
    re-imported with a heavily edited title (past what fuzzy's similarity
    threshold would still catch) can still match here if its Persistent
    ID or file size/duration survived the re-import unchanged, which
    neither the exact nor fuzzy pass can key on since neither looks at
    those fields.

    A group of 1 (nothing else shares the fingerprint) is never returned,
    same "only report actual duplicates" convention as
    _split_by_duration() and the fuzzy pass use.
    """

    strategy_id: str = "fingerprint"

    def _fingerprint(self, track: Track) -> Optional[tuple]:
        persistent_id = track.raw.get("Persistent ID")
        if persistent_id:
            return ("pid", persistent_id)
        size = track.raw.get("Size")
        duration = track.total_time_ms
        if size and duration:
            return ("size_duration", int(size), int(duration))
        return None

    def find_groups(
        self,
        library: Library,
        already_grouped_ids: Optional[set[int]] = None,
    ) -> list[DuplicateGroup]:
        already_grouped_ids = already_grouped_ids or set()
        buckets: dict[tuple, list[Track]] = defaultdict(list)
        for track in library.tracks.values():
            if track.track_id in already_grouped_ids:
                continue
            fp = self._fingerprint(track)
            if fp is not None:
                buckets[fp].append(track)

        groups: list[DuplicateGroup] = []
        for fp, tracks in buckets.items():
            if len(tracks) < 2:
                continue
            sample = tracks[0]
            key = (sample.artist.lower(), sample.name.lower())
            groups.append(
                DuplicateGroup(key=key, tracks=tracks, tier=TIER_FINGERPRINT, similarity=1.0)
            )
        return groups


class CompositeDuplicateStrategy:
    """Runs an ordered list of DuplicateStrategy instances, exactly the
    way find_all_candidate_groups() already composes exact-then-fuzzy:
    each strategy in turn only sees tracks not already claimed by an
    earlier one, and results are concatenated in strategy order.

    Not itself a DuplicateStrategy subclass (it composes strategies
    rather than being one), so `CompositeDuplicateStrategy([...]).run(...)`
    stays unambiguous about what it does versus a single strategy's
    `find_groups()`.
    """

    def __init__(self, strategies: list[DuplicateStrategy]):
        self.strategies = list(strategies)

    def run(self, library: Library) -> list[DuplicateGroup]:
        claimed: set[int] = set()
        all_groups: list[DuplicateGroup] = []
        for strategy in self.strategies:
            groups = strategy.find_groups(library, already_grouped_ids=claimed)
            all_groups.extend(groups)
            for g in groups:
                claimed.update(t.track_id for t in g.tracks)
        return all_groups


def default_strategy_pipeline(
    low_confidence: float = FUZZY_LOW_CONFIDENCE,
    high_confidence: float = FUZZY_HIGH_CONFIDENCE,
    parallel: bool = False,
    max_workers: Optional[int] = None,
    time_budget_seconds: float = FUZZY_SCAN_TIME_BUDGET_SECONDS,
    progress_callback: Optional[FuzzyProgressCallback] = None,
) -> CompositeDuplicateStrategy:
    """Convenience factory: exact -> fuzzy, in that order -- the same
    pipeline and defaults find_all_candidate_groups() already runs, just
    expressed as a composable pipeline for callers that want to insert or
    reorder strategies (e.g. add FingerprintDuplicateStrategy() before or
    after fuzzy) without hand-assembling the list themselves. Using this
    factory with no arguments and calling `.run(library)` returns
    equivalent groups to `find_all_candidate_groups(library)`.
    """
    return CompositeDuplicateStrategy(
        [
            ExactDuplicateStrategy(),
            FuzzyDuplicateStrategy(
                low_confidence=low_confidence,
                high_confidence=high_confidence,
                parallel=parallel,
                max_workers=max_workers,
                time_budget_seconds=time_budget_seconds,
                progress_callback=progress_callback,
            ),
        ]
    )
