"""
Embedded-artwork extraction.

Library.xml never contains artwork bytes -- only an "Artwork Count"
integer (see itunes_xml.Track). To actually preview a track's cover art
in the duplicate-review UI, this reads the embedded image directly from
the track's own audio file on disk, using its Location field.

Deliberately dependency-free: hand-rolled, read-only parsers for the
embedded-artwork containers actually in common use --
  - MP3: ID3v2 APIC frame (v2.2 "PIC" and v2.3/2.4 "APIC")
  - MP4/M4A/M4P: the 'covr' atom inside moov/udta/meta/ilst -- this is
    also where Apple Lossless (ALAC) artwork lives, since ALAC is itself
    just audio packed into an .m4a MP4 container, not a distinct
    container format of its own, so no separate ALAC-specific parsing is
    needed here
  - FLAC: the METADATA_BLOCK_PICTURE ("PICTURE", type 6) block in the
    file's own metadata-block chain (v1.7.6)
covering the vast majority of real iTunes/Apple Music libraries without
adding a new third-party dependency (e.g. mutagen) for what is, on
inspection, a small, well-documented binary format in each case. Ogg
Vorbis and other less common iTunes formats are simply not supported here
(read_embedded_artwork returns None) rather than growing this into a
general-purpose tag library.

Nothing here writes to any file -- read-only, used only to render a
preview thumbnail.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

# Hard cap on how much of a file we'll read while searching for artwork,
# so a huge or malformed file can't make the UI hang. Real embedded
# artwork is essentially always well within a few MB of the file start
# (MP3 ID3 headers) or discoverable via the MP4 atom sizes themselves
# (which we trust and seek through rather than scanning byte-by-byte).
_MAX_ID3_SCAN_BYTES = 20 * 1024 * 1024


def file_uri_to_path(uri: str) -> Optional[Path]:
    """Converts a Library.xml 'Location' file:// URI to a local Path, or
    None if it isn't a local file reference (streamed/cloud/remote).

    Bug fix: on Windows, iTunes writes drive-letter locations as
    "file://localhost/C:/Users/.../Track.mp3" -- urlparse's .path for that
    URI is "/C:/Users/.../Track.mp3", with a leading slash in front of the
    drive letter. Path() on Windows treats that leading slash as part of
    the path rather than stripping it, producing a location like
    "\\C:\\Users\\..." that never exists on disk, so path.is_file() was
    always False and embedded artwork could never be found for any
    Windows-style Location -- the overwhelming majority of libraries this
    app is built for (see build.spec/README: Windows-only distribution).
    A leading "/<drive letter>:/" is stripped before constructing the
    Path; plain POSIX-style paths (no drive letter) are unaffected."""
    if not uri:
        return None
    try:
        parsed = urlparse(uri)
    except ValueError:
        return None
    if parsed.scheme != "file":
        return None
    try:
        raw_path = unquote(parsed.path)
    except (ValueError, OSError):
        return None
    if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]
    try:
        return Path(raw_path)
    except (ValueError, OSError):
        return None


def read_embedded_artwork(path: Path) -> Optional[bytes]:
    """Returns the first embedded cover image's raw bytes (JPEG/PNG),
    or None if the file doesn't exist, isn't a supported format, or has
    no embedded artwork. Never raises -- any parse failure is treated the
    same as "no artwork found", since this only feeds an optional preview
    thumbnail, not anything that should ever block the app."""
    try:
        if not path.is_file():
            return None
        suffix = path.suffix.lower()
        if suffix in (".mp3",):
            return _read_id3_apic(path)
        if suffix in (".m4a", ".m4p", ".mp4"):
            return _read_mp4_covr(path)
        if suffix in (".flac",):
            return _read_flac_picture(path)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------- MP3/ID3

def _read_id3_apic(path: Path) -> Optional[bytes]:
    with open(path, "rb") as f:
        header = f.read(10)
        if len(header) < 10 or header[0:3] != b"ID3":
            return None
        version_major = header[3]
        flags = header[5]
        tag_size = _syncsafe_to_int(header[6:10])
        tag_size = min(tag_size, _MAX_ID3_SCAN_BYTES)

        body = f.read(tag_size)

        offset = 0
        if flags & 0x40:  # extended header present
            if len(body) < 4:
                return None
            ext_size = _syncsafe_to_int(body[0:4]) if version_major >= 4 else struct.unpack(">I", body[0:4])[0]
            offset += ext_size

        if version_major == 2:
            return _scan_id3v22_frames(body, offset)
        return _scan_id3v23plus_frames(body, offset, version_major)


def _syncsafe_to_int(b: bytes) -> int:
    result = 0
    for byte in b:
        result = (result << 7) | (byte & 0x7F)
    return result


def _scan_id3v23plus_frames(body: bytes, offset: int, version_major: int) -> Optional[bytes]:
    while offset + 10 <= len(body):
        frame_id = body[offset:offset + 4]
        if frame_id == b"\x00\x00\x00\x00":
            break  # padding reached
        size_bytes = body[offset + 4:offset + 8]
        frame_size = (
            _syncsafe_to_int(size_bytes) if version_major >= 4
            else struct.unpack(">I", size_bytes)[0]
        )
        frame_start = offset + 10
        frame_end = frame_start + frame_size
        if frame_size <= 0 or frame_end > len(body):
            break
        if frame_id == b"APIC":
            image = _parse_apic_payload(body[frame_start:frame_end])
            if image:
                return image
        offset = frame_end
    return None


def _scan_id3v22_frames(body: bytes, offset: int) -> Optional[bytes]:
    # ID3v2.2 uses 3-char frame ids and 3-byte sizes; "PIC" is the
    # artwork frame (format differs slightly from APIC: fixed 3-char
    # image format code instead of a MIME string).
    while offset + 6 <= len(body):
        frame_id = body[offset:offset + 3]
        if frame_id == b"\x00\x00\x00":
            break
        size_bytes = body[offset + 3:offset + 6]
        frame_size = struct.unpack(">I", b"\x00" + size_bytes)[0]
        frame_start = offset + 6
        frame_end = frame_start + frame_size
        if frame_size <= 0 or frame_end > len(body):
            break
        if frame_id == b"PIC":
            payload = body[frame_start:frame_end]
            image = _parse_pic_payload(payload)
            if image:
                return image
        offset = frame_end
    return None


def _parse_apic_payload(payload: bytes) -> Optional[bytes]:
    if len(payload) < 2:
        return None
    # text_encoding(1) + mime_type(null-terminated ascii) + picture_type(1)
    # + description(null-terminated, encoding-dependent) + image data.
    mime_end = payload.find(b"\x00", 1)
    if mime_end == -1:
        return None
    pos = mime_end + 1 + 1  # skip null + picture_type byte
    if pos >= len(payload):
        return None
    text_encoding = payload[0]
    if text_encoding in (1, 2):  # UTF-16 variants: null terminator is 2 bytes
        desc_end = payload.find(b"\x00\x00", pos)
        if desc_end == -1:
            return None
        image_start = desc_end + 2
    else:
        desc_end = payload.find(b"\x00", pos)
        if desc_end == -1:
            return None
        image_start = desc_end + 1
    image = payload[image_start:]
    return image if image else None


def _parse_pic_payload(payload: bytes) -> Optional[bytes]:
    if len(payload) < 5:
        return None
    # text_encoding(1) + image_format(3, e.g. b"JPG") + picture_type(1) +
    # description(null-terminated) + image data.
    pos = 1 + 3 + 1
    if pos >= len(payload):
        return None
    desc_end = payload.find(b"\x00", pos)
    if desc_end == -1:
        return None
    image = payload[desc_end + 1:]
    return image if image else None


# --------------------------------------------------------------- MP4/M4A

def _read_mp4_covr(path: Path) -> Optional[bytes]:
    with open(path, "rb") as f:
        moov = _find_mp4_atom(f, b"moov", file_end=path.stat().st_size)
        if moov is None:
            return None
        moov_start, moov_size = moov
        udta = _find_mp4_atom(f, b"udta", file_end=moov_start + moov_size, start=moov_start + 8)
        if udta is None:
            return None
        udta_start, udta_size = udta
        meta = _find_mp4_atom(f, b"meta", file_end=udta_start + udta_size, start=udta_start + 8)
        if meta is None:
            return None
        meta_start, meta_size = meta
        # 'meta' has a 4-byte version/flags field before its children.
        ilst = _find_mp4_atom(f, b"ilst", file_end=meta_start + meta_size, start=meta_start + 12)
        if ilst is None:
            return None
        ilst_start, ilst_size = ilst
        covr = _find_mp4_atom(f, b"covr", file_end=ilst_start + ilst_size, start=ilst_start + 8)
        if covr is None:
            return None
        covr_start, covr_size = covr
        # 'covr' contains one or more 'data' sub-atoms; take the first.
        data = _find_mp4_atom(f, b"data", file_end=covr_start + covr_size, start=covr_start + 8)
        if data is None:
            return None
        data_start, data_size = data
        # data atom: 8-byte header + 4-byte type flag + 4-byte reserved,
        # then the raw image bytes.
        f.seek(data_start + 8 + 4 + 4)
        image = f.read(data_size - 8 - 4 - 4)
        return image if image else None



# ----------------------------------------------------------------- FLAC

# FLAC metadata block type for an embedded PICTURE block (the format's
# own artwork container -- see
# https://xiph.org/flac/format.html#metadata_block_picture). Unlike an
# Ogg/Vorbis comment's METADATA_BLOCK_PICTURE field, a native FLAC
# PICTURE block stores the image bytes directly (no base64 layer), so
# nothing beyond struct unpacking is needed to read it.
_FLAC_BLOCK_TYPE_PICTURE = 6


def _read_flac_picture(path: Path) -> Optional[bytes]:
    with open(path, "rb") as f:
        if f.read(4) != b"fLaC":
            return None
        bytes_scanned = 4
        while bytes_scanned < _MAX_ID3_SCAN_BYTES:
            header = f.read(4)
            if len(header) < 4:
                return None
            bytes_scanned += 4
            is_last = bool(header[0] & 0x80)
            block_type = header[0] & 0x7F
            block_size = struct.unpack(">I", b"\x00" + header[1:4])[0]
            if block_type == _FLAC_BLOCK_TYPE_PICTURE:
                payload = f.read(block_size)
                bytes_scanned += block_size
                image = _parse_flac_picture_payload(payload)
                if image:
                    return image
                # A malformed/undecodable PICTURE block is treated as "no
                # artwork here", same as any other parse failure, rather
                # than continuing to scan for a second PICTURE block --
                # FLAC files in practice carry at most one.
                return None
            if is_last:
                return None
            f.seek(block_size, 1)
            bytes_scanned += block_size
        return None  # exceeded the scan cap without finding a PICTURE block


def _parse_flac_picture_payload(payload: bytes) -> Optional[bytes]:
    """Parses a FLAC METADATA_BLOCK_PICTURE payload (big-endian, per the
    FLAC spec): picture_type(4) + mime_length(4) + mime(mime_length) +
    description_length(4) + description(description_length) + width(4) +
    height(4) + depth(4) + colors_used(4) + data_length(4) +
    data(data_length)."""
    if len(payload) < 4:
        return None
    pos = 4  # skip picture_type
    if pos + 4 > len(payload):
        return None
    mime_length = struct.unpack(">I", payload[pos:pos + 4])[0]
    pos += 4 + mime_length
    if pos + 4 > len(payload):
        return None
    desc_length = struct.unpack(">I", payload[pos:pos + 4])[0]
    pos += 4 + desc_length
    # width(4) + height(4) + depth(4) + colors_used(4) precede data_length.
    pos += 16
    if pos + 4 > len(payload):
        return None
    data_length = struct.unpack(">I", payload[pos:pos + 4])[0]
    pos += 4
    image = payload[pos:pos + data_length]
    return image if image else None


def _find_mp4_atom(f, target: bytes, file_end: int, start: int = 0) -> Optional[tuple[int, int]]:
    """Linear scan for a top-level-within-range MP4 atom named `target`,
    starting at byte offset `start` and not reading past `file_end`.
    Returns (atom_start_offset, atom_size) if found, else None."""
    pos = start
    while pos + 8 <= file_end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return None
        size = struct.unpack(">I", header[0:4])[0]
        atom_type = header[4:8]
        if size == 1:
            # 64-bit extended size follows immediately.
            ext = f.read(8)
            if len(ext) < 8:
                return None
            size = struct.unpack(">Q", ext)[0]
        if size < 8:
            return None  # malformed; bail out rather than looping forever
        if atom_type == target:
            return (pos, size)
        pos += size
    return None
