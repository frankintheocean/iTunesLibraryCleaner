#!/usr/bin/env python3
"""Pre-build menu popup for GenreCleanup's build.bat (stdlib tkinter only -
same reasoning and same styling approach as build_progress.py: no new
dependency, and the popup should look like part of the same app rather
than a mismatched window). Ported from WhiteBoard's build\\build_menu.py.

build.bat launches this BEFORE it does anything else (before even its own
minimized-relaunch), so the person always sees this menu first when they
double-click build.bat, and picks one of:

    Start Build   - proceed with the normal build (build.bat's existing
                    flow: deps then PyInstaller then installer then finalize).
    Uninstall     - run the currently-installed GenreCleanup's own Inno
                    Setup uninstaller, if one is registered.
    Fix Build     - clean out build artifacts (venv, the dist folder, the
                    build/work folder, a stale root-level
                    GenreCleanup.exe) and then proceed with a fresh
                    Start Build.

This script never touches the filesystem beyond writing its single-line
result file (passed as argv[1]) - build.bat itself does all the actual
work for each choice, exactly as it already does for the build steps
below. If tkinter isn't available for any reason, this exits immediately
without writing a result, and build.bat falls back to starting the build
directly (same "popup is a nice-to-have, never something depended on"
guarantee build_progress.py already makes).

Usage (invoked by build.bat, not meant to be run directly):
    python build_menu.py <result_file>

Result file protocol (this script writes exactly one line, once, then
exits):
    START       - user chose Start Build
    UNINSTALL   - user chose Uninstall
    FIX         - user chose Fix Build
    (no file)   - window was closed without a choice; build.bat treats a
                  missing/empty result file the same as if the person had
                  cancelled entirely and does not start a build.
"""
import sys

try:
    import tkinter as tk
except Exception:
    # No display / no tkinter - degrade to no popup, exactly like
    # build_progress.py's own fallback; build.bat's own check for a
    # missing result file handles this the same way as a closed window.
    sys.exit(0)


def _rounded_rect_points(x0, y0, x1, y1, radius):
    """Identical to build_progress.py's helper of the same name - kept as
    its own copy here (rather than importing build_progress) so this
    script has no dependency on that file and can be invoked completely
    independently, matching how build.bat already treats the two popups
    as separate, independently-optional processes."""
    radius = max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0, y0 + radius,
        x0, y0,
        x0 + radius, y0,
        x1 - radius, y0,
        x1, y0,
        x1, y0 + radius,
        x1, y1 - radius,
        x1, y1,
        x1 - radius, y1,
        x0 + radius, y1,
        x0, y1,
        x0, y1 - radius,
    ]


def _write_result(path: str, value: str):
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
    except OSError:
        pass  # best-effort, same as build_progress.py's status writes


