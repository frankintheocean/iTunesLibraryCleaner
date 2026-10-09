#!/usr/bin/env python3
"""Build progress popup for GenreCleanup's build.bat (stdlib tkinter only -
no new dependency). Ported from WhiteBoard's build\\build_progress.py.

build.bat launches this as a separate, detached background process at the
very start of the real build and writes a single-line status to a small
status file (passed as argv[1]) before/after each of its existing steps;
this script just polls that file and updates a small "Building
GenreCleanup..." window with a live step label + an elapsed-time timer,
self-closing the instant it sees a terminal status (success, failure, or
cancel) - never something the person has to click to dismiss. If tkinter
isn't available for any reason, this exits immediately and silently; the
popup is a nice-to-have layered on top of the real build steps in
build.bat, never something they depend on.

During step 2/4 (PyInstaller), build.bat also tees PyInstaller's own
console output to a second log file (passed as argv[2]); this script tails
that log and matches it against PYI_PHASE_MARKERS below -- an ordered list
of substrings PyInstaller actually prints, in the order it prints them, as
it works through Analysis -> PYZ -> PKG -> EXE. The progress bar shown
for step 2/4 is "how many of those markers have appeared so far", i.e. a
real (if coarse-grained) reflection of how far PyInstaller has actually
gotten, not a fake animation running on a timer. If PyInstaller's output
ever changes and none of the markers match, the bar just stays wherever it
last was -- still correct, just less granular -- rather than showing
anything misleading.

NOTE on markers vs. WhiteBoard's original list: GenreCleanup.spec builds a
*onefile* exe (see build/genrecleanup.spec - a.binaries/a.zipfiles/a.datas
go straight into EXE(), with no COLLECT() call), unlike WhiteBoard's onedir
build. PyInstaller's own console output for a onefile build ends at
"Building EXE" - it never prints a COLLECT phase - so the "checking
COLLECT"/"Building COLLECT" markers from WhiteBoard's list are dropped
here; keeping them would have left the bar permanently stuck below 100%
for the entire step, since those two markers would simply never appear.

Usage (invoked by build.bat, not meant to be run directly):
    python build_progress.py <status_file> [pyi_log] [cancel_flag] [build_pid]

Status file protocol (build.bat overwrites this file's single line at
each step, see build.bat itself for the exact points):
    STEP:<n>:<label text>      -- now running step n (1-based)
    DONE                       -- build finished successfully, close now
    FAILED:<label text>        -- build failed at this step, show it briefly then close

Cancel button: writes <cancel_flag> (so build.bat's own between-step
checks can notice it) and, if a build PID was passed, immediately
"taskkill /PID <pid> /T /F"s that process tree so a build genuinely stuck
inside a long-running step (e.g. PyInstaller) is actually stopped rather
than only stopping at the next checkpoint. build.bat's own :cancelled
cleanup then removes only that run's own temp/partial-build files (see
build.bat) - this script never touches the filesystem itself beyond
writing the cancel flag.
"""
import subprocess
import sys
import time

try:
    import tkinter as tk
except Exception:
    # No display / no tkinter (e.g. minimal Python install) - the popup is
    # purely cosmetic, so just exit quietly and let build.bat's own console
    # output (in the minimized window) be the only feedback.
    sys.exit(0)

STEPS_TOTAL = 4  # matches build.bat: [1/4] deps, [2/4] PyInstaller, [3/4] installer, [4/4] finalize

# Terminal-state icon paired with a colour that itself communicates state
# (accent while running, green on success, red on failure/cancel) - see the
# STATE_ICON usages below. "running" is intentionally unused for the timer
# label itself while a build is in progress - see RUNNING_ICON below,
# which shows a static hammer-and-wrench glyph there instead.
STATE_ICON = {"running": "\u23F1\uFE0F", "success": "\u2705", "failed": "\u274C", "cancelled": "\u26D4"}

