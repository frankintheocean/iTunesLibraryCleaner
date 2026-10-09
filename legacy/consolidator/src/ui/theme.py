"""
macOS/iOS-inspired stylesheet for the Windows app, in both a light and a
dark variant. `current_qss()` picks between them by following the current
Windows theme (falling back to light if that can't be determined), so the
app matches the rest of the OS instead of always forcing light mode.

Design tokens -- light (chosen deliberately, not Qt defaults):
  Background:      #F5F5F7  (Apple's marketing-site neutral, not pure white)
  Surface/card:     #FFFFFF
  Border/hairline:  #D8D8DC
  Text primary:     #1D1D1F
  Text secondary:   #6E6E73
  Accent:           #0A84FF  (macOS system blue, dark-mode variant reads well
                     on light backgrounds too and matches Big Sur+ accents)
  Success:          #30D158
  Warning:          #FF9F0A
  Danger:           #FF453A

Design tokens -- dark (macOS Dark Mode equivalents of the same tokens):
  Background:      #1E1E20
  Surface/card:     #2A2A2D
  Border/hairline:  #3D3D40
  Text primary:     #F5F5F7
  Text secondary:   #98989D
  Accent:           #0A84FF  (same accent -- Apple keeps system blue
                     identical across light/dark, it already has enough
                     contrast on both)
  Success:          #32D74B
  Warning:          #FF9F0A
  Danger:           #FF453A

Typography: SF Pro is requested first, but it is an Apple system font and
is NOT licensed for redistribution or use on Windows -- so it is never
bundled with this app, only referenced by name. On the near-total majority
of Windows machines where it isn't installed, Qt's font matching silently
falls through to Segoe UI Variable (Windows 11 default), which was chosen
as the closest visual match to SF Pro. Do not add an actual SF Pro font
file to this repo/installer; that would be a license violation.
"""

from __future__ import annotations

import re
import sys

from .design_tokens import radius, size, spacing, type_scale

FONT_FAMILY = "'SF Pro Display', 'SF Pro Text', 'Segoe UI Variable', 'Segoe UI', -apple-system, sans-serif"

# ---------------------------------------------------------------------------
# Named accent themes
#
# QSS_LIGHT/QSS_DARK below are the original, hand-tuned "Blue" theme (the
# app's default/only theme prior to this) and are left byte-for-byte
# unchanged so existing behavior/appearance never regresses. Every other
# named theme is derived from those two stylesheets by swapping the single
# accent hue (#0A84FF, used for buttons, tabs, progress fill, links, focus
# highlights, etc.) for a different hue -- the layout, spacing, surface and
# text colors from the original design stay identical across every theme,
# only the accent (and the few things computed from it, like hover/pressed
# shades and the text color the accent must contrast against) changes. This
# keeps all ten themes visually consistent with each other and avoids
# hand-authoring ~700 lines of QSS ten times over.
#
# Each entry: display label -> (accent, accent_hover, accent_pressed,
# accent_disabled_light, accent_disabled_dark, accent_on_text). accent_on_text
# is the color used for text/icons drawn on top of a solid accent fill (e.g.
# QPushButton#primary), chosen per-theme for contrast (white on most hues,
# near-black on the lightest ones).
THEME_ACCENTS: dict[str, dict[str, str]] = {
    "blue": {
        "label": "Blue (default)",
        "accent": "#0A84FF",
        "hover_light": "#0074E0",
        "hover_dark": "#3399FF",
        "disabled_light": "#A8D1FF",
        "disabled_dark": "#2E4A66",
        "on_text": "#FFFFFF",
    },
    "purple": {
        "label": "Purple",
        "accent": "#8E44EC",
        "hover_light": "#7A2FD8",
        "hover_dark": "#A566F5",
        "disabled_light": "#D9BFF9",
        "disabled_dark": "#4A3466",
        "on_text": "#FFFFFF",
    },
    "pink": {
        "label": "Pink",
        "accent": "#FF2D8A",
        "hover_light": "#E01B74",
        "hover_dark": "#FF5CA3",
        "disabled_light": "#FFC2DD",
        "disabled_dark": "#66293F",
        "on_text": "#FFFFFF",
    },
    "red": {
        "label": "Red",
        "accent": "#E0342C",
        "hover_light": "#C22821",
        "hover_dark": "#F0564E",
        "disabled_light": "#F5B8B5",
        "disabled_dark": "#5C2724",
        "on_text": "#FFFFFF",
    },
    "orange": {
        "label": "Orange",
        "accent": "#FF7A17",
        "hover_light": "#E5680A",
        "hover_dark": "#FF9645",
        "disabled_light": "#FFCEA0",
        "disabled_dark": "#663B10",
        "on_text": "#FFFFFF",
    },
    "yellow": {
        "label": "Yellow",
        "accent": "#D9A400",
        "hover_light": "#B98A00",
        "hover_dark": "#F0BE2E",
        "disabled_light": "#F2DA96",
        "disabled_dark": "#5C4A0F",
        "on_text": "#1D1D1F",
    },
    "green": {
        "label": "Green",
        "accent": "#1FA34A",
        "hover_light": "#178A3D",
        "hover_dark": "#34C168",
        "disabled_light": "#A9E0BC",
        "disabled_dark": "#1E4A2C",
        "on_text": "#FFFFFF",
    },
    "teal": {
        "label": "Teal",
        "accent": "#00A3A3",
        "hover_light": "#008787",
        "hover_dark": "#2ABFBF",
        "disabled_light": "#9EDDDD",
        "disabled_dark": "#1B4A4A",
        "on_text": "#FFFFFF",
    },
    "graphite": {
        "label": "Graphite",
        "accent": "#5C5C63",
        "hover_light": "#48484E",
        "hover_dark": "#77777E",
        "disabled_light": "#C6C6CA",
        "disabled_dark": "#3A3A3F",
        "on_text": "#FFFFFF",
    },
    "indigo": {
        "label": "Indigo",
        "accent": "#5856D6",
        "hover_light": "#4644B8",
        "hover_dark": "#7472E8",
        "disabled_light": "#C3C2F2",
        "disabled_dark": "#332F66",
        "on_text": "#FFFFFF",
    },
}

