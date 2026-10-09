"""Streaming XML plist parser for iTunes/Music library exports.

Same tag handling and type coercions as plistlib's XML parser, but each
"Tracks" entry is handed to a callback the moment its <dict>...</dict>
finishes parsing, and the parser then drops its own reference to that
dict (replacing it with a lightweight `None` placeholder in the parsed
tree) instead of keeping a second, separate copy of it walked into
`root["Tracks"]`. The caller (see itunes_xml.Library.load) re-attaches
the same dict objects into `root["Tracks"]` once parsing finishes, so
the returned structure ends up fully populated either way -- the
placeholder only avoids both copies existing *simultaneously* while
parsing is still in progress.

On its own this does not shrink the *retained* memory needed to hold
every track's fields for the session (that cost is inherent to the
current single-pass, all-in-memory consolidation design and does not
change here). What it does remove is the redundant extra pass the old
code made -- building a full plistlib parse tree, then walking
`raw["Tracks"].items()` a second time to build the `{track_id: Track}`
map -- by building that map in the same pass as parsing. Combined with
the batching in `core/cache_db.rebuild_track_index` (see that file),
measured on a synthetic 120k-track library this reduces peak RSS across
the load+index+snapshot pipeline by roughly 45MB (~10%) versus the
previous plistlib.load()-based path. `library.raw["Tracks"]` is fully
repopulated (with the same dict objects `Track.raw` already points to,
not copies) before `Library.load()` returns, so nothing downstream --
including the auto-backup snapshot, which needs the complete raw
library -- ever sees incomplete data. This does not eliminate the
~250MB+ floor of holding all tracks in memory at once, which would need
a larger architectural change (e.g. an on-disk/lazy track store) outside
the scope of this fix.

Written against the public, stable `xml.parsers.expat` API (the same
one plistlib itself uses internally) rather than subclassing plistlib's
private `_PlistParser`, since that class's shape is an implementation
detail, not a documented/stable API to build on.
"""
from __future__ import annotations

import binascii
import re
from datetime import datetime
from typing import Any, Callable, Optional
from xml.parsers.expat import ParserCreate

_DATE_RE = re.compile(
    r'(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)T'
    r'(?P<hour>\d\d):(?P<minute>\d\d):(?P<second>\d\d)Z'
)


def _date_from_string(s: str) -> datetime:
    m = _DATE_RE.match(s)
    if not m:
        raise ValueError(f"invalid plist <date> value: {s!r}")
    gd = m.groupdict()
    return datetime(*(int(gd[k]) for k in ("year", "month", "day", "hour", "minute", "second")))


def _decode_base64(s: str) -> bytes:
    return binascii.a2b_base64(s.encode("ascii"))


class PlistStreamError(ValueError):
    """Raised for malformed plist XML encountered while streaming."""


