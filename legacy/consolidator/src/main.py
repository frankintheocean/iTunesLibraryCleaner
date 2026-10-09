from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import crash_reporter, error_log
from .changelog import APP_VERSION
from .errors import with_recovery_guidance
from .resources import app_icon_path
from .ui.main_window import APP_DATA_DIR, MainWindow
from .ui.widgets import show_critical


def _install_excepthook() -> None:
    """Catch anything that reaches the top of the Qt event loop without
    being handled anywhere else and log it, matching WhiteBoard's startup
    behavior. The default handler still runs afterward (prints to
    stderr, preserves normal crash behavior) -- this only adds a record
    of what happened, it never suppresses or changes how an unhandled
    exception is otherwise treated."""
    default_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            error_log.log_error("Unhandled exception", exc_value)
        except Exception:
            pass
        try:
            # Local-only crash dump with repro context (see
            # crash_reporter.py) -- a separate, richer artifact from the
            # rolling error.log above, meant to be read on its own or
            # attached to a bug report. Never phones home.
            crash_reporter.write_crash_dump("Unhandled exception", exc_value)
        except Exception:
            pass
        default_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def main() -> int:
    _install_excepthook()
    error_log.init(str(APP_DATA_DIR))
    crash_reporter.init(str(APP_DATA_DIR))

    app = QApplication(sys.argv)
    app.setApplicationName("iTunes Library Consolidator")
    app.setApplicationVersion(APP_VERSION)

    # Bug fix: this used to set a one-time, unpaletted app.setStyleSheet(
    # current_qss()) here (i.e. always plain Blue, no base palette),
    # separate from MainWindow's own setStyleSheet(current_qss(saved
    # preference)) below. Because both are full stylesheets targeting the
    # same selectors, that left the QApplication-level sheet's unpaletted
    # rules able to compete with MainWindow's palette-recolored ones --
    # most visibly for the four *light*-family named base palettes
    # (Paper/Slate/Sand/Mint), which blended almost invisibly with the
    # plain-light app-level sheet under the common "auto" mode. The actual
    # (palette-aware) stylesheet is now applied once, from MainWindow.
    # __init__ via _apply_theme_stylesheet, which sets it on both the
    # QApplication instance and the window itself -- so child top-level
    # windows (e.g. the "What's new" dialog) still follow the same theme,
    # just with the correct saved preference instead of the default.

    icon_path = app_icon_path()
    if icon_path is not None:
        # Sets the window/taskbar icon at runtime. The .exe's own file icon
        # (what Explorer/the Start Menu show before the app is running) is
        # set separately via PyInstaller's icon= in build.spec.
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        window = MainWindow()
    except Exception as exc:
        # Building MainWindow can fail before any window is on screen (e.g.
        # can't create/open the local cache DB due to a permissions issue).
        # Windowed builds (console=False in build.spec) have no console for
        # a bare traceback to appear in, so without this the app would just
        # vanish with no explanation. Show it in a dialog instead, since
        # QApplication is already running at this point. Also logged (same
        # as any other unhandled exception) so it shows up on disk even
        # though it's caught here rather than reaching the excepthook.
        # error_log.log_error already records the full technical detail
        # (WinError/exception text, traceback) to error.log -- the dialog
        # below only ever shows the sanitized version via
        # with_recovery_guidance/sanitize_for_display (see errors.py), so
        # nothing technical is lost, it's just not put in front of the user.
        error_log.log_error("Startup failed", exc)
        crash_reporter.write_crash_dump("Startup failed", exc)
        show_critical(
            None,
            "iTunes Library Consolidator couldn't start",
            with_recovery_guidance(f"Startup failed: {exc}"),
        )
        return 1

    # Bug fix: closing the window via the titlebar's X button was leaving
    # the process behind in Task Manager. QMainWindow.closeEvent() (see
    # ui/main_window.py) already tears down its own workers/threads/DB
    # connection cleanly, but that alone doesn't guarantee app.exec()
    # actually returns -- e.g. if closeEvent ever hit an unexpected
    # exception partway through, super().closeEvent(event) (the call that
    # tells Qt this was a real close, not just a hide) could be skipped,
    # leaving Qt still waiting on a "closed" window that technically never
    # finished closing. destroyed connects the last line of defense here:
    # once the main window is actually destroyed for any reason, quit()
    # is called explicitly rather than relying on quitOnLastWindowClosed
    # (Qt's default) alone.
    window.destroyed.connect(app.quit)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