# Order controls how themes are listed in Settings -> General; "blue" is
# first/default to match the app's pre-existing look for anyone upgrading.
THEME_ORDER: tuple[str, ...] = (
    "blue", "purple", "pink", "red", "orange",
    "yellow", "green", "teal", "graphite", "indigo",
)

# The one accent hue baked into the original hand-authored QSS_LIGHT/
# QSS_DARK strings below, used as the find target when deriving the other
# nine themes' stylesheets. Case matters for the substitution but not for
# matching (see _recolor()).
_BASE_ACCENT_HEX = "#0A84FF"
_BASE_HOVER_LIGHT_HEX = "#0074E0"
_BASE_HOVER_DARK_HEX = "#3399FF"
_BASE_DISABLED_LIGHT_HEX = "#A8D1FF"
_BASE_DISABLED_DARK_HEX = "#2E4A66"


# ---------------------------------------------------------------------------
# Named base palettes (v2.0)
#
# THEME_ACCENTS above only ever swaps the single accent hue; the base
# surface/text colors documented in this module's docstring (background,
# card surface, border, primary/secondary text, and the few tints derived
# from them -- e.g. QSS_LIGHT's #FAFAFB/#F0F0F2/#E5E5E8, QSS_DARK's
# #232326/#333336/#A0A0A5) were always the same two fixed sets (one for
# "light", one for "dark"), no matter which accent was picked. These 8
# palettes are new, additional base surface treatments -- distinct from
# both "Light" and "Dark" and from the accent-only THEME_ACCENTS above --
# selectable the same way (see _split_preference/current_qss), so someone
# who wants e.g. a warm paper-toned light mode or a cool near-black dark
# mode isn't limited to the original two.
#
# Each palette entry maps the same base tokens QSS_LIGHT/QSS_DARK already
# use, keyed by the literal hex each replaces (see _BASE_LIGHT_TOKENS/
# _BASE_DARK_TOKENS below) -- background, card surface, border/hairline,
# primary text, secondary text, and the handful of derived neutral tints
# used for hover/disabled/subtle-fill states. "family" says which of
# QSS_LIGHT/QSS_DARK this palette is derived from (its structure --
# layout, spacing, which selectors get which token -- is otherwise
# unchanged; only these token values differ), so a palette can offer a
# genuinely dark or genuinely light surface treatment while reusing the
# exact same, already-tested stylesheet structure.
BASE_PALETTES: dict[str, dict[str, str]] = {
    "paper": {
        "label": "Paper",
        "family": "light",
        "background": "#F7F3EC",
        "surface": "#FFFDF8",
        "border": "#E3DACB",
        "text_primary": "#2B241A",
        "text_secondary": "#7A6F5C",
        "tint_a": "#FBF8F2",  # lightest fill (was #FAFAFB)
        "tint_b": "#F0E9DC",  # subtle fill (was #F0F0F2)
        "tint_c": "#E9E0D0",  # hairline-adjacent fill (was #E5E5E8)
    },
    "slate": {
        "label": "Slate",
        "family": "light",
        "background": "#EEF1F4",
        "surface": "#FBFCFD",
        "border": "#CBD3DB",
        "text_primary": "#1B2430",
        "text_secondary": "#5B6B7C",
        "tint_a": "#F5F7F9",
        "tint_b": "#E6EAEE",
        "tint_c": "#DCE2E8",
    },
    "sand": {
        "label": "Sand",
        "family": "light",
        "background": "#F4EFE6",
        "surface": "#FFFCF6",
        "border": "#DCCFB8",
        "text_primary": "#332B1E",
        "text_secondary": "#8A7A5F",
        "tint_a": "#FAF6EE",
        "tint_b": "#EEE4D2",
        "tint_c": "#E3D5BC",
    },
    "mint": {
        "label": "Mint",
        "family": "light",
        "background": "#EEF6F1",
        "surface": "#FBFEFC",
        "border": "#CBE2D3",
        "text_primary": "#16281E",
        "text_secondary": "#57715F",
        "tint_a": "#F4FAF6",
        "tint_b": "#E2F0E7",
        "tint_c": "#D3E7DA",
    },
    "midnight": {
        "label": "Midnight",
        "family": "dark",
        "background": "#12141C",
        "surface": "#1B1E29",
        "border": "#2E3242",
        "text_primary": "#F2F3F8",
        "text_secondary": "#8D93A8",
        "tint_a": "#1E212C",  # replaces #232326
        "tint_b": "#282C3A",  # replaces #333336
        "tint_c": "#767C90",  # replaces #A0A0A5
    },
    "charcoal": {
        "label": "Charcoal",
        "family": "dark",
        "background": "#19191A",
        "surface": "#232323",
        "border": "#38383A",
        "text_primary": "#F2F2F0",
        "text_secondary": "#9B9B96",
        "tint_a": "#202020",
        "tint_b": "#2C2C2C",
        "tint_c": "#8C8C87",
    },
    "espresso": {
        "label": "Espresso",
        "family": "dark",
        "background": "#1C1512",
        "surface": "#271E19",
        "border": "#3E322A",
        "text_primary": "#F3EBE4",
        "text_secondary": "#A6907F",
        "tint_a": "#221A16",
        "tint_b": "#332822",
        "tint_c": "#8F7A69",
    },
    "forest": {
        "label": "Forest",
        "family": "dark",
        "background": "#131C17",
        "surface": "#1B2721",
        "border": "#2E4038",
        "text_primary": "#EDF5F0",
        "text_secondary": "#8AA598",
        "tint_a": "#182320",
        "tint_b": "#22332C",
        "tint_c": "#729183",
    },
}