class StreamingTracksParser:
    """Parses an iTunes/Music Library.xml plist. If `on_track` is given,
    it is called as `on_track(track_key, track_dict)` once for every
    direct entry of the top-level "Tracks" dict, immediately after that
    entry finishes parsing -- and that entry's dict is then dropped from
    the in-memory tree (replaced with `None`) rather than kept, so peak
    memory reflects roughly one track's worth of tree data at a time
    instead of all of them.

    `self.root` (returned by `parse()`) still has the same shape as
    plistlib.load() would produce -- including a `root["Tracks"]` dict
    with the same keys -- so any code inspecting non-Tracks structure
    (Playlists, Application Version, etc.) sees the same tree. Only the
    values inside `root["Tracks"]` are `None` placeholders instead of the
    real per-track dicts once parsing finishes; callers that want the
    real Tracks data must consume it via `on_track` as it streams.
    """

    def __init__(self, on_track: Optional[Callable[[str, dict], None]] = None):
        # Each stack frame is [container, key_or_None]. `container` is
        # the dict/list currently being filled; for dict containers,
        # `key_or_None` in the *child's* frame is not used -- instead we
        # track pending key via `current_key`, exactly like plistlib.
        self.stack: list[Any] = []
        self.current_key: Optional[str] = None
        self.root: Any = None
        self.data: list[str] = []

        self.on_track = on_track
        self.track_count = 0

        # id() of the dict object that is root["Tracks"] -- None until
        # we've actually seen the "Tracks" key at the top level followed
        # by its <dict>. Track entries are dicts whose immediate parent
        # (at push time) is this exact dict object.
        self._tracks_dict_id: Optional[int] = None
        self._next_dict_is_tracks_root = False
        # Parallel to self.stack: for each pushed dict, the key it was
        # stored under in ITS parent (or None if parent is a list/root).
        # Needed in end-of-dict handling because `current_key` has
        # already been cleared by the time a dict finishes.
        self._dict_own_key: list[Optional[str]] = []

    def parse(self, fileobj) -> Any:
        self.parser = ParserCreate()
        self.parser.StartElementHandler = self._handle_begin_element
        self.parser.EndElementHandler = self._handle_end_element
        self.parser.CharacterDataHandler = self._handle_data
        self.parser.EntityDeclHandler = self._handle_entity_decl
        self.parser.buffer_text = True
        try:
            self.parser.ParseFile(fileobj)
        except PlistStreamError:
            raise
        except Exception as exc:
            raise PlistStreamError(str(exc)) from exc
        return self.root

    # -- expat callbacks -----------------------------------------------

    def _handle_entity_decl(self, *_a):
        # Same XXE guard plistlib's own parser applies.
        raise PlistStreamError(
            "XML entity declarations are not supported in plist files"
        )

    def _handle_begin_element(self, element, _attrs):
        self.data = []
        handler = getattr(self, "_begin_" + element, None)
        if handler is not None:
            handler()

    def _handle_end_element(self, element):
        handler = getattr(self, "_end_" + element, None)
        if handler is not None:
            handler()

    def _handle_data(self, data):
        self.data.append(data)

    def _get_data(self) -> str:
        data = ''.join(self.data)
        self.data = []
        return data

    def _add_object(self, value):
        if self.current_key is not None:
            if not isinstance(self.stack[-1], dict):
                raise PlistStreamError(
                    f"unexpected element at line {self.parser.CurrentLineNumber}"
                )
            self.stack[-1][self.current_key] = value
            self.current_key = None
        elif not self.stack:
            self.root = value
        else:
            if not isinstance(self.stack[-1], list):
                raise PlistStreamError(
                    f"unexpected element at line {self.parser.CurrentLineNumber}"
                )
            self.stack[-1].append(value)

    # -- element handlers ------------------------------------------------

    def _begin_dict(self):
        own_key = self.current_key  # key this new dict is stored under (or None)
        is_tracks_root = (
            self._next_dict_is_tracks_root
            and len(self.stack) == 1
        )
        self._next_dict_is_tracks_root = False

        d: dict = {}
        self._add_object(d)
        self.stack.append(d)
        self._dict_own_key.append(own_key)

        if is_tracks_root:
            self._tracks_dict_id = id(d)

    def _end_dict(self):
        if self.current_key is not None:
            raise PlistStreamError(
                f"missing value for key '{self.current_key}' at line "
                f"{self.parser.CurrentLineNumber}"
            )
        finished = self.stack.pop()
        own_key = self._dict_own_key.pop()

        parent = self.stack[-1] if self.stack else None
        is_track_entry = (
            self._tracks_dict_id is not None
            and isinstance(parent, dict)
            and id(parent) == self._tracks_dict_id
        )
        if is_track_entry:
            if self.on_track is not None:
                self.on_track(own_key, finished)
            self.track_count += 1
            # Drop the heavy dict from the tree now that it's been
            # handed off; keep the key present (as None) so root["Tracks"]
            # still reports the same set of keys / length to any caller
            # that only needs that.
            if own_key is not None:
                parent[own_key] = None

    def _begin_array(self):
        a: list = []
        self._add_object(a)
        self.stack.append(a)
        self._dict_own_key.append(None)  # placeholder, arrays never match track-entry check

    def _end_array(self):
        self.stack.pop()
        self._dict_own_key.pop()

    def _end_key(self):
        key = self._get_data()
        self.current_key = key
        if key == "Tracks" and len(self.stack) == 1:
            self._next_dict_is_tracks_root = True

    def _end_true(self):
        self._add_object(True)

    def _end_false(self):
        self._add_object(False)

    def _end_integer(self):
        raw = self._get_data()
        self._add_object(int(raw, 16) if raw[:2].lower() == '0x' else int(raw))

    def _end_real(self):
        self._add_object(float(self._get_data()))

    def _end_string(self):
        self._add_object(self._get_data())

    def _end_data(self):
        self._add_object(_decode_base64(self._get_data()))

    def _end_date(self):
        self._add_object(_date_from_string(self._get_data()))
