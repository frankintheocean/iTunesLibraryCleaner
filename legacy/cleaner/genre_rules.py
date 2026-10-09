"""
Pure logic ported from GenreCleanup.hta: the pattern -> canonical genre
table, junk-filename detection, accent stripping, artist-name splitting,
and "kids" genre stripping. No COM/network here - keeps this importable
and testable on its own.
"""
import csv
import io
import re
import json
import os
import tempfile
from collections import deque

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_RULES_PATH = os.path.join(APP_DIR, "custom_genre_rules.json")

# ---- Pattern list: order matters, first match wins ----
# (lowercase substring, canonical target genre)
PATTERNS = [
    ("indie", "Indie"),
    ("singer & songwriter", "Folk"),
    ("singer-songwriter", "Folk"),
    ("films/games;film scores", "Soundtrack"),
    ("film score", "Soundtrack"),
    ("score", "Soundtrack"),
    ("musical", "Soundtrack"),

    ("hip hop", "Hip-Hop/Rap"),
    ("hip-hop", "Hip-Hop/Rap"),
    ("rap", "Hip-Hop/Rap"),
    ("trap", "Hip-Hop/Rap"),
    ("grime", "Hip-Hop/Rap"),
    ("phonk", "Hip-Hop/Rap"),
    ("drill", "Hip-Hop/Rap"),

    ("electro", "Electronic"),
    ("electronic", "Electronic"),
    ("edm", "Electronic"),
    ("dance", "Electronic"),
    ("house", "Electronic"),
    ("techno", "Electronic"),
    ("trance", "Electronic"),
    ("dubstep", "Electronic"),
    ("drum and bass", "Electronic"),
    ("drum & bass", "Electronic"),
    ("breakbeat", "Electronic"),
    ("garage", "Electronic"),
    ("electronica", "Electronic"),
    ("industrial", "Electronic"),
    ("ambient", "Electronic"),
    ("downtempo", "Electronic"),
    ("synth", "Electronic"),
    ("chillwave", "Electronic"),
    ("lo-fi", "Electronic"),
    ("lofi", "Electronic"),

    ("rock", "Rock"),
    ("metal", "Rock"),
    ("punk", "Punk"),
    ("grunge", "Grunge"),
    ("emo", "Emo"),
    ("hardcore", "Hardcore"),
    ("alternative", "Alternative"),

    ("pop", "Pop"),

    ("r&b/soul", "R&B"),
    ("soul", "R&B"),
    ("funk", "Funk"),
    ("motown", "R&B"),
    ("disco", "Funk"),
    ("r&b", "R&B"),
    ("rnb", "R&B"),
    ("neo-soul", "R&B"),
    ("neo soul", "R&B"),

    ("blues", "Blues"),
    ("jazz", "Jazz"),
    ("country", "Country"),
    ("bluegrass", "Country"),
    ("americana", "Folk"),
    ("folk", "Folk"),
    ("acoustic", "Folk"),

    ("classical", "Classical"),
    ("orchestral", "Classical"),
    ("opera", "Classical"),
    ("reggaeton", "Reggaeton"),
    ("reggae", "Reggae"),
    ("dancehall", "Reggae"),
    ("ska", "Reggae"),
    ("latin", "International"),
    ("salsa", "International"),
    ("afrobeat", "International"),
    ("afrobeats", "International"),
    ("k-pop", "K-Pop"),
    ("kpop", "K-Pop"),
    ("gospel", "Gospel"),
    ("christian", "Gospel"),
    ("contemporary gospel", "Gospel"),
    ("praise & worship", "Gospel"),
    ("praise and worship", "Gospel"),

    # "worldwide" and "world" both fold into International, matching the
    # same canonical tag foreign-language titles resolve to.
    ("worldwide", "International"),
    ("world", "International"),

    ("soundtrack", "Soundtrack"),

    # ---- Additional genre consolidations ----
    ("african music", "International"),
    ("afro-fusion", "International"),
    ("afrofusion", "International"),
    ("afropop", "International"),
    ("afro-pop", "International"),
    ("highlife", "International"),
    ("amapiano", "International"),
    ("soca", "Reggae"),
    ("dub", "Reggae"),
    ("bachata", "International"),
    ("merengue", "International"),
    ("cumbia", "International"),
    ("bossa nova", "International"),
    ("flamenco", "International"),
    ("swing", "Jazz"),
    ("bebop", "Jazz"),
    ("smooth jazz", "Jazz"),
    ("vocal jazz", "Jazz"),
    ("new age", "Electronic"),
    ("chillout", "Electronic"),
    ("future bass", "Electronic"),
    ("hyperpop", "Electronic"),
    ("bedroom pop", "Pop"),
    ("dream pop", "Pop"),
    ("synth-pop", "Pop"),
    ("synthpop", "Pop"),
    ("post-punk", "Punk"),
    ("pop punk", "Punk"),
    ("ska punk", "Reggae"),
    ("doom metal", "Rock"),
    ("death metal", "Rock"),
    ("black metal", "Rock"),
    ("thrash", "Rock"),
    ("post-rock", "Rock"),
    ("prog rock", "Rock"),
    ("progressive rock", "Rock"),
    ("yacht rock", "Rock"),
    ("surf rock", "Rock"),
    ("children's music", "Kids"),
    ("spoken word", "Spoken Word"),
    ("comedy", "Comedy"),
    ("holiday", "Holiday"),
    ("christmas", "Holiday"),

    # ---- User-requested mapping additions ----
    ("asian music", "International"),
    ("brazilian", "International"),
    ("idm", "Electronic"),
    ("french pop", "Pop"),
    ("easy listening", "Pop"),
    ("adult contemporary", "Pop"),
    ("musica mexicana", "International"),
    ("musica tropical", "International"),
]