# Display order for the base-palette picker; grouped light-family then
# dark-family so the combo box reads as two visual clusters.
BASE_PALETTE_ORDER: tuple[str, ...] = (
    "paper", "slate", "sand", "mint",
    "midnight", "charcoal", "espresso", "forest",
)

# The literal hex tokens QSS_LIGHT/QSS_DARK were originally authored with,
# in the same key order BASE_PALETTES entries use above, so _recolor_base
# can build its find/replace pairs generically instead of hand-writing 8
# separate substitution tables. Order matters: longer/more-specific tints
# are listed after the primary surface tokens they're derived from so a
# broader substitution never accidentally clobbers a narrower one already
# written by an earlier replacement (each source hex is distinct, so in
# practice this is just for readability/maintenance, not correctness).
_BASE_LIGHT_TOKENS: dict[str, str] = {
    "background": "#F5F5F7",
    "surface": "#FFFFFF",
    "border": "#D8D8DC",
    "text_primary": "#1D1D1F",
    "text_secondary": "#6E6E73",
    "tint_a": "#FAFAFB",
    "tint_b": "#F0F0F2",
    "tint_c": "#E5E5E8",
}
_BASE_DARK_TOKENS: dict[str, str] = {
    "background": "#1E1E20",
    "surface": "#2A2A2D",
    "border": "#3D3D40",
    "text_primary": "#F5F5F7",
    "text_secondary": "#98989D",
    "tint_a": "#232326",
    "tint_b": "#333336",
    "tint_c": "#A0A0A5",
}