# Per-step emoji shown in front of each STEP:<n>:<label> line build.bat
# reports, so the step text itself carries a quick-glance icon matching
# what that step is actually doing (deps, PyInstaller, installer,
# finalize) rather than a single generic running icon throughout. Keyed
# by the 1-based step number as a string, matching STEP:<n>:... exactly;
# an unrecognized/future step number falls back to STATE_ICON["running"]
# below rather than crashing on a KeyError.
STEP_ICON = {
    "1": "\U0001F4E6",  # package - installing/checking Python deps
    "2": "\U0001F4BB",  # computer - PyInstaller freezing the app
    "3": "\U0001F4E6",  # package - building the Windows installer
    "4": "\U0001F3C1",  # checkered flag - finalizing/moving the .exe
}

# Static icon shown next to the elapsed-time label while a build is in
# progress (matches WhiteBoard's build_progress.py exactly - see that
# file's comment for why this is static rather than an animated spinner).
RUNNING_ICON = "\U0001F6E0\uFE0F"

# Substrings PyInstaller's own console output actually contains, in the
# order it prints them for a normal ONEFILE build (matches
# build/genrecleanup.spec: a single Analysis -> PYZ -> PKG -> EXE
# pipeline, no COLLECT - see the module docstring above for why the
# COLLECT markers from WhiteBoard's onedir-build list are omitted here).
# Kept as plain substrings (not regex) so this only ever needs an `in`
# check against each new log line.
PYI_PHASE_MARKERS = [
    "checking Analysis",
    "Analyzing base_library.zip",
    "Analyzing ",  # "Analyzing <entry script>.py" - the main analysis pass
    "Processing module hooks",
    "checking PYZ",
    "Building PYZ",
    "checking PKG",
    "Building PKG",
    "checking EXE",
    "Building EXE",
]


def _rounded_rect_points(x0, y0, x1, y1, radius):
    """Corner-anchor points for a rounded rectangle from (x0,y0) to (x1,y1),
    meant to be drawn via canvas.create_polygon(..., smooth=True). Tk's
    polygon smoothing turns each sharp corner here into a curve, which is
    the standard way to get a true rounded rect on a plain Tk Canvas (no
    native rounded-rectangle primitive exists). radius is clamped to half
    the shorter side so a very thin/short bar (e.g. width 0 or 1 right at
    the start of a build) never produces a degenerate/inverted shape."""
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


