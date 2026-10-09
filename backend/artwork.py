"""Small, bounded artwork thumbnails; cache invalidates when the media file changes."""
import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from . import legacy


def encode_thumbnail(data, size=96):
    if not data or len(data) > 20 * 1024 * 1024: return None
    try:
        with Image.open(BytesIO(data)) as image:
            image.thumbnail((size, size))
            output = BytesIO()
            image.convert('RGB').save(output, format='JPEG', quality=80)
            return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


@lru_cache(maxsize=256)
def _read(path, modified, size):
    return encode_thumbnail(legacy.read_embedded_artwork(Path(path)))


def thumbnail(path):
    if not path: return None
    try:
        file = Path(path); stat = file.stat()
        return _read(str(file), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=128)
def _image_file(path, modified, size):
    if size > 20 * 1024 * 1024: return None
    return encode_thumbnail(Path(path).read_bytes())


def image_file(path):
    try:
        file = Path(path); stat = file.stat()
        return _image_file(str(file), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError): return None
