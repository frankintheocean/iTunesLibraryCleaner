"""LibraryCleaner GUI.

The UI uses ttk for normal controls so Windows/native ttk theming works
cleanly. A small tk.Text is retained for the multiline log because ttk has
no native text widget.
"""
import json
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

from cleanup_engine import (CleanupEngine, CleanupOptions, undo_last_run, retry_failed_records,
                             UNDO_LOG_NAME, configure_file_logging, DELETE_BATCH_SIZE,
                             vacuum_processed_cache, clear_processed_cache)
import itunes_com
from album_merge import (find_split_groups, build_merge_plan, read_library_tracks,
                          AlbumMergeEngine, confirm_split_groups_online)
from genre_rules import (load_custom_patterns, save_custom_patterns, PATTERNS,
                          test_pattern_against, preview_genre_mapping, search_builtin_patterns,
                          parse_patterns_csv, find_shadowing_rule)
from style import (surface_window_kwargs, text_widget_kwargs, listbox_kwargs, tooltip_label_kwargs,
                    log_tag_colors, ttk_style_spec, state_banner_kwargs)
import icons

log = logging.getLogger(__name__)


def _safe_after(widget, callback):
    """widget.after(0, callback), swallowing the TclError/RuntimeError a
    background thread hits if the window was closed (root destroyed)
    between the thread starting its work and this marshal-back call -
    e.g. a run stopped via on_close's confirm-then-stop path, where the
    worker thread notices the stop request and reports back after root
    is already gone. Without this, that's an uncaught exception on a
    daemon thread (harmless to the process since the app is closing
    anyway, but still an unhandled error rather than a clean no-op)."""
    try:
        widget.after(0, callback)
    except (RuntimeError, tk.TclError):
        pass


def run_in_background(widget, work, on_done=None):
    """Runs work() on a daemon thread, then marshals its result back onto
    the Tk thread via widget.after(0, ...) before calling on_done(result).

    Small shared abstraction for the hand-rolled "thread + after(0, apply)"
    pattern used by refresh/undo/retry actions, so each call site only
    supplies the actual work and the GUI-thread follow-up rather than
    re-wiring the threading plumbing itself. work must not touch Tk
    widgets (it runs off the main thread); on_done runs on the Tk thread
    and is where widget updates belong. Any exception from work() is
    logged and swallowed so on_done is not called with an error - callers
    that need failures reflected in the UI should catch/report inside
    work() itself and return a value on_done can act on.
    """
    def run():
        result = None
        try:
            result = work()
        except Exception:
            log.exception("Background task failed")
        if on_done:
            _safe_after(widget, lambda: on_done(result))
    threading.Thread(target=run, daemon=True).start()


APP_NAME = "LibraryCleaner"
APP_VERSION = "3.0"
LOG_MAX_LINES = 500
APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

THEMES = {
    "Midnight": {"bg": "#0b0f14", "panel": "#121821", "input": "#18212d", "fg": "#f3f6fa", "muted": "#9aa7b5", "accent": "#64b5f6", "border": "#2c3948", "active": "#1d2a38"},
    "Slate":    {"bg": "#20242a", "panel": "#292f36", "input": "#323943", "fg": "#f1f3f5", "muted": "#aeb6bf", "accent": "#8ab4f8", "border": "#46515d", "active": "#394550"},
    "Nord":     {"bg": "#2e3440", "panel": "#3b4252", "input": "#434c5e", "fg": "#eceff4", "muted": "#b7c0ce", "accent": "#88c0d0", "border": "#4c566a", "active": "#485365"},
    "Ocean":    {"bg": "#071a24", "panel": "#0d2a38", "input": "#123747", "fg": "#e9fbff", "muted": "#9bc4d0", "accent": "#4dd0e1", "border": "#245264", "active": "#174354"},
    "Forest":   {"bg": "#0c1711", "panel": "#14231a", "input": "#1b3023", "fg": "#eef8f0", "muted": "#a8b9ac", "accent": "#81c784", "border": "#2e4b38", "active": "#25402f"},
    "Purple":   {"bg": "#140e1d", "panel": "#20152d", "input": "#2b1d3c", "fg": "#f8f1ff", "muted": "#c0b0ca", "accent": "#c39bea", "border": "#49365a", "active": "#39284b"},
    "Rose":     {"bg": "#1c0d12", "panel": "#2b151d", "input": "#391c26", "fg": "#fff3f6", "muted": "#c9aeb7", "accent": "#f48fb1", "border": "#57303d", "active": "#472530"},
    "Amber":    {"bg": "#191308", "panel": "#2a1e0d", "input": "#382912", "fg": "#fff8e8", "muted": "#c7b99b", "accent": "#ffca62", "border": "#55401e", "active": "#473517"},
    "Light":    {"bg": "#f3f5f7", "panel": "#ffffff", "input": "#ffffff", "fg": "#18202a", "muted": "#65717e", "accent": "#1565c0", "border": "#c8d0d8", "active": "#e7edf3"},
    "Paper":    {"bg": "#f5f1e8", "panel": "#fffdf8", "input": "#fffdf8", "fg": "#28231c", "muted": "#776f64", "accent": "#8a5a22", "border": "#d5cbbb", "active": "#eee7da"},
}

# Shown in the theme picker alongside the 10 fixed themes above. Not a key
# in THEMES itself - resolve_theme_name() swaps it for "Midnight" or
# "Light" depending on the Windows light/dark setting, so every other
# call site (_apply_theme, THEMES[self.theme_name], etc.) never has to
# know "Auto" exists.
AUTO_THEME_NAME = "Auto (match Windows)"
THEME_CHOICES = [AUTO_THEME_NAME] + list(THEMES)


def _windows_prefers_light_theme():
    """Reads the same registry value Windows itself uses for the
    system-wide light/dark choice (Settings > Personalization > Colors).
    Returns True/False, or None if it can't be read (non-Windows, older
    Windows without the key, or any other error) so the caller can fall
    back to a fixed default instead of guessing."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except Exception:
        return None


def resolve_theme_name(theme_name):
    """Turns a saved/selected theme name into an actual key in THEMES.
    Every fixed theme name maps to itself; AUTO_THEME_NAME resolves to
    "Light" or "Midnight" based on the current Windows setting, checked
    fresh each call so switching the OS theme and reopening the app (or
    Settings) picks it up. Falls back to "Midnight" if the OS setting
    can't be read at all."""
    if theme_name != AUTO_THEME_NAME:
        return theme_name if theme_name in THEMES else "Midnight"
    prefers_light = _windows_prefers_light_theme()
    if prefers_light is None:
        return "Midnight"
    return "Light" if prefers_light else "Midnight"

FONT_CHOICES = [
    "Segoe UI", "Arial", "Calibri", "Consolas", "Courier New", "Tahoma",
    "Verdana", "Trebuchet MS", "Georgia", "Times New Roman",
]


@dataclass
class ViewState:
    """Owns both the run-progress values shown on the main screen and
    (once bind_widgets() is called) the ttk widgets that display them,
    so resetting to the main menu is "update the state, then push it
    to whichever widgets are bound" instead of a hand-maintained list
    of (attr, widget) pairs kept in sync by hand at every call site."""
    percent: str = "0%"
    processed: str = "0 / 0"
    remaining: str = "0"
    changed: str = "0"
    deleted: str = "0"
    eta: str = "--:--"
    elapsed: str = "0s"
    current_track: str = "Ready."
    output_folder: str = ""

    def __post_init__(self):
        self._widgets = {}

    def bind_widgets(self, **widgets):
        """widgets maps field name -> the ttk.Label (or similar, with
        a .config(text=...) method) that displays that field."""
        self._widgets.update(widgets)
        self.push()

    def push(self):
        """Write current field values into every bound widget."""
        for field, widget in self._widgets.items():
            widget.config(text=getattr(self, field))

    def reset(self):
        bound = self._widgets
        self.__dict__.update(asdict(ViewState()))
        self._widgets = bound
        self.push()


SETTINGS_WINDOW_DEFAULT_SIZE = "640x480"
SETTINGS_WINDOW_MIN_SIZE = (560, 400)


def load_preferences():
    defaults = {
        "theme": "Midnight", "font": "Segoe UI",
        "lastfm_user": "", "lastfm_key": "",
        "unknown_lookup": True, "foreign_detect": True,
        "dry_run": False, "force_rescan": False,
        # Advanced: how many junk-track deletes to batch before
        # re-enumerating the library (see cleanup_engine.DELETE_BATCH_SIZE).
        "delete_batch_size": DELETE_BATCH_SIZE,
        "source": "itunes", "scope": "Entire library",
        # scope_names/scope_mode supersede the older single "scope"
        # string for multi-playlist / exclude-mode scopes; "scope" is
        # kept for older settings.json files and as a display fallback.
        "scope_names": [], "scope_mode": "include",
        # Last size the Settings dialog was resized to, so a user who
        # made the cramped Genres/Built-in rules tabs bigger doesn't
        # have to redo it every time they open Settings.
        "settings_window_size": SETTINGS_WINDOW_DEFAULT_SIZE,
        # Last size+position the main window was left at, mirroring
        # settings_window_size above.
        "main_window_geometry": "",
        # Where changelog.txt/GenreCleanup_UndoLog.csv/GenreCleanup_Debug.log/
        # the processed-tracks cache are written. Empty string means "use
        # the app install directory" (the original fixed behavior) - kept
        # as the default so upgraders with no saved preference see no
        # change in where their files land.
        "output_folder": "",
    }
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            defaults.update({k: data[k] for k in defaults if k in data})
        if defaults["theme"] not in THEME_CHOICES: defaults["theme"] = "Midnight"
        if defaults["font"] not in FONT_CHOICES: defaults["font"] = "Segoe UI"
        if defaults["source"] not in ("itunes", "lastfm"): defaults["source"] = "itunes"
        if not isinstance(defaults["scope_names"], list): defaults["scope_names"] = []
        if defaults["scope_mode"] not in ("include", "exclude"): defaults["scope_mode"] = "include"
        if not isinstance(defaults["settings_window_size"], str) or "x" not in defaults["settings_window_size"]:
            defaults["settings_window_size"] = SETTINGS_WINDOW_DEFAULT_SIZE
        if not isinstance(defaults["main_window_geometry"], str):
            defaults["main_window_geometry"] = ""
        if not isinstance(defaults["output_folder"], str) or not defaults["output_folder"].strip() \
                or not os.path.isdir(defaults["output_folder"]):
            # Falls back to the app dir if unset, or if a previously
            # chosen folder no longer exists (moved drive, deleted
            # folder, etc.) rather than silently failing every file
            # write at run time.
            defaults["output_folder"] = ""
        try:
            defaults["delete_batch_size"] = int(defaults["delete_batch_size"])
            if defaults["delete_batch_size"] <= 0:
                defaults["delete_batch_size"] = DELETE_BATCH_SIZE
        except (TypeError, ValueError):
            defaults["delete_batch_size"] = DELETE_BATCH_SIZE
    except Exception:
        pass
    return defaults


def save_preferences(**values):
    current = load_preferences()
    current.update(values)
    try:
        # Write to a temp file in the same directory, then atomically
        # replace settings.json, so a crash/power-loss mid-write can't
        # leave a truncated/corrupt settings.json behind (os.replace is
        # atomic on both POSIX and Windows).
        fd, tmp_path = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=os.path.dirname(SETTINGS_PATH) or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, SETTINGS_PATH)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass


