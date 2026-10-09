"""
Pre-build menu popup for build.bat.

Shown once, before any build work starts, so the person running build.bat
can choose what happens after a successful build (auto-launch the app or
not) without editing the .bat file itself. Self-contained: stdlib tkinter
only, no new dependency beyond what's already on any Windows Python 3.10+
install. If tkinter can't be imported or no display/window station is
available (e.g. run under a headless CI account), this degrades silently:
it prints one line explaining that and falls back to the default choice,
so build.bat can proceed non-interactively rather than hanging or
crashing.

Contract with build.bat:
  - Exit code 0  -> proceed with build, auto-launch on success.
  - Exit code 2  -> proceed with build, do NOT auto-launch on success.
  - Exit code 1  -> user cancelled; build.bat aborts without building.
  - Any other outcome (tkinter/display unavailable, unexpected error) ->
    printed explanation on stdout, exit code 0 (proceed + auto-launch),
    matching the auto-launch default described to the user in build.bat.
"""

from __future__ import annotations

import sys

EXIT_PROCEED_LAUNCH = 0
EXIT_CANCEL = 1
EXIT_PROCEED_NO_LAUNCH = 2


def _fallback(reason: str) -> int:
    print(f"build_menu: {reason} -- proceeding with defaults (build, then launch).")
    return EXIT_PROCEED_LAUNCH


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - environment dependent
        return _fallback(f"tkinter unavailable ({exc})")

    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - no display/window station
        return _fallback(f"could not open a display ({exc})")

    choice = {"code": EXIT_PROCEED_LAUNCH}

    try:
        root.title("iTunes Library Consolidator - Build")
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        frame = ttk.Frame(root, padding=16)
        frame.grid()

        ttk.Label(
            frame,
            text="Build iTunes Library Consolidator",
            font=("Segoe UI", 11, "bold"),
        ).grid(column=0, row=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(
            frame,
            text="This creates a virtual environment, installs dependencies,\n"
            "runs the test suite, and builds the .exe with PyInstaller.",
            justify="left",
        ).grid(column=0, row=1, columnspan=2, sticky="w", pady=(0, 12))

        launch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Launch the app automatically after a successful build",
            variable=launch_var,
        ).grid(column=0, row=2, columnspan=2, sticky="w", pady=(0, 12))

        def on_build():
            choice["code"] = (
                EXIT_PROCEED_LAUNCH if launch_var.get() else EXIT_PROCEED_NO_LAUNCH
            )
            root.destroy()

        def on_cancel():
            choice["code"] = EXIT_CANCEL
            root.destroy()

        button_row = ttk.Frame(frame)
        button_row.grid(column=0, row=3, columnspan=2, sticky="e")
        ttk.Button(button_row, text="Cancel", command=on_cancel).grid(
            column=0, row=0, padx=(0, 8)
        )
        ttk.Button(button_row, text="Build", command=on_build, default="active").grid(
            column=1, row=0
        )

        root.protocol("WM_DELETE_WINDOW", on_cancel)
        root.update_idletasks()

        # Center on screen.
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

        root.mainloop()
    except Exception as exc:  # pragma: no cover - defensive
        try:
            root.destroy()
        except Exception:
            pass
        return _fallback(f"menu popup failed ({exc})")

    return choice["code"]


if __name__ == "__main__":
    sys.exit(main())