def _read_status(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


class LogTailer:
    """Incrementally reads new lines appended to a growing log file,
    without re-reading the whole file each poll -- the PyInstaller log can
    grow to several thousand lines over a build, and re-reading it from
    the top every 200ms would waste real time on exactly the kind of
    repeated work this popup shouldn't be adding to the build."""

    def __init__(self, path):
        self.path = path
        self._pos = 0

    def new_lines(self):
        if not self.path:
            return []
        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                lines = f.readlines()
                self._pos = f.tell()
            return lines
        except OSError:
            # Log doesn't exist yet (PyInstaller hasn't started writing to
            # it, or Tee-Object isn't available) - nothing new, try again
            # next poll rather than treating this as an error.
            return []


def main():
    if len(sys.argv) < 2:
        sys.exit(0)
    status_path = sys.argv[1]
    pyi_log_path = sys.argv[2] if len(sys.argv) > 2 else None
    cancel_flag_path = sys.argv[3] if len(sys.argv) > 3 else None
    build_pid = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
    tailer = LogTailer(pyi_log_path)
    pyi_phase_idx = 0  # how many PYI_PHASE_MARKERS have been seen so far
    cancelled = {"flag": False}  # mutable so the button callback can set it

    # Matches gui.py's own black/white palette (BG="#000000", FG="#ffffff",
    # DIM="#666666") instead of WhiteBoard's iOS-Dark theme, so this popup
    # looks like part of the same app rather than a mismatched window.
    # Status colors (accent/success/danger) are standard choices since
    # gui.py itself has no build tooling of its own to match.
    FONT_FAMILY = "Segoe UI"
    FONT_FALLBACKS = ("Segoe UI Variable", "Helvetica Neue", "Arial")
    BG = "#000000"          # matches gui.py BG
    SURFACE = "#1A1A1A"
    BORDER = "#333333"
    TEXT = "#FFFFFF"        # matches gui.py FG
    ACCENT = "#3399FF"
    DANGER = "#FF4444"
    SUCCESS = "#33CC66"
    TRACK = "#333333"

    try:
        import tkinter.font as tkfont

        root = tk.Tk()
        root.title("GenreCleanup - Building")
        # A little taller than a bare label stack to fit the progress bar
        # and timer/hourglass text below without cramping the card's
        # padding (matches WhiteBoard's sizing).
        root.geometry("380x204")
        root.resizable(False, False)
        root.configure(bg=BG)
        # Small always-on-top popup rather than a taskbar-hogging full
        # window - the minimized console window build.bat runs in is what
        # keeps the rest of the screen clear.
        root.attributes("-topmost", True)
        # Closing this window manually via its own [X] just hides it early;
        # it doesn't stop or affect the real build already running in
        # build.bat's own (minimized) console, so a stray click there can't
        # leave anything in a stale state (unlike the Cancel button below,
        # which deliberately does stop the build).
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        # Dark title bar (Windows 10 1809+/11): tkinter's own window frame
        # has no theming API, so this asks the OS compositor directly via
        # DWM's undocumented-but-stable "immersive dark mode" attribute,
        # the same mechanism apps like Explorer/Notepad use. Best-effort
        # only - any failure (older Windows, non-Windows OS, ctypes
        # unavailable) just leaves the default title bar rather than
        # breaking the popup.
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
                # Older Windows 10 builds used attribute 19 before the API
                # was finalized as 20 - try that as a fallback rather than
                # silently giving up on any pre-22H2-ish build.
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(value), ctypes.sizeof(value),
                )
            root.withdraw()
            root.deiconify()
        except Exception:
            pass  # non-Windows or older Windows - default title bar stands

        # Resolve the font family to whatever's actually installed, trying
        # Segoe UI first (matching gui.py) and falling through a plain
        # Windows-native stack.
        available = set(tkfont.families(root))
        family = next((f for f in (FONT_FAMILY,) + FONT_FALLBACKS if f in available), "TkDefaultFont")

        # Emoji-capable font, resolved up front so every label that mixes
        # emoji into its text (title, step_label, spinner_label, cancel
        # button) can use it. Windows' text-UI fonts do not reliably
        # contain full-color emoji glyphs; Tk's fallback for a missing
        # glyph is font-substitution to whatever the OS considers the
        # nearest match for that *character*, which on Windows is
        # frequently a monochrome symbol-style glyph rather than the real
        # color "Segoe UI Emoji" presentation - even though the emoji font
        # itself is installed and would render it in color if actually
        # selected.
        emoji_family = next(
            (f for f in ("Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji") if f in available),
            family,
        )

        # Outer BG frame + an inset dark "card" panel.
        card = tk.Frame(root, bg=SURFACE, padx=16, pady=14, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        # These two mix an emoji with plain text in a single Label, so the
        # whole label is set to the emoji font rather than the text font -
        # Tk has no per-character font-run mixing within one Label, and
        # the emoji font family still renders plain ASCII/Latin text just
        # fine, so this doesn't cost any text legibility.
        tk.Label(card, text="\U0001F528 Building GenreCleanup\u2026", font=(emoji_family, 12, "bold"),
                 bg=SURFACE, fg=TEXT, anchor="w").pack(fill="x")
        step_label = tk.Label(card, text="Starting\u2026", font=(emoji_family, 11),
                               bg=SURFACE, fg=TEXT, anchor="w")
        step_label.pack(fill="x", pady=(8, 3))

        # Progress bar: a plain Canvas rather than ttk.Progressbar, so its
        # fill color matches the app's accent exactly and so it can sit
        # flush in this hand-styled card instead of themed OS chrome.
        # Every one of the 4 steps advances it, not only step 2/4: steps
        # 1, 3 and 4 fill their own 1/4-wide slice as soon as build.bat
        # reports them started/finished (a real, if coarse, reflection of
        # actual progress through the 4 real steps), while step 2/4 keeps
        # its existing fine-grained PyInstaller-marker-driven fill *within*
        # its own slice. Colour reflects build state, same as the timer
        # label.
        bar_canvas = tk.Canvas(card, height=12, bg=SURFACE, highlightthickness=0)
        # Rounded pill shape rather than hard corners: Tk's Canvas has no
        # native rounded-rectangle primitive, so _rounded_rect_points below
        # builds one as a smoothed polygon. Track and fill are each their
        # own polygon item so the fill's rounding can be recomputed
        # independently as its width changes on every progress update.
        BAR_RADIUS = 6  # = half of the 12px bar height, i.e. a full pill
        bar_track = bar_canvas.create_polygon(
            _rounded_rect_points(0, 0, 0, 12, BAR_RADIUS), fill=TRACK, width=0, smooth=True
        )
        bar_fill = bar_canvas.create_polygon(
            _rounded_rect_points(0, 0, 0, 12, BAR_RADIUS), fill=ACCENT, width=0, smooth=True
        )

        # Timer/icon line. Split into two labels side-by-side rather than
        # one, so the icon's own fixed-width slot keeps the elapsed text
        # from shifting if the icon's rendered width ever varies by font/
        # platform.
        timer_row = tk.Frame(card, bg=SURFACE)
        timer_row.pack(fill="x", pady=(8, 8))
        # height=28 (not 1): this frame uses pack_propagate(False) so it
        # never resizes to fit its child, which is exactly what's needed to
        # keep the icon from shifting the row horizontally if its rendered
        # width ever varies - but a height that's too short clips the
        # label's content vertically instead of just constraining its
        # width.
        spinner_slot = tk.Frame(timer_row, bg=SURFACE, width=28, height=28)
        spinner_slot.pack(side="left")
        spinner_slot.pack_propagate(False)
        spinner_label = tk.Label(spinner_slot, text=RUNNING_ICON, font=(emoji_family, 13),
                                  bg=SURFACE, fg=ACCENT, anchor="center", justify="center")
        spinner_label.pack(fill="both", expand=True)
        timer_label = tk.Label(timer_row, text="", font=(family, 13, "bold"),
                                bg=SURFACE, fg=ACCENT, anchor="w")
        timer_label.pack(side="left", fill="x", expand=True)

        # Cancel button: styled as a flat "danger" pill.
        #
        # The visible border is a rounded-rect drawn on a Canvas (same
        # _rounded_rect_points helper as the progress bar above), not a
        # plain Frame: a Tk Frame's border is always a hard-cornered
        # rectangle with no radius option. The Canvas sits behind the
        # button (the button is placed on top of it via create_window) and
        # is kept in sync with the button's actual on-screen size via a
        # <Configure> binding, since the button's size isn't known until
        # Tk actually lays it out.
        #
        # A plain Tk Button's highlightthickness/highlightbackground ring
        # is a *focus* ring on Windows - it only paints once the widget
        # actually has keyboard focus, which this popup never sets - so
        # that alone would leave the button with no visible box around it,
        # unlike every other bordered surface in this popup.
        CANCEL_BORDER_COLOR = "#5C2B2B"
        CANCEL_RADIUS = 8
        cancel_border = tk.Canvas(card, height=1, bg=SURFACE, highlightthickness=0)
        cancel_border.pack(fill="x", pady=(2, 0))
        cancel_border_shape = cancel_border.create_polygon(
            _rounded_rect_points(0, 0, 0, 0, CANCEL_RADIUS),
            fill=SURFACE, outline=CANCEL_BORDER_COLOR, width=1, smooth=True,
        )
        cancel_btn = tk.Button(
            cancel_border, text="\u2716 Cancel Build", font=(family, 10, "bold"),
            bg=SURFACE, fg=DANGER, activebackground="#331F1E", activeforeground=DANGER,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            highlightthickness=0,
        )
        cancel_btn_window = cancel_border.create_window(0, 0, window=cancel_btn, anchor="nw")

        _cancel_border_last_h = {"h": None}  # guards against a redundant self-triggered <Configure>

        def _sync_cancel_border(event=None):
            # Button's own requested size drives the canvas's height (the
            # canvas itself is created at height=1 above and grows to fit)
            # and the rounded outline redrawn to match exactly, so the
            # border always hugs the button rather than being a fixed guess
            # that could clip or leave a gap at a different font/DPI.
            w = cancel_border.winfo_width()
            h = cancel_btn.winfo_reqheight()
            if w <= 1 or h <= 1:
                return
            if _cancel_border_last_h["h"] != h:
                _cancel_border_last_h["h"] = h
                cancel_border.config(height=h)
            cancel_border.coords(cancel_border_shape, *_rounded_rect_points(0, 0, w - 1, h - 1, CANCEL_RADIUS))
            cancel_border.coords(cancel_btn_window, 0, 0)
            cancel_border.itemconfig(cancel_btn_window, width=w, height=h)

        cancel_border.bind("<Configure>", _sync_cancel_border)
    except Exception:
        # Any Tk failure (e.g. headless environment) - degrade to no popup.
        sys.exit(0)

    def _set_progress_bar(fraction, color=ACCENT):
        """fraction: None to hide the bar, or 0.0-1.0 to show it filled to
        that point. Redraws against the canvas's current on-screen width so
        it stays accurate across the resize Tk does on first show."""
        if fraction is None:
            bar_canvas.pack_forget()
            return
        if not bar_canvas.winfo_manager():
            bar_canvas.pack(fill="x", pady=(4, 6), before=timer_row)
        bar_canvas.itemconfig(bar_fill, fill=color)
        width = bar_canvas.winfo_width()
        if width <= 1:
            width = 380 - 16 * 2 - 10 * 2 - 4  # fallback: card's usable inner width
        fraction = max(0.0, min(1.0, fraction))
        bar_canvas.coords(bar_track, *_rounded_rect_points(0, 0, width, 12, BAR_RADIUS))
        fill_width = int(width * fraction)
        # Below one full radius' worth of width, a rounded rect would
        # invert/degenerate (see the radius clamp in _rounded_rect_points),
        # so the fill polygon is simply omitted at that point rather than
        # drawn as a malformed shape - visually indistinguishable from "not
        # started yet" against the track underneath it.
        if fill_width > 0:
            bar_canvas.coords(bar_fill, *_rounded_rect_points(0, 0, fill_width, 12, BAR_RADIUS))
            bar_canvas.itemconfig(bar_fill, state="normal")
        else:
            bar_canvas.itemconfig(bar_fill, state="hidden")

    def _on_cancel():
        # Idempotent: a fast double-click just no-ops on the second call
        # instead of trying to kill an already-dead process tree or write
        # the flag file twice.
        if cancelled["flag"]:
            return
        cancelled["flag"] = True
        cancel_btn.config(state="disabled", text="Cancelling\u2026")
        step_label.config(text="\U0001F6D1 Cancelling build\u2026")
        spinner_label.config(fg=DANGER)
        timer_label.config(fg=DANGER)
        # Write the cancel flag first (build.bat's own between-step checks
        # pick this up even if the taskkill below fails or PowerShell/the
        # PID isn't available), then also try to stop a build that's stuck
        # inside a long-running step (e.g. PyInstaller) right away rather
        # than waiting for the next checkpoint.
        if cancel_flag_path:
            try:
                with open(cancel_flag_path, "w", encoding="utf-8") as f:
                    f.write("cancel")
            except OSError:
                pass
        if build_pid:
            try:
                subprocess.run(
                    ["taskkill", "/PID", build_pid, "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                )
            except Exception:
                pass  # best-effort - the cancel flag above is still in place

    cancel_btn.config(command=_on_cancel)

    start = time.time()
    last_status = None
    in_pyinstaller_step = False
    current_step_n = 0  # 1-based step number of the step currently running, 0 before STEP:1 arrives

    def _overall_fraction():
        """Live progress across all 4 steps, not just PyInstaller: each
        step owns an equal 1/4-wide slice of the bar in step order, so the
        bar fills continuously from step 1 through step 4 instead of only
        moving during step 2. Steps 1, 3 and 4 have no per-line progress
        source the way PyInstaller's log gives step 2 (see
        PYI_PHASE_MARKERS), so - rather than inventing a fake animation
        with no relation to real progress - each of those steps' slice is
        shown as filled the moment build.bat reports that step has
        started. Step 2's slice instead fills gradually within itself
        using pyi_phase_idx."""
        if current_step_n <= 0:
            return 0.0
        completed_slices = current_step_n - 1
        if current_step_n == 2:
            within_step = pyi_phase_idx / len(PYI_PHASE_MARKERS)
        else:
            within_step = 1.0
        return (completed_slices + within_step) / STEPS_TOTAL

    while True:
        try:
            root.update()
        except Exception:
            # Window was destroyed (e.g. user closed it manually) - the
            # real build keeps running regardless; just stop polling.
            return

        status = _read_status(status_path)
        if status != last_status and status:
            last_status = status
            if status == "DONE":
                cancel_border.pack_forget()
                step_label.config(text=f"{STATE_ICON['success']} Done! GenreCleanup.exe is ready.")
                _set_progress_bar(1.0, SUCCESS)
                spinner_label.config(text=STATE_ICON["success"], fg=SUCCESS)
                timer_label.config(fg=SUCCESS)
                _close_after_pause(root, start, spinner_label, timer_label, SUCCESS, success=True)
                return
            if status.startswith("FAILED"):
                _, _, label = status.partition(":")
                cancel_border.pack_forget()
                step_label.config(text=f"{STATE_ICON['failed']} Failed: {label or 'build error'}")
                _set_progress_bar(_overall_fraction(), DANGER)
                spinner_label.config(text=STATE_ICON["failed"], fg=DANGER)
                timer_label.config(fg=DANGER)
                _close_after_pause(root, start, spinner_label, timer_label, DANGER, success=False)
                return
            if status.startswith("STEP:"):
                _, _, rest = status.partition(":")
                n, _, label = rest.partition(":")
                icon = STEP_ICON.get(n, STATE_ICON["running"])
                step_label.config(text=f"{icon} [{n}/{STEPS_TOTAL}] {label}")
                try:
                    current_step_n = int(n)
                except ValueError:
                    # Defensive only: build.bat always writes a numeric
                    # step (STEP:1.. through STEP:4..), so this path isn't
                    # reachable in practice; leave current_step_n at its
                    # last known-good value instead of crashing the popup
                    # on an unexpected status line.
                    pass
                in_pyinstaller_step = (n == "2")
                if in_pyinstaller_step:
                    pyi_phase_idx = 0
                _set_progress_bar(_overall_fraction(), ACCENT)

        if cancelled["flag"]:
            step_label.config(text=f"{STATE_ICON['cancelled']} Build cancelled.")
            _set_progress_bar(_overall_fraction(), DANGER)
            spinner_label.config(text=STATE_ICON["cancelled"], fg=DANGER)
            _close_after_pause(root, start, spinner_label, timer_label, DANGER, success=False)
            return

        if in_pyinstaller_step:
            for line in tailer.new_lines():
                # Advance past every marker the line matches, in order,
                # picking up from wherever we already are -- a single
                # burst of new lines between polls can easily cross more
                # than one marker at once.
                while (pyi_phase_idx < len(PYI_PHASE_MARKERS)
                       and PYI_PHASE_MARKERS[pyi_phase_idx] in line):
                    pyi_phase_idx += 1
            _set_progress_bar(_overall_fraction(), ACCENT)

        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)
        timer_label.config(text=f"{mins:02d}:{secs:02d} elapsed")

        time.sleep(0.2)


def _close_after_pause(root, start, spinner_label, timer_label, color, success: bool):
    """Self-closes immediately - never waits for a click. Briefly holds the
    final state on screen (pumping events throughout, so the window stays
    responsive rather than appearing to hang) so the person actually sees
    the finished/failed/cancelled state before it disappears. The timer
    keeps ticking (in the final state's colour) during this pause instead
    of freezing, so it never looks stuck. spinner_label is held fixed on
    the terminal-state icon (already set by the caller) rather than reset
    here, since the fixed-width slot exists precisely so this final icon
    doesn't shift the elapsed text next to it."""
    deadline = time.time() + (0.6 if success else 1.5)
    while time.time() < deadline:
        try:
            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
            timer_label.config(text=f"{mins:02d}:{secs:02d} elapsed", fg=color)
            root.update()
        except Exception:
            return
        time.sleep(0.05)
    try:
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
