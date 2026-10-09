"""Centralized emoji/icon constants used in status/log messages and
button labels across gui.py and cleanup_engine.py.

Before this module existed, each emoji (🎵, 🔎, ✅, ❌, ⚠, ...) was a
literal copy-pasted into every f-string that needed it, including the
GUI's `_log_tag_for()` classifier, which matched on those same literals.
That meant three ways for things to quietly drift out of sync: a typo'd
codepoint at one call site, a new status message that forgot to reuse
an existing icon instead of introducing a near-duplicate, or a message
whose icon prefix no longer matched what `_log_tag_for()` was looking
for. Centralizing the glyphs here - one name per meaning - fixes all
three, and gives any future localization pass a single place to swap
text labels without touching call sites.

Only the glyphs themselves live here; the surrounding message text
stays inline at each call site (unchanged from before), since that
text is call-site-specific and doesn't benefit from centralizing.
"""

# Status/outcome icons - used as message prefixes throughout gui.py and
# cleanup_engine.py, and by GenreCleanupApp._log_tag_for() to classify a
# log line's semantic tag (success/warning/error/info) from its prefix.
MUSIC = "🎵"
LOOKUP = "🔎"
GLOBE = "🌐"
PREVIEW = "👀"
REPEAT = "🔁"
SUCCESS = "✅"
CHECK = "✓"
CROSS = "✗"
ERROR = "❌"
CLOSE = "✕"
WARNING = "⚠"
FOLDER = "📁"
TRASH = "🗑"
PAUSE = "⏸"
PLAY = "▶"
STOP_SQUARE = "■"
STOPPED = "⏹"
UNDO = "↺"
GEAR = "⚙"
PLUG = "🔌"
BOOKS = "📚"
BROOM = "🧹"

# Icon groups matching GenreCleanupApp._log_tag_for()'s existing
# classification rules - kept here so the prefix tuples it checks
# against can't silently drift from the icons actually in use above.
ERROR_ICONS = (WARNING, ERROR, CLOSE)
ERROR_ONLY_ICONS = (ERROR, CLOSE)
SUCCESS_ICONS = (SUCCESS, CHECK, REPEAT)
INFO_ICONS = (LOOKUP, GLOBE, BOOKS, PLUG, PREVIEW, FOLDER, UNDO, PLAY, PAUSE, STOP_SQUARE)