def _recolor_base(qss: str, family: str, palette_id: str | None) -> str:
    """Substitutes QSS_LIGHT's or QSS_DARK's base surface/text tokens for
    the given named palette's tokens -- the base-palette equivalent of
    _recolor()'s accent substitution above, same technique (plain
    string replacement over the already-authored stylesheet, so layout/
    structure/spacing never change, only these literal colors).

    `family` is "light" or "dark" (which base stylesheet `qss` is), used
    to pick the matching token table to replace *from*. `palette_id` of
    None or "" leaves `qss` untouched (the original Light/Dark look).
    Falls back to no-op for any unrecognized palette_id or a
    family/palette family mismatch, rather than raising, so a corrupt or
    stale saved setting can never prevent a stylesheet from applying.
    """
    if not palette_id or palette_id not in BASE_PALETTES:
        return qss
    spec = BASE_PALETTES[palette_id]
    if spec["family"] != family:
        return qss
    source_tokens = _BASE_LIGHT_TOKENS if family == "light" else _BASE_DARK_TOKENS
    for token_name, source_hex in source_tokens.items():
        target_hex = spec[token_name]
        qss = re.sub(re.escape(source_hex), target_hex, qss, flags=re.IGNORECASE)
    return qss


def base_palette_choices() -> list[tuple[str, str]]:
    """(label, palette_id) pairs in display order, for populating a base-
    palette picker combo box -- separate from theme_choices() (accent
    hues) and separate from the Light/Dark mode toggle."""
    return [(BASE_PALETTES[pid]["label"], pid) for pid in BASE_PALETTE_ORDER]