TARGET_GENRES = {target for _, target in PATTERNS} | {"International"}


# Custom rules are read from disk once and cached in memory. Every track in
# a run used to re-open/re-parse custom_genre_rules.json on both
# map_genre() and is_already_target() - i.e. twice per track - which is
# pure I/O overhead unrelated to the genre it's checking. The cache is
# invalidated only when save_custom_patterns() actually writes a change,
# so edits made in the GUI (which always go through save_custom_patterns)
# are picked up immediately without needing a disk read on every track.
_custom_patterns_cache = None

# map_genre()/genre_lookup_key() used to re-scan the full pattern list with
# a plain "pattern in text" check per pattern - O(number of patterns) per
# track. That's negligible at the built-in table's size, but scales
# linearly if a power user accumulates hundreds of custom rules. An
# Aho-Corasick automaton built once over all_patterns() finds every
# matching pattern in a single pass over the genre string instead, so
# lookups scale with the length of the genre string rather than the
# number of rules. It's rebuilt lazily and only when the custom-rule
# cache is invalidated (see save_custom_patterns()), so normal runs
# (no rule edits) build it once.
_automaton_cache = None


class _AhoNode:
    __slots__ = ("children", "fail", "output")

    def __init__(self):
        self.children = {}
        self.fail = None
        self.output = ()  # tuple of priority indices (lower = higher priority)


def _build_automaton(patterns):
    """Builds an Aho-Corasick automaton over `patterns`, an ordered list of
    (pattern, target) tuples using the same first-match-wins priority as a
    plain left-to-right scan (earlier entries win). See
    _first_match_index() for how it's queried."""
    root = _AhoNode()
    root.fail = root
    for idx, (pattern, _target) in enumerate(patterns):
        if not pattern:
            continue
        node = root
        for ch in pattern:
            child = node.children.get(ch)
            if child is None:
                child = _AhoNode()
                node.children[ch] = child
            node = child
        node.output = node.output + (idx,)

    queue = deque()
    for child in root.children.values():
        child.fail = root
        queue.append(child)
    while queue:
        curr = queue.popleft()
        for ch, child in curr.children.items():
            f = curr.fail
            while f is not root and ch not in f.children:
                f = f.fail
            candidate = f.children.get(ch, root)
            child.fail = candidate if candidate is not child else root
            if child.fail.output:
                child.output = child.output + child.fail.output
            queue.append(child)
    return root


def _first_match_index(root, text):
    """Single pass over `text` returning the lowest priority index among
    all patterns in the automaton that occur anywhere in it (None if none
    match) - equivalent to `next((i for i, (p, _) in enumerate(patterns)
    if p in text), None)` but without rescanning `text` once per pattern."""
    node = root
    best = None
    for ch in text:
        while node is not root and ch not in node.children:
            node = node.fail
        node = node.children.get(ch, root)
        if node.output:
            local_min = node.output[0] if len(node.output) == 1 else min(node.output)
            if best is None or local_min < best:
                best = local_min
    return best


def _get_automaton():
    global _automaton_cache
    if _automaton_cache is None:
        _automaton_cache = _build_automaton(all_patterns())
    return _automaton_cache


