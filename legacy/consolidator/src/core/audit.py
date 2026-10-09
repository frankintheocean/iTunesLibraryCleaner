"""
Audit export.

Builds a precise, machine-readable record of exactly what a consolidation
run changed: which tracks were removed, which canonical track absorbed
them, the specific fields that were backfilled (with their before/after
values), the merged play count/rating/date, and which playlists were
repointed and how.

This is deliberately built from the ConsolidationPlan and the
*pre-mutation* Library -- i.e. call build_audit_record() before
apply_plan() runs -- rather than by diffing the library after the fact,
since the plan already carries every value apply_plan() is about to
write, and reading "before" state from the still-unmutated library is the
simplest way to avoid an audit implementation that could quietly drift
out of sync with what apply_plan() actually does.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .consolidator import ConsolidationPlan, MergeAction, _NEVER_BACKFILLED
from .itunes_xml import Library


def _json_safe(value: Any) -> Any:
    """Renders plist-typed values (notably datetime, which plistlib uses
    for <date> fields) as JSON-safe text, since the audit export is plain
    JSON, not a plist."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class FieldChange:
    field: str
    before: Any
    after: Any


@dataclass
class TrackChangeRecord:
    canonical_track_id: int
    canonical_name: str
    canonical_artist: str
    removed_track_ids: list[int]
    tier: str
    similarity: float
    play_count_before: int
    play_count_after: int
    rating_before: int
    rating_after: int
    backfilled_fields: list[FieldChange] = field(default_factory=list)
    playlists_repointed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_track_id": self.canonical_track_id,
            "canonical_name": self.canonical_name,
            "canonical_artist": self.canonical_artist,
            "removed_track_ids": self.removed_track_ids,
            "match_tier": self.tier,
            "match_similarity": self.similarity,
            "play_count": {"before": self.play_count_before, "after": self.play_count_after},
            "rating": {"before": self.rating_before, "after": self.rating_after},
            "backfilled_fields": [
                {"field": c.field, "before": c.before, "after": c.after}
                for c in self.backfilled_fields
            ],
            "playlists_repointed": self.playlists_repointed,
        }


@dataclass
class AuditRecord:
    app_version: str
    generated_at: str
    source_library_path: str
    output_library_path: str
    total_groups_merged: int
    total_tracks_removed: int
    changes: list[TrackChangeRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_version": self.app_version,
            "generated_at": self.generated_at,
            "platform": platform.platform(),
            "source_library_path": self.source_library_path,
            "output_library_path": self.output_library_path,
            "total_groups_merged": self.total_groups_merged,
            "total_tracks_removed": self.total_tracks_removed,
            "changes": [c.to_dict() for c in self.changes],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=_json_safe)


def _field_changes_for_action(library: Library, action: MergeAction) -> list[FieldChange]:
    """Recomputes, field by field, exactly which values apply_plan() is
    about to backfill onto the canonical track -- same eligibility rule
    (_NEVER_BACKFILLED, "only fill if canonical's own value is empty") as
    consolidator.apply_plan(), read from the library before it mutates
    anything, so before/after values are both real, not inferred."""
    canonical = library.tracks.get(action.canonical_id)
    if canonical is None:
        return []
    changes: list[FieldChange] = []
    seen_fields: set[str] = set()
    for removed_id in action.removed_ids:
        removed = library.tracks.get(removed_id)
        if removed is None:
            continue
        for k, v in removed.raw.items():
            if k in _NEVER_BACKFILLED or k in seen_fields:
                continue
            if not canonical.raw.get(k) and v:
                changes.append(FieldChange(field=k, before=None, after=_json_safe(v)))
                seen_fields.add(k)
    return changes


def build_audit_record(
    library: Library,
    plan: ConsolidationPlan,
    app_version: str,
    output_path: Path,
) -> AuditRecord:
    """Builds the full audit record for a plan that is about to be applied.
    Must be called BEFORE consolidator.apply_plan() mutates the library --
    it reads each canonical/removed track's pre-merge state to compute
    accurate before/after values."""
    changes: list[TrackChangeRecord] = []
    for action in plan.actions:
        canonical = library.tracks.get(action.canonical_id)
        play_count_before = canonical.play_count if canonical else 0
        rating_before = canonical.rating if canonical else 0
        changes.append(
            TrackChangeRecord(
                canonical_track_id=action.canonical_id,
                canonical_name=action.canonical_name,
                canonical_artist=action.canonical_artist,
                removed_track_ids=list(action.removed_ids),
                tier=action.tier,
                similarity=action.similarity,
                play_count_before=play_count_before,
                play_count_after=action.merged_play_count,
                rating_before=rating_before,
                rating_after=action.merged_rating or rating_before,
                backfilled_fields=_field_changes_for_action(library, action),
                playlists_repointed=list(action.playlists_updated),
            )
        )

    return AuditRecord(
        app_version=app_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_library_path=str(library.source_path) if library.source_path else "",
        output_library_path=str(output_path),
        total_groups_merged=len(plan.actions),
        total_tracks_removed=plan.total_duplicates_removed,
        changes=changes,
    )