class Tooltip:
    """Small, delayed tooltip with plain-English explanations.

    Idempotent per widget: constructing a second Tooltip on a widget
    that already has one (e.g. _render_finished() re-annotating
    start_btn on every stopped run) updates the existing tooltip's text
    in place instead of stacking a fresh set of <Enter>/<Leave>/
    <ButtonPress> bindings on top of the old ones - each bound with
    add="+", so without this a widget re-tooltipped many times over an
    app session would accumulate one duplicate handler (and one
    redundant tooltip Toplevel per hover) per call, a small but
    real and unbounded leak."""
    def __new__(cls, widget, text):
        existing = getattr(widget, "_tooltip", None)
        if isinstance(existing, cls):
            existing.text = text
            return existing
        return super().__new__(cls)

    def __init__(self, widget, text):
        if getattr(self, "widget", None) is widget:
            # __new__ returned the already-initialized existing tooltip
            # for this widget (text was already updated there) - skip
            # re-running setup/re-binding.
            return
        self.widget = widget
        self.text = text
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget._tooltip = self

    def _schedule(self, _event=None):
        self._hide()
        self.after_id = self.widget.after(500, self._show)

    def _show(self):
        if self.tip:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(self.tip, text=self.text, justify="left", wraplength=360,
                             **tooltip_label_kwargs())
            label.pack()
        except tk.TclError:
            self.tip = None

    def _hide(self, _event=None):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class SmoothProgressbar(ttk.Progressbar):
    """Interpolate toward a target value without geometry-based animation."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._target = 0.0
        self._animating = False

    def set_target(self, value):
        self._target = max(0.0, min(100.0, float(value)))
        if not self._animating:
            self._animating = True
            self._step()

    def _step(self):
        current = float(self["value"])
        delta = self._target - current
        if abs(delta) < 0.25:
            self["value"] = self._target
            self._animating = False
            return
        self["value"] = current + delta * 0.35
        try:
            self.after(16, self._step)
        except tk.TclError:
            self._animating = False


class PhaseBar(ttk.Frame):
    """Two-segment progress breakdown: one segment for the
    junk-deletion phase, one for the genre-writing phase, each sized
    by the fraction of *processed* tracks that phase accounted for so
    far (not by time), plus a small text readout above them. Distinct
    from the main SmoothProgressbar (overall % of the run) - this
    shows how that overall progress splits between the two kinds of
    work, which one blended percentage can't convey."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.label_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.label_var, style="Muted.TLabel").pack(anchor="w")
        bars = ttk.Frame(self)
        bars.pack(fill="x", pady=(2, 0))
        bars.grid_columnconfigure(0, weight=1)
        bars.grid_columnconfigure(1, weight=1)
        self.delete_bar = ttk.Progressbar(bars, mode="determinate", maximum=100,
                                           style="Delete.Horizontal.TProgressbar")
        self.delete_bar.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.genre_bar = ttk.Progressbar(bars, mode="determinate", maximum=100,
                                          style="Genre.Horizontal.TProgressbar")
        self.genre_bar.grid(row=0, column=1, sticky="ew", padx=(2, 0))

    def update_from_stats(self, stats):
        deleting = getattr(stats, "deleting_phase_count", 0)
        genres = getattr(stats, "genres_phase_count", 0)
        total = deleting + genres
        if total <= 0:
            self.delete_bar["value"] = 0
            self.genre_bar["value"] = 0
            self.label_var.set("")
            return
        self.delete_bar["value"] = 100 * deleting / total
        self.genre_bar["value"] = 100 * genres / total
        self.label_var.set(
            f"{icons.TRASH} Deleting junk: {deleting}    {icons.LOOKUP} Genres: {genres}")

    def reset(self):
        self.delete_bar["value"] = 0
        self.genre_bar["value"] = 0
        self.label_var.set("")


class RunStateBanner(tk.Label):
    """One-line banner shown above the progress area only while a run
    is paused or stopped, as a visual cue distinct from button text
    (see on_pause/on_stop) - hidden the rest of the time via
    pack_forget rather than left blank, so it doesn't reserve empty
    vertical space during a normal run."""
    def __init__(self, parent, app):
        super().__init__(parent, text="", anchor="w", padx=10, pady=4)
        self.app = app
        self._visible = False

    def show(self, kind, text):
        self.configure(text=text, **state_banner_kwargs(self.app.t, kind))
        if not self._visible:
            self.pack(fill="x", before=self.app.progress, pady=(0, 6))
            self._visible = True

    def hide(self):
        if self._visible:
            self.pack_forget()
            self._visible = False

    def refresh_theme(self, kind):
        if self._visible:
            self.configure(**state_banner_kwargs(self.app.t, kind))


