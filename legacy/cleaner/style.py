"""Shared widget-styling helpers for LibraryCleaner.

ttk widgets already get their colours from one place: the named ttk
styles configured in GenreCleanupApp._apply_theme(). The handful of
raw tk widgets ttk has no equivalent for (Text, Listbox, Toplevel, and
the tooltip's Label) don't go through ttk styles, so their bg/fg/
insertbackground/etc. kwargs used to be repeated by hand at every
construction and reconfigure site. This module centralizes those
kwarg bundles into small factory functions, keyed off the same theme
dict (`app.t` / `THEMES[name]`) the rest of the app already uses, so a
theme's colours only need to be listed in one place per widget kind.
"""


def surface_window_kwargs(theme):
    """kwargs for a plain window/Frame-level surface: root window,
    Toplevel dialogs, etc. Just the background."""
    return {"bg": theme["bg"]}


def text_widget_kwargs(theme, font=None):
    """kwargs for a raw tk.Text widget styled to match the current
    theme's "input" surface (used for the log pane and the changelog
    viewer)."""
    kwargs = {
        "bg": theme["input"],
        "fg": theme["fg"],
        "insertbackground": theme["fg"],
        "relief": "flat",
        "borderwidth": 0,
    }
    if font is not None:
        kwargs["font"] = font
    return kwargs


def listbox_kwargs(theme, font=None):
    """kwargs for a raw tk.Listbox styled to match the current theme
    (used by the genre-rule editor's rule list)."""
    kwargs = {
        "bg": theme["input"],
        "fg": theme["fg"],
        "selectbackground": theme["active"],
        "activestyle": "none",
        "relief": "flat",
        "borderwidth": 0,
    }
    if font is not None:
        kwargs["font"] = font
    return kwargs


def log_tag_colors(theme):
    """Foreground colours for the log pane's semantic text tags
    (success/warning/error/info), derived from the current theme so
    they stay readable across both dark and light themes instead of
    using fixed colours. Falls back to the theme's normal fg for any
    tag not listed here."""
    return {
        "success": "#6fcf6f" if theme.get("bg", "#000000") not in ("#f3f5f7", "#f5f1e8") else "#2e7d32",
        "warning": theme.get("accent", theme["fg"]),
        "error": "#e57373" if theme.get("bg", "#000000") not in ("#f3f5f7", "#f5f1e8") else "#c62828",
        "info": theme["muted"],
    }