def system_prefers_dark() -> bool:
    """Best-effort detection of whether Windows is currently set to a dark
    app theme, so the app can follow the OS instead of always being light.

    Reads the same registry value Windows itself uses
    (HKCU\\...\\Personalize!AppsUseLightTheme, 0 = dark, 1 = light).
    Falls back to False (light) if the key is missing, unreadable, or this
    isn't Windows -- e.g. running the source tree on macOS/Linux during
    development -- so the app never fails to start over a theme lookup.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except (OSError, FileNotFoundError, ImportError, ValueError):
        return False


def _split_preference(preference: str) -> tuple[str, str, str]:
    """Splits a stored preference string into (mode, theme_id, palette_id).

    Supported forms:
      "auto" / "light" / "dark"                    -- legacy, pre-theming
      "auto:purple" / "light:teal" / etc.           -- mode + accent theme
      "dark:teal:midnight" / "light:blue:paper"     -- v2.0: mode + accent
                                                         + named base palette

    Anything that doesn't parse into a recognized mode falls back to
    ("auto", "blue", "") -- the original default look -- rather than
    raising, so a corrupt/stale saved setting can never prevent the app
    from starting or applying a stylesheet. An unrecognized/mismatched
    palette_id (e.g. a dark-family palette saved while mode was "light")
    resolves to "" (no base-palette override, i.e. the original Light/
    Dark look for that mode) rather than raising -- see _recolor_base's
    own family-mismatch fallback for the second half of that guarantee.
    """
    parts = preference.split(":", 2)
    mode = parts[0] if parts else "auto"
    theme_id = parts[1] if len(parts) > 1 else "blue"
    palette_id = parts[2] if len(parts) > 2 else ""
    if mode not in ("auto", "light", "dark"):
        return "auto", "blue", ""
    if theme_id not in THEME_ACCENTS:
        theme_id = "blue"
    if palette_id and palette_id not in BASE_PALETTES:
        palette_id = ""
    return mode, theme_id, palette_id


def _recolor(qss: str, theme_id: str) -> str:
    """Substitutes the base ("blue") theme's accent hues for the given
    named theme's hues. A plain string/regex substitution rather than
    re-templating the whole stylesheet -- this is intentionally the
    smallest change that produces a fully-recolored, structurally
    identical stylesheet, since QSS_LIGHT/QSS_DARK are otherwise kept
    exactly as originally authored.
    """
    if theme_id == "blue":
        return qss
    spec = THEME_ACCENTS[theme_id]
    replacements = (
        (_BASE_ACCENT_HEX, spec["accent"]),
        (_BASE_HOVER_LIGHT_HEX, spec["hover_light"]),
        (_BASE_HOVER_DARK_HEX, spec["hover_dark"]),
        (_BASE_DISABLED_LIGHT_HEX, spec["disabled_light"]),
        (_BASE_DISABLED_DARK_HEX, spec["disabled_dark"]),
    )
    for old, new in replacements:
        qss = re.sub(re.escape(old), new, qss, flags=re.IGNORECASE)
    # QPushButton#primary's text color is hardcoded "white" in the base
    # stylesheet (light-on-blue always contrasts); themes whose accent is
    # light enough to need dark-on-accent text (currently just Yellow)
    # override that single rule here rather than baking a second color
    # token into every accent-colored QSS block above.
    if spec["on_text"].upper() != "#FFFFFF":
        qss = re.sub(
            r"(QPushButton#primary\s*\{[^}]*?color:\s*)white(;)",
            rf"\g<1>{spec['on_text']}\2",
            qss,
        )
    return qss


def current_qss(preference: str = "auto") -> str:
    """Stylesheet for the given theme preference.

    preference: "auto" (follow the OS -- the original, still-default
    behavior), "light", or "dark", optionally suffixed with
    ":<theme_id>" to select one of the ten named accent themes (see
    THEME_ACCENTS/THEME_ORDER), e.g. "dark:teal", and (v2.0) further
    suffixed with ":<palette_id>" to select one of the 8 named base
    palettes (see BASE_PALETTES/BASE_PALETTE_ORDER) on top of that, e.g.
    "dark:teal:midnight". Bare "auto"/"light"/"dark" (no suffix) is still
    accepted for backward compatibility with settings saved before
    theming existed, and resolves to the original Blue accent with no
    base-palette override. Any other/unrecognized value falls back to
    "auto" (Blue, no palette override) rather than raising, so a corrupt/
    stale saved setting can never prevent the app from starting or
    applying a stylesheet.
    """
    mode, theme_id, palette_id = _split_preference(preference)
    if mode == "light":
        base = QSS_LIGHT
        family = "light"
    elif mode == "dark":
        base = QSS_DARK
        family = "dark"
    else:
        if system_prefers_dark():
            base, family = QSS_DARK, "dark"
        else:
            base, family = QSS_LIGHT, "light"
    base = _recolor_base(base, family, palette_id)
    return _recolor(base, theme_id)


def accent_color(preference: str = "auto") -> str:
    """The single accent hex color in effect for `preference`, for the
    handful of places outside theme.py that draw with the accent color
    directly (e.g. the health-history chart's line color, badge accents)
    instead of going through the app-wide stylesheet. Kept in sync with
    current_qss() by construction since both read from THEME_ACCENTS.
    """
    _, theme_id, _ = _split_preference(preference)
    return THEME_ACCENTS[theme_id]["accent"]


def theme_choices() -> list[tuple[str, str]]:
    """(label, theme_id) pairs in display order, for populating a theme
    picker combo box."""
    return [(THEME_ACCENTS[tid]["label"], tid) for tid in THEME_ORDER]


QSS_LIGHT = f"""
* {{
    font-family: {FONT_FAMILY};
}}

QMainWindow, QWidget#centralWidget {{
    background-color: #F5F5F7;
}}

QLabel {{
    color: #1D1D1F;
}}

QLabel#eyebrow {{
    color: #6E6E73;
    font-size: {type_scale.eyebrow};
    font-weight: 600;
    letter-spacing: {spacing.eyebrow_tracking};
    text-transform: uppercase;
}}

QLabel#pageTitle {{
    font-size: {type_scale.title};
    font-weight: 600;
    color: #1D1D1F;
}}

QLabel#subtitle {{
    color: #6E6E73;
    font-size: {type_scale.body};
}}

QLabel#phaseLabel {{
    color: #0A84FF;
    font-size: {type_scale.caption};
    font-weight: 600;
}}

QFrame#card {{
    background-color: #FFFFFF;
    border: 1px solid #D8D8DC;
    border-radius: {radius.card};
}}

QToolBar#mainToolBar {{
    background-color: #FFFFFF;
    border: none;
    border-bottom: 1px solid #D8D8DC;
    padding: {spacing.toolbar};
    spacing: {spacing.toolbar_gap};
}}

QToolBar#mainToolBar QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {radius.control};
    padding: {spacing.toolbar_button};
    color: #1D1D1F;
    font-size: {type_scale.body};
}}

