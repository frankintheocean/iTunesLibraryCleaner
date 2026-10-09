"""
Design tokens: the non-color, non-accent constants (spacing, radius, font
sizes) that theme.py's QSS_LIGHT/QSS_DARK stylesheets repeat throughout.

Why this module exists (v1.9.1): theme.py's own docstring already
documents the *color* tokens (background/surface/border/text/accent) for
each variant, and THEME_ACCENTS already centralizes the ten accent-hue
tokens. What was still duplicated ad hoc across QSS_LIGHT/QSS_DARK -- the
same "8px" border-radius, "13px" font-size, "7px 16px" button padding,
etc., typed out independently every place it's used -- had no single
source of truth, so changing e.g. "the standard control corner radius"
meant hunting down every literal "8px" in two ~300-line stylesheets and
hoping none were missed or mismatched between light/dark.

This module gives those repeated values names. theme.py's QSS_LIGHT/
QSS_DARK f-strings interpolate them (`{radius.control}` etc.) instead of
repeating the literal, so there is exactly one place that defines "how
big is a standard corner radius" or "how much does a toolbar button
pad" for the whole app.

Deliberately NOT included here: the per-theme accent hues (THEME_ACCENTS
in theme.py already owns those, keyed by theme id) and the base light/
dark surface-and-text palette (documented in theme.py's module docstring
and only used once each, at the top of QSS_LIGHT/QSS_DARK, so giving
those a token here would add a layer of indirection without removing any
duplication). This module is specifically for values that were
*repeated* -- spacing, radius, and type scale -- across the stylesheets.

Byte-for-byte compatibility: every token below is set to exactly the
value theme.py already used at that call site, so substituting a literal
for `{token}` changes nothing about the rendered stylesheet -- this is a
refactor of where the value is defined, not a redesign of the app's look.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RadiusTokens:
    """Corner radii, from smallest (chips/tooltips) to largest (cards)."""

    xs: str = "4px"     # progress bar chunk, small toolbar-adjacent shapes
    sm: str = "5px"      # scrollbar handle
    tooltip: str = "6px"  # QToolTip
    control: str = "8px"  # buttons, toolbar buttons, badges, folder strip
    panel: str = "10px"   # tables, health/summary cards
    card: str = "12px"    # QFrame#card, the largest surface radius in the app
    # detailPanel's radius is asymmetric (rounded only on the bottom two
    # corners, to sit flush under the row it expands from) so it is kept
    # as its own token rather than reusing `panel` positionally.
    detail_panel: str = "0px 0px 10px 10px"


@dataclass(frozen=True)
class SpacingTokens:
    """Padding/margin/spacing values, as used verbatim in QSS
    `padding:`/`margin:`/`spacing:` declarations (values already include
    their unit and, where relevant, both axes)."""

    toolbar: str = "6px 10px"       # QToolBar#mainToolBar padding
    toolbar_button: str = "6px 10px"  # QToolBar#mainToolBar QToolButton padding
    button: str = "7px 16px"        # QPushButton padding
    badge: str = "2px 8px"          # tier badge labels padding
    tooltip: str = "4px 8px"        # QToolTip padding
    tab: str = "8px 18px"           # QTabBar::tab padding
    tab_gap: str = "4px"            # QTabBar::tab margin-right
    detail_panel: str = "4px"       # QFrame#detailPanel padding
    checkbox: str = "8px"           # QCheckBox spacing (icon-to-label gap)
    toolbar_gap: str = "6px"        # QToolBar#mainToolBar spacing (icon gaps)
    eyebrow_tracking: str = "0.5px"  # QLabel#eyebrow letter-spacing


@dataclass(frozen=True)
class SizeTokens:
    """Fixed pixel dimensions that aren't corner radii or padding."""

    progress_bar_height: str = "8px"
    scrollbar_width: str = "10px"
    scrollbar_min_handle: str = "24px"
    scrollbar_end_cap: str = "0px"   # add-line/sub-line height (hidden caps)
    tab_underline: str = "2px"       # QTabBar::tab:selected border-bottom width
    healthcard_accent: str = "3px"   # QFrame#healthCard[tone] border-left width
    dialog_accent: str = "4px"       # info/message dialog top border width


@dataclass(frozen=True)
class TypeTokens:
    """Font sizes used across the QSS, smallest to largest."""

    eyebrow: str = "11px"
    caption: str = "12px"
    body: str = "13px"
    heading: str = "14px"
    title: str = "22px"


# Singleton instances -- theme.py imports and interpolates these directly
# (`from .design_tokens import radius, spacing, size, type_scale`) rather
# than instantiating the dataclasses itself, since there is exactly one
# active token set for the whole app (no per-theme spacing variation
# today; only color/accent varies by theme).
radius = RadiusTokens()
spacing = SpacingTokens()
size = SizeTokens()
type_scale = TypeTokens()