class GenreCleanupApp:
    def __init__(self, root):
        self.root = root
        self.engine = None
        self.preferences = load_preferences()
        # Empty string (default/unset, or a previously chosen folder that
        # no longer exists - see load_preferences) means "use the app
        # install directory", matching the original fixed behavior.
        self.output_folder = self.preferences["output_folder"] or APP_DIR
        self.theme_name = self.preferences["theme"]
        self.font_family = self.preferences["font"]

        root.title(APP_NAME)
        # Restore the last size/position the user left the main window
        # at, same as the Settings dialog already does for itself. Falls
        # back to the original fixed default size if nothing was saved
        # yet, or the saved geometry string is malformed.
        saved_geometry = self.preferences.get("main_window_geometry") or ""
        if saved_geometry and "x" in saved_geometry.split("+")[0]:
            try:
                root.geometry(saved_geometry)
            except tk.TclError:
                root.geometry("680x760")
        else:
            root.geometry("680x760")
        root.minsize(600, 650)
        root.resizable(True, True)
        try:
            icon_path = os.path.join(APP_DIR, "GenreCleanup.ico")
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
        except Exception:
            pass

        self.fonts = {
            "body": tkfont.Font(root, family=self.font_family, size=9),
            "small": tkfont.Font(root, family=self.font_family, size=8),
            "title": tkfont.Font(root, family=self.font_family, size=16, weight="bold"),
            "percent": tkfont.Font(root, family=self.font_family, size=25, weight="bold"),
            "stat": tkfont.Font(root, family=self.font_family, size=12, weight="bold"),
            "mono": tkfont.Font(root, family=self.font_family, size=8),
        }
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self._build_variables()
        self._apply_theme()
        self._build_ui()
        self.view_state.bind_widgets(
            percent=self.pct_label, processed=self.processed_val, remaining=self.remaining_val,
            changed=self.changed_val, deleted=self.deleted_val, eta=self.eta_val,
            elapsed=self.elapsed_val, current_track=self.current_track_label,
            output_folder=self.output_folder_label,
        )
        self._check_existing_undo_log()
        self.on_refresh_playlists()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._toast_available = self._detect_toast_available()

    @staticmethod
    def _detect_toast_available():
        """Cheap one-time check of whether the optional win10toast
        package is importable, so the About tab can hint at installing
        it instead of the feature just silently no-op'ing."""
        try:
            import win10toast  # noqa: F401
            return True
        except ImportError:
            return False

    def _build_variables(self):
        p = self.preferences
        self.unknown_var = tk.BooleanVar(value=bool(p["unknown_lookup"]))
        self.foreign_var = tk.BooleanVar(value=bool(p["foreign_detect"]))
        self.dry_run_var = tk.BooleanVar(value=bool(p["dry_run"]))
        self.force_rescan_var = tk.BooleanVar(value=bool(p["force_rescan"]))
        self.delete_batch_size_var = tk.IntVar(value=int(p.get("delete_batch_size", DELETE_BATCH_SIZE)))
        self.source_var = tk.StringVar(value=p["source"])
        # Scope state: a plain list of playlist names + an include/exclude
        # mode, restored from the saved preference (old single-name
        # "scope" string values load fine too - a single-item include list).
        self.scope_names = list(p.get("scope_names") or ([] if p["scope"] in ("", "Entire library") else [p["scope"]]))
        self.scope_mode = p.get("scope_mode") or "include"
        self.available_playlists = []
        self.view_state = ViewState()
        self._eta_pace_ema = None  # reset at the start of each run; see _smoothed_eta_seconds
        # Once the user has acknowledged the live-run warning in this
        # session, don't nag them with the identical dialog on every
        # subsequent live run in the same session - reset on app restart.
        self._live_run_acknowledged = False

    def _apply_theme(self):
        t = THEMES[resolve_theme_name(self.theme_name)]
        self.t = t
        self.root.configure(**surface_window_kwargs(t))
        # Style bundle lives in style.ttk_style_spec() as data (one entry
        # per named ttk style) instead of a hand-written configure()/map()
        # call per style here - see that function's docstring.
        for style_name, configure_kwargs, map_kwargs in ttk_style_spec(t, self.fonts):
            if configure_kwargs:
                self.style.configure(style_name, **configure_kwargs)
            if map_kwargs:
                self.style.map(style_name, **map_kwargs)

    def _build_ui(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        wrap = ttk.Frame(self.root, padding=(22, 18))
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(7, weight=1)

        ttk.Label(wrap, text=f"{icons.MUSIC} {APP_NAME}", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(wrap, text="Clean up genres, detect international tracks and remove malformed library entries.",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="ew", pady=(2, 10))

        options = ttk.Frame(wrap)
        options.grid(row=2, column=0, sticky="ew")
        options.grid_columnconfigure(0, weight=1)
        self.unknown_cb = ttk.Checkbutton(options, text=f"{icons.LOOKUP} Look up missing genres online", variable=self.unknown_var)
        self.unknown_cb.grid(row=0, column=0, sticky="w", pady=1)
        self.foreign_cb = ttk.Checkbutton(options, text=f"{icons.GLOBE} Foreign-language detection → International", variable=self.foreign_var)
        self.foreign_cb.grid(row=1, column=0, sticky="w", pady=1)
        self.dry_run_cb = ttk.Checkbutton(options, text=f"{icons.PREVIEW} Dry run — preview only; make no changes", variable=self.dry_run_var)
        self.dry_run_cb.grid(row=2, column=0, sticky="w", pady=1)
        self.force_rescan_cb = ttk.Checkbutton(options, text=f"{icons.REPEAT} Force full re-scan", variable=self.force_rescan_var)
        self.force_rescan_cb.grid(row=3, column=0, sticky="w", pady=1)
        Tooltip(self.force_rescan_cb, "Ignores LibraryCleaner’s saved ‘already processed’ list and checks every track again. It does not delete your music or reset iTunes metadata by itself.")
        Tooltip(self.foreign_cb, "Checks the artist + song title for a non-English language. If the detected language is not English, the track is tagged International. Existing International tracks are skipped.")

        source = ttk.Frame(wrap)
        source.grid(row=3, column=0, sticky="ew", pady=(7, 4))
        ttk.Label(source, text="Genre lookup order:").pack(side="left", padx=(0, 8))
        self.itunes_rb = ttk.Radiobutton(source, text="iTunes", variable=self.source_var, value="itunes")
        self.itunes_rb.pack(side="left", padx=(0, 10))
        self.lastfm_rb = ttk.Radiobutton(source, text="Last.fm", variable=self.source_var, value="lastfm")
        self.lastfm_rb.pack(side="left")

        creds = ttk.Frame(wrap)
        creds.grid(row=4, column=0, sticky="ew", pady=(0, 5))
        creds.grid_columnconfigure(0, weight=1)
        creds.grid_columnconfigure(1, weight=1)
        # Small greyed hint labels above each field instead of
        # placeholder-in-field text: a hand-rolled placeholder that
        # swaps in and out of the same Entry as real input is fragile
        # (easy to accidentally save/submit the hint text itself) and
        # is invisible to screen readers once real text is entered. A
        # separate always-visible label has neither problem and is a
        # standard ttk-friendly pattern.
        ttk.Label(creds, text="Last.fm username (optional)", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Label(creds, text="Last.fm API key (optional)", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(4, 0))
        self.lastfm_user_var = tk.StringVar(value=self.preferences.get("lastfm_user", ""))
        self.lastfm_key_var = tk.StringVar(value=self.preferences.get("lastfm_key", ""))
        self.lastfm_user_entry = ttk.Entry(creds, textvariable=self.lastfm_user_var)
        self.lastfm_key_entry = ttk.Entry(creds, textvariable=self.lastfm_key_var, show="\u2022")
        self.lastfm_user_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.lastfm_key_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0))

        scope = ttk.Frame(wrap)
        scope.grid(row=5, column=0, sticky="ew", pady=(0, 7))
        scope.grid_columnconfigure(1, weight=1)
        ttk.Label(scope, text="Scope:").grid(row=0, column=0, sticky="w", padx=(0, 7))
        # A read-only Entry (not a Combobox) showing a short summary of
        # the current scope - the actual picking happens in
        # ScopePickerDialog, which is the only way to get more than one
        # playlist (or "all except these") into scope_names/scope_mode.
        self.scope_summary_var = tk.StringVar(value="Entire library")
        self.scope_display = ttk.Entry(scope, textvariable=self.scope_summary_var, state="readonly")
        self.scope_display.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        self.scope_pick_btn = ttk.Button(scope, text="Choose…", command=self.on_open_scope_picker)
        self.scope_pick_btn.grid(row=0, column=2, padx=(0, 3))
        self.scope_refresh_btn = ttk.Button(scope, text="⟳ Refresh", command=self.on_refresh_playlists)
        self.scope_refresh_btn.grid(row=0, column=3)

        ttk.Label(wrap, text="0%", style="Percent.TLabel", name="pct").grid(row=6, column=0, sticky="w", pady=(0, 2))
        self.pct_label = wrap.nametowidget("pct")
        # Banner packs into progress_area (not the grid) so it can
        # insert itself immediately above the main progress bar via
        # pack(before=...) without disturbing the row grid below it.
        progress_area = ttk.Frame(wrap)
        progress_area.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        self.state_banner = RunStateBanner(progress_area, self)
        self.progress = SmoothProgressbar(progress_area, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        self.progress.pack(fill="x")
        self.phase_bar = PhaseBar(progress_area, self)
        self.phase_bar.pack(fill="x", pady=(6, 0))

        stats = ttk.Frame(wrap, style="Panel.TFrame", padding=8)
        stats.grid(row=8, column=0, sticky="ew", pady=(0, 7))
        for c in range(3):
            stats.columnconfigure(c, weight=1)
        self.processed_val = self._stat_cell(stats, "Processed", "0 / 0", 0, 0)
        self.remaining_val = self._stat_cell(stats, "Remaining", "0", 0, 1)
        self.changed_val = self._stat_cell(stats, "Changed", "0", 0, 2)
        self.deleted_val = self._stat_cell(stats, "Deleted", "0", 1, 0)
        self.eta_val = self._stat_cell(stats, "ETA", "--:--", 1, 1)
        self.elapsed_val = self._stat_cell(stats, "Elapsed", "0s", 1, 2)

        self.current_track_label = ttk.Label(wrap, text="Ready.", style="Muted.TLabel")
        self.current_track_label.grid(row=9, column=0, sticky="ew", pady=(0, 2))
        self.output_folder_label = ttk.Label(wrap, text="", style="Muted.TLabel")
        self.output_folder_label.grid(row=10, column=0, sticky="ew", pady=(0, 3))

        log_frame = ttk.Frame(wrap, style="Panel.TFrame", padding=5)
        log_frame.grid(row=11, column=0, sticky="nsew", pady=(0, 7))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", height=7, state="disabled", padx=5, pady=4,
                                **text_widget_kwargs(self.t, font=self.fonts["mono"]))
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._configure_log_tags()
        self._log_line_count = 0

        buttons = ttk.Frame(wrap)
        buttons.grid(row=12, column=0, sticky="ew")
        self.undo_btn = ttk.Button(buttons, text=f"{icons.UNDO} Undo", command=self.on_undo)
        self.undo_btn.pack(side="left", padx=(0, 5))
        self.merge_albums_btn = ttk.Button(buttons, text=f"{icons.MUSIC} Merge Albums…", command=self.on_open_merge_albums)
        self.merge_albums_btn.pack(side="left", padx=(0, 5))
        Tooltip(self.merge_albums_btn, "Finds albums iTunes split into two entries (e.g. an 11-track album plus 1 stray track with a missing/mismatched Album Artist) and lets you review and merge them back into one album.")
        self.settings_btn = ttk.Button(buttons, text=f"{icons.GEAR} Settings", command=self.on_open_settings)
        self.settings_btn.pack(side="left")
        self.close_btn = ttk.Button(buttons, text=f"{icons.CLOSE} Close", command=self.on_close)
        self.close_btn.pack(side="right", padx=(5, 0))
        self.start_btn = ttk.Button(buttons, text=f"{icons.PLAY} Start Cleanup", command=self.on_start, style="Accent.TButton")
        self.start_btn.pack(side="right")
        self.pause_btn = ttk.Button(buttons, text=f"{icons.PAUSE} Pause", command=self.on_pause)
        self.stop_btn = ttk.Button(buttons, text=f"{icons.STOP_SQUARE} Stop", command=self.on_stop)
        Tooltip(self.pause_btn, "Suspends the run in place. Resume continues from the exact same track — no progress is lost.")
        Tooltip(self.stop_btn, "Ends this run early. Unlike Pause, starting again begins a brand-new run from the top rather than continuing where you left off.")
        self._buttons_row = buttons
        self.pause_btn.pack_forget()
        self.stop_btn.pack_forget()
        self.undo_btn.config(state="disabled")

    def _stat_cell(self, parent, label, value, row, col):
        cell = ttk.Frame(parent, style="Panel.TFrame", padding=(8, 4))
        cell.grid(row=row, column=col, sticky="ew")
        ttk.Label(cell, text=label.upper(), style="PanelMuted.TLabel").pack(anchor="w")
        val = ttk.Label(cell, text=value, style="Panel.TLabel", font=self.fonts["stat"])
        val.pack(anchor="w")
        return val

    def _entry_value(self, entry):
        return entry.get().strip()

    def _configure_log_tags(self):
        """(Re)configures the log pane's semantic colour tags so
        success/warning/error/info lines are visually distinct at a
        glance, not just by their emoji prefix - color-coding on top
        of the existing emoji, using colours already defined per-theme
        in style.py so it stays readable in every theme."""
        colors = log_tag_colors(self.t)
        for tag, color in colors.items():
            self.log_text.tag_configure(tag, foreground=color)

    @staticmethod
    def _log_tag_for(msg):
        """Best-effort classification of a log line into a semantic
        tag, based on the same emoji prefixes already used throughout
        the app's status messages - no change to message text needed."""
        if msg.startswith(icons.ERROR_ICONS):
            return "error" if msg.startswith(icons.ERROR_ONLY_ICONS) else "warning"
        if msg.startswith(icons.SUCCESS_ICONS):
            return "success"
        if msg.startswith(icons.INFO_ICONS):
            return "info"
        return None

    def _apply_preferences_to_widgets(self):
        self._apply_theme()
        self.log_text.configure(**text_widget_kwargs(self.t, font=self.fonts["mono"]))
        self._configure_log_tags()
        self._refresh_log_if_open()
        if self.engine and self.engine.is_paused():
            self.state_banner.refresh_theme("paused")
        elif self.state_banner._visible:
            self.state_banner.refresh_theme("stopped")
        self.root.update_idletasks()

    def _refresh_log_if_open(self):
        # Keep log colours/font in sync after a theme/font change.
        pass

    def on_theme_or_font_change(self, theme, font):
        if theme not in THEME_CHOICES or font not in FONT_CHOICES:
            return
        self.theme_name = theme
        self.font_family = font
        for f in self.fonts.values():
            f.configure(family=font)
        save_preferences(theme=theme, font=font)
        self._apply_preferences_to_widgets()

    # ---- actions ----
    def _save_current_preferences(self):
        """Persists the current option/preset state to settings.json.
        Called at run start, on window close, and after Undo, so presets
        (including Last.fm creds) survive even if the user quits without
        ever clicking Start."""
        save_preferences(
            theme=self.theme_name, font=self.font_family,
            lastfm_user=self._entry_value(self.lastfm_user_entry),
            lastfm_key=self._entry_value(self.lastfm_key_entry),
            unknown_lookup=self.unknown_var.get(), foreign_detect=self.foreign_var.get(),
            dry_run=self.dry_run_var.get(), force_rescan=self.force_rescan_var.get(),
            delete_batch_size=self.delete_batch_size_var.get(),
            source=self.source_var.get(),
            scope=(self.scope_names[0] if len(self.scope_names) == 1 and self.scope_mode == "include" else "Entire library"),
            scope_names=self.scope_names, scope_mode=self.scope_mode,
            # Empty string means "use the app install directory" (see
            # load_preferences) rather than persisting the resolved APP_DIR
            # path, so an app moved to a new install location doesn't keep
            # pointing at the old one.
            output_folder=("" if self.output_folder == APP_DIR else self.output_folder),
        )

    def _refresh_output_folder_display(self):
        """Called after the output folder changes in Settings so the
        main-window label (if it's currently showing a previous run's
        "Files saved to: ..." text) doesn't keep pointing at the old
        folder. Only touches the label when it's already displaying that
        line - an idle/mid-run label is left alone since it isn't
        showing a folder path at all."""
        if self.view_state.output_folder.startswith(f"{icons.FOLDER} Files saved to:"):
            self.view_state.output_folder = f"{icons.FOLDER} Files saved to: {self.output_folder}"
            self.view_state.push()

    def on_close(self):
        # Closing while a run is still active (whether via the window's
        # [X] or the in-app Close button, which now both route here)
        # used to destroy root out from under the worker thread: its
        # on_progress/on_status/on_finished callbacks still call
        # self.root.after(0, ...) after root is gone, and the run's
        # iTunes COM work/undo-log/cache writes are abandoned mid-flight
        # instead of stopping cleanly. Ask first, same confirm-before-
        # risky-action pattern as _confirm_live_run, and stop() the
        # engine (mirroring on_stop) before tearing down the window.
        if self.engine and self.engine.is_running():
            if not messagebox.askyesno(
                "Cleanup still running",
                "A cleanup run is still in progress. Closing now will "
                "stop it early - the same as clicking Stop.\n\n"
                "Close anyway?",
                parent=self.root,
            ):
                return
            self.engine.stop()
        self._save_current_preferences()
        # Remember whatever size/position the user leaves the main window
        # at, mirroring SettingsDialog._on_close's handling of its own
        # window - a deliberate resize (e.g. to see more of the log pane)
        # persists across launches instead of resetting to the fixed
        # default every time.
        try:
            geometry = self.root.geometry()
            save_preferences(main_window_geometry=geometry)
            self.preferences["main_window_geometry"] = geometry
        except Exception:
            pass
        self.root.destroy()

    def on_start(self):
        if self.engine and self.engine.is_running():
            return
        if not self.dry_run_var.get() and not self._live_run_acknowledged:
            if not self._confirm_live_run():
                return
        self._eta_pace_ema = None
        self._save_current_preferences()
        options = CleanupOptions(
            unknown_lookup=self.unknown_var.get(), foreign_detect=self.foreign_var.get(),
            dry_run=self.dry_run_var.get(), force_rescan=self.force_rescan_var.get(),
            lastfm_user=self._entry_value(self.lastfm_user_entry), lastfm_key=self._entry_value(self.lastfm_key_entry),
            prefer_lastfm=(self.source_var.get() == "lastfm"), output_folder=self.output_folder,
            scope_playlists=self.scope_names, scope_mode=self.scope_mode,
            delete_batch_size=self.delete_batch_size_var.get(),
        )
        self._set_controls_running(True)
        self.progress.configure(style="Horizontal.TProgressbar")
        self.state_banner.hide()
        self.phase_bar.reset()
        self.current_track_label.config(text=f"{icons.PLUG} Connecting to iTunes...")
        self._clear_log(); self._log(f"{icons.PLUG} Connecting to iTunes...")
        self.engine = CleanupEngine(options, on_progress=self._on_progress_threadsafe,
                                    on_finished=self._on_finished_threadsafe, on_status=self._on_status_threadsafe)
        self.engine.start()

    def _confirm_live_run(self):
        """Warns before a live (non-dry-run) run, since it can rewrite
        genres and permanently delete junk-named tracks. Includes a
        "don't ask again this session" checkbox so the identical
        dialog doesn't have to be dismissed on every single live run -
        it still reappears on the next app launch, and re-enabling Dry
        run and turning it back off resets it too (see on_dry_run's
        caller), so the warning can't be silently skipped forever by
        accident."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Confirm live run")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(**surface_window_kwargs(self.t))
        body = ttk.Frame(dlg, padding=(16, 14))
        body.pack(fill="both", expand=True)
        msg = (
            "This is a LIVE run (Dry run is off).\n\n"
            "LibraryCleaner may rewrite genre tags and PERMANENTLY "
            "DELETE tracks it identifies as junk (badly ripped CD "
            "entries). Deleted tracks cannot be restored automatically "
            "- iTunes has no undelete via COM.\n\n"
            "Genre changes can be reverted afterward with Undo; "
            "deletions cannot."
        )
        ttk.Label(body, text=msg, wraplength=380, justify="left").pack(anchor="w")
        skip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Don't ask again this session", variable=skip_var).pack(
            anchor="w", pady=(10, 0))
        result = {"go": False}
        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(14, 0))
        def do_continue():
            result["go"] = True
            if skip_var.get():
                self._live_run_acknowledged = True
            dlg.destroy()
        def do_cancel():
            dlg.destroy()
        ttk.Button(btns, text="Cancel", command=do_cancel).pack(side="right")
        ttk.Button(btns, text="Continue", command=do_continue, style="Accent.TButton").pack(
            side="right", padx=(0, 6))
        dlg.bind("<Escape>", lambda _e: do_cancel())
        dlg.protocol("WM_DELETE_WINDOW", do_cancel)
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.root.wait_window(dlg)
        return result["go"]

    def on_stop(self):
        if self.engine:
            self.engine.stop()
            self.stop_btn.config(state="disabled", text="… Stopping...")
            self.pause_btn.config(state="disabled")
            self.progress.configure(style="Paused.Horizontal.TProgressbar")
            self.state_banner.show("stopped", f"{icons.STOP_SQUARE} Stopping — this run cannot be resumed; starting again begins a new run.")
            self._log(f"{icons.STOP_SQUARE} Stop requested — this run will end and cannot be resumed; starting again begins a new run from the top. Use Pause instead to preserve your place.")

    def on_pause(self):
        if not self.engine: return
        if self.engine.is_paused():
            self.engine.resume(); self.pause_btn.config(text=f"{icons.PAUSE} Pause"); self.current_track_label.config(text=f"{icons.PLAY} Resumed."); self._log(f"{icons.PLAY} Resumed."); self.stop_btn.config(state="normal")
            self.progress.configure(style="Horizontal.TProgressbar")
            self.state_banner.hide()
        else:
            self.engine.pause(); self.pause_btn.config(text=f"{icons.PLAY} Resume"); self.current_track_label.config(text=f"{icons.PAUSE} Paused."); self._log(f"{icons.PAUSE} Paused.")
            self.progress.configure(style="Paused.Horizontal.TProgressbar")
            self.state_banner.show("paused", f"{icons.PAUSE} Paused — Resume continues from exactly this track.")

    def on_refresh_playlists(self, on_done=None):
        """Reloads the playlist list from iTunes. on_done, if given, is
        called on the GUI thread once the refresh completes (whether or
        not it succeeded) - used so the scope picker can auto-refresh
        itself when opened instead of requiring a separate manual
        Refresh click first."""
        self.scope_refresh_btn.config(state="disabled", text="…")

        def work():
            try:
                with itunes_com.com_apartment():
                    app = itunes_com.connect()
                    return itunes_com.list_playlist_names(app)
            except Exception:
                log.exception("Failed to refresh playlist list from iTunes")
                return []

        def apply(names):
            self.available_playlists = names
            # Drop any previously-selected scope names that no longer
            # exist (renamed/deleted playlist) rather than silently
            # running against a stale/empty selection.
            self.scope_names = [n for n in self.scope_names if n in names]
            self._refresh_scope_summary()
            self.scope_refresh_btn.config(state="normal", text="⟳ Refresh")
            if on_done:
                on_done()

        run_in_background(self.root, work, apply)

    def on_open_scope_picker(self):
        # Auto-refresh the playlist list as the picker opens, so a
        # playlist created/renamed/deleted in iTunes since the app
        # launched (or since the last manual ⟳ Refresh) is reflected
        # immediately instead of requiring a separate Refresh click
        # before Choose… shows accurate options.
        dlg = ScopePickerDialog(self.root, self)
        dlg.set_refreshing(True)
        self.on_refresh_playlists(on_done=lambda: dlg.refresh_playlist_list())

    def _refresh_scope_summary(self):
        if not self.scope_names:
            self.scope_summary_var.set("Entire library")
        elif self.scope_mode == "exclude":
            self.scope_summary_var.set(
                f"All except {self.scope_names[0]}" if len(self.scope_names) == 1
                else f"All except {len(self.scope_names)} playlists")
        else:
            self.scope_summary_var.set(
                self.scope_names[0] if len(self.scope_names) == 1
                else f"{len(self.scope_names)} playlists selected")

    def on_open_settings(self):
        SettingsDialog(self.root, self)

    def on_open_merge_albums(self):
        MergeAlbumsDialog(self.root, self)

    def on_undo(self):
        self.undo_btn.config(state="disabled"); self.start_btn.config(state="disabled")
        self.current_track_label.config(text=f"{icons.UNDO} Undoing last run..."); self._clear_log(); self._log(f"{icons.UNDO} Undoing last run...")

        def work():
            undo_last_run(self.output_folder, on_status=self._on_status_threadsafe)

        def apply(_result):
            self.undo_btn.config(state="normal"); self.start_btn.config(state="normal")

        run_in_background(self.root, work, apply)

    def _check_existing_undo_log(self):
        if os.path.exists(os.path.join(self.output_folder, UNDO_LOG_NAME)):
            self.undo_btn.config(state="normal")

    # ---- logging/progress ----
    def _log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        tag = self._log_tag_for(msg)
        self.log_text.config(state="normal")
        if tag:
            self.log_text.insert("end", f"[{timestamp}] {msg}\n", (tag,))
        else:
            self.log_text.insert("end", f"[{timestamp}] {msg}\n")
        self._log_line_count += 1
        if self._log_line_count > LOG_MAX_LINES:
            self.log_text.delete("1.0", "2.0"); self._log_line_count -= 1
        self.log_text.see("end"); self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal"); self.log_text.delete("1.0", "end"); self.log_text.config(state="disabled"); self._log_line_count = 0

    def _on_progress_threadsafe(self, stats): _safe_after(self.root, lambda: self._render_progress(stats))
    def _on_status_threadsafe(self, msg): _safe_after(self.root, lambda: (self.current_track_label.config(text=msg), self._log(msg)))
    def _on_finished_threadsafe(self, stats): _safe_after(self.root, lambda: self._render_finished(stats))

    def _render_progress(self, stats):
        total = max(stats.total_tracks, 1)
        pct = min(100, int((stats.current_index / total) * 100))
        vs = self.view_state
        vs.percent = f"{pct}%"
        vs.processed = f"{stats.current_index} / {stats.total_tracks}"
        vs.remaining = str(max(0, stats.total_tracks - stats.current_index))
        vs.changed = str(stats.changed_count)
        vs.deleted = str(stats.deleted_count)
        if stats.start_time:
            elapsed = time.time() - stats.start_time
            m, sec = divmod(int(elapsed), 60)
            vs.elapsed = f"{m}m {sec}s" if m else f"{sec}s"
            if stats.current_index > 0 and elapsed >= 1 and stats.total_tracks > stats.current_index:
                eta = int(self._smoothed_eta_seconds(stats, elapsed))
                em, es = divmod(eta, 60); eh, em = divmod(em, 60)
                vs.eta = f"{eh}h {em}m" if eh else (f"{em}m {es}s" if em else f"{es}s")
            elif stats.current_index >= stats.total_tracks:
                vs.eta = "Complete"
        vs.push()
        self.progress.set_target(pct)
        self.phase_bar.update_from_stats(stats)

    def _smoothed_eta_seconds(self, stats, elapsed):
        """ETA via an exponential moving average of seconds-per-track,
        instead of a single elapsed/index-so-far ratio. A raw linear
        extrapolation swings wildly on the first few tracks (e.g. one
        slow online lookup early on skews the whole estimate); an EMA
        of the observed pace responds to real trend changes over the
        run but damps single-track noise, giving a steadier number
        without needing to store a full sample history."""
        pace = elapsed / stats.current_index
        prev = self._eta_pace_ema
        if prev is None:
            self._eta_pace_ema = pace
        else:
            alpha = 0.25  # weight on the newest sample; lower = smoother
            self._eta_pace_ema = (alpha * pace) + ((1 - alpha) * prev)
        remaining = stats.total_tracks - stats.current_index
        return self._eta_pace_ema * remaining

    def _render_finished(self, stats):
        vs = self.view_state
        self.progress.configure(style="Horizontal.TProgressbar")
        self.state_banner.hide()
        if stats.total_tracks == 0:
            vs.percent = "0%"; vs.push()
            self.progress.set_target(0); self._set_controls_running(False); self._check_existing_undo_log(); return
        vs.percent = "100%"; vs.eta = "Complete"
        vs.processed = f"{stats.current_index} / {stats.total_tracks}"; vs.remaining = "0"
        if stats.stopped: msg = f"{icons.STOPPED} Stopped."
        elif self.dry_run_var.get(): msg = f"{icons.PREVIEW} Dry run complete — nothing was changed."
        elif stats.failed_write_count or stats.failed_delete_count: msg = f"{icons.WARNING} Done, but some changes failed. See changelog."
        else: msg = f"{icons.SUCCESS} All done! ({stats.skipped_fixed_count} already clean)"
        vs.current_track = msg
        if not self.dry_run_var.get(): vs.output_folder = f"{icons.FOLDER} Files saved to: {self.output_folder}"
        vs.push()
        self.progress.set_target(100)
        self._log(msg)
        self._set_controls_running(False); self._check_existing_undo_log()
        if stats.stopped:
            self.start_btn.config(text=f"{icons.PLAY} Start New Run", command=self.on_start, state="normal")
            Tooltip(self.start_btn, "Stopped runs can't be continued — this starts a fresh run from the beginning. Use Pause instead of Stop next time to preserve your place.")
        else:
            self.start_btn.config(text=f"{icons.CHECK} Finished", command=self._reset_to_main_menu, state="normal")
        self._notify_run_finished(stats)
        self._show_review_popup(stats)

    def _notify_run_finished(self, stats):
        """Best-effort notification that a run has finished, for when the
        window isn't focused: taskbar flash on Windows (bell() elsewhere
        is a no-op fallback) plus an OS-level toast if available. Never
        raises - a notification failing is not worth interrupting the
        user's finished run over."""
        try:
            if not bool(self.root.focus_get()):
                try:
                    self.root.bell()
                except Exception:
                    pass
                try:
                    # Windows-only taskbar flash; silently skipped elsewhere.
                    import ctypes
                    hwnd = self.root.winfo_id()
                    FLASHW_ALL, FLASHW_TIMERNOFG = 0x00000003, 0x0000000C
                    class FLASHWINFO(ctypes.Structure):
                        _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                                    ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                                    ("dwTimeout", ctypes.c_uint)]
                    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 5, 0)
                    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
                except Exception:
                    pass
            try:
                summary = ("Dry run complete" if self.dry_run_var.get() else "Cleanup finished") \
                    + f" - {stats.changed_count} changed, {stats.deleted_count} deleted"
                self._show_os_toast(f"{APP_NAME} finished", summary)
            except Exception:
                pass
        except Exception:
            pass

    def _show_os_toast(self, title, message):
        """Shows a Windows toast notification if win10toast (or an
        equivalent) is importable; silently does nothing otherwise so this
        stays an optional enhancement rather than a new hard dependency."""
        try:
            from win10toast import ToastNotifier
        except ImportError:
            self._toast_available = False
            return
        self._toast_available = True
        try:
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        except Exception:
            pass

    def _show_review_popup(self, stats):
        """Post-run review: what changed, what was deleted, and any
        failures - the same detail the changelog.txt gets, surfaced in
        the app so a user doesn't have to go find that file."""
        if stats.total_tracks == 0 or stats.stopped:
            return
        rows = list(getattr(self.engine, "undo_log_rows", []) or [])
        diag_lines = list(stats.delete_diag_lines or [])
        RunReviewDialog(self.root, self, stats, rows, diag_lines, dry_run=self.dry_run_var.get())

    def _reset_to_main_menu(self):
        self.view_state.reset()
        self.progress.set_target(0)
        self.progress.configure(style="Horizontal.TProgressbar")
        self.state_banner.hide()
        self.phase_bar.reset()
        self._clear_log()
        self.start_btn.config(text=f"{icons.PLAY} Start Cleanup", command=self.on_start, state="normal")

    def _set_controls_running(self, running):
        state = "disabled" if running else "normal"
        for w in (self.unknown_cb, self.foreign_cb, self.dry_run_cb, self.force_rescan_cb, self.itunes_rb, self.lastfm_rb,
                  self.lastfm_user_entry, self.lastfm_key_entry, self.undo_btn, self.scope_refresh_btn, self.settings_btn):
            w.config(state=state)
        self.scope_pick_btn.config(state=state)
        self.start_btn.config(state="disabled" if running else "normal", text="… Running..." if running else self.start_btn.cget("text"))
        if running:
            self.pause_btn.pack(side="right", padx=3); self.stop_btn.pack(side="right", padx=3)
            self.pause_btn.config(state="normal", text=f"{icons.PAUSE} Pause"); self.stop_btn.config(state="normal", text=f"{icons.STOP_SQUARE} Stop")
        else:
            self.pause_btn.pack_forget(); self.stop_btn.pack_forget()