def load_custom_patterns():
    """Load user-managed rules without mutating the built-in PATTERNS list.
    Cached after the first read; see save_custom_patterns() for invalidation."""
    global _custom_patterns_cache
    if _custom_patterns_cache is not None:
        return _custom_patterns_cache
    try:
        with open(CUSTOM_RULES_PATH, "r", encoding="utf-8") as f:
            rows = json.load(f)
        if not isinstance(rows, list):
            _custom_patterns_cache = []
        else:
            _custom_patterns_cache = [
                (str(row.get("pattern", "")).strip().lower(), str(row.get("target", "")).strip())
                for row in rows if isinstance(row, dict) and row.get("pattern") and row.get("target")
            ]
    except (OSError, ValueError, TypeError):
        _custom_patterns_cache = []
    return _custom_patterns_cache


def save_custom_patterns(patterns):
    cleaned = [{"pattern": str(pattern).strip().lower(), "target": str(target).strip()}
               for pattern, target in patterns if str(pattern).strip() and str(target).strip()]
    # Same temp-file + os.replace atomic-write pattern used for
    # settings.json / the undo log / changelog.txt elsewhere in this
    # app: a crash or power loss mid-write can no longer leave
    # custom_genre_rules.json truncated or corrupt (os.replace is
    # atomic on both POSIX and Windows).
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".genre-rules-", suffix=".tmp",
                                         dir=os.path.dirname(CUSTOM_RULES_PATH) or ".")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CUSTOM_RULES_PATH)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    global _custom_patterns_cache, _automaton_cache
    _custom_patterns_cache = [(row["pattern"], row["target"]) for row in cleaned]
    _automaton_cache = None  # rebuilt lazily on next lookup with the new rule set


def parse_patterns_csv(text: str):
    """Parses pasted/imported CSV text into (pattern, target) rows for
    bulk-loading into the Genre Rule Editor, without touching the saved
    rule file - callers combine the result with the existing in-memory
    rows and go through save_custom_patterns() same as any other edit.

    Accepts a header row or not; recognizes "pattern,target" (in either
    order, via a header) or plain two-column "pattern,target" rows if no
    recognizable header is present. Extra columns are ignored. Returns
    (rows, errors): rows is a list of (pattern, target) tuples for every
    valid line, errors is a list of "line N: reason" strings for lines
    that were skipped (blank pattern/target, wrong column count, etc.),
    so the caller can report both without one bad line silently
    discarding the whole paste.
    """
    rows = []
    errors = []
    reader = csv.reader(io.StringIO(text))
    all_lines = list(reader)
    if not all_lines:
        return rows, errors

    start = 0
    pattern_col, target_col = 0, 1
    header = [c.strip().lower() for c in all_lines[0]]
    if "pattern" in header or "target" in header:
        start = 1
        if "pattern" in header:
            pattern_col = header.index("pattern")
        if "target" in header:
            target_col = header.index("target")

    for line_no, row in enumerate(all_lines[start:], start=start + 1):
        if not row or all(not c.strip() for c in row):
            continue
        if len(row) <= max(pattern_col, target_col):
            errors.append(f"line {line_no}: expected at least 2 columns, got {len(row)}")
            continue
        pattern = row[pattern_col].strip().lower()
        target = row[target_col].strip()
        if not pattern or not target:
            errors.append(f"line {line_no}: pattern and target must both be non-empty")
            continue
        rows.append((pattern, target))
    return rows, errors


def all_patterns():
    return load_custom_patterns() + PATTERNS


def is_already_target(genre: str) -> bool:
    custom_targets = {target for _, target in load_custom_patterns()}
    return genre in TARGET_GENRES or genre in custom_targets


_ACCENT_MAP = str.maketrans({
    "á": "a", "à": "a", "â": "a", "ã": "a", "ä": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ó": "o", "ò": "o", "ô": "o", "õ": "o", "ö": "o",
    "ú": "u", "ù": "u", "û": "u", "ü": "u",
    "ñ": "n", "ç": "c",
    "Á": "A", "À": "A", "Â": "A", "Ã": "A", "Ä": "A",
    "É": "E", "È": "E", "Ê": "E", "Ë": "E",
    "Í": "I", "Ì": "I", "Î": "I", "Ï": "I",
    "Ó": "O", "Ò": "O", "Ô": "O", "Õ": "O", "Ö": "O",
    "Ú": "U", "Ù": "U", "Û": "U", "Ü": "U",
    "Ñ": "N", "Ç": "C",
})


