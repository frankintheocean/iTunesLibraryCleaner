"""Adapters load original modules without altering their source."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'legacy' / 'consolidator' / 'src'))
sys.path.insert(0, str(ROOT / 'legacy' / 'cleaner'))
from core.itunes_xml import Library, Track, Playlist, default_library_xml_candidates
from core.duplicate_detector import find_all_candidate_groups, make_manual_merge_group
from core.consolidator import build_plan, apply_plan, ConsolidationPlan
from core.artwork import file_uri_to_path, read_embedded_artwork
from core.health_actions import find_missing_files_in_root, relink_track_location
from core.providers.spotify_export import SpotifyExportProvider
import genre_rules
import album_merge
import online_lookup


def manual_group(tracks, canonical_id):
    group = make_manual_merge_group(tracks)
    group.canonical_override_id = canonical_id
    return group


def configure_rules(data_dir):
    genre_rules.CUSTOM_RULES_PATH = str(data_dir / 'custom_genre_rules.json')
    genre_rules._custom_patterns_cache = None
    genre_rules._automaton_cache = None
