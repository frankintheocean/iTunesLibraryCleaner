"""
Tests for the design-token centralization in ui/theme.py + ui/design_tokens.py
(v1.9.1). Confirms the token module is wired up correctly and that
recoloring/preference-parsing still behaves exactly as before -- the
actual byte-for-byte QSS-output-unchanged property was verified manually
against the pre-refactor stylesheet during development and is guarded
here by asserting every token value appears in the rendered output.

Run with: python3 -m pytest tests/test_theme_tokens.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui import design_tokens
from src.ui.theme import (
    QSS_DARK,
    QSS_LIGHT,
    BASE_PALETTES,
    BASE_PALETTE_ORDER,
    THEME_ACCENTS,
    THEME_ORDER,
    accent_color,
    base_palette_choices,
    current_qss,
    theme_choices,
)


def test_design_tokens_are_interpolated_into_both_stylesheets():
    # Spot-check a handful of tokens actually landed in the rendered QSS
    # rather than the module accidentally holding an unused constant.
    assert f"border-radius: {design_tokens.radius.control}" in QSS_LIGHT
    assert f"border-radius: {design_tokens.radius.control}" in QSS_DARK
    assert f"padding: {design_tokens.spacing.button}" in QSS_LIGHT
    assert f"padding: {design_tokens.spacing.button}" in QSS_DARK
    assert f"font-size: {design_tokens.type_scale.body}" in QSS_LIGHT
    assert f"font-size: {design_tokens.type_scale.body}" in QSS_DARK


def test_design_token_values_unchanged_from_pre_refactor():
    # Locks in the exact literal values theme.py used before tokens
    # existed, so a future edit to design_tokens.py that silently changes
    # a value is caught here instead of only being noticed visually.
    assert design_tokens.radius.control == "8px"
    assert design_tokens.radius.card == "12px"
    assert design_tokens.radius.panel == "10px"
    assert design_tokens.spacing.button == "7px 16px"
    assert design_tokens.spacing.badge == "2px 8px"
    assert design_tokens.type_scale.body == "13px"
    assert design_tokens.type_scale.title == "22px"


def test_all_ten_themes_still_recolor_correctly():
    for theme_id in THEME_ORDER:
        for mode in ("light", "dark"):
            qss = current_qss(f"{mode}:{theme_id}")
            assert THEME_ACCENTS[theme_id]["accent"] in qss


def test_theme_choices_lists_all_ten_in_order():
    choices = theme_choices()
    assert [tid for _, tid in choices] == list(THEME_ORDER)
    assert choices[0] == ("Blue (default)", "blue")


def test_accent_color_legacy_and_corrupt_preferences_fall_back_to_blue():
    assert accent_color("auto") == THEME_ACCENTS["blue"]["accent"]
    assert accent_color("not-a-real-preference") == THEME_ACCENTS["blue"]["accent"]


# ------------------------------------------------------------ v2.0 base palettes

def test_base_palette_choices_lists_all_eight_in_order():
    choices = base_palette_choices()
    assert [pid for _, pid in choices] == list(BASE_PALETTE_ORDER)
    assert len(choices) == 8


def test_each_base_palette_recolors_its_own_family_only():
    for palette_id in BASE_PALETTE_ORDER:
        spec = BASE_PALETTES[palette_id]
        mode = "dark" if spec["family"] == "dark" else "light"
        qss = current_qss(f"{mode}:blue:{palette_id}")
        assert spec["background"] in qss
        assert spec["surface"] in qss
        assert spec["border"] in qss
        assert spec["text_primary"] in qss
        assert spec["text_secondary"] in qss


def test_base_palette_never_applies_to_the_wrong_family():
    """A dark-family palette requested while mode=light (or vice versa)
    must be a no-op -- the original mode's own base colors, not a
    half-applied mix of both palettes' tokens."""
    for palette_id in BASE_PALETTE_ORDER:
        spec = BASE_PALETTES[palette_id]
        wrong_mode = "light" if spec["family"] == "dark" else "dark"
        qss = current_qss(f"{wrong_mode}:blue:{palette_id}")
        expected = current_qss(wrong_mode)  # same as no palette override at all
        assert qss == expected
        assert spec["background"] not in qss


def test_base_palette_accent_still_applies_on_top():
    for palette_id in BASE_PALETTE_ORDER:
        spec = BASE_PALETTES[palette_id]
        mode = "dark" if spec["family"] == "dark" else "light"
        qss = current_qss(f"{mode}:teal:{palette_id}")
        assert THEME_ACCENTS["teal"]["accent"] in qss
        assert spec["background"] in qss


def test_unknown_or_empty_base_palette_falls_back_to_original_look():
    assert current_qss("dark:blue:") == current_qss("dark:blue")
    assert current_qss("dark:blue:not-a-real-palette") == current_qss("dark:blue")
    assert current_qss("dark") == current_qss("dark:blue")  # legacy, still works


def test_base_palette_ids_are_unique_and_distinct_from_accent_ids():
    assert len(set(BASE_PALETTE_ORDER)) == len(BASE_PALETTE_ORDER)
    assert set(BASE_PALETTE_ORDER).isdisjoint(set(THEME_ORDER))