QToolBar#mainToolBar QToolButton:hover {{
    background-color: #F0F0F2;
    border: 1px solid #D8D8DC;
}}

QToolBar#mainToolBar QToolButton:pressed {{
    background-color: #E5E5E8;
}}

QToolBar#mainToolBar QToolButton:disabled {{
    color: #A0A0A5;
}}

QPushButton {{
    background-color: #FFFFFF;
    border: 1px solid #D8D8DC;
    border-radius: {radius.control};
    padding: {spacing.button};
    color: #1D1D1F;
    font-size: {type_scale.body};
}}

QPushButton:hover {{
    background-color: #F0F0F2;
}}

QPushButton:pressed {{
    background-color: #E5E5E8;
}}

QPushButton#primary {{
    background-color: #0A84FF;
    color: white;
    border: none;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background-color: #0074E0;
}}

QPushButton#primary:disabled {{
    background-color: #A8D1FF;
    color: #F0F0F0;
}}

QPushButton#danger {{
    background-color: #FFFFFF;
    color: #FF453A;
    border: 1px solid #FFD4D1;
}}

QPushButton#danger:hover {{
    background-color: #FFF1F0;
}}

QPushButton:disabled {{
    color: #A0A0A5;
    border-color: #E5E5E8;
}}

QTableWidget {{
    background-color: #FFFFFF;
    border: 1px solid #D8D8DC;
    border-radius: {radius.panel};
    gridline-color: #EDEDEF;
    selection-background-color: #E8F2FF;
    selection-color: #1D1D1F;
}}

QHeaderView::section {{
    background-color: #FAFAFB;
    color: #6E6E73;
    padding: {spacing.checkbox};
    border: none;
    border-bottom: 1px solid #D8D8DC;
    font-size: {type_scale.caption};
    font-weight: 600;
}}

QProgressBar {{
    border: none;
    background-color: #E5E5E8;
    border-radius: {radius.xs};
    height: {size.progress_bar_height};
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: #0A84FF;
    border-radius: {radius.xs};
}}

QLabel#tierBadgeExact {{
    color: #1C7C34;
    background-color: #E3F6E7;
    border: 1px solid #BEEACA;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeHigh {{
    color: #A15C00;
    background-color: #FFF1DB;
    border: 1px solid #FFD9A0;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeReview {{
    color: #B3271E;
    background-color: #FFE9E7;
    border: 1px solid #FFC6C1;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeManual {{
    color: #0A5FC2;
    background-color: #E3EFFF;
    border: 1px solid #BBD6FF;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QCheckBox {{
    spacing: {spacing.checkbox};
    color: #1D1D1F;
    font-size: {type_scale.body};
}}

QStatusBar {{
    background-color: #F5F5F7;
    color: #6E6E73;
    border-top: 1px solid #D8D8DC;
}}

QToolTip {{
    background-color: #1D1D1F;
    color: white;
    border: none;
    padding: {spacing.tooltip};
    border-radius: {radius.tooltip};
}}

QScrollBar:vertical {{
    background: transparent;
    width: {size.scrollbar_width};
}}
QScrollBar::handle:vertical {{
    background: #C7C7CC;
    border-radius: {radius.sm};
    min-height: {size.scrollbar_min_handle};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: {size.scrollbar_end_cap};
}}

QTabWidget::pane {{
    border: none;
    top: 4px;
}}

QTabBar::tab {{
    background: transparent;
    color: #6E6E73;
    padding: {spacing.tab};
    margin-right: {spacing.tab_gap};
    border-bottom: {size.tab_underline} solid transparent;
    font-size: {type_scale.body};
    font-weight: 600;
}}

QTabBar::tab:selected {{
    color: #0A84FF;
    border-bottom: {size.tab_underline} solid #0A84FF;
}}

QTabBar::tab:hover:!selected {{
    color: #1D1D1F;
}}

QLabel#sectionHeading {{
    font-size: {type_scale.heading};
    font-weight: 600;
    color: #1D1D1F;
}}

QFrame#healthCard {{
    background-color: #FFFFFF;
    border: 1px solid #D8D8DC;
    border-radius: {radius.panel};
}}

QFrame#summaryBar {{
    background-color: #FFFFFF;
    border: 1px solid #D8D8DC;
    border-radius: {radius.panel};
}}

QLabel#summaryBarLabel {{
    color: #1D1D1F;
    font-size: {type_scale.body};
    font-weight: 600;
}}