def strip_accents(s: str) -> str:
    return s.translate(_ACCENT_MAP)


def split_artist_names(artist: str):
    """Split a combined-artist field ("A/B", "A, B", "A feat. B") into
    individual names so foreign-language detection checks each one
    separately."""
    if not artist:
        return [""]
    normalized = artist
    for sep in (" feat. ", " ft. ", " Feat. ", " Ft. "):
        normalized = normalized.replace(sep, "/")
    for ch in (",", "&", ";"):
        normalized = normalized.replace(ch, "/")
    parts = [p.strip() for p in normalized.split("/") if p.strip()]
    return parts if parts else [artist.strip()]


def strip_kids_genre(genre: str) -> str:
    """Removes any semicolon-delimited segment containing "kids"
    (e.g. "Kids;Pop" -> "Pop"). Returns "" if nothing survives."""
    parts = [p.strip() for p in genre.split(";") if p.strip()]
    kept = [p for p in parts if "kids" not in p.lower()]
    return ";".join(kept)


def test_pattern_against(genre_string: str, pattern: str):
    """Checks whether `pattern` (a single custom-rule pattern, not the
    whole rule table) would match `genre_string`, the same way map_genre()
    matches it: accent-stripped, lowercased substring containment.
    Returns (matches: bool, normalized_genre: str) so the Genre Rule
    Editor's test box can sanity-check a pattern before saving it,
    without needing to save the rule first to see what it does.
    Both matching rules and non-matching are informative here, so this
    doesn't consult PATTERNS/custom rule ordering at all - it only
    answers "would *this* pattern match *this* string".
    """
    normalized = strip_accents(genre_string or "").lower()
    pat = str(pattern or "").strip().lower()
    if not pat:
        return False, normalized
    return pat in normalized, normalized


def find_shadowing_rule(candidate_pattern: str, existing_rows=None, exclude_index=None):
    """Checks whether `candidate_pattern` would be fully shadowed by a
    higher-priority existing rule - i.e. every genre string the
    candidate could ever match also contains some existing pattern
    that's checked first, so the candidate could never actually fire.

    Matching throughout this app is plain substring containment
    (see test_pattern_against/map_genre), so pattern Q fully shadows
    pattern P whenever Q is itself a substring of P: any genre string
    containing P necessarily also contains Q, and Q is checked first
    (custom rules before built-ins, and earlier custom rows before
    later ones - the same precedence preview_genre_mapping/map_genre
    use), so Q always wins before P is ever reached. This is a
    conservative, purely structural check (no sample genre string
    needed) meant for live-typing feedback in the rule editor -
    distinct from the test box's preview_genre_mapping, which checks
    one concrete genre string against the full pipeline instead.

    existing_rows: the custom rule list to check against, in priority
    order (defaults to the persisted custom rules via
    load_custom_patterns() if not given). exclude_index: skip this
    index in existing_rows - used when checking a rule being edited
    in place, so it isn't compared against itself.

    Returns (pattern, target, source) for the first shadowing rule
    found, or None if the candidate isn't shadowed.
    """
    candidate = str(candidate_pattern or "").strip().lower()
    if not candidate:
        return None
    rows = load_custom_patterns() if existing_rows is None else existing_rows
    for idx, (pattern, target) in enumerate(rows):
        if idx == exclude_index:
            continue
        pattern = str(pattern or "").strip().lower()
        if pattern and pattern != candidate and pattern in candidate:
            return (pattern, target, "custom")
    for pattern, target in PATTERNS:
        if pattern and pattern != candidate and pattern in candidate:
            return (pattern, target, "built-in")
    return None


def preview_genre_mapping(genre_string: str, extra_pattern=None, extra_target=None):
    """Runs the full mapping pipeline (custom rules, then built-ins) for
    a sample genre string, same order and precedence map_genre() uses,
    optionally with one extra candidate pattern->target rule inserted at
    the front (highest priority) - so a rule being edited but not yet
    saved can be tested against a genre string before committing it.
    Returns a dict: {"result": <mapped genre>, "matched_pattern": str or
    None, "matched_target": str or None, "matched_source": "candidate"|
    "custom"|"built-in"|None} describing which rule (if any) fired.
    """
    lower = strip_accents(genre_string or "").lower()
    candidates = []
    if extra_pattern and extra_target:
        candidates.append((str(extra_pattern).strip().lower(), str(extra_target).strip(), "candidate"))
    for pattern, target in load_custom_patterns():
        candidates.append((pattern, target, "custom"))
    for pattern, target in PATTERNS:
        candidates.append((pattern, target, "built-in"))

    for pattern, target, source in candidates:
        if pattern and pattern in lower:
            return {"result": target, "matched_pattern": pattern,
                    "matched_target": target, "matched_source": source}
    return {"result": genre_string, "matched_pattern": None,
            "matched_target": None, "matched_source": None}