class GenreRuleEditor(ttk.Frame):
    """Small CRUD/reorder editor for persistent custom genre rules."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.rows = []

        top = ttk.Frame(self)
        top.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(top, height=8, **listbox_kwargs(app.t, font=app.fonts["body"]))
        self.listbox.pack(fill="both", expand=True, side="left")
        side = ttk.Frame(top); side.pack(fill="y", side="right", padx=(8, 0))
        self.pattern_var = tk.StringVar(); self.target_var = tk.StringVar()
        ttk.Label(side, text="Pattern").pack(anchor="w")
        ttk.Entry(side, textvariable=self.pattern_var, width=22).pack(pady=(0, 5))
        ttk.Label(side, text="Target genre").pack(anchor="w")
        ttk.Entry(side, textvariable=self.target_var, width=22).pack(pady=(0, 2))
        # Inline shadow warning: fires as the pattern/target fields are
        # edited (not just when the separate test box below is used), so
        # "this new rule would never fire because an existing
        # higher-priority rule already matches everything it would" is
        # visible while still composing the rule, before Add/Update.
        self.inline_warning_var = tk.StringVar(value="")
        self.inline_warning_label = ttk.Label(side, textvariable=self.inline_warning_var,
                                               style="PanelMuted.TLabel", wraplength=170, justify="left")
        self.inline_warning_label.pack(anchor="w", pady=(0, 6), fill="x")
        self.pattern_var.trace_add("write", lambda *_a: self._check_inline_shadow())
        self.target_var.trace_add("write", lambda *_a: self._check_inline_shadow())
        for text, cmd in (("Add", self.add_rule), ("Update", self.update_rule), ("Delete", self.delete_rule), ("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1))):
            ttk.Button(side, text=text, command=cmd).pack(fill="x", pady=2)
        ttk.Button(side, text="Import CSV…", command=self.import_csv).pack(fill="x", pady=(8, 2))
        self.listbox.bind("<<ListboxSelect>>", self.select_rule)
        # Drag-and-drop reordering, as an alternative to the ↑/↓ buttons
        # above (both remain available - this doesn't replace them).
        # Tracks the row a drag started on and swaps it toward wherever
        # the pointer currently is over the listbox on every <B1-Motion>
        # tick, so the list visually reorders live as you drag rather
        # than only snapping into place on release. Uses the same
        # self.rows + persist() path as move(), so it's exercised by
        # the same import/edit code the button-based reorder already
        # relies on.
        self._drag_index = None
        self.listbox.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.listbox.bind("<B1-Motion>", self._drag_motion, add="+")
        self.listbox.bind("<ButtonRelease-1>", self._drag_end, add="+")

        # Test box: lets a pattern be sanity-checked against a sample
        # genre string before it's saved, using the same substring match
        # map_genre() uses - so "does this pattern do what I think" can
        # be answered without adding the rule and re-running the app.
        test_box = ttk.Frame(self, style="Panel.TFrame", padding=6)
        test_box.pack(fill="x", pady=(8, 0))
        test_box.grid_columnconfigure(0, weight=1)
        ttk.Label(test_box, text="Test pattern against a genre string:", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.test_genre_var = tk.StringVar()
        test_entry = ttk.Entry(test_box, textvariable=self.test_genre_var)
        test_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(test_box, text="Test", command=self.run_test).grid(row=1, column=1, padx=(6, 0), pady=(4, 0))
        self.test_result_var = tk.StringVar(value="")
        ttk.Label(test_box, textvariable=self.test_result_var, style="PanelMuted.TLabel", wraplength=380).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        test_entry.bind("<Return>", lambda _e: self.run_test())

        self.reload()

    def _check_inline_shadow(self):
        """Live shadow check as the pattern field is edited: warns if a
        higher-priority existing rule (an earlier custom row, or any
        built-in) is itself a substring of the new pattern - meaning
        every genre string the new pattern could ever match also
        contains that existing pattern, so the existing rule always
        fires first and the new one could never actually apply.
        Structural (find_shadowing_rule), not tied to any sample genre
        string - complements the test box below, which checks one
        concrete string against the full pipeline instead."""
        pattern = self.pattern_var.get().strip()
        if not pattern:
            self.inline_warning_var.set("")
            return
        sel = self.listbox.curselection()
        exclude_index = sel[0] if sel else None
        hit = find_shadowing_rule(pattern, existing_rows=self.rows, exclude_index=exclude_index)
        if hit is None:
            self.inline_warning_var.set("")
            return
        shadow_pattern, _shadow_target, source = hit
        self.inline_warning_var.set(
            f'⚠ Fully shadowed by "{shadow_pattern}" ({source}), which '
            f'matches first and will always fire before this rule can.')

    def import_csv(self):
        """Bulk-loads pattern,target rows from a CSV file (dialog) or
        pasted text (small paste dialog) - faster than one-by-one Add
        for a large rule set. Parsed via genre_rules.parse_patterns_csv
        so header/no-header and error reporting stay in one place;
        valid rows are appended to the in-memory list and saved
        together in one persist() call, and any per-line errors are
        shown so a bad line doesn't silently vanish."""
        path = filedialog.askopenfilename(
            title="Import genre rules from CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
        except OSError as e:
            messagebox.showerror("Import failed", f"Could not read that file:\n{e}", parent=self)
            return
        new_rows, errors = parse_patterns_csv(text)
        if not new_rows:
            messagebox.showwarning(
                "Nothing to import",
                "No valid pattern,target rows were found in that file."
                + (f"\n\n{len(errors)} line(s) had problems:\n" + "\n".join(errors[:10]) if errors else ""),
                parent=self,
            )
            return
        existing = {p for p, _ in self.rows}
        added = 0
        for pattern, target in new_rows:
            if pattern in existing:
                # A pattern already present is updated in place (last
                # imported row wins) rather than duplicated, matching
                # how Update behaves for a single manual edit.
                self.rows = [(pattern, target) if p == pattern else (p, t) for p, t in self.rows]
            else:
                self.rows.append((pattern, target))
                existing.add(pattern)
            added += 1
        self.persist()
        summary = f"Imported {added} rule(s) from {os.path.basename(path)}."
        if errors:
            summary += f"\n\n{len(errors)} line(s) were skipped:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                summary += f"\n…and {len(errors) - 10} more."
        messagebox.showinfo("Import complete", summary, parent=self)

    def run_test(self):
        pattern = self.pattern_var.get().strip()
        genre = self.test_genre_var.get().strip()
        target = self.target_var.get().strip()
        if not pattern or not genre:
            self.test_result_var.set("Enter both a pattern and a sample genre string above.")
            return
        matches, normalized = test_pattern_against(genre, pattern)
        if not matches:
            self.test_result_var.set(f'✗ "{pattern}" does NOT match "{genre}" (compared as "{normalized}").')
            return
        # Also show what the full pipeline (custom rules, then
        # built-ins) would actually produce, in case a higher-priority
        # existing rule would fire first and shadow this one.
        preview = preview_genre_mapping(genre, extra_pattern=pattern, extra_target=target or None)
        if preview["matched_source"] == "candidate" or not target:
            self.test_result_var.set(f'✓ "{pattern}" matches "{genre}" → would map to "{target or "(set a target genre)"}"')
        else:
            self.test_result_var.set(
                f'✓ "{pattern}" matches, but "{preview["matched_pattern"]}" ({preview["matched_source"]}) '
                f'has higher priority and would map it to "{preview["result"]}" instead. '
                f'Move this rule above that one to make it win.')

    def reload(self):
        self.rows = list(load_custom_patterns())
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, "end")
        for pattern, target in self.rows:
            self.listbox.insert("end", f"{pattern}  →  {target}")
        self.app._apply_theme()

    def select_rule(self, _event=None):
        sel = self.listbox.curselection()
        if sel:
            p, t = self.rows[sel[0]]; self.pattern_var.set(p); self.target_var.set(t)

    def persist(self):
        save_custom_patterns(self.rows)
        self.refresh()

    def add_rule(self):
        p, t = self.pattern_var.get().strip(), self.target_var.get().strip()
        if p and t: self.rows.append((p, t)); self.persist()

    def update_rule(self):
        sel = self.listbox.curselection()
        p, t = self.pattern_var.get().strip(), self.target_var.get().strip()
        if sel and p and t: self.rows[sel[0]] = (p, t); self.persist()

    def delete_rule(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        p, t = self.rows[sel[0]]
        if not messagebox.askyesno(
            "Delete custom rule",
            f'Delete the custom rule "{p}" → "{t}"?\n\nThis can\'t be undone.',
            parent=self,
        ):
            return
        self.rows.pop(sel[0]); self.persist()

    def move(self, delta):
        sel = self.listbox.curselection()
        if not sel: return
        i = sel[0]; j = i + delta
        if 0 <= j < len(self.rows):
            self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
            self.persist(); self.listbox.selection_set(j); self.listbox.activate(j)

    def _drag_start(self, event):
        index = self.listbox.nearest(event.y)
        if 0 <= index < len(self.rows):
            self._drag_index = index
        else:
            self._drag_index = None

    def _drag_motion(self, event):
        if self._drag_index is None:
            return
        target = self.listbox.nearest(event.y)
        target = max(0, min(target, len(self.rows) - 1))
        if target == self._drag_index:
            return
        # Move the dragged row directly to the pointer's row (not a
        # single-step swap like move()), so a fast drag across several
        # rows keeps up with the pointer in one motion event instead of
        # trailing behind it.
        row = self.rows.pop(self._drag_index)
        self.rows.insert(target, row)
        self._drag_index = target
        self.refresh()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(target)
        self.listbox.activate(target)

    def _drag_end(self, _event):
        if self._drag_index is not None:
            # persist() re-saves and calls refresh() again; a no-op
            # visually since _drag_motion already left the list in its
            # final order, but it's what writes the reordered rows to
            # disk (refresh() alone only updates the widget).
            self.persist()
            self.listbox.selection_set(self._drag_index)
            self.listbox.activate(self._drag_index)
        self._drag_index = None


class ScopePickerDialog(tk.Toplevel):
    """Lets the user scope a run to zero, one, or several playlists, in
    either "only these" (include) or "everything except these"
    (exclude) mode - the multi-select / exclude-mode picker the old
    single-choice Combobox couldn't offer."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = app.t
        self.title("Choose scope")
        self.geometry("380x440")
        self.minsize(320, 340)
        self.transient(parent)
        self.grab_set()
        self.configure(**surface_window_kwargs(t))

        ttk.Label(self, text="Run against", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(14, 6))

        self.mode_var = tk.StringVar(value=app.scope_mode)
        mode_frame = ttk.Frame(self)
        mode_frame.pack(fill="x", padx=14)
        ttk.Radiobutton(mode_frame, text="Only the selected playlists", variable=self.mode_var,
                         value="include", command=self._sync_state).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Entire library, except the selected playlists", variable=self.mode_var,
                         value="exclude", command=self._sync_state).pack(anchor="w", pady=(2, 0))

        list_header = ttk.Frame(self)
        list_header.pack(fill="x", padx=14, pady=(10, 3))
        ttk.Label(list_header, text="Playlists (pick any number):", style="Muted.TLabel").pack(side="left")
        self.refresh_status_var = tk.StringVar(value="")
        ttk.Label(list_header, textvariable=self.refresh_status_var, style="Muted.TLabel").pack(side="right")

        list_frame = ttk.Frame(self, style="Panel.TFrame", padding=4)
        list_frame.pack(fill="both", expand=True, padx=14)
        self.listbox = tk.Listbox(list_frame, selectmode="extended", **listbox_kwargs(t, font=app.fonts["body"]))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.hint_var, style="Muted.TLabel", wraplength=340).pack(
            anchor="w", padx=14, pady=(6, 0))
        self._sync_state()

        self.empty_hint = ttk.Label(self, text="No playlists found in your library.",
                                     style="Muted.TLabel", wraplength=340)

        btns = ttk.Frame(self, padding=(14, 10, 14, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Clear (entire library)", command=self._clear).pack(side="left")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Apply", command=self._apply).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())

        self.refresh_playlist_list()

    def set_refreshing(self, refreshing):
        self.refresh_status_var.set("⟳ Refreshing playlists…" if refreshing else "")

    def refresh_playlist_list(self):
        """(Re)populates the listbox from app.available_playlists,
        preserving whatever's currently selected/checked where the
        name still exists. Safe to call multiple times, including
        after the dialog is already open (e.g. once an
        auto-refresh triggered from on_open_scope_picker completes)."""
        if not self.winfo_exists():
            return
        self.set_refreshing(False)
        current_selection = {self.listbox.get(i) for i in self.listbox.curselection()}
        wanted = current_selection or set(self.app.scope_names)
        self.listbox.delete(0, "end")
        for name in self.app.available_playlists:
            self.listbox.insert("end", name)
        for i, name in enumerate(self.app.available_playlists):
            if name in wanted:
                self.listbox.selection_set(i)
        if self.app.available_playlists:
            self.empty_hint.pack_forget()
        else:
            self.empty_hint.pack(anchor="w", padx=14, pady=(4, 0))

    def _sync_state(self):
        if self.mode_var.get() == "exclude":
            self.hint_var.set("Everything in your library will be processed, except tracks in the playlists you check above.")
        else:
            self.hint_var.set("Only tracks in the playlists you check above will be processed. Select several to combine them.")

    def _clear(self):
        self.listbox.selection_clear(0, "end")
        self.app.scope_names = []
        self.app.scope_mode = "include"
        self.app._refresh_scope_summary()
        self.destroy()

    def _apply(self):
        sel = self.listbox.curselection()
        names = [self.listbox.get(i) for i in sel]
        self.app.scope_names = names
        self.app.scope_mode = self.mode_var.get() if names else "include"
        self.app._refresh_scope_summary()
        self.destroy()


class RunReviewDialog(tk.Toplevel):
    """Post-run review popup: a scrollable, filterable list of every
    genre change and deletion from the run that just finished, plus any
    delete failures. Read-only summary - Undo (main window) remains the
    way to revert genre changes."""
    def __init__(self, parent, app, stats, undo_rows, diag_lines, dry_run):
        super().__init__(parent)
        self.app = app
        t = app.t
        self.title("Run review — what changed")
        self.geometry("620x460")
        self.minsize(480, 340)
        self.transient(parent)
        self.configure(**surface_window_kwargs(t))

        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        title_text = "Dry run preview — nothing was written" if dry_run else "Run complete"
        ttk.Label(header, text=title_text, font=app.fonts["stat"]).pack(anchor="w")
        summary = (f"{stats.changed_count} genre change(s) · {stats.deleted_count} deletion(s) · "
                   f"{stats.skipped_fixed_count} already clean · {stats.current_index}/{stats.total_tracks} tracks processed")
        if stats.failed_write_count or stats.failed_delete_count:
            summary += f" · {stats.failed_write_count + stats.failed_delete_count} failed"
        ttk.Label(header, text=summary, style="Muted.TLabel", wraplength=580).pack(anchor="w", pady=(2, 0))

        filt = ttk.Frame(self, padding=(14, 4))
        filt.pack(fill="x")
        ttk.Label(filt, text="Show:").pack(side="left", padx=(0, 6))
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(filt, textvariable=self.filter_var, state="readonly",
                                     values=["All", "Genre changes", "Deletions", "Failures"], width=16)
        filter_combo.pack(side="left")
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        list_frame = ttk.Frame(self, style="Panel.TFrame", padding=5)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(6, 6))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(list_frame, wrap="word", state="disabled", padx=6, pady=6,
                             **text_widget_kwargs(t, font=app.fonts["mono"]))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self._rows = undo_rows
        self._diag_lines = diag_lines
        self._failed_records = list(getattr(stats, "failed_records", []) or [])
        self._refresh()

        btns = ttk.Frame(self, padding=(14, 0, 14, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")
        self.retry_btn = ttk.Button(btns, text=f"{icons.REPEAT} Retry failed", command=self._on_retry)
        if self._failed_records:
            self.retry_btn.pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())

    def _refresh(self):
        choice = self.filter_var.get()
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        shown = 0
        if choice in ("All", "Genre changes"):
            for row in self._rows:
                if row["action"] == "GENRE":
                    self.text.insert("end", f"{icons.MUSIC} {row['artist']} - {row['name']}\n"
                                             f"    \"{row['old_genre'] or '(blank)'}\" → \"{row['new_genre']}\"\n\n")
                    shown += 1
        if choice in ("All", "Deletions"):
            for row in self._rows:
                if row["action"] == "DELETED":
                    self.text.insert("end", f"{icons.TRASH} {row['artist']} - {row['name']} — deleted (junk filename)\n\n")
                    shown += 1
        if choice in ("All", "Failures"):
            # Prefer the structured per-track records (artist/name/reason)
            # so a failure is actionable in-UI; fall back to the plain
            # diagnostic lines for anything without a structured record
            # (shouldn't normally happen, but keeps this robust).
            if self._failed_records:
                for rec in self._failed_records:
                    label = f"{rec.get('artist', '')} - {rec.get('name', '')}".strip(" -") or "(unknown track)"
                    kind = "Delete" if rec.get("kind") == "delete" else "Genre write"
                    self.text.insert("end", f"{icons.WARNING} {kind} | {label}\n    Reason: {rec.get('reason', 'Unknown error')}\n\n")
                    shown += 1
            else:
                for line in self._diag_lines:
                    self.text.insert("end", f"{icons.WARNING} {line}\n\n")
                    shown += 1
        if shown == 0:
            self.text.insert("end", "Nothing to show for this filter.")
        self.text.config(state="disabled")

    def _on_retry(self):
        if not self._failed_records:
            return
        self.retry_btn.config(state="disabled", text="… Retrying")
        records = list(self._failed_records)

        def work():
            return retry_failed_records(records, on_status=lambda _m: None)

        def apply(still_failed):
            self._failed_records = still_failed
            if not self.winfo_exists():
                return
            if still_failed:
                self.retry_btn.config(state="normal", text=f"{icons.REPEAT} Retry failed")
            else:
                self.retry_btn.pack_forget()
            messagebox.showinfo(
                "Retry complete",
                f"{len(records) - len(still_failed)} of {len(records)} succeeded."
                + (f"\n{len(still_failed)} still failing — see the Failures list."
                   if still_failed else "\nAll failed items were fixed."),
                parent=self,
            )
            self._refresh()

        run_in_background(self, work, apply)


class MergeAlbumsDialog(tk.Toplevel):
    """Scans the library for albums iTunes has split into two entries
    (a main group plus one or more stray tracks with a missing or
    mismatched Album/AlbumArtist) and lets the user review and apply
    the merge. Three steps in one window, swapped in place rather than
    as separate dialogs: Scan -> Review (checkable list of detected
    groups + a per-field diff preview) -> Apply (progress, reusing the
    same on_progress/on_finished callback shape as CleanupEngine)."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = app.t
        self.title("Merge Albums")
        self.geometry("640x520")
        self.minsize(520, 400)
        self.transient(parent)
        self.grab_set()
        self.configure(**surface_window_kwargs(t))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._groups = []          # list[SplitGroup] from the last scan
        self._group_vars = []      # list[tk.BooleanVar], one per group, in the same order
        self._merge_engine = None

        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        ttk.Label(header, text=f"{icons.MUSIC} Merge split albums", font=app.fonts["stat"]).pack(anchor="w")
        ttk.Label(header,
                  text="Scans your library for albums split into two entries - e.g. an 11/12-track "
                       "album plus a lone track missing the correct Album Artist or Album title - "
                       "and lets you review each group before merging.",
                  style="Muted.TLabel", wraplength=600).pack(anchor="w", pady=(2, 0))

        self.status_var = tk.StringVar(value="Click Scan to look for split albums.")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel", wraplength=600).pack(anchor="w", pady=(6, 0))

        self.confirm_online_var = tk.BooleanVar(value=False)
        confirm_cb = ttk.Checkbutton(
            header, variable=self.confirm_online_var,
            text=f"{icons.GLOBE} Confirm matches online (iTunes catalog) before showing them")
        confirm_cb.pack(anchor="w", pady=(6, 0))
        Tooltip(confirm_cb,
                "After the offline scan, double-checks each candidate group against the iTunes "
                "Search API and drops any where the two sides confidently resolve to different "
                "albums by different artists - e.g. two same-titled albums by unrelated artists. "
                "Off by default since it needs network access and adds one lookup per candidate "
                "group; a group is never added or removed just because a lookup failed or found "
                "nothing, so leaving this off just skips the extra check.")

        list_frame = ttk.Frame(self, style="Panel.TFrame", padding=5)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(6, 6))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(list_frame, wrap="word", state="disabled", padx=6, pady=6,
                             **text_widget_kwargs(t, font=app.fonts["mono"]))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.progress = SmoothProgressbar(self, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        # Only packed once a merge is actually running - see _on_apply/_on_merge_finished.

        btns = ttk.Frame(self, padding=(14, 0, 14, 12))
        btns.pack(fill="x")
        self._btns_frame = btns
        ttk.Button(btns, text="Close", command=self._on_close).pack(side="right")
        self.apply_btn = ttk.Button(btns, text=f"{icons.CHECK} Merge selected", command=self._on_apply, state="disabled")
        self.apply_btn.pack(side="right", padx=(0, 6))
        self.cancel_btn = ttk.Button(btns, text=f"{icons.STOP_SQUARE} Cancel", command=self._on_cancel)
        Tooltip(self.cancel_btn, "Stops the merge after the track currently being written finishes. Tracks already merged stay merged.")
        # Only packed once a merge is actually running - see _on_apply/_on_merge_finished.
        self.scan_btn = ttk.Button(btns, text=f"{icons.LOOKUP} Scan library", command=self._on_scan)
        self.scan_btn.pack(side="left")
        self.select_all_btn = ttk.Button(btns, text="Select all", command=lambda: self._set_all(True), state="disabled")
        self.select_all_btn.pack(side="left", padx=(6, 0))
        self.select_none_btn = ttk.Button(btns, text="Select none", command=lambda: self._set_all(False), state="disabled")
        self.select_none_btn.pack(side="left", padx=(6, 0))
        self.bind("<Escape>", lambda _e: self._on_close())

        self._checkbox_frame = None  # built fresh in _render_groups each scan

    # ---- scan ----
    def _on_scan(self):
        self.scan_btn.config(state="disabled", text=f"{icons.LOOKUP} Scanning…")
        self.apply_btn.config(state="disabled")
        self.select_all_btn.config(state="disabled")
        self.select_none_btn.config(state="disabled")
        self.status_var.set(f"{icons.PLUG} Connecting to iTunes and reading your library…")
        self._clear_checkbox_frame()

        def on_scan_status(msg):
            # Called from the background thread (see read_library_tracks) -
            # marshal onto the Tk thread before touching status_var, same
            # as CleanupEngine's on_status/_on_status_threadsafe elsewhere.
            _safe_after(self, lambda: self.status_var.set(msg))

        def work():
            with itunes_com.com_apartment():
                app_com = itunes_com.connect()
                tracks = read_library_tracks(app_com, on_status=on_scan_status)
            on_scan_status(f"{icons.LOOKUP} Comparing albums…")
            groups = find_split_groups(tracks)
            if groups and self.confirm_online_var.get():
                groups = confirm_split_groups_online(groups, on_status=on_scan_status)
            return groups

        def apply(groups):
            self.scan_btn.config(state="normal", text=f"{icons.LOOKUP} Scan library")
            if groups is None:
                self.status_var.set(f"{icons.ERROR} Could not read your library - is iTunes running?")
                return
            self._groups = groups
            if not groups:
                self.status_var.set(f"{icons.SUCCESS} No split albums found - your library looks clean.")
                self._render_groups()
                return
            self.status_var.set(
                f"{icons.LOOKUP} Found {len(groups)} possible split album(s). "
                "Review each below, untick any that aren't a real match, then Merge selected.")
            self._render_groups()
            self.apply_btn.config(state="normal")
            self.select_all_btn.config(state="normal")
            self.select_none_btn.config(state="normal")

        run_in_background(self, work, apply)

    # ---- review list ----
    def _clear_checkbox_frame(self):
        if self._checkbox_frame is not None:
            self._checkbox_frame.destroy()
            self._checkbox_frame = None
        self._group_vars = []

    def _render_groups(self):
        self._clear_checkbox_frame()
        self.text.config(state="normal")
        self.text.delete("1.0", "end")

        if not self._groups:
            self.text.insert("end", "Nothing to show. Run a scan to look for split albums.")
            self.text.config(state="disabled")
            return

        # A checkbox row per group is embedded into the Text widget via
        # window_create, and the diff preview for that group is written
        # as plain text right after it - keeps everything in one
        # scrollable pane instead of a separate fixed-height listbox
        # plus a separate preview pane fighting for space.
        self._checkbox_frame = ttk.Frame(self.text)  # parent for embedded checkbuttons; destroyed as a whole on next scan
        for idx, group in enumerate(self._groups):
            var = tk.BooleanVar(value=True)
            self._group_vars.append(var)
            cb = ttk.Checkbutton(self.text, variable=var,
                                  text=f"{group.main_album}  —  {group.main_album_artist}  "
                                       f"({len(group.main_tracks)} tracks + {len(group.stray_tracks)} stray)")
            self.text.window_create("end", window=cb)
            self.text.insert("end", "\n")
            for stray, fields in build_merge_plan(group):
                label = f"{stray.artist} - {stray.name}".strip(" -") or "(unknown track)"
                if not fields:
                    continue
                diff = ", ".join(f"{k}: \"{getattr(stray, _FIELD_ATTR.get(k, ''), '') or '(blank)'}\" → \"{v}\""
                                  for k, v in fields.items())
                self.text.insert("end", f"    {icons.MUSIC} {label}\n        {diff}\n")
            self.text.insert("end", "\n")
        self.text.config(state="disabled")

    def _set_all(self, value):
        for var in self._group_vars:
            var.set(value)

    # ---- apply ----
    def _on_apply(self):
        selected_groups = [g for g, var in zip(self._groups, self._group_vars) if var.get()]
        if not selected_groups:
            messagebox.showinfo("Nothing selected", "Tick at least one group to merge.", parent=self)
            return
        plan = []
        for g in selected_groups:
            plan.extend(build_merge_plan(g))
        if not plan:
            messagebox.showinfo("Nothing to change", "The selected group(s) already match - nothing to write.", parent=self)
            return

        if not messagebox.askyesno(
            "Merge albums",
            f"This will update {len(plan)} track(s) across {len(selected_groups)} album(s) in iTunes.\n\n"
            "Continue?",
            parent=self,
        ):
            return

        self.apply_btn.config(state="disabled", text=f"{icons.MUSIC} Merging…")
        self.scan_btn.config(state="disabled")
        self.select_all_btn.config(state="disabled")
        self.select_none_btn.config(state="disabled")
        self.progress.pack(fill="x", padx=14, pady=(0, 8), before=self._btns_frame)
        self.progress.set_target(0)
        self.status_var.set(f"{icons.MUSIC} Merging {len(plan)} track(s)…")
        self.cancel_btn.config(state="normal", text=f"{icons.STOP_SQUARE} Cancel")
        self.cancel_btn.pack(side="right", padx=(0, 6), before=self.apply_btn)

        self._merge_engine = AlbumMergeEngine(
            plan,
            on_progress=lambda stats: _safe_after(self, lambda: self._on_merge_progress(stats)),
            on_finished=lambda stats: _safe_after(self, lambda: self._on_merge_finished(stats)),
            on_status=lambda msg: _safe_after(self, lambda: self.status_var.set(msg)),
        )
        self._merge_engine.start()

    def _on_cancel(self):
        if self._merge_engine is not None and self._merge_engine.is_running():
            self._merge_engine.stop()
            self.cancel_btn.config(state="disabled", text=f"{icons.STOP_SQUARE} Cancelling…")
            self.status_var.set(f"{icons.STOP_SQUARE} Cancelling — finishing the current track, then stopping…")

    def _on_merge_progress(self, stats):
        if not self.winfo_exists():
            return
        pct = int(100 * stats.current_index / stats.total_tracks) if stats.total_tracks else 0
        self.progress.set_target(pct)

    def _on_merge_finished(self, stats):
        if not self.winfo_exists():
            return
        self.progress.pack_forget()
        self.cancel_btn.pack_forget()
        self.apply_btn.config(state="normal", text=f"{icons.CHECK} Merge selected")
        self.scan_btn.config(state="normal")
        self.select_all_btn.config(state="normal")
        self.select_none_btn.config(state="normal")
        msg = f"{icons.SUCCESS} Merge complete: {stats.updated_count} track(s) updated"
        if stats.failed_count:
            msg += f", {stats.failed_count} failed"
        if stats.stopped:
            msg += " (stopped early)"
        self.status_var.set(msg)
        # Re-scan so the review list reflects the new, merged state
        # rather than showing groups that no longer exist.
        self._on_scan()

    def _on_close(self):
        if self._merge_engine is not None and self._merge_engine.is_running():
            self._merge_engine.stop()
        self.destroy()


# Maps a merge-plan field name back to the TrackInfo attribute holding
# its *current* value, purely for building the "old" → "new" preview
# text in MergeAlbumsDialog._render_groups - the plan dict itself only
# carries the new value.
_FIELD_ATTR = {
    "Album": "album", "AlbumArtist": "album_artist", "TrackCount": "track_count",
    "DiscCount": "disc_count", "DiscNumber": "disc_number", "TrackNumber": "track_number",
    "Year": "year", "Genre": "genre",
}


class BuiltinRuleBrowser(ttk.Frame):
    """Read-only, searchable view of the built-in pattern -> target
    genre table, so "why did this get mapped to X" can be answered by
    searching here instead of reading source code - and so a user
    knows there's a pattern to add a higher-priority custom rule for."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        search_row = ttk.Frame(self)
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Search:").pack(side="left", padx=(0, 6))
        self.query_var = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.count_var = tk.StringVar()
        ttk.Label(self, textvariable=self.count_var, style="Muted.TLabel").pack(anchor="w", pady=(4, 4))

        list_frame = ttk.Frame(self, style="Panel.TFrame", padding=4)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, **listbox_kwargs(app.t, font=app.fonts["mono"]))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        rows = search_builtin_patterns(self.query_var.get())
        self.listbox.delete(0, "end")
        for pattern, target in rows:
            self.listbox.insert("end", f"{pattern}  →  {target}")
        total = len(PATTERNS)
        self.count_var.set(f"{len(rows)} of {total} built-in rules" if self.query_var.get().strip()
                            else f"{total} built-in rules (checked in this order, first match wins)")


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Settings")
        saved_size = app.preferences.get("settings_window_size") or SETTINGS_WINDOW_DEFAULT_SIZE
        self.geometry(saved_size)
        self.minsize(*SETTINGS_WINDOW_MIN_SIZE)
        self.transient(parent)
        self.grab_set()
        self.configure(**surface_window_kwargs(app.t))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.theme_var = tk.StringVar(value=app.theme_name)
        self.font_var = tk.StringVar(value=app.font_family)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        general = ttk.Frame(notebook); themes = ttk.Frame(notebook); genres = ttk.Frame(notebook); builtin_genres = ttk.Frame(notebook); changelog = ttk.Frame(notebook); info = ttk.Frame(notebook)
        notebook.add(general, text="General"); notebook.add(themes, text="Themes"); notebook.add(genres, text="Genres"); notebook.add(builtin_genres, text="Built-in rules"); notebook.add(changelog, text="Changelog"); notebook.add(info, text="About")

        ttk.Label(general, text="App-wide font", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(16, 4))
        ttk.Label(general, text="Applies to labels, controls, statistics, the log and this window.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 10))
        font_combo = ttk.Combobox(general, textvariable=self.font_var, values=FONT_CHOICES, state="readonly")
        font_combo.pack(fill="x", padx=14)
        font_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply())

        ttk.Label(general, text="Output folder", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(20, 4))
        ttk.Label(general, text="Where changelog.txt, the undo log, the debug log, and the processed-tracks cache are saved. Defaults to the app's install folder - pick another folder for a portable install or a synced folder (e.g. Dropbox/OneDrive).", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 6))
        folder_row = ttk.Frame(general)
        folder_row.pack(fill="x", padx=14)
        self.output_folder_var = tk.StringVar(value=app.output_folder)
        folder_entry = ttk.Entry(folder_row, textvariable=self.output_folder_var, state="readonly")
        folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Choose…", command=self._choose_output_folder).pack(side="left", padx=(6, 0))
        ttk.Button(folder_row, text="Reset to default", command=self._reset_output_folder).pack(side="left", padx=(6, 0))
        self.output_folder_status_var = tk.StringVar(value="")
        ttk.Label(general, textvariable=self.output_folder_status_var, style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(4, 0))

        ttk.Label(general, text="Advanced", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(20, 4))
        ttk.Label(general, text="How many junk-named tracks to delete before re-checking iTunes' track order. Lower this on slow/network drives if deletes seem to skip tracks; raise it on fast local libraries to speed up large cleanups.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 6))
        batch_row = ttk.Frame(general)
        batch_row.pack(anchor="w", padx=14)
        self.delete_batch_spin = tk.Spinbox(batch_row, from_=1, to=500, width=6,
                                             textvariable=self.app.delete_batch_size_var,
                                             command=self._on_batch_size_change)
        self.delete_batch_spin.pack(side="left")
        self.delete_batch_spin.bind("<FocusOut>", lambda _e: self._on_batch_size_change())
        self.delete_batch_spin.bind("<Return>", lambda _e: self._on_batch_size_change())

        ttk.Label(general, text="Processed-track cache (grows over years of use; deleted tracks leave stale entries behind)", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(12, 6))
        cache_row = ttk.Frame(general)
        cache_row.pack(anchor="w", padx=14)
        self.clean_cache_btn = ttk.Button(cache_row, text=f"{icons.BROOM} Reclaim space", command=self._on_vacuum_cache)
        self.clean_cache_btn.pack(side="left")
        Tooltip(self.clean_cache_btn, "Shrinks the cache file by reclaiming freed space. Keeps all entries - the next run still skips already-processed tracks.")
        self.clear_cache_btn = ttk.Button(cache_row, text=f"{icons.TRASH} Clear cache", command=self._on_clear_cache)
        self.clear_cache_btn.pack(side="left", padx=(6, 0))
        Tooltip(self.clear_cache_btn, "Removes every cached entry, including stale ones for tracks deleted from iTunes. The next run will re-check every track from scratch.")
        self.cache_status_var = tk.StringVar(value="")
        ttk.Label(general, textvariable=self.cache_status_var, style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(6, 0))

        ttk.Label(themes, text="Colour theme", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(16, 4))
        ttk.Label(themes, text="Ten themes are included, plus Auto, which follows your Windows light/dark setting. Text, muted text, controls and accents change together for readable contrast.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 10))
        theme_combo = ttk.Combobox(themes, textvariable=self.theme_var, values=THEME_CHOICES, state="readonly")
        theme_combo.pack(fill="x", padx=14)
        theme_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply())

        ttk.Label(genres, text="Custom genre mappings", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(14, 4))
        ttk.Label(genres, text="Add your own pattern → target rules. Rules are checked before the built-in mappings, and you can move them up or down.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 8))
        self.genre_editor = GenreRuleEditor(genres, app)
        self.genre_editor.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        ttk.Label(builtin_genres, text="Built-in genre mappings", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(14, 4))
        ttk.Label(builtin_genres, text="Checked after your custom rules above. To override one, add a custom rule for the same pattern (or a broader one) - custom rules always win.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(0, 8))
        self.builtin_browser = BuiltinRuleBrowser(builtin_genres, app)
        self.builtin_browser.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        ttk.Label(changelog, text="What's changed", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(14, 5))
        changelog_wrap = ttk.Frame(changelog)
        changelog_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        changelog_text = tk.Text(changelog_wrap, wrap="word", padx=8, pady=8, state="disabled",
                                  **text_widget_kwargs(app.t, font=app.fonts["mono"]))
        changelog_scroll = ttk.Scrollbar(changelog_wrap, orient="vertical", command=changelog_text.yview)
        changelog_text.configure(yscrollcommand=changelog_scroll.set)
        changelog_text.grid(row=0, column=0, sticky="nsew")
        changelog_scroll.grid(row=0, column=1, sticky="ns")
        changelog_wrap.grid_rowconfigure(0, weight=1); changelog_wrap.grid_columnconfigure(0, weight=1)
        try:
            with open(os.path.join(APP_DIR, "CHANGELOG.md"), "r", encoding="utf-8") as f:
                notes = f.read()
        except OSError:
            notes = "Changelog unavailable."
        changelog_text.configure(state="normal"); changelog_text.insert("1.0", notes); changelog_text.configure(state="disabled")

        ttk.Label(info, text=f"{APP_NAME} v{APP_VERSION}", font=app.fonts["stat"]).pack(anchor="w", padx=14, pady=(16, 5))
        ttk.Label(info, text="LibraryCleaner uses iTunes COM for local metadata changes and only contacts online services when an enabled lookup or language check needs them.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14)
        if not getattr(app, "_toast_available", True):
            ttk.Label(info, text="ℹ Windows toast notifications aren't available — install the optional win10toast package (pip install win10toast) to enable them. The taskbar flash still works without it.", style="Muted.TLabel", wraplength=450).pack(anchor="w", padx=14, pady=(10, 0))

        ttk.Button(self, text="Close", command=self._on_close).pack(anchor="e", padx=12, pady=(0, 12))

    def _apply(self):
        self.app.on_theme_or_font_change(self.theme_var.get(), self.font_var.get())
        self.configure(**surface_window_kwargs(self.app.t))

    def _on_batch_size_change(self):
        # Guard against a blank/non-numeric Spinbox entry (mid-edit or
        # cleared by the user) rather than letting IntVar.get() raise.
        try:
            value = int(self.delete_batch_spin.get())
        except (TypeError, ValueError):
            return
        if value <= 0:
            return
        self.app.delete_batch_size_var.set(value)
        save_preferences(delete_batch_size=value)
        self.app.preferences["delete_batch_size"] = value

    def _choose_output_folder(self):
        """Lets the user redirect changelog/undo-log/debug-log/cache
        output to a folder of their choice instead of the fixed app
        install directory - e.g. a portable USB install or a folder
        synced by Dropbox/OneDrive. Takes effect immediately (existing
        files are left where they were; nothing is moved) and is saved
        so it survives a restart."""
        chosen = filedialog.askdirectory(
            title="Choose output folder",
            initialdir=self.app.output_folder if os.path.isdir(self.app.output_folder) else APP_DIR,
            parent=self,
        )
        if not chosen:
            return
        chosen = os.path.normpath(chosen)
        if not os.access(chosen, os.W_OK):
            messagebox.showerror(
                "Folder not writable",
                f"LibraryCleaner can't write to:\n{chosen}\n\nChoose a different folder.",
                parent=self,
            )
            return
        self._set_output_folder(chosen)

    def _reset_output_folder(self):
        self._set_output_folder(APP_DIR)

    def _set_output_folder(self, folder):
        self.app.output_folder = folder
        self.output_folder_var.set(folder)
        save_preferences(output_folder=("" if folder == APP_DIR else folder))
        self.app.preferences["output_folder"] = "" if folder == APP_DIR else folder
        self.app._refresh_output_folder_display()
        self.output_folder_status_var.set(f"{icons.CHECK} Saved. New runs will write here.")

    def _on_vacuum_cache(self):
        # VACUUM rewrites the whole database file, which can take a
        # noticeable moment on a cache accumulated over years of use -
        # run it off the Tk thread (same run_in_background pattern as
        # on_undo/on_refresh_playlists) so it can't freeze the Settings
        # dialog (and the whole app, since Tk is single-threaded).
        self.clean_cache_btn.config(state="disabled", text=f"{icons.BROOM} Cleaning…")
        self.cache_status_var.set("")

        def work():
            return vacuum_processed_cache(self.app.output_folder)

        def apply(result):
            ok, msg = result if result else (False, f"{icons.WARNING} Could not clean the cache.")
            self.cache_status_var.set(msg)
            self.clean_cache_btn.config(state="normal", text=f"{icons.BROOM} Reclaim space")

        run_in_background(self, work, apply)

    def _on_clear_cache(self):
        if not messagebox.askyesno(
            "Clear processed-track cache",
            "This removes every cached entry, including ones still valid for "
            "tracks that haven't changed. The next run will re-check every "
            "track from scratch instead of skipping already-processed ones.\n\n"
            "Continue?",
            parent=self,
        ):
            return
        # Same off-thread reasoning as _on_vacuum_cache: DELETE + VACUUM
        # on a large cache can take a moment and must not block the UI.
        self.clear_cache_btn.config(state="disabled", text=f"{icons.TRASH} Clearing…")
        self.cache_status_var.set("")

        def work():
            return clear_processed_cache(self.app.output_folder)

        def apply(result):
            ok, msg = result if result else (False, f"{icons.WARNING} Could not clear the cache.")
            self.cache_status_var.set(msg)
            self.clear_cache_btn.config(state="normal", text=f"{icons.TRASH} Clear cache")

        run_in_background(self, work, apply)

    def _on_close(self):
        # Remember whatever size the user leaves the window at, so a
        # deliberate resize (e.g. to see more of the Genres or
        # Built-in rules tabs) persists across Settings openings.
        try:
            size = f"{self.winfo_width()}x{self.winfo_height()}"
            save_preferences(settings_window_size=size)
            self.app.preferences["settings_window_size"] = size
        except Exception:
            pass
        self.destroy()


def main():
    # settings.json itself always lives in APP_DIR (it's what tells us
    # where the *rest* of the output should go, so it can't itself be
    # relocated) - but the debug log, like changelog/undo-log/cache,
    # should follow the user's chosen output folder if one is saved.
    prefs = load_preferences()
    output_folder = prefs["output_folder"] or APP_DIR
    if not os.path.isdir(output_folder):
        output_folder = APP_DIR
    configure_file_logging(output_folder)
    root = tk.Tk()
    GenreCleanupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
