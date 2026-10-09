"""
Build progress popup for build.bat.

Shows a single window with the current step name, a step counter, a live
progress bar, and an elapsed/ETA timer for the whole duration of
build.bat's 4 steps (deps, fixture+tests, PyInstaller build, done).
Self-contained: stdlib tkinter only, no new dependency. Degrades silently
if tkinter or a display isn't available -- build.bat's own echo/step
numbering already covers that case in the console, so a popup failure
here is diagnostic-only and never blocks the build.

Bug fix: this used to be launched fresh, once per step, as its own
short-lived process that displayed for a fixed ~1.2s and then destroyed
itself on a timer -- regardless of whether the real work for that step
(pip install, PyInstaller, etc.) was still running. In practice the
popup would flash and vanish long before a step actually finished, so it
did not "stay open" through the build at all. It's now started ONCE, in
the background, before step 1, and stays open -- polling a small
step-file that build.bat rewrites before/after each step -- until build.bat
tells it to close (on completion, cancellation, or failure) or the user
clicks Cancel. There is still no long-running IPC channel beyond that
step file; polling it is enough since updates only need to be visible
within a fraction of a second, not real-time.

Usage (build.bat starts this once, in the background, before step 1):

    python build_progress.py --step-file PATH --total N [--cancel-file PATH]
        [--pyinstaller-log PATH]

build.bat then updates PATH before/after each step with a small text
payload (see _read_step below) and, on completion/cancel/failure, writes
a "close" step so the popup exits itself. If a --cancel-file path is
given and the user clicks Cancel, that file is created and the process
exits with code 1; build.bat checks for the file's existence after each
step and aborts the remaining steps if present. Every build.bat run uses
a unique step-file/cancel-file path (based on the run's own temp
directory) so concurrent/overlapping runs never share or clobber each
other's state.

Live PyInstaller sub-progress: if --pyinstaller-log is given, the popup
tails that file (build.bat redirects PyInstaller's own console output to
it during step 3) and matches known phase lines from PyInstaller's real
output (see _PYI_PHASE_MARKERS below) to advance the progress bar
smoothly *within* step 3, instead of the bar sitting frozen on "3 of 4"
for however long the PyInstaller step actually takes. This is display-
only and best-effort: an unrecognized or reordered line simply doesn't
advance the sub-progress further, it never moves it backwards, and any
read/parse failure (log not yet created, mid-write) is treated the same
as "no change yet" like every other polled read in this file.

ETA: computed from the wall-clock time actually spent so far vs. how
much of the *overall* step range has elapsed (# of whole completed steps,
plus this step's own fractional sub-progress if any), so it improves in
accuracy as the build proceeds rather than assuming every step takes the
same fixed share of the total. Hidden until at least one step has fully
completed, since a single early sample is too noisy to be a useful
estimate.
"""

from __future__ import annotations

import os
import sys
import time

EXIT_OK = 0
EXIT_CANCELLED = 1

# How often the popup re-reads the step file (and, if configured, the
# PyInstaller log) for a change.
POLL_MS = 250

# Known lines from PyInstaller's own console output (post "pyinstaller
# ... --noconfirm"), in the order PyInstaller actually prints them, each
# mapped to how far through the *step* they represent (0.0-1.0). Matched
# by substring, case-sensitive, against each new line tailed from the log
# -- exact wording PyInstaller uses today; harmless if a future
# PyInstaller version changes its wording; the bar simply stops advancing
# past whatever markers still match, rather than erroring.
_PYI_PHASE_MARKERS: list[tuple[str, float]] = [
    ("Analyzing base_library.zip", 0.05),
    ("running Analysis", 0.10),
    ("Analyzing hidden import", 0.15),
    ("Processing pre-safe import module hook", 0.20),
    ("Loading module hook", 0.30),
    ("checking Analysis", 0.35),
    ("Building PYZ", 0.45),
    ("Building PKG", 0.60),
    ("checking PKG", 0.62),
    ("Building EXE", 0.75),
    ("Appending PKG archive", 0.85),
    ("Building EXE from EXE-00.toc completed", 0.97),
]