def search_builtin_patterns(query: str = ""):
    """Returns built-in (pattern, target) rows whose pattern or target
    contains `query` (case-insensitive substring), in the same
    first-match-wins priority order PATTERNS is defined in. An empty
    query returns the full built-in table. Used by the read-only
    "Built-in rules" browser so users can see (and search) the large
    built-in mapping table the app ships with, instead of it only being
    visible by reading source code.
    """
    q = (query or "").strip().lower()
    if not q:
        return list(PATTERNS)
    return [(p, t) for p, t in PATTERNS if q in p.lower() or q in t.lower()]


def map_genre(cleaned_genre: str) -> str:
    """Apply the first matching pattern to a genre string already
    stripped of double-spaces and "kids" segments. Returns the
    original string unchanged if nothing matches."""
    lower = strip_accents(cleaned_genre).lower()
    combined = all_patterns()
    idx = _first_match_index(_get_automaton(), lower)
    if idx is not None:
        return combined[idx][1]
    return cleaned_genre


def genre_lookup_key(clean_genre: str) -> str:
    """Precomputed (already_target, lower-accent-stripped) pair for a
    cleaned genre, so a caller processing many tracks can do the
    is_already_target + map_genre work with a single pass over the
    (now-cached) pattern list instead of two."""
    lower = strip_accents(clean_genre).lower()
    custom = load_custom_patterns()
    custom_targets = {target for _, target in custom}
    if clean_genre in TARGET_GENRES or clean_genre in custom_targets:
        return clean_genre
    combined = custom + PATTERNS
    idx = _first_match_index(_get_automaton(), lower)
    if idx is not None:
        return combined[idx][1]
    return clean_genre


# ---- Junk track-name detection ----
# Matches the "ripped from a numbered CD track list, badly" naming
# pattern: <digits> - <anything> -<n> (or -<n>-<n>, -<n>-<n>-<n>)
# e.g. "006 - UB40 - Please Don't Make Me Cry-1-1-1"
#      "031 - Taylor Swift - Delicate-1-1"
# Covers common dash variants (en dash, em dash, minus sign, figure
# dash, horizontal bar) and non-breaking space, since ripped filenames
# occasionally use one of these instead of a plain ASCII hyphen/space -
# visually indistinguishable in iTunes' UI but not to a strict regex.
#
# The leading "<digits> - " separator REQUIRES at least one whitespace
# character on both sides of the dash (not just "optional" as before).
# Every real ripped-CD junk name has that space (e.g. "031 - Title"),
# but without this requirement the pattern could also match a genuine,
# purely-numeric-with-dashes track title with no spaces at all, e.g.
# "1-800-273-8255" (Logic's song) - digit, dash, digits, ..., dash,
# digits satisfies the old "optional whitespace" version even though
# it isn't a ripped-track-list name at all. Requiring real whitespace
# around the leading separator excludes that false positive while
# still matching every genuine junk-name example above.
_DASH_CHARS = "\\-\u2013\u2012\u2015\u2212\u2010"
_WS_CHARS = r"\s\u00A0"
_JUNK_NAME_RE = re.compile(
    rf"^[{_WS_CHARS}]*\d+[{_WS_CHARS}]+[{_DASH_CHARS}][{_WS_CHARS}]+.+"
    rf"[{_DASH_CHARS}]\d+([{_DASH_CHARS}]\d+){{0,2}}[{_WS_CHARS}]*$",
    re.IGNORECASE,
)


def is_junk_track_name(name: str, fallback_location: str) -> bool:
    """Checked against Track.Name; if Name is blank (no ID3 tag),
    falls back to the bare filename from Location, since that's what
    iTunes' own UI displays in that case."""
    candidate = (name or "").strip()
    if not candidate:
        if not fallback_location:
            return False
        loc = fallback_location.strip()
        if not loc:
            return False
        file_only = loc.replace("/", "\\").rsplit("\\", 1)[-1]
        if "." in file_only:
            file_only = file_only.rsplit(".", 1)[0]
        candidate = file_only.strip()
        if not candidate:
            return False
    return bool(_JUNK_NAME_RE.match(candidate))