QFrame#itunesFolderStrip {{
    background-color: #F2F2F5;
    border: 1px solid #D8D8DC;
    border-radius: {radius.control};
}}

QLabel#itunesFolderStripLabel {{
    color: #6E6E73;
    font-size: {type_scale.caption};
}}

QFrame#healthCard[tone="good"] {{
    border-left: {size.healthcard_accent} solid #30D158;
}}

QFrame#healthCard[tone="warning"] {{
    border-left: {size.healthcard_accent} solid #FF9F0A;
}}

QFrame#healthCard[tone="danger"] {{
    border-left: {size.healthcard_accent} solid #FF453A;
}}

QLabel#healthCardValue {{
    font-size: {type_scale.title};
    font-weight: 700;
    color: #1D1D1F;
}}

QLabel#healthCardTitle {{
    font-size: {type_scale.caption};
    color: #6E6E73;
}}

QFrame#detailPanel {{
    background-color: #FAFAFB;
    border: 1px solid #D8D8DC;
    border-top: none;
    border-radius: {radius.detail_panel};
    padding: {spacing.detail_panel};
}}

QScrollArea#detailScrollArea {{
    background: transparent;
    border: none;
}}

QSplitter#tableDetailSplitter::handle {{
    background-color: #D8D8DC;
    border-radius: 2px;
    margin: 2px 40%;
}}

QSplitter#tableDetailSplitter::handle:hover {{
    background-color: #0A84FF;
}}
"""


QSS_DARK = f"""
* {{
    font-family: {FONT_FAMILY};
}}

QMainWindow, QWidget#centralWidget {{
    background-color: #1E1E20;
}}

QLabel {{
    color: #F5F5F7;
}}

QLabel#eyebrow {{
    color: #98989D;
    font-size: {type_scale.eyebrow};
    font-weight: 600;
    letter-spacing: {spacing.eyebrow_tracking};
    text-transform: uppercase;
}}

QLabel#pageTitle {{
    font-size: {type_scale.title};
    font-weight: 600;
    color: #F5F5F7;
}}

QLabel#subtitle {{
    color: #98989D;
    font-size: {type_scale.body};
}}

QFrame#card {{
    background-color: #2A2A2D;
    border: 1px solid #3D3D40;
    border-radius: {radius.card};
}}

QToolBar#mainToolBar {{
    background-color: #1E1E20;
    border: none;
    border-bottom: 1px solid #3D3D40;
    padding: {spacing.toolbar};
    spacing: {spacing.toolbar_gap};
}}

QToolBar#mainToolBar QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {radius.control};
    padding: {spacing.toolbar_button};
    color: #F5F5F7;
    font-size: {type_scale.body};
}}

QToolBar#mainToolBar QToolButton:hover {{
    background-color: #333336;
    border: 1px solid #3D3D40;
}}

QToolBar#mainToolBar QToolButton:pressed {{
    background-color: #3D3D40;
}}

QToolBar#mainToolBar QToolButton:disabled {{
    color: #6E6E73;
}}

QPushButton {{
    background-color: #2A2A2D;
    border: 1px solid #3D3D40;
    border-radius: {radius.control};
    padding: {spacing.button};
    color: #F5F5F7;
    font-size: {type_scale.body};
}}

QPushButton:hover {{
    background-color: #333336;
}}

QPushButton:pressed {{
    background-color: #3D3D40;
}}

QPushButton#primary {{
    background-color: #0A84FF;
    color: white;
    border: none;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background-color: #3399FF;
}}

QPushButton#primary:disabled {{
    background-color: #2E4A66;
    color: #7A7A7D;
}}

QPushButton#danger {{
    background-color: #2A2A2D;
    color: #FF6B61;
    border: 1px solid #5C2E2B;
}}

QPushButton#danger:hover {{
    background-color: #3A2624;
}}

QPushButton:disabled {{
    color: #6E6E73;
    border-color: #3D3D40;
}}

QTableWidget {{
    background-color: #2A2A2D;
    border: 1px solid #3D3D40;
    border-radius: {radius.panel};
    gridline-color: #38383B;
    selection-background-color: #123A5C;
    selection-color: #F5F5F7;
}}

QHeaderView::section {{
    background-color: #232326;
    color: #98989D;
    padding: {spacing.checkbox};
    border: none;
    border-bottom: 1px solid #3D3D40;
    font-size: {type_scale.caption};
    font-weight: 600;
}}