def main():
    if len(sys.argv) < 2:
        sys.exit(0)
    result_path = sys.argv[1]

    # Matches gui.py's own black/white palette (BG="#000000", FG="#ffffff",
    # DIM="#666666" - see app's main window) rather than reusing
    # WhiteBoard's iOS-Dark theme, plus standard status colors (accent/
    # danger/warning) that gui.py itself doesn't define since it has no
    # build tooling of its own. Font stack leads with "Segoe UI" to match
    # gui.py's own font choice instead of WhiteBoard's SF Pro stack.
    FONT_FAMILY = "Segoe UI"
    FONT_FALLBACKS = ("Segoe UI Variable", "Helvetica Neue", "Arial")
    BG = "#000000"          # matches gui.py BG
    SURFACE = "#1A1A1A"
    BORDER = "#333333"
    TEXT = "#FFFFFF"        # matches gui.py FG
    TEXT_MUTED = "#999999"  # matches gui.py's output_folder_label fg
    ACCENT = "#3399FF"
    DANGER = "#FF4444"
    WARNING = "#FF9F0A"

    try:
        import tkinter.font as tkfont

        root = tk.Tk()
        root.title("GenreCleanup - Build Menu")
        root.geometry("360x300")
        root.resizable(False, False)
        root.configure(bg=BG)
        # Always-on-top like build_progress.py's popup, for the same
        # reason: a small utility window shouldn't get lost behind other
        # windows the instant it loses focus.
        root.attributes("-topmost", True)

        # Closing this window (the [X], Alt+F4, Esc) is treated exactly
        # like not making a choice: no result is written, and build.bat's
        # own check for a missing/empty result file means no build starts
        # and nothing is uninstalled or cleaned - the safe default for an
        # abandoned prompt.
        def _on_close():
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _on_close)
        root.bind("<Escape>", lambda e: _on_close())

        # Dark title bar - identical best-effort DWM call to
        # build_progress.py's _apply_dark_title_bar, inlined here rather
        # than imported so this script stays fully standalone.
        try:
            import ctypes
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ok = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value),
            )
            if ok != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(value), ctypes.sizeof(value),
                )
            root.withdraw()
            root.deiconify()
        except Exception:
            pass  # non-Windows or older Windows - default title bar stands

        available = set(tkfont.families(root))
        family = next((f for f in (FONT_FAMILY,) + FONT_FALLBACKS if f in available), "TkDefaultFont")
        # Same color-emoji-font resolution as build_progress.py, for the
        # same reason: Windows' text-UI fonts don't reliably contain
        # color emoji glyphs, so any label mixing emoji with text needs
        # the emoji font explicitly rather than relying on substitution.
        emoji_family = next(
            (f for f in ("Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji") if f in available),
            family,
        )

        card = tk.Frame(root, bg=SURFACE, padx=16, pady=14, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(card, text="\U0001F4CB GenreCleanup Build", font=(emoji_family, 12, "bold"),
                 bg=SURFACE, fg=TEXT, anchor="w").pack(fill="x")
        tk.Label(card, text="What would you like to do?", font=(family, 11),
                 bg=SURFACE, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(4, 12))

        choice = {"value": None}

        def _choose(value):
            choice["value"] = value
            root.destroy()

        # Each menu option is a rounded-bordered "card button", mirroring
        # build_progress.py's Cancel Build button treatment exactly: a
        # Canvas-drawn rounded rectangle behind a borderless flat Button,
        # since a plain Tk Button's highlightthickness ring is a focus-only
        # ring on Windows and never paints as a permanent visible border.
        def _make_option(parent, emoji, title, subtitle, fg, value):
            border_color = fg
            radius = 8
            outer = tk.Canvas(parent, height=1, bg=SURFACE, highlightthickness=0)
            outer.pack(fill="x", pady=(0, 8))
            shape = outer.create_polygon(
                _rounded_rect_points(0, 0, 0, 0, radius),
                fill=SURFACE, outline=border_color, width=1, smooth=True,
            )
            btn_frame = tk.Frame(outer, bg=SURFACE, cursor="hand2")
            title_label = tk.Label(
                btn_frame, text=f"{emoji} {title}", font=(emoji_family, 11, "bold"),
                bg=SURFACE, fg=TEXT, anchor="w", cursor="hand2",
            )
            title_label.pack(fill="x", padx=12, pady=(8, 0))
            sub_label = tk.Label(
                btn_frame, text=subtitle, font=(family, 9),
                bg=SURFACE, fg=TEXT_MUTED, anchor="w", justify="left",
                wraplength=290, cursor="hand2",
            )
            sub_label.pack(fill="x", padx=12, pady=(2, 8))
            btn_window = outer.create_window(0, 0, window=btn_frame, anchor="nw")

            last_h = {"h": None}

            def _sync(event=None):
                w = outer.winfo_width()
                h = btn_frame.winfo_reqheight()
                if w <= 1 or h <= 1:
                    return
                if last_h["h"] != h:
                    last_h["h"] = h
                    outer.config(height=h)
                outer.coords(shape, *_rounded_rect_points(0, 0, w - 1, h - 1, radius))
                outer.coords(btn_window, 0, 0)
                outer.itemconfig(btn_window, width=w, height=h)

            outer.bind("<Configure>", _sync)
            for widget in (outer, btn_frame, title_label, sub_label):
                widget.bind("<Button-1>", lambda e, v=value: _choose(v))
            return outer

        _make_option(
            card, "\u25B6\uFE0F", "Start Build", "Run the normal build: dependencies, PyInstaller, installer, then finalize.",
            ACCENT, "START",
        )
        _make_option(
            card, "\U0001F5D1\uFE0F", "Uninstall", "Remove the currently installed GenreCleanup using its own uninstaller.",
            DANGER, "UNINSTALL",
        )
        _make_option(
            card, "\U0001F527", "Fix Build", "Clean the virtual environment and build artifacts, then start a fresh build.",
            WARNING, "FIX",
        )

        root.mainloop()
    except Exception:
        # Any Tk failure (e.g. headless environment) - degrade to no
        # popup, same guarantee as build_progress.py.
        sys.exit(0)

    if choice["value"]:
        _write_result(result_path, choice["value"])


if __name__ == "__main__":
    main()