def ttk_style_spec(theme, fonts):
    """The ttk named-style bundles _apply_theme() feeds to
    ttk.Style().configure()/.map() on every theme change, as data instead
    of one hand-written call per style. Returns a list of
    (style_name, configure_kwargs, map_kwargs) tuples - either kwargs dict
    may be None to skip that call for a given style. Centralizing the
    bundle here (keyed off the same theme dict / fonts dict the caller
    already has) means adding a widget style, or reviewing what a theme
    change touches, is one list to read instead of ~40 discrete calls -
    and every entry goes through the same configure/map loop, so a new
    style can't accidentally be added without its map() (or vice versa)."""
    t = theme
    return [
        ("TFrame", {"background": t["bg"]}, None),
        ("Panel.TFrame", {"background": t["panel"]}, None),
        ("TLabel", {"background": t["bg"], "foreground": t["fg"], "font": fonts["body"]}, None),
        ("Panel.TLabel", {"background": t["panel"], "foreground": t["fg"], "font": fonts["body"]}, None),
        ("Muted.TLabel", {"background": t["bg"], "foreground": t["muted"], "font": fonts["small"]}, None),
        ("PanelMuted.TLabel", {"background": t["panel"], "foreground": t["muted"], "font": fonts["small"]}, None),
        ("Title.TLabel", {"background": t["bg"], "foreground": t["fg"], "font": fonts["title"]}, None),
        ("Percent.TLabel", {"background": t["bg"], "foreground": t["accent"], "font": fonts["percent"]}, None),
        ("TCheckbutton", {"background": t["bg"], "foreground": t["fg"], "font": fonts["body"]},
            {"foreground": [("disabled", t["muted"]), ("active", t["fg"])], "background": [("active", t["bg"])]}),
        ("TRadiobutton", {"background": t["bg"], "foreground": t["fg"], "font": fonts["body"]},
            {"foreground": [("disabled", t["muted"]), ("active", t["fg"])], "background": [("active", t["bg"])]}),
        ("TButton", {"background": t["panel"], "foreground": t["fg"], "bordercolor": t["border"],
                     "lightcolor": t["border"], "darkcolor": t["border"], "padding": (10, 5), "font": fonts["body"]},
            {"background": [("active", t["active"]), ("pressed", t["active"]), ("disabled", t["bg"])],
             "foreground": [("disabled", t["muted"])]}),
        ("Accent.TButton", {"background": t["accent"], "foreground": t["bg"], "bordercolor": t["accent"],
                             "padding": (12, 6), "font": fonts["body"]},
            {"background": [("active", t["fg"]), ("pressed", t["fg"]), ("disabled", t["border"])],
             "foreground": [("disabled", t["muted"])]}),
        ("TEntry", {"fieldbackground": t["input"], "foreground": t["fg"], "insertcolor": t["fg"],
                    "bordercolor": t["border"], "lightcolor": t["border"], "darkcolor": t["border"],
                    "padding": 6, "font": fonts["body"]}, None),
        ("TCombobox", {"fieldbackground": t["input"], "background": t["input"], "foreground": t["fg"],
                       "arrowcolor": t["fg"], "bordercolor": t["border"], "lightcolor": t["border"],
                       "darkcolor": t["border"], "padding": 5, "font": fonts["body"]},
            {"fieldbackground": [("readonly", t["input"])], "foreground": [("readonly", t["fg"])]}),
        ("Horizontal.TProgressbar", {"troughcolor": t["input"], "background": t["accent"], "bordercolor": t["border"],
                                      "lightcolor": t["accent"], "darkcolor": t["accent"], "thickness": 8}, None),
        # Dimmed variant applied to the main progress bar while a run is
        # paused, so "paused" is visible at a glance in the bar itself,
        # not just in button text - see GenreCleanupApp.on_pause.
        ("Paused.Horizontal.TProgressbar", {"troughcolor": t["input"], "background": t["muted"], "bordercolor": t["border"],
                                             "lightcolor": t["muted"], "darkcolor": t["muted"], "thickness": 8}, None),
        # Per-phase breakdown bars (PhaseBar): deletion segment uses the
        # error/warning-adjacent tone, genre segment uses the accent, so
        # the two phases read as distinct at a glance next to each other.
        ("Delete.Horizontal.TProgressbar", {"troughcolor": t["input"], "background": t["muted"], "bordercolor": t["border"],
                                             "lightcolor": t["muted"], "darkcolor": t["muted"], "thickness": 6}, None),
        ("Genre.Horizontal.TProgressbar", {"troughcolor": t["input"], "background": t["accent"], "bordercolor": t["border"],
                                            "lightcolor": t["accent"], "darkcolor": t["accent"], "thickness": 6}, None),
        ("TNotebook", {"background": t["bg"], "borderwidth": 0}, None),
        ("TNotebook.Tab", {"background": t["panel"], "foreground": t["fg"], "padding": (10, 5), "font": fonts["body"]},
            {"background": [("selected", t["active"])], "foreground": [("selected", t["fg"])]}),
        ("Vertical.TScrollbar", {"background": t["panel"], "troughcolor": t["bg"], "arrowcolor": t["fg"]}, None),
    ]


def state_banner_kwargs(theme, kind):
    """kwargs for the run-state banner shown above the progress area
    while a run is paused or stopped (see RunStateBanner in gui.py) -
    a visual cue beyond the Pause/Stop button text, using colours
    already defined per-theme so it stays readable in every theme.
    kind is "paused" or "stopped"."""
    if kind == "stopped":
        bg = theme.get("border", theme["panel"])
    else:
        bg = theme.get("active", theme["panel"])
    return {"bg": bg, "fg": theme["fg"]}


def tooltip_label_kwargs():
    """kwargs for the small popup Label a Tooltip shows. Deliberately
    not theme-driven (dark-on-white regardless of app theme, like a
    native OS tooltip), but centralized here rather than inlined so
    all raw-tk widget styling lives in one module."""
    return {"bg": "#111111", "fg": "#ffffff", "padx": 9, "pady": 7, "font": ("Segoe UI", 9)}