def _fallback(reason: str) -> int:
    print(f"build_progress: {reason} -- continuing without a progress popup.")
    return EXIT_OK


def _parse_args(args: list[str]):
    step_file = None
    total = 0
    cancel_file = None
    pyinstaller_log = None
    i = 0
    while i < len(args):
        if args[i] == "--step-file" and i + 1 < len(args):
            step_file = args[i + 1]
            i += 2
        elif args[i] == "--total" and i + 1 < len(args):
            try:
                total = int(args[i + 1])
            except ValueError:
                total = 0
            i += 2
        elif args[i] == "--cancel-file" and i + 1 < len(args):
            cancel_file = args[i + 1]
            i += 2
        elif args[i] == "--pyinstaller-log" and i + 1 < len(args):
            pyinstaller_log = args[i + 1]
            i += 2
        else:
            i += 1
    return step_file, total, cancel_file, pyinstaller_log


def _read_step(step_file: str):
    """Reads the two-line step-file payload build.bat writes before each
    step: line 1 is the step number, or the literal "close" to ask the
    popup to exit cleanly; line 2 is the label text. Returns
    (step_or_none, label, should_close). Any read/parse failure (file not
    yet written, mid-write, deleted) is treated as "no change yet" rather
    than an error -- the popup just keeps showing whatever it last
    displayed until the next successful read, since build.bat rewrites
    this file frequently and a torn read is expected, not exceptional."""
    try:
        with open(step_file, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return None, None, False
    if not lines:
        return None, None, False
    first = lines[0].strip()
    label = lines[1] if len(lines) > 1 else ""
    if first == "close":
        return None, None, True
    try:
        step = int(first)
    except ValueError:
        return None, None, False
    return step, label, False


def _pyinstaller_sub_progress(log_file: str, last_size: int, last_fraction: float):
    """Best-effort: reads only the *new* bytes appended to log_file since
    last_size (a cheap tail, not a full re-read -- this file can grow to
    several hundred KB over a real PyInstaller run and is polled every
    POLL_MS), scans those new lines for the furthest-along marker in
    _PYI_PHASE_MARKERS, and returns (new_size, fraction). fraction only
    ever increases (never regresses on an out-of-order or repeated match)
    and defaults to last_fraction unchanged if nothing new matched or the
    file can't be read yet (e.g. PyInstaller hasn't created/flushed it
    yet at the moment step 3 starts)."""
    try:
        size = os.path.getsize(log_file)
    except Exception:
        return last_size, last_fraction
    if size <= last_size:
        return size, last_fraction
    try:
        with open(log_file, "rb") as fh:
            fh.seek(last_size)
            new_bytes = fh.read()
    except Exception:
        return last_size, last_fraction
    new_text = new_bytes.decode("utf-8", errors="ignore")
    fraction = last_fraction
    for line in new_text.splitlines():
        for marker, frac in _PYI_PHASE_MARKERS:
            if marker in line and frac > fraction:
                fraction = frac
    return size, fraction


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def main() -> int:
    args = sys.argv[1:]
    step_file, total, cancel_file, pyinstaller_log = _parse_args(args)

    if not step_file:
        print(
            "build_progress: usage: build_progress.py --step-file PATH "
            "--total N [--cancel-file PATH] [--pyinstaller-log PATH]"
        )
        return EXIT_OK

    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - environment dependent
        return _fallback(f"tkinter unavailable ({exc})")

    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - no display/window station
        return _fallback(f"could not open a display ({exc})")

    result = {"code": EXIT_OK}

    try:
        root.title("Building iTunes Library Consolidator...")
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        frame = ttk.Frame(root, padding=16)
        frame.grid()

        step_label_var = tk.StringVar(value=f"Step 1 of {total}" if total > 0 else "")
        text_label_var = tk.StringVar(value="Starting build...")
        eta_var = tk.StringVar(value="")

        ttk.Label(
            frame, textvariable=step_label_var, font=("Segoe UI", 9)
        ).grid(column=0, row=0, sticky="w")
        ttk.Label(
            frame, textvariable=text_label_var, font=("Segoe UI", 11, "bold")
        ).grid(column=0, row=1, sticky="w", pady=(2, 10))

        # Progress bar is scaled to total*100 "units" (rather than one
        # unit per whole step) so the PyInstaller step's own live
        # sub-progress (see _pyinstaller_sub_progress) can advance the
        # bar smoothly within step 3, not just jump in four coarse
        # whole-step increments.
        _SCALE = 100
        progress = ttk.Progressbar(
            frame,
            mode="determinate" if total > 0 else "indeterminate",
            length=280,
            maximum=max(total, 1) * _SCALE,
            value=0,
        )
        progress.grid(column=0, row=2, sticky="we", pady=(0, 4))
        if total <= 0:
            progress.start(15)

        ttk.Label(
            frame, textvariable=eta_var, font=("Segoe UI", 8)
        ).grid(column=0, row=3, sticky="w", pady=(0, 10))

        def on_cancel():
            result["code"] = EXIT_CANCELLED
            if cancel_file:
                try:
                    with open(cancel_file, "w", encoding="utf-8") as fh:
                        fh.write("cancelled\n")
                except Exception:
                    pass
            root.destroy()

        ttk.Button(frame, text="Cancel", command=on_cancel).grid(
            column=0, row=4, sticky="e"
        )
        root.protocol("WM_DELETE_WINDOW", on_cancel)

        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

        last_step = None
        last_label = None
        start_time = time.monotonic()
        pyi_log_size = 0
        pyi_fraction = 0.0
        completed_steps = 0  # whole steps fully finished, for the ETA estimate

        def overall_fraction() -> float:
            """Fraction (0.0-1.0) of the whole build done so far: whole
            completed steps plus the current step's own live sub-progress
            (only ever non-zero during step 3, once pyinstaller-log is
            wired up and matching lines have been seen)."""
            if total <= 0:
                return 0.0
            current_partial = pyi_fraction if last_step == 3 else 0.0
            return min(1.0, (completed_steps + current_partial) / total)

        def update_progress_value():
            if total <= 0:
                return
            step_base = max(0, (last_step or 1) - 1)
            sub = pyi_fraction if last_step == 3 else 0.0
            progress["value"] = (step_base + sub) * _SCALE

        def update_eta():
            frac = overall_fraction()
            elapsed = time.monotonic() - start_time
            # Wait for at least one whole step to finish (or meaningful
            # sub-progress into step 3) before showing an estimate --
            # a single very-early sample swings wildly and is more
            # misleading than showing nothing yet.
            if frac < 0.15 or elapsed < 2:
                eta_var.set(f"Elapsed: {_format_duration(elapsed)}")
                return
            total_estimate = elapsed / frac
            remaining = max(0, total_estimate - elapsed)
            eta_var.set(
                f"Elapsed: {_format_duration(elapsed)}  \u2022  "
                f"ETA: ~{_format_duration(remaining)}"
            )

        def poll():
            nonlocal last_step, last_label, pyi_log_size, pyi_fraction, completed_steps
            step, label, should_close = _read_step(step_file)
            if should_close:
                root.destroy()
                return
            if step is not None and (step, label) != (last_step, last_label):
                if last_step is not None and step > last_step:
                    completed_steps = max(completed_steps, last_step)
                last_step, last_label = step, label
                if step != 3:
                    pyi_fraction = 0.0
                if total > 0:
                    step_label_var.set(f"Step {step} of {total}")
                text_label_var.set(label or "")
                update_progress_value()
            if pyinstaller_log and last_step == 3:
                pyi_log_size, pyi_fraction = _pyinstaller_sub_progress(
                    pyinstaller_log, pyi_log_size, pyi_fraction
                )
                update_progress_value()
            update_eta()
            root.after(POLL_MS, poll)

        root.after(POLL_MS, poll)
        root.mainloop()
    except Exception as exc:  # pragma: no cover - defensive
        try:
            root.destroy()
        except Exception:
            pass
        return _fallback(f"progress popup failed ({exc})")

    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