QProgressBar {{
    border: none;
    background-color: #3D3D40;
    border-radius: {radius.xs};
    height: {size.progress_bar_height};
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: #0A84FF;
    border-radius: {radius.xs};
}}

QLabel#tierBadgeExact {{
    color: #6FE28A;
    background-color: #163821;
    border: 1px solid #2A5C39;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeHigh {{
    color: #FFC069;
    background-color: #3D2B0F;
    border: 1px solid #5C4419;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeReview {{
    color: #FF8A80;
    background-color: #3D1917;
    border: 1px solid #5C2925;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QLabel#tierBadgeManual {{
    color: #7DB2FF;
    background-color: #142A47;
    border: 1px solid #24466F;
    border-radius: {radius.control};
    padding: {spacing.badge};
    font-size: {type_scale.eyebrow};
    font-weight: 600;
}}

QCheckBox {{
    spacing: {spacing.checkbox};
    color: #F5F5F7;
    font-size: {type_scale.body};
}}

QStatusBar {{
    background-color: #1E1E20;
    color: #98989D;
    border-top: 1px solid #3D3D40;
}}

QToolTip {{
    background-color: #F5F5F7;
    color: #1D1D1F;
    border: none;
    padding: {spacing.tooltip};
    border-radius: {radius.tooltip};
}}

QScrollBar:vertical {{
    background: transparent;
    width: {size.scrollbar_width};
}}
QScrollBar::handle:vertical {{
    background: #4A4A4D;
    border-radius: {radius.sm};
    min-height: {size.scrollbar_min_handle};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: {size.scrollbar_end_cap};
}}

QTabWidget::pane {{
    border: none;
    top: 4px;
}}

QTabBar::tab {{
    background: transparent;
    color: #98989D;
    padding: {spacing.tab};
    margin-right: {spacing.tab_gap};
    border-bottom: {size.tab_underline} solid transparent;
    font-size: {type_scale.body};
    font-weight: 600;
}}

QTabBar::tab:selected {{
    color: #0A84FF;
    border-bottom: {size.tab_underline} solid #0A84FF;
}}

QTabBar::tab:hover:!selected {{
    color: #F5F5F7;
}}

QLabel#sectionHeading {{
    font-size: {type_scale.heading};
    font-weight: 600;
    color: #F5F5F7;
}}

QFrame#healthCard {{
    background-color: #2A2A2D;
    border: 1px solid #3D3D40;
    border-radius: {radius.panel};
}}

QFrame#summaryBar {{
    background-color: #2A2A2D;
    border: 1px solid #3D3D40;
    border-radius: {radius.panel};
}}

QLabel#summaryBarLabel {{
    color: #F5F5F7;
    font-size: {type_scale.body};
    font-weight: 600;
}}

QFrame#itunesFolderStrip {{
    background-color: #232326;
    border: 1px solid #3D3D40;
    border-radius: {radius.control};
}}

QLabel#itunesFolderStripLabel {{
    color: #A0A0A5;
    font-size: {type_scale.caption};
}}

QFrame#healthCard[tone="good"] {{
    border-left: {size.healthcard_accent} solid #32D74B;
}}

QFrame#healthCard[tone="warning"] {{
    border-left: {size.healthcard_accent} solid #FF9F0A;
}}

QFrame#healthCard[tone="danger"] {{
    border-left: {size.healthcard_accent} solid #FF453A;
}}

QLabel#healthCardValue {{
    font-size: {type_scale.title};
    font-weight: 700;
    color: #F5F5F7;
}}

QLabel#healthCardTitle {{
    font-size: {type_scale.caption};
    color: #98989D;
}}

QFrame#detailPanel {{
    background-color: #232326;
    border: 1px solid #3D3D40;
    border-top: none;
    border-radius: {radius.detail_panel};
    padding: {spacing.detail_panel};
}}

QScrollArea#detailScrollArea {{
    background: transparent;
    border: none;
}}

QSplitter#tableDetailSplitter::handle {{
    background-color: #3D3D40;
    border-radius: 2px;
    margin: 2px 40%;
}}

QSplitter#tableDetailSplitter::handle:hover {{
    background-color: #0A84FF;
}}
"""

# Backward-compat alias: earlier versions exposed a single QSS constant.
# Kept pointing at the light theme so any external/legacy import of
# `theme.QSS` keeps working unchanged; new code should use current_qss().
QSS = QSS_LIGHT
