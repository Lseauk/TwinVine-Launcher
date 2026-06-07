"""
TwinVine Launcher  v1.0.2
=======================
A self-contained Windows application for TwinVine.

HOW IT WORKS
------------
TwinVine Launcher is a Windows GUI application that wraps VineFeeder and
Envied into a single window — no terminal required.

Rather than launching VineFeeder as a subprocess, the launcher:

1.  Installs all required tools automatically (Git, FFmpeg, Bento4,
    MKVToolNix, N_m3u8DL-RE, and more) via the built-in Install/Update page.

2.  Adds the TwinVine venv site-packages to sys.path so it can import
    VineFeeder and its service modules directly at runtime.

3.  Monkey-patches BaseLoader's beaupy-based selection methods with native
    Qt inline panels — series and episode selection happen inside the app
    window using checkboxes, not terminal prompts.

4.  Monkey-patches console.input() calls with Qt inline input widgets.

5.  Captures all subprocess output from downloads into an in-app download
    panel with a live log, progress bar, and cancel button.

6.  Provides a Batch Mode that queues episodes from multiple series and
    downloads them all at once via the Run Batch button.

7.  Embeds the HellYes DRM key extraction tool as a built-in page.

The user experience is entirely self-contained — dark themed window,
service buttons, search box, download panel, and settings all in one place.

REQUIREMENTS
------------
End users: Windows 10/11 (64-bit), Python 3.12, 3.13 or 3.14 from python.org.
           Everything else is installed automatically by the launcher.

For building the installer exe, see BUILD.md.
"""

import os
import sys
import json

# When running as a PyInstaller frozen exe, ensure stdlib modules are findable
# by venv packages (e.g. rich needs colorsys which may not be in the frozen bundle)
if getattr(sys, 'frozen', False):
    import sysconfig
    _stdlib = sysconfig.get_path('stdlib')
    if _stdlib and _stdlib not in sys.path:
        sys.path.insert(0, _stdlib)
    # Also add the system Python Lib folder as fallback
    import pathlib as _pl
    for _candidate in [
        _pl.Path(sys.executable).parent / 'Lib',
        _pl.Path(sys.executable).parent.parent / 'Lib',
    ]:
        if _candidate.exists() and str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
import subprocess
import threading
import shutil
import webbrowser
from pathlib import Path
from datetime import datetime


# ── PyQt6 ─────────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QCheckBox, QComboBox, QSlider,
    QTextEdit, QScrollArea, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QSplitter, QStackedWidget,
    QProgressBar, QPlainTextEdit, QMessageBox, QFileDialog, QInputDialog, QTabWidget,
    QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QProcess, QTimer, QSize,
)
from PyQt6.QtGui import QPalette, QColor, QFont, QTextCursor

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────

APP_NAME        = "TwinVine Launcher"
APP_VERSION     = "1.0.2"
GITHUB_REPO     = "Lseauk/TwinVine-Launcher"
GITHUB_API      = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
GITHUB_URL      = f"https://github.com/{GITHUB_REPO}"
CLONE_REPO      = "Lseauk/TwinVine-Launcher-Core"
CLONE_URL       = f"https://github.com/{CLONE_REPO}.git"
LAUNCHER_URL    = "https://github.com/Lseauk/TwinVine-Launcher"

# Work out the best default install directory:
#   1. If the launcher lives inside an existing TwinVine checkout, use that.
#   2. If the launcher's own directory looks like a good home, put TwinVine
#      as a sibling folder next to the launcher.
#   3. Fall back to ~/TwinVine.
def _detect_default_install() -> Path:
    # When frozen by PyInstaller sys.executable is the .exe path;
    # when run as a .py file __file__ is the script path.
    if getattr(sys, "frozen", False):
        launcher_dir = Path(sys.executable).resolve().parent
    else:
        launcher_dir = Path(__file__).resolve().parent
    # Check if we're already inside a TwinVine checkout
    for candidate in [launcher_dir, launcher_dir.parent]:
        if (candidate / "packages" / "vinefeeder").exists():
            return candidate
    # Otherwise put TwinVine as a sibling of the launcher
    return launcher_dir / "TwinVine"

DEFAULT_INSTALL = _detect_default_install()
CONFIG_FILE     = Path(os.path.expanduser("~")) / ".twinvine_launcher.json"

# Catppuccin Mocha palette (matching VineFeeder exactly)
C = {
    "bg":           "#1e1e2e",
    "surface":      "#181825",
    "overlay":      "#313244",
    "text":         "#cdd6f4",
    "subtext":      "#a6adc8",
    "pink":         "#f5c2e7",
    "mauve":        "#cba6f7",
    "blue":         "#89b4fa",
    "green":        "#a6e3a1",
    "yellow":       "#f9e2af",
    "red":          "#f38ba8",
    "peach":        "#fab387",
    "border":       "#45475a",
}

# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    d = {"install_dir": str(DEFAULT_INSTALL), "installed": False,
         "last_commit": None, "install_date": None}
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            # Only trust a saved install_dir if it actually exists on this
            # machine — prevents stale paths from a different PC breaking things.
            saved_dir = saved.get("install_dir", "")
            if saved_dir and not Path(saved_dir).exists():
                saved.pop("install_dir", None)
                saved["installed"] = False   # force re-install on new machine
            d.update(saved)
        except Exception:
            pass
    return d

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── VineFeeder runtime bootstrap ──────────────────────────────────────────────

_VF_LOADED = False

def bootstrap_vinefeeder(install_dir: Path) -> tuple[bool, str]:
    """
    Add TwinVine's uv venv site-packages to sys.path so we can import
    vinefeeder and its service modules directly in this process.

    Critical: also os.chdir() to install_dir so that VineFeeder's own
    load_config_with_fallback() finds config.yaml via relative paths.

    Returns (True, "") on success, or (False, reason) on failure.
    """
    global _VF_LOADED
    if _VF_LOADED:
        return True, ""

    # ── 1. Change working directory ──────────────────────────────────────────
    # VineFeeder uses relative paths everywhere (./batch.txt, config.yaml,
    # ./packages/...).  The launcher may have been started from anywhere.
    try:
        os.chdir(install_dir)
    except Exception as e:
        return False, f"Cannot chdir to {install_dir}: {e}"

    # ── 2. Find uv venv site-packages ────────────────────────────────────────
    # uv on Windows creates  .venv\Lib\site-packages  (capital L)
    # uv on Linux creates    .venv/lib/pythonX.Y/site-packages
    # We search both patterns plus a lowercase fallback for safety.
    venv_root = install_dir / ".venv"
    if not venv_root.exists():
        return False, f"No .venv found inside {install_dir}. Please run the Install tab to run uv sync first."

    candidates = []
    # Windows (capital Lib)
    candidates += list(venv_root.glob("Lib/site-packages"))
    # Linux / macOS
    candidates += list(venv_root.glob("lib/python*/site-packages"))
    # Lowercase fallback (some edge cases)
    candidates += list(venv_root.glob("lib/site-packages"))

    if not candidates:
        # List what IS in .venv to help diagnose
        children = [str(p) for p in venv_root.iterdir()]
        return False, f".venv exists but no site-packages found. Contents: {children[:8]}"

    site_packages = str(candidates[0])
    venv_scripts  = str(venv_root / "Scripts")   # Windows
    venv_bin      = str(venv_root / "bin")         # Linux

    # ── 3. Rebuild sys.path — venv FIRST, system packages AFTER ─────────────────
    # The root problem on fresh installs: the launcher runs under system Python
    # (e.g. 3.14) which may have its own lxml/scrapy/etc already imported or
    # on sys.path.  Those system copies shadow the correct venv copies, causing
    # "cannot import name 'etree' from 'lxml'" because system lxml for 3.14
    # has no compiled etree yet.
    #
    # Solution: strip every non-stdlib, non-venv path from sys.path, then
    # prepend the venv site-packages.  This guarantees venv packages win.
    src_pkg = str(install_dir / "packages" / "vinefeeder" / "src")

    # Paths we always want to KEEP (stdlib, frozen, our own launcher dir)
    launcher_dir = str(Path(__file__).resolve().parent) if not getattr(sys, "frozen", False)                    else str(Path(sys.executable).resolve().parent)
    keep_prefixes = (
        site_packages, src_pkg, str(install_dir),
        venv_scripts, venv_bin, launcher_dir,
    )

    # Remove system site-packages paths that could shadow venv packages
    sys.path = [
        p for p in sys.path
        if (
            # keep stdlib (no site-packages in path name, or is a zip/frozen)
            "site-packages" not in p and "dist-packages" not in p
        ) or any(p.startswith(k) for k in keep_prefixes)
    ]

    # Now prepend venv paths at the very front
    for p in reversed([site_packages, src_pkg, str(install_dir),
                        venv_scripts, venv_bin]):
        if p not in sys.path:
            sys.path.insert(0, p)

    # ── 4. Evict conflicting cached modules ──────────────────────────────────────
    # Two cases to handle:
    # A) Running as PyInstaller exe: frozen stdlib modules (xmlrpc, email, http
    #    etc.) are incomplete — e.g. frozen xmlrpc has no xmlrpc.server.
    #    Their __file__ points to a _MEI temp dir. Evict ALL of them.
    # B) Running as .py under wrong Python: modules already imported from
    #    system site-packages shadow the venv copies. Evict those too.
    _ALWAYS_EVICT = (
        # venv-managed packages that must come from the venv, not system Python
        "lxml", "scrapy", "parsel", "cssselect", "itemloaders",
        "defusedxml", "beaupy", "rich", "httpx", "vinefeeder", "envied",
        # stdlib modules that PyInstaller may freeze incompletely
        # Note: xmlrpc is now fully included via hiddenimports, so not evicted
        "email", "http", "urllib", "html", "importlib.metadata",
    )
    for mod in list(sys.modules.keys()):
        for prefix in _ALWAYS_EVICT:
            if mod == prefix or mod.startswith(prefix + "."):
                m = sys.modules[mod]
                src = getattr(m, "__file__", "") or ""
                # Evict if from _MEI frozen dir OR from outside the venv
                if ("_MEI" in src or
                        (site_packages not in src and src_pkg not in src)):
                    sys.modules.pop(mod, None)
                break

    # ── 5. Environment variables ──────────────────────────────────────────────
    existing = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"]        = site_packages + os.pathsep + existing
    os.environ["PYTHONUTF8"]        = "1"
    os.environ["PYTHONIOENCODING"]  = "utf-8"
    os.environ["PYTHONWARNINGS"]    = "ignore"   # suppress SyntaxWarnings

    # ── 6. Version check — auto-relaunch under venv Python if needed ────────────
    # lxml, cryptography etc. are compiled extensions tied to a specific Python
    # ABI. If the launcher is running under a different Python version than the
    # venv (e.g. system 3.14 vs venv 3.13), those extensions cannot load.
    # Solution: detect the mismatch and silently relaunch under the venv Python.
    venv_cfg = venv_root / "pyvenv.cfg"
    if venv_cfg.exists():
        try:
            venv_ver = None
            for line in venv_cfg.read_text().splitlines():
                if line.startswith("version") and "=" in line:
                    venv_ver = line.split("=", 1)[1].strip()
                    break
            if venv_ver:
                run_mm  = f"{sys.version_info.major}.{sys.version_info.minor}"
                venv_mm = ".".join(venv_ver.split(".")[:2])
                if run_mm != venv_mm:
                    launcher_script = str(Path(__file__).resolve())
                    _startup_log(f"mismatch: {run_mm} vs {venv_mm}")
                    # Prefer real pythonw from uv cache (truly windowless)
                    relaunch = None
                    appdata = os.environ.get("APPDATA", "")
                    if appdata:
                        for d in sorted(Path(appdata).glob(
                                f"uv/python/cpython-{venv_mm}*-windows-x86_64-none"),
                                key=str, reverse=True):
                            pyw = d / "pythonw.exe"
                            py  = d / "python.exe"
                            if pyw.exists() and py.exists():
                                try:
                                    if pyw.stat().st_size != py.stat().st_size:
                                        relaunch = str(pyw)
                                        _startup_log(f"uv cache pythonw: {relaunch}")
                                        break
                                except Exception:
                                    pass
                    # Fall back to venv python.exe
                    if not relaunch:
                        venv_py = venv_root / "Scripts" / "python.exe"
                        if not venv_py.exists():
                            return False, f"Version mismatch and venv Python not found"
                        relaunch = str(venv_py)
                        _startup_log(f"venv python fallback: {relaunch}")
                    import subprocess as _sp2
                    proc = _sp2.Popen(
                        [relaunch, launcher_script],
                        cwd=str(install_dir),
                        creationflags=0x00000008|0x08000000,
                        close_fds=True,
                    )
                    _startup_log(f"relaunched PID={proc.pid} with {relaunch}")
                    sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            pass  # if we can't read pyvenv.cfg just try importing

    # ── 7. Try importing vinefeeder ───────────────────────────────────────────
    try:
        import vinefeeder  # noqa: F401
        _VF_LOADED = True
        return True, ""
    except Exception as e:
        return False, f"import vinefeeder failed: {e}  --  sys.path[0:4]={sys.path[:4]}"


# ── Qt selection dialogs (replace beaupy) ─────────────────────────────────────

class SingleSelectDialog(QDialog):
    """Replace beaupy.select() — pick exactly one item from a list."""

    def __init__(self, items: list, title="Select", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(520, 400)
        self._result = None
        self._apply_mocha(self)

        layout = QVBoxLayout(self)
        lbl = QLabel("Select one item:")
        lbl.setStyleSheet(f"color:{C['subtext']};")
        layout.addWidget(lbl)

        self.listw = QListWidget()
        self.listw.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listw.setStyleSheet(f"""
            QListWidget {{background:{C['surface']};color:{C['text']};
                          border:1px solid {C['border']};font-size:12px;}}
            QListWidget::item:selected {{background:{C['green']};color:{C['bg']};}}
            QListWidget::item:hover {{background:{C['overlay']};}}
        """)
        for item in items:
            self.listw.addItem(str(item))
        if items:
            self.listw.setCurrentRow(0)
        self.listw.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.listw)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.setStyleSheet(f"color:{C['text']};background:{C['overlay']};")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def accept(self):
        sel = self.listw.selectedItems()
        if sel:
            self._result = sel[0].text()
        super().accept()

    def result_item(self):
        return self._result

    @staticmethod
    def _apply_mocha(w):
        w.setStyleSheet(f"background:{C['bg']};color:{C['text']};")


class MultiSelectDialog(QDialog):
    """Replace beaupy.select_multiple() — pick one or more items."""

    def __init__(self, items: list, title="Select episodes", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 500)
        self._results = []
        self._apply_mocha(self)

        layout = QVBoxLayout(self)
        lbl = QLabel("Select one or more items  (Ctrl+click for multiple):")
        lbl.setStyleSheet(f"color:{C['subtext']};")
        layout.addWidget(lbl)

        # Quick select buttons
        btn_row = QHBoxLayout()
        for label, slot in [("Select All", self._sel_all),
                             ("Clear All",  self._sel_none)]:
            b = QPushButton(label)
            b.setStyleSheet(f"""QPushButton{{background:{C['overlay']};color:{C['text']};
                border:none;padding:4px 10px;border-radius:3px;}}
                QPushButton:hover{{background:{C['green']};color:{C['bg']};}}""")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.listw = QListWidget()
        self.listw.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listw.setStyleSheet(f"""
            QListWidget {{background:{C['surface']};color:{C['text']};
                          border:1px solid {C['border']};font-size:12px;}}
            QListWidget::item:selected {{background:{C['green']};color:{C['bg']};}}
            QListWidget::item:hover {{background:{C['overlay']};}}
        """)
        for item in items:
            self.listw.addItem(str(item))
        layout.addWidget(self.listw)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.setStyleSheet(f"color:{C['text']};background:{C['overlay']};")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _sel_all(self):
        self.listw.selectAll()

    def _sel_none(self):
        self.listw.clearSelection()

    def accept(self):
        self._results = [i.text() for i in self.listw.selectedItems()]
        super().accept()

    def result_items(self) -> list:
        return self._results

    @staticmethod
    def _apply_mocha(w):
        w.setStyleSheet(f"background:{C['bg']};color:{C['text']};")




class _DialogBridge(QObject if False else object):
    pass

# We build the real bridge class after QApplication exists (see _init_bridge())
_bridge = None


def _init_bridge():
    """Create the dialog bridge — must be called from the main thread."""
    global _bridge

    from PyQt6.QtCore import QObject, pyqtSignal as _sig

    class _Bridge(QObject):
        _request = _sig(object, object)   # (fn, container)

        def __init__(self):
            super().__init__()
            # Qt.ConnectionType.QueuedConnection guarantees the slot runs on
            # the thread that owns this QObject (the main thread).
            self._request.connect(self._on_request,
                                  Qt.ConnectionType.QueuedConnection)

        def _on_request(self, fn, container):
            try:
                container["result"] = fn()
            except Exception:
                container["result"] = None
            finally:
                container["event"].set()

        def run_sync(self, fn):
            """Call from any thread. Blocks until fn() completes on main thread."""
            container = {"result": None, "event": threading.Event()}
            self._request.emit(fn, container)
            container["event"].wait()
            return container["result"]

    _bridge = _Bridge()


def _gui_call(fn):
    """
    Run fn() on the main GUI thread and return its result.
    If already on the main thread, calls fn() directly to avoid deadlock.
    Safe to call from any thread.
    IMPORTANT: never call _bridge.run_sync from main thread — deadlock.
    """
    if _bridge is None:
        return fn()
    try:
        from PyQt6.QtCore import QCoreApplication, QThread
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            return fn()  # already on main thread — direct call
    except Exception:
        pass
    return _bridge.run_sync(fn)


class _UserCancelled(Exception):
    """Raised when user cancels a selection dialog — stops the service worker cleanly."""
    pass


def _qt_select(items, **kwargs):
    """Drop-in replacement for beaupy.select() — shows inline panel on Download page."""
    import threading as _th
    title = kwargs.get("_title", "Select one")
    str_items = [str(i) for i in items]
    result_box = [None]
    done_event = _th.Event()

    def _show():
        w = _qt_parent
        if w is None or not hasattr(w, "_sel_panel"):
            # Fallback to dialog if inline panel unavailable
            dlg = SingleSelectDialog(str_items, title=title, parent=_qt_parent)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_item():
                result_box[0] = dlg.result_item()
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()
            return

        # Build radio-button list
        panel = w._sel_panel
        w._sel_title.setText(title)
        w._sel_range_widget.setVisible(False)

        # Clear previous items
        while w._sel_list_layout.count():
            child = w._sel_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        group = QButtonGroup(panel)
        for i, item in enumerate(str_items):
            rb = QRadioButton(item)
            rb.setStyleSheet(
                "QRadioButton {"
                f"color:{C['text']};font-size:12px;padding:5px 8px;"
                f"border:1px solid {C['border']};border-radius:3px;"
                f"background:{C['bg']};}}"
                "QRadioButton:hover {"
                f"background:{C['surface']};}}"
                "QRadioButton::indicator {"
                "width:14px;height:14px;border-radius:7px;"
                f"border:2px solid {C['subtext']};background:{C['bg']};}}"
                "QRadioButton::indicator:checked {"
                f"background:{C['green']};border:2px solid {C['green']};}}"
            )
            if i == 0:
                rb.setChecked(True)
            group.addButton(rb, i)
            w._sel_list_layout.addWidget(rb)
        w._sel_list_layout.addStretch()

        def _confirm():
            checked_id = group.checkedId()
            if checked_id >= 0:
                result_box[0] = str_items[checked_id]
            panel.setVisible(False)
            w._sel_all_btn.setVisible(False)
            w._sel_none_btn.setVisible(False)
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
                w._sel_all_btn.clicked.disconnect()
                w._sel_none_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        def _cancel():
            panel.setVisible(False)
            w._sel_all_btn.setVisible(False)
            w._sel_none_btn.setVisible(False)
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
                w._sel_all_btn.clicked.disconnect()
                w._sel_none_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        try:
            w._sel_confirm_btn.clicked.disconnect()
            w._sel_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        # Hide Select All/None — not needed for series selection
        w._sel_all_btn.setVisible(False)
        w._sel_none_btn.setVisible(False)
        w._sel_confirm_btn.clicked.connect(_confirm)
        w._sel_cancel_btn.clicked.connect(_cancel)
        panel.setVisible(True)
        panel.raise_()

    from PyQt6.QtCore import QCoreApplication, QThread, QEventLoop
    on_main = (QCoreApplication.instance() is not None and
               QThread.currentThread() is QCoreApplication.instance().thread())

    if on_main:
        # On main thread — use QEventLoop so Qt can process button clicks
        loop = QEventLoop()
        done_event._loop = loop
        _show()  # direct call — sets up panel, returns immediately
        loop.exec()  # blocks but processes Qt events (button clicks fire here)
    else:
        _gui_call(_show)
        done_event.wait()

    if result_box[0] is None:
        raise _UserCancelled("Selection cancelled by user")
    # Map back to original object
    for item in items:
        if str(item) == result_box[0]:
            return item
    return result_box[0]


def _qt_select_multiple(items, _is_episode=False, **kwargs):
    """Drop-in replacement for beaupy.select_multiple() — shows inline panel."""
    import threading as _th
    str_items = [str(i) for i in items]
    result_box = [None]
    done_event = _th.Event()

    def _show():
        w = _qt_parent
        if w is None or not hasattr(w, "_sel_panel"):
            dlg = MultiSelectDialog(str_items, title="Select episodes",
                                    parent=_qt_parent)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                result_box[0] = dlg.result_items()
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()
            return

        panel = w._sel_panel
        title = kwargs.get("_title", "Select episodes  (tick all you want, then Confirm)")
        w._sel_title.setText(title)
        w._sel_range_widget.setVisible(False)

        # Clear previous items
        while w._sel_list_layout.count():
            child = w._sel_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        checkboxes = []
        for item in str_items:
            # Show a clean version — strip the URL and synopsis for readability
            parts = item.split(", ")
            display = parts[0] if len(parts) < 2 else f"S{parts[0]}  {parts[1]}"
            cb = QCheckBox(display)
            cb.setProperty("full_text", item)
            cb.setStyleSheet(
                "QCheckBox {"
                f"color:{C['text']};font-size:12px;padding:5px 8px;"
                f"border:1px solid {C['border']};border-radius:3px;"
                f"background:{C['bg']};}}"
                "QCheckBox:hover {"
                f"background:{C['surface']};}}"
                "QCheckBox::indicator {"
                "width:14px;height:14px;border-radius:2px;"
                f"border:2px solid {C['subtext']};background:{C['bg']};}}"
                "QCheckBox::indicator:checked {"
                f"background:{C['green']};border:2px solid {C['green']};}}"
            )
            checkboxes.append(cb)
            w._sel_list_layout.addWidget(cb)

        w._sel_list_layout.addStretch()

        def _do_confirm():
            """Actually commit the selection and resume vinefeeder."""
            selected = [cb.property("full_text")
                        for cb in checkboxes if cb.isChecked()]
            result_box[0] = selected if selected else None
            panel.setVisible(False)
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        def _do_cancel():
            """Cancel from opts panel — release done_event so vinefeeder unblocks."""
            result_box[0] = None
            panel.setVisible(False)
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        def _confirm():
            """Show Download Options panel first, then confirm."""
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
            except Exception:
                pass
            # Only show opts panel for episode selection (flag set by caller)
            if hasattr(w, '_opts_show') and _is_episode:
                w._opts_show(_do_confirm, _do_cancel)
            else:
                _do_confirm()

        def _cancel():
            panel.setVisible(False)
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        try:
            w._sel_confirm_btn.clicked.disconnect()
            w._sel_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        # Show and wire Select All/None for episode selection
        w._sel_all_btn.setVisible(True)
        w._sel_none_btn.setVisible(True)
        try:
            w._sel_all_btn.clicked.disconnect()
            w._sel_none_btn.clicked.disconnect()
        except Exception:
            pass
        w._sel_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes])
        w._sel_none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes])
        w._sel_confirm_btn.clicked.connect(_confirm)
        w._sel_cancel_btn.clicked.connect(_cancel)
        panel.setVisible(True)
        panel.raise_()

    from PyQt6.QtCore import QCoreApplication, QThread, QEventLoop
    on_main = (QCoreApplication.instance() is not None and
               QThread.currentThread() is QCoreApplication.instance().thread())

    if on_main:
        loop = QEventLoop()
        done_event._loop = loop
        _show()
        loop.exec()
    else:
        _gui_call(_show)
        done_event.wait()

    if result_box[0] is None:
        raise _UserCancelled("Selection cancelled by user")
    originals = []
    for rs in result_box[0]:
        for item in items:
            if str(item) == rs:
                originals.append(item)
                break
        else:
            originals.append(rs)
    return originals if originals else ([items[0]] if items else [])


def _qt_console_input(prompt=""):
    """Replace Console().input() — shows inline series range input on Download page."""
    import threading as _th
    result_box = ["0"]
    done_event = _th.Event()

    def _show():
        w = _qt_parent
        if w is None or not hasattr(w, "_sel_panel"):
            result_box[0] = "0"
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()
            return
        # Extract series count from prompt if possible
        w._sel_title.setText("Which series to download?")
        w._sel_range_widget.setVisible(True)
        w._sel_range_input.clear()
        w._sel_range_input.setPlaceholderText("0 = all, or e.g. 1  or  2,3  or  1..4")

        # Hide the list, just show the range input
        while w._sel_list_layout.count():
            child = w._sel_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Strip Rich markup like [rgb(...)], [{var}], [/] from prompt
        import re as _re2
        clean_prompt = _re2.sub(r'[[]/?[^]]*[]]', '', prompt).strip()
        lbl = QLabel(clean_prompt or "Which series to download?")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        w._sel_list_layout.addWidget(lbl)
        w._sel_list_layout.addStretch()

        def _confirm():
            val = w._sel_range_input.text().strip() or "0"
            result_box[0] = val
            panel.setVisible(False)
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        def _cancel():
            result_box[0] = "0"
            panel.setVisible(False)
            try:
                w._sel_confirm_btn.clicked.disconnect()
                w._sel_cancel_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(done_event, "_loop"):
                done_event._loop.quit()
            done_event.set()

        # Allow Enter key to confirm
        w._sel_range_input.returnPressed.connect(_confirm)

        try:
            w._sel_confirm_btn.clicked.disconnect()
            w._sel_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        w._sel_confirm_btn.clicked.connect(_confirm)
        w._sel_cancel_btn.clicked.connect(_cancel)
        panel.setVisible(True)
        panel.raise_()
        w._sel_range_input.setFocus()

    from PyQt6.QtCore import QCoreApplication, QThread, QEventLoop
    on_main = (QCoreApplication.instance() is not None and
               QThread.currentThread() is QCoreApplication.instance().thread())

    if on_main:
        loop = QEventLoop()
        done_event._loop = loop
        _show()
        loop.exec()
    else:
        _gui_call(_show)
        done_event.wait()
    return result_box[0]


def _qt_runsubprocess(self, command):
    """
    Replace BaseLoader.runsubprocess() — runs the download command.
    Injects any extra options set in the Download Options panel.
    """
    # Inject Download Options panel flags into the command
    w = _main_window
    if w and hasattr(w, '_opts_extra_args') and w._opts_extra_args:
        try:
            dl_idx = command.index('dl')
            for arg in reversed(w._opts_extra_args):
                command.insert(dl_idx + 1, arg)
        except ValueError:
            command.extend(w._opts_extra_args)
        # Do NOT clear here — args must apply to every episode in the batch


    if self.BATCH_DOWNLOAD:
        batch_path = Path(os.getcwd()) / "batch.txt"
        with open(batch_path, "a") as f:
            f.write(" ".join(command) + "\n")
        _log_fn(f"[batch] Written to batch.txt: {' '.join(command)}")
        return

    import tempfile, shutil as _shutil

    cwd = os.getcwd()   # already chdir'd to install_dir in bootstrap

    # Queue the command — we collect all episodes first, then run them
    # sequentially in a single PowerShell window rather than opening one
    # window per episode simultaneously.
    import threading as _th2

    # Collect all episode commands into a shared list.
    # VineFeeder calls runsubprocess once per episode synchronously,
    # so by the time the first call returns all episodes are queued.
    # We delay launching until a short idle period confirms no more
    # commands are coming, then write ONE PS1 with all commands and
    # run it once — exactly like the original terminal behaviour.
    if not hasattr(_qt_runsubprocess, "_lock"):
        _qt_runsubprocess._lock    = _th2.Lock()
        _qt_runsubprocess._queue   = []
        _qt_runsubprocess._timer   = None

    with _qt_runsubprocess._lock:
        _qt_runsubprocess._queue.append((command, cwd))
        _log_fn(f"[download] Queued episode {len(_qt_runsubprocess._queue)}")

        # Cancel any pending launch timer — more commands may still come
        if _qt_runsubprocess._timer is not None:
            _qt_runsubprocess._timer.cancel()

        # Start a new timer — if no more commands arrive within 0.5s, launch
        def _do_launch():
            with _qt_runsubprocess._lock:
                cmds = list(_qt_runsubprocess._queue)
                _qt_runsubprocess._queue.clear()
                _qt_runsubprocess._timer = None
            if cmds:
                w = _main_window
                _slow = False
                _slow_min, _slow_max = 10, 60
                if w is not None:
                    if hasattr(w, '_opts_slow') and w._opts_slow.isChecked():
                        _slow = True
                        try: _slow_min = max(1, int(w._opts_slow_min.text()))
                        except ValueError: pass
                        try: _slow_max = max(_slow_min, int(w._opts_slow_max.text()))
                        except ValueError: pass
                    elif hasattr(w, '_url_slow') and w._url_slow.isChecked():
                        _slow = True
                        try: _slow_min = max(1, int(w._url_slow_min.text()))
                        except ValueError: pass
                        try: _slow_max = max(_slow_min, int(w._url_slow_max.text()))
                        except ValueError: pass
                _launch_all_powershell(cmds, slow_mode=_slow,
                                       slow_min=_slow_min, slow_max=_slow_max)

        t = _th2.Timer(0.5, _do_launch)
        _qt_runsubprocess._timer = t
        t.start()
    return

# Module-level reference to main window for signal emission
_main_window = None



def _launch_all_powershell(episode_list, slow_mode=False, slow_min=10, slow_max=60):
    """
    Run all episode commands sequentially, capturing output and displaying
    it in the app's download panel via signals. No console window opens.
    episode_list: list of (command, cwd) tuples
    """
    import re as _re
    import threading as _th

    if not episode_list:
        return

    # Strip ANSI escape codes
    _ansi = _re.compile(r'\x1b\[[0-9;]*[mGKHF]|\x1b\][^\x07]*\x07|\r')

    def _strip(line: str) -> str:
        return _ansi.sub('', line).strip()

    # Try to extract percentage from progress lines
    _pct_re = _re.compile(r'(\d{1,3})%')

    cwd = episode_list[0][1]
    total = len(episode_list)

    def _resolve_exe(name: str) -> str:
        venv_scripts = Path(cwd) / ".venv" / "Scripts"
        try:
            saved_cfg = load_config()
            saved = saved_cfg.get("uv_exe") or ""
            if saved and name.lower() in Path(saved).name.lower():
                if Path(saved).exists():
                    return saved
        except Exception:
            pass
        p = venv_scripts / (name + ".exe")
        if p.exists():
            return str(p)
        import shutil as _sh
        hit = _sh.which(name)
        if hit:
            return hit
        for d in [
            Path(os.path.expanduser("~")) / ".local" / "bin",
            Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
        ]:
            if (d / (name + ".exe")).exists():
                return str(d / (name + ".exe"))
        return name

    def _run():
        w = _main_window
        _all_ok = True
        _cancelled = False
        for i, (cmd, ep_cwd) in enumerate(episode_list, 1):
            resolved = [_resolve_exe(cmd[0])] + list(cmd[1:])
            label = f"Episode {i} of {total}"
            _log_fn(f"[download] Starting {label}: {' '.join(resolved[:4])}...")
            if w:
                w._dl_signals.episode.emit(label)
                w._dl_signals.progress.emit(0)
                w._dl_signals.line.emit(f"─── {label} ───")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONUTF8"]       = "1"
            env["PYTHONWARNINGS"]   = "ignore"
            # Add tools to PATH
            tools_dirs = [
                str(Path(ep_cwd) / ".venv" / "Scripts"),
                r"C:\Tools\bin",
                r"C:\Program Files\MKVToolNix",
            ]
            env["PATH"] = ";".join(tools_dirs) + ";" + env.get("PATH", "")

            try:
                proc = subprocess.Popen(
                    resolved,
                    cwd=ep_cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    text=False,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if w:
                    _gui_call(lambda p=proc: setattr(w, '_dl_proc', p))

                last_pct = 0

                # Timer animates progress 0->88% while envied buffers its output.
                # _active list holds [True]; set to [False] to stop the timer.
                _active = [True]

                def _progress_ticker(active):
                    import time as _time
                    _p = 0
                    while active[0] and _p < 88:
                        _time.sleep(2)
                        if not active[0]:
                            break
                        if _p < 30:
                            _p += 3
                        elif _p < 70:
                            _p += 2
                        else:
                            _p += 1
                        if w and active[0]:
                            w._dl_signals.progress.emit(min(_p, 88))

                _th.Thread(target=_progress_ticker, args=(_active,), daemon=True).start()

                # Read output in chunks so we can check for cancellation
                _buf = b""
                while True:
                    chunk = proc.stdout.read(256)
                    if not chunk:
                        break
                    # Check if user cancelled
                    if w and w._dl_proc is None:
                        _cancelled = True
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        break
                    _buf += chunk

                _active[0] = False  # stop timer

                if _cancelled:
                    proc.wait()
                    break  # exit episode loop — no more downloads

                # Process the buffered output
                try:
                    text = _buf.decode("utf-8", errors="replace")
                except Exception:
                    text = ""

                for raw in text.splitlines():
                    clean = _strip(raw)
                    if not clean:
                        continue
                    if 'Track downloads finished' in clean:
                        last_pct = 90
                        if w: w._dl_signals.progress.emit(90)
                    elif 'Multiplexing' in clean:
                        last_pct = 93
                        if w: w._dl_signals.progress.emit(93)
                    elif 'Title downloaded' in clean or 'downloaded in' in clean.lower():
                        last_pct = 97
                        if w: w._dl_signals.progress.emit(97)
                    if any(c in clean for c in ['█', '░', '▓', '▒']):
                        continue
                    if w:
                        w._dl_signals.line.emit(clean)
                    _log_fn(f"[dl] {clean}")

                proc.wait()
                if w and not _cancelled:
                    w._dl_signals.progress.emit(100)
                    if proc.returncode == 0:
                        status = "✓ complete"
                    else:
                        status = f"✗ failed (code {proc.returncode})"
                        _all_ok = False
                    w._dl_signals.line.emit(f"Episode {i}: {status}")

                # Slow mode delay between episodes
                if slow_mode and i < total and not _cancelled:
                    import random as _random, time as _time_slow
                    delay = _random.randint(slow_min, slow_max)
                    _log_fn(f"[download] Slow mode: waiting {delay}s before next episode...")
                    if w:
                        w._dl_signals.line.emit(
                            f"⏱  Slow mode — waiting {delay}s before next episode...")
                    _time_slow.sleep(delay)

            except Exception as e:
                _all_ok = False
                _log_fn(f"[download] Error: {e}")
                if w:
                    w._dl_signals.line.emit(f"Error: {e}")

        if _cancelled:
            _log_fn("[download] Download cancelled")
            if w:
                w._dl_signals.done.emit(False)
        else:
            _log_fn("[download] All episodes complete")
            if w:
                w._dl_signals.done.emit(_all_ok)

    # Show the download panel on main thread, then start worker thread
    def _show_panel():
        w = _main_window
        if not w:
            return
        w._dl_log.clear()
        w._dl_progress.setValue(0)
        w._dl_proc = None
        w._dl_ep_label.setText(f"Downloading {total} episode(s)...")
        w._dl_ep_label.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        try:
            w._dl_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        w._dl_cancel_btn.setText("\u2715  Cancel Download")
        w._dl_cancel_btn.clicked.connect(w._dl_cancel)
        w._dl_panel.setVisible(True)
        w._sel_panel.setVisible(False)
        w._action_widget.setVisible(False)
        w._action_input_widget.setVisible(False)

    _gui_call(_show_panel)
    _th.Thread(target=_run, daemon=True).start()
    return  # return immediately — output comes via signals



def _launch_powershell(command, cwd):
    """Open a single PowerShell window for one download command and WAIT for it to finish."""
    import tempfile, shutil as _shutil

    # Quote each argument for PowerShell (wrap in single-quotes, escape
    # any literal single-quotes inside by doubling them).
    def ps_quote(s):
        return "'" + str(s).replace("'", "''") + "'"

    venv_scripts = Path(cwd) / ".venv" / "Scripts"

    # Resolve the executable (first token, usually "uv") to its absolute path.
    # Priority:
    #   1. Saved uv_exe from config  (most reliable — recorded during install)
    #   2. TwinVine venv Scripts
    #   3. Next to sys.executable (where pip puts it)
    #   4. System PATH
    #   5. uv self-install locations
    def _resolve_exe(name: str) -> str:
        # 1. Config-saved path (set during install, survives restarts)
        try:
            saved_cfg = load_config()
            saved = saved_cfg.get("uv_exe") or ""
            if saved and name.lower() in Path(saved).name.lower():
                if Path(saved).exists():
                    return saved
        except Exception:
            pass
        # 2. venv Scripts
        p = venv_scripts / (name + ".exe")
        if p.exists():
            return str(p)
        # 3. Next to sys.executable and its Scripts subdirectory
        for py_dir in [Path(sys.executable).parent,
                       Path(sys.executable).parent / "Scripts",
                       Path(sys.prefix) / "Scripts",
                       Path(sys.base_prefix) / "Scripts"]:
            c = py_dir / (name + ".exe")
            if c.exists():
                return str(c)
        # 4. System PATH
        import shutil as _sh
        hit = _sh.which(name)
        if hit:
            return hit
        # 5. uv self-install locations
        for d in [
            Path(os.path.expanduser("~")) / ".local" / "bin",
            Path(os.path.expanduser("~")) / ".cargo" / "bin",
            Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
        ]:
            if (d / (name + ".exe")).exists():
                return str(d / (name + ".exe"))
        return name   # last resort

    resolved_command = [_resolve_exe(command[0])] + list(command[1:])
    cmd_ps = " ".join(ps_quote(a) for a in resolved_command)
    _log_fn(f"[download] Resolved exe: {resolved_command[0]}")

    # Tool dirs for PATH inside the PS1 session
    # Install-media-tools.ps1 puts ALL tools into C:\Tools\bin (confirmed from source).
    # MKVToolNix goes to C:\Program Files\MKVToolNix via its own silent installer.
    # We hardcode these and then do a fallback search so it works even if the
    # user moved things.
    tools_bin = Path("C:/Tools/bin")
    mkv_dir   = Path("C:/Tools/bin")  # portable install goes here

    # Fallback: scan inside the TwinVine install dir in case tools ended up there
    def _find_exe(name: str) -> str | None:
        if (tools_bin / name).exists():
            return str(tools_bin)
        if mkv_dir.exists() and (mkv_dir / name).exists():
            return str(mkv_dir)
        try:
            for p in Path(cwd).rglob(name):
                return str(p.parent)
        except Exception:
            pass
        import shutil as _sh2
        hit = _sh2.which(name)
        return str(Path(hit).parent) if hit else None

    nm3u8_dir    = _find_exe("N_m3u8DL-RE.exe") or str(tools_bin)
    ffmpeg_dir   = _find_exe("ffmpeg.exe")       or str(tools_bin)
    mkvmerge_dir = _find_exe("mkvmerge.exe")     or str(mkv_dir)

    _log_fn(f"[download] N_m3u8DL-RE dir : {nm3u8_dir}")
    _log_fn(f"[download] ffmpeg dir       : {ffmpeg_dir}")
    _log_fn(f"[download] mkvmerge dir     : {mkvmerge_dir}")

    # Build deduplicated PATH list — venv Scripts first, then tools
    seen = set()
    tools_dirs = []
    for d in [str(venv_scripts), str(tools_bin), nm3u8_dir,
              ffmpeg_dir, mkvmerge_dir, str(mkv_dir),
              "C:\\Program Files (x86)\\MKVToolNix"]:
        if d and d not in seen:
            seen.add(d)
            tools_dirs.append(d)

    path_prepend = ";".join(tools_dirs)
    # Display command for debugging — shows exactly what's being run
    cmd_display = " ".join(str(a) for a in resolved_command)

    script_lines = [
        # Extend PATH with all tool locations
        f"$env:PATH = '{path_prepend}' + ';' + $env:PATH",
        # Suppress Python SyntaxWarnings from third-party packages (e.g. tinycss)
        "$env:PYTHONWARNINGS = 'ignore'",
        "$env:PYTHONUTF8 = '1'",
        f"Set-Location {ps_quote(cwd)}",
        # Show command at top of window so user can see what's being run
        f"Write-Host 'Running: {cmd_display}' -ForegroundColor DarkGray",
        "Write-Host ''",
        # Run the command; capture exit code so we can report errors
        f"& {cmd_ps}",
        "$exit_code = $LASTEXITCODE",
        "Write-Host ''",
        # Show success or failure clearly
        "if ($exit_code -eq 0) {",
        "    Write-Host 'Download complete.' -ForegroundColor Green",
        "} else {",
        "    Write-Host 'Command exited with code ' + $exit_code -ForegroundColor Red",
        "}",
        "Write-Host 'Press any key to close...' -ForegroundColor DarkGray",
        "$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')",
    ]
    script_content = "\r\n".join(script_lines)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False,
        encoding="utf-8", prefix="twinvine_dl_"
    )
    tmp.write(script_content)
    tmp.close()
    script_path = tmp.name
    _log_fn(f"[download] Wrote helper script: {script_path}")

    # Use powershell.exe or pwsh.exe directly — NOT wt.exe.
    # wt.exe (Windows Terminal) exits immediately after spawning a tab,
    # so proc.wait() returns instantly and the queue opens the next window
    # simultaneously, defeating the sequential download logic.
    term = next((e for e in ("pwsh.exe", "powershell.exe")
                 if _shutil.which(e)), None)
    if term is None:
        _log_fn("[download] ERROR: powershell.exe not found")
        return

    outer = [term, "-ExecutionPolicy", "Bypass", "-File", script_path]

    _log_fn(f"[download] Opening terminal: {term}")
    # proc.wait() blocks until the PowerShell window closes — ensures
    # sequential downloads, one window at a time
    proc = subprocess.Popen(outer, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    proc.wait()
    _log_fn("[download] Episode complete, moving to next in queue...")



def patch_base_loader():
    """
    Replace all beaupy/console.input calls in base_loader with Qt equivalents.
    Must be called AFTER bootstrap_vinefeeder() succeeds.
    """
    try:
        from vinefeeder import base_loader
    except Exception as e:
        _log_fn(f"[patch] cannot import vinefeeder.base_loader: {e}")
        import traceback
        _log_fn(traceback.format_exc())
        return False

    try:
        import beaupy
    except Exception as e:
        _log_fn(f"[patch] cannot import beaupy: {e} -- is uv sync complete?")
        import traceback
        _log_fn(traceback.format_exc())
        return False

    # Patch the module-level beaupy functions used by base_loader
    beaupy.select          = _qt_select
    beaupy.select_multiple = _qt_select_multiple

    # Patch BaseLoader instance methods
    from vinefeeder.base_loader import BaseLoader

    # display_series_list — returns a single series name string
    def _display_series_list(self):
        series_list = list(self.series_data.keys())
        return _qt_select(series_list, _title="Select series")

    # display_episode_list — returns list of "s, ep, url, synopsis" strings
    def _display_episode_list(self, series_name):
        episodes = self.series_data.get(series_name, [])
        episode_list = [
            f"S{ep['series_no']} · {ep['title']}\n    {ep.get('synopsis','')[:80]}"
            for ep in episodes
        ]
        selected_strs = _qt_select_multiple(episode_list, _is_episode=True)
        # Map back to original format that services expect
        result = []
        for s in selected_strs:
            idx = episode_list.index(s)
            ep = episodes[idx]
            result.append(
                f"{ep['series_no']}, {ep['title']}, {ep['url']}, \n\t {ep.get('synopsis','')}"
            )
        return result

    # display_final_episode_list — same shape
    def _display_final_episode_list(self, final_episode_data):
        episode_list = [
            f"S{ep['series_no']} · {ep['title']}\n    {ep.get('synopsis','')[:80]}"
            for ep in final_episode_data
        ]
        selected_strs = _qt_select_multiple(episode_list, _is_episode=True)
        result = []
        for s in selected_strs:
            idx = episode_list.index(s)
            ep = final_episode_data[idx]
            result.append(
                f"{ep['series_no']}, {ep['title']}, {ep['url']}, \n\t {ep.get('synopsis','')}"
            )
        return result

    # display_beaupylist — takes list of strings, returns one
    def _display_beaupylist(self, beaupylist):
        return _qt_select(beaupylist, _title="Select")

    # list_display_beaupylist — takes list of lists, returns one
    def _list_display_beaupylist(self, beaupylist):
        items = [" · ".join(str(x) for x in item) if isinstance(item, list) else str(item)
                 for item in beaupylist]
        chosen_str = _qt_select(items, _title="Select")
        # Return the original item
        idx = items.index(chosen_str)
        return beaupylist[idx]

    # console.input replacement — used in prepare_series_for_episode_selection
    # We patch the rich Console instance on BaseLoader so console.input → dialog
    class _FakeConsole:
        def input(self, prompt=""):
            return _qt_console_input(prompt)
        def print(self, *args, **kwargs):
            from rich.console import Console as _C
            _C().print(*args, **kwargs)
            # also send to our log
            _log_fn(str(args[0]) if args else "")

    # Assign patched methods
    BaseLoader.display_series_list         = _display_series_list
    BaseLoader.display_episode_list        = _display_episode_list
    BaseLoader.display_final_episode_list  = _display_final_episode_list
    BaseLoader.display_beaupylist          = _display_beaupylist
    BaseLoader.list_display_beaupylist     = _list_display_beaupylist
    BaseLoader.runsubprocess               = _qt_runsubprocess

    # Patch the console instance used by prepare_series_for_episode_selection
    base_loader.console = _FakeConsole()

    # ── Patch prepare_series_for_episode_selection ──────────────────────────
    # Instead of console.input() for series number, show series checkboxes
    _orig_prepare = BaseLoader.prepare_series_for_episode_selection

    def _qt_prepare_series(self, series_name):
        # If <= 12 episodes, original logic is fine (no series selection needed)
        number_episodes = self.get_number_of_episodes(series_name)
        if number_episodes <= 12:
            for episode in self.series_data[series_name]:
                self.add_final_episode(episode)
            return

        # Get available series numbers
        try:
            series_numbers = self.get_episodes_series_numbers(series_name)
        except Exception:
            _orig_prepare(self, series_name)
            return

        # Build display list — show as "Series 1", "Series 2" etc.
        display_items = []
        for s in series_numbers:
            display_items.append(str(s))

        # Use _qt_select_multiple to show as checkboxes
        selected = _qt_select_multiple(
            display_items,
            _is_episode=False,
            _title="Select series  (tick all you want, then Confirm)"
        )

        if not selected:
            return

        # Convert selected back to series numbers and populate final_episode_data
        selected_nums = set()
        for s in selected:
            try:
                selected_nums.add(int(str(s).strip()))
            except ValueError:
                pass

        for series_no in selected_nums:
            for episode in self.series_data[series_name]:
                try:
                    if int(episode["series_no"]) == series_no:
                        self.add_final_episode(episode)
                except Exception:
                    pass

    BaseLoader.prepare_series_for_episode_selection = _qt_prepare_series

    return True


# ── Worker thread ─────────────────────────────────────────────────────────────

class FetchTracksWorker(QThread):
    log_line = pyqtSignal(str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, uv_exe, install_dir, service, url):
        super().__init__()
        self.uv_exe      = str(uv_exe)
        self.install_dir = Path(install_dir)
        self.service     = service
        self.url         = url

    def run(self):
        import subprocess as _sp
        try:
            cmd = [self.uv_exe, "run", "envied", "dl",
                   "--list", self.service, self.url]
            self.log_line.emit(f"[fetch] {' '.join(cmd)}")
            r = _sp.run(cmd, cwd=str(self.install_dir),
                        capture_output=True, text=True, timeout=90,
                        creationflags=_sp.CREATE_NO_WINDOW,
                        encoding="utf-8", errors="replace")
            self.log_line.emit(f"[fetch] return code: {r.returncode}")
            output = (r.stdout or "") + (r.stderr or "")
            for line in output.splitlines():
                if line.strip():
                    self.log_line.emit(f"[fetch] {line}")
            self.finished.emit(output)
        except Exception as e:
            self.error.emit(str(e))


class ServiceWorker(QThread):
    """
    Runs a VineFeeder service loader in a background thread.
    Uses a plain threading.Thread internally so the main thread's Qt event
    loop stays free to process dialog signals from _gui_call/_bridge.
    If ServiceWorker were itself a QThread, its event.wait() would block
    Qt signal delivery causing a deadlock on category browse dialogs.
    """
    log_line   = pyqtSignal(str)
    finished   = pyqtSignal()
    error      = pyqtSignal(str)

    def __init__(self, loader_cls, inx, text, found, hlg_status, options):
        super().__init__()
        self.loader_cls  = loader_cls
        self.inx         = inx
        self.text        = text
        self.found       = found
        self.hlg_status  = hlg_status
        self.options     = options
        self._done_event = threading.Event()

    def run(self):
        # Run the actual work in a plain thread so the Qt main event loop
        # stays responsive for _gui_call dialog signals.
        import threading as _th
        result_box = [None]

        def _crash_log(msg: str):
            """Write to crash log AND the app log."""
            _log_fn(msg)
            try:
                import pathlib, datetime
                log = pathlib.Path.home() / ".twinvine_crash.log"
                with open(log, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')}] {msg}\n")
            except Exception:
                pass

        def _worker():
            try:
                _crash_log(f"[worker] START {self.loader_cls.__name__} "
                           f"inx={self.inx} text={self.text!r} found={self.found!r}")
                _crash_log(f"[worker] Creating instance...")
                instance = self.loader_cls()
                _crash_log(f"[worker] Instance created, calling receive()...")
                instance.receive(self.inx, self.text, self.found,
                                 self.hlg_status, self.options)
                _crash_log("[worker] receive() completed normally")
            except _UserCancelled:
                _crash_log("[worker] Cancelled by user")
            except SystemExit as e:
                _crash_log(f"[worker] SystemExit code={e.code} — normal completion")
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                _crash_log(f"[worker] EXCEPTION: {type(e).__name__}: {e}")
                _crash_log(tb)
                result_box[0] = str(e)
            finally:
                _crash_log("[worker] done, setting event")
                self._done_event.set()

        t = _th.Thread(target=_worker, daemon=True)
        t.start()
        # Wait in this QThread without blocking Qt — process events while waiting
        while not self._done_event.wait(timeout=0.05):
            pass
        if result_box[0]:
            self.error.emit(result_box[0])
        self.finished.emit()


# ── Install worker ────────────────────────────────────────────────────────────

def _run_hidden(cmd, cwd=None, env=None):
    base_env = os.environ.copy()
    base_env["PYTHONUTF8"] = "1"
    base_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        base_env.update(env)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=base_env, startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

def _run_cmd(cmd, cwd=None, env=None):
    proc = _run_hidden(cmd, cwd=cwd, env=env)
    for line in proc.stdout:
        yield line.rstrip()
    proc.wait()
    return proc.returncode


class _UpdateCheckThread(QThread):
    """Checks GitHub for a new commit SHA in a background QThread."""
    result_ready = pyqtSignal(str, str)   # (remote_sha, local_sha)

    def __init__(self, local_commit: str):
        super().__init__()
        self._local = local_commit or ""

    def run(self):
        remote = ""
        if REQUESTS_AVAILABLE:
            try:
                r = requests.get(GITHUB_API, timeout=10,
                                 headers={"Accept": "application/vnd.github.v3+json"})
                if r.ok:
                    remote = r.json().get("sha", "")[:12]
            except Exception:
                pass
        self.result_ready.emit(remote, self._local)


class InstallWorker(QThread):
    log_line  = pyqtSignal(str)
    step_done = pyqtSignal(str, str)   # key, state
    progress  = pyqtSignal(float, str)
    finished  = pyqtSignal(bool, str)  # success, message

    def __init__(self, install_dir: Path):
        super().__init__()
        self.install_dir = install_dir

    def _log(self, msg):
        self.log_line.emit(msg)

    def _step(self, key, state):
        self.step_done.emit(key, state)

    def _require_git(self) -> bool:
        """Ensure git is available, installing it via winget if needed."""
        if shutil.which("git"):
            return True

        self._log("git not found — attempting to install via winget...")
        # winget is built into Windows 10 1809+ and all Windows 11 machines
        if not shutil.which("winget"):
            return False

        for l in _run_cmd([
            "winget", "install", "--id", "Git.Git",
            "-e", "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]):
            self._log(l)

        # After winget install, git may not be on PATH in this process yet.
        # Find it manually in the standard location.
        git_default = Path("C:/Program Files/Git/cmd/git.exe")
        if git_default.exists():
            # Add to PATH for this process so subsequent calls work
            os.environ["PATH"] = str(git_default.parent) + os.pathsep + os.environ.get("PATH", "")
            self._log(f"git installed at {git_default}")
            return True

        return bool(shutil.which("git"))

    def _git(self, args: list, cwd=None):
        """Run a git command, using full path if needed."""
        git_exe = shutil.which("git") or "C:/Program Files/Git/cmd/git.exe"
        for l in _run_cmd([git_exe] + args, cwd=cwd):
            self._log(l)

    def run(self):
        try:
            d = self.install_dir
            self.progress.emit(0, "Starting…")

            # ── Step 0: ensure git exists ──────────────────────────────────
            self._step("git", "active")
            self._log("── STEP 1: Checking git")
            if not self._require_git():
                raise RuntimeError(
                    "git is not installed and could not be installed automatically. "
                    "Please install Git from https://git-scm.com/download/win "
                    "then re-run the installer."
                )

            # ── Step 1: clone or pull ──────────────────────────────────────
            self._log("── STEP 1: Repository")
            if (d / ".git").exists():
                # Verify the existing repo is the correct one before pulling
                try:
                    import subprocess as _sp_git
                    git_exe = shutil.which("git") or "C:/Program Files/Git/cmd/git.exe"
                    _r = _sp_git.run(
                        [git_exe, "remote", "get-url", "origin"],
                        cwd=str(d), capture_output=True, text=True,
                        creationflags=_sp_git.CREATE_NO_WINDOW
                    )
                    existing_remote = _r.stdout.strip()
                except Exception:
                    existing_remote = ""
                if CLONE_REPO.lower() not in existing_remote.lower():
                    self._log(
                        f"Existing repo points at wrong remote ({existing_remote}). "
                        f"Removing and recloning from {CLONE_URL}..."
                    )
                    import shutil as _shutil
                    _shutil.rmtree(str(d), ignore_errors=True)
                    self._log(f"Cloning {CLONE_URL} → {d}")
                    d.parent.mkdir(parents=True, exist_ok=True)
                    self._git(["clone", CLONE_URL, str(d)])
                else:
                    self._log(f"Updating existing repo at {d}")
                    self._git(["pull"], cwd=d)
            else:
                self._log(f"Cloning {CLONE_URL} → {d}")
                d.parent.mkdir(parents=True, exist_ok=True)
                self._git(["clone", CLONE_URL, str(d)])

            # Verify clone worked
            if not (d / "packages").exists():
                raise RuntimeError(
                    f"Clone succeeded but {d}/packages is missing. Check Log tab for git errors."
                )
            self.progress.emit(0.2, "Repository ready.")

            # ── Step 2: media tools via PS1 ────────────────────────────────
            self._step("tools", "active")
            self._step("tools", "active")
            self._log("── STEP 2: Media tools")

            tools_bin = Path("C:/Tools/bin")
            tools_bin.mkdir(parents=True, exist_ok=True)

            # ── 2a. Download media tools directly with progress reporting ────────
            # Previously used Install-media-tools.ps1 but it gives no progress
            # output during the long FFmpeg download, making users think it crashed.
            # Now we download everything ourselves with per-MB progress logging.
            import urllib.request as _urlreq, zipfile as _zf, tempfile as _tf2

            mkv_dir = Path("C:/Program Files/MKVToolNix")

            def _download_to_bin(url: str, dest_name: str, zip_match: str = None):
                """Download url with progress; if zip extract the file matching zip_match."""
                if (tools_bin / dest_name).exists():
                    self._log(f"{dest_name} already present — skipped.")
                    return
                self._log(f"Downloading {dest_name}...")
                try:
                    tmp = _tf2.NamedTemporaryFile(delete=False,
                        suffix=".zip" if zip_match else ".exe")
                    tmp.close()

                    _last_pct = [-1]
                    def _progress(block_num, block_size, total_size):
                        if total_size > 0:
                            pct = min(int(block_num * block_size * 100 / total_size), 100)
                            if pct != _last_pct[0] and pct % 5 == 0:
                                mb_done = block_num * block_size / 1024 / 1024
                                mb_total = total_size / 1024 / 1024
                                self._log(f"  {dest_name}: {pct}% ({mb_done:.1f} / {mb_total:.1f} MB)")
                                _last_pct[0] = pct
                        else:
                            mb_done = block_num * block_size / 1024 / 1024
                            if int(mb_done) != _last_pct[0]:
                                self._log(f"  {dest_name}: {mb_done:.1f} MB downloaded...")
                                _last_pct[0] = int(mb_done)

                    _urlreq.urlretrieve(url, tmp.name, reporthook=_progress)
                    self._log(f"  {dest_name}: download complete")
                    if zip_match:
                        with _zf.ZipFile(tmp.name) as z:
                            for member in z.namelist():
                                if member.lower().endswith(zip_match.lower()):
                                    data = z.read(member)
                                    (tools_bin / dest_name).write_bytes(data)
                                    self._log(f"Installed {dest_name} to {tools_bin}")
                                    break
                            else:
                                self._log(f"WARNING: {zip_match} not found in zip")
                    else:
                        import shutil as _sh2
                        _sh2.move(tmp.name, str(tools_bin / dest_name))
                        self._log(f"Installed {dest_name} to {tools_bin}")
                    try:
                        import os as _os3; _os3.unlink(tmp.name)
                    except Exception:
                        pass
                except Exception as e:
                    self._log(f"WARNING: Could not download {dest_name}: {e}")

            # ── Download FFmpeg if not present ───────────────────────────────
            if (tools_bin / "ffmpeg.exe").exists():
                self._log("ffmpeg.exe already present — skipped.")
            else:
                self._log("Fetching latest FFmpeg release URL...")
                try:
                    import json as _json
                    import urllib.request as _req2
                    # Get latest release from GitHub API
                    api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
                    with _req2.urlopen(api_url, timeout=15) as _r:
                        _rel = _json.loads(_r.read())
                    _ffmpeg_url = next(
                        (a["browser_download_url"] for a in _rel.get("assets", [])
                         if a["name"].endswith("full_build.zip")),
                        None
                    )
                    if not _ffmpeg_url:
                        raise ValueError("Could not find FFmpeg full_build.zip in release")
                    self._log(f"Downloading FFmpeg: {_ffmpeg_url.split('/')[-1]}")
                    # Download zip with progress
                    _tmp_ffmpeg = _tf2.NamedTemporaryFile(delete=False, suffix=".zip")
                    _tmp_ffmpeg.close()
                    _ffmpeg_last = [-1]
                    def _ffmpeg_progress(block_num, block_size, total_size):
                        if total_size > 0:
                            pct = min(int(block_num * block_size * 100 / total_size), 100)
                            if pct != _ffmpeg_last[0] and pct % 5 == 0:
                                mb_done = block_num * block_size / 1024 / 1024
                                mb_total = total_size / 1024 / 1024
                                self._log(f"  ffmpeg: {pct}% ({mb_done:.0f} / {mb_total:.0f} MB)")
                                _ffmpeg_last[0] = pct
                    _urlreq.urlretrieve(_ffmpeg_url, _tmp_ffmpeg.name, reporthook=_ffmpeg_progress)
                    self._log("  ffmpeg: download complete — extracting...")
                    # Extract ffmpeg.exe, ffprobe.exe from zip
                    with _zf.ZipFile(_tmp_ffmpeg.name) as _zff:
                        for _member in _zff.namelist():
                            _bn = _member.split("/")[-1].lower()
                            if _bn in ("ffmpeg.exe", "ffprobe.exe"):
                                _data = _zff.read(_member)
                                (tools_bin / _bn).write_bytes(_data)
                                self._log(f"  Installed {_bn} to {tools_bin}")
                    try:
                        import os as _os4; _os4.unlink(_tmp_ffmpeg.name)
                    except Exception:
                        pass
                except Exception as _fe:
                    self._log(f"WARNING: FFmpeg download failed: {_fe}")

            # ── Install Bento4 (mp4decrypt) via winget ───────────────────────
            if (tools_bin / "mp4decrypt.exe").exists():
                self._log("mp4decrypt.exe already present — skipped.")
            else:
                self._log("Installing Bento4 via winget...")
                try:
                    _b4_result = []
                    for _l in _run_cmd(
                        ["winget", "install", "--id", "AxiomaticSystems.Bento4",
                         "--silent", "--accept-package-agreements",
                         "--accept-source-agreements"],
                    ):
                        self._log(f"  {_l}")
                        _b4_result.append(_l)
                    # Copy mp4decrypt.exe to tools_bin - winget installs to LocalAppData
                    import glob as _glob, shutil as _sh3
                    _b4_search = [
                        str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/AxiomaticSystems*/**/mp4decrypt.exe"),
                        str(Path.home() / "AppData/Local/Programs/Bento4*/**/mp4decrypt.exe"),
                        "C:/Program Files/Bento4*/**/mp4decrypt.exe",
                    ]
                    _b4_paths = []
                    for _pat in _b4_search:
                        _b4_paths += _glob.glob(_pat, recursive=True)
                    if _b4_paths:
                        _sh3.copy2(_b4_paths[0], str(tools_bin / "mp4decrypt.exe"))
                        self._log(f"  Copied mp4decrypt.exe to {tools_bin}")
                    elif not (tools_bin / "mp4decrypt.exe").exists():
                        self._log("WARNING: mp4decrypt.exe not found after winget install")
                except Exception as _b4e:
                    self._log(f"WARNING: Bento4 winget install failed: {_b4e}")

            # ── MKVToolNix handled below with portable zip ────────────────────
            # (skipped here — done after other tools using portable zip)

            # ── N_m3u8DL-RE — always ensure this is present ──────────────────
            _download_to_bin(
                "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/"
                "v0.3.0-beta/N_m3u8DL-RE_v0.3.0-beta_win-x64_20241203.zip",
                "N_m3u8DL-RE.exe",
                "N_m3u8DL-RE.exe"
            )
            # dovi_tool — also after the abort point
            _download_to_bin(
                "https://github.com/quietvoid/dovi_tool/releases/download/"
                "2.3.1/dovi_tool-2.3.1-x86_64-pc-windows-msvc.zip",
                "dovi_tool.exe",
                "dovi_tool.exe"
            )
            # hdr10plus_tool — also after the abort point
            _download_to_bin(
                "https://github.com/quietvoid/hdr10plus_tool/releases/download/"
                "1.7.1/hdr10plus_tool-1.7.1-x86_64-pc-windows-msvc.zip",
                "hdr10plus_tool.exe",
                "hdr10plus_tool.exe"
            )
            # shaka-packager — required for DASH decryption (ITV, Disney+, etc.)
            # PS1 downloads this as a plain .exe (not a zip)
            _download_to_bin(
                "https://github.com/shaka-project/shaka-packager/releases/download/"
                "v2.6.1/packager-win-x64.exe",
                "shaka-packager.exe",
                None   # not a zip — direct .exe download
            )
            # ── Install MKVToolNix via winget (no admin, no download URL needed) ─
            mkv_dir = tools_bin
            if (tools_bin / "mkvmerge.exe").exists():
                self._log("mkvmerge.exe already present — skipped.")
            else:
                self._log("Installing MKVToolNix via winget...")
                try:
                    for _l in _run_cmd(
                        ["winget", "install", "--id", "MoritzBunkus.MKVToolNix",
                         "--silent", "--accept-package-agreements",
                         "--accept-source-agreements"],
                    ):
                        self._log(f"  {_l}")
                    # Copy key exes to tools_bin from default install location
                    import glob as _glob2, shutil as _sh4
                    _mkv_search = [
                        "C:/Program Files/MKVToolNix/mkvmerge.exe",
                        str(Path.home() / "AppData/Local/Programs/MKVToolNix/mkvmerge.exe"),
                        str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/MoritzBunkus*/**/mkvmerge.exe"),
                    ]
                    _mkv_installed = []
                    for _pat in _mkv_search:
                        _mkv_installed += _glob2.glob(_pat, recursive=True)
                    if _mkv_installed:
                        _mkv_install_dir = Path(_mkv_installed[0]).parent
                        _mkv_skip = {"uninst.exe", "uninstall.exe"}
                        for _mkv_exe in _mkv_install_dir.glob("*.exe"):
                            if _mkv_exe.name.lower() not in _mkv_skip:
                                _sh4.copy2(str(_mkv_exe), str(tools_bin / _mkv_exe.name))
                        self._log(f"  Copied MKVToolNix exes to {tools_bin}")
                    elif not (tools_bin / "mkvmerge.exe").exists():
                        self._log("WARNING: mkvmerge.exe not found after winget install")
                except Exception as _me3:
                    self._log(f"WARNING: MKVToolNix winget install failed: {_me3}")
            # SubtitleEdit — portable zip, goes to C:\Tools\SubtitleEdit
            se_dir = Path("C:/Tools/SubtitleEdit")
            se_exe = se_dir / "SubtitleEdit.exe"
            if se_exe.exists():
                self._log("SubtitleEdit already installed — skipped.")
            else:
                self._log("Downloading SubtitleEdit...")
                se_dir.mkdir(parents=True, exist_ok=True)
                import tempfile as _tf_se, zipfile as _zf_se
                se_tmp = _tf_se.NamedTemporaryFile(
                    delete=False, suffix=".zip", prefix="twinvine_se_"
                )
                se_tmp.close()
                try:
                    _urlreq.urlretrieve(
                        "https://github.com/SubtitleEdit/subtitleedit/releases/"
                        "download/4.0.14/SE4014.zip",
                        se_tmp.name
                    )
                    with _zf_se.ZipFile(se_tmp.name) as z:
                        z.extractall(str(se_dir))
                    # Create a launcher .cmd in C:\Tools\bin for PATH access
                    launcher_cmd = tools_bin / "SubtitleEdit.cmd"
                    launcher_cmd.write_text(
                        '@echo off\n"C:\\Tools\\SubtitleEdit\\SubtitleEdit.exe" %*\n'
                    )
                    if se_exe.exists():
                        self._log(f"SubtitleEdit installed to {se_dir}")
                    else:
                        self._log("WARNING: SubtitleEdit zip extracted but .exe not found")
                except Exception as e:
                    self._log(f"WARNING: Could not install SubtitleEdit: {e}")
                finally:
                    try:
                        import os as _os_se; _os_se.unlink(se_tmp.name)
                    except Exception:
                        pass

            # ── 2c. Add tool dirs to User PATH (no admin needed) ──────────────
            import tempfile as _tf3, os as _os4
            user_path_script = (
                "$toolDirs = @('C:\\Tools\\bin', 'C:\\Program Files\\MKVToolNix')\r\n"
                "$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')\r\n"
                "foreach ($dir in $toolDirs) {\r\n"
                "    if (-not $userPath.Contains($dir)) {\r\n"
                "        $userPath = $dir + ';' + $userPath\r\n"
                "    }\r\n"
                "}\r\n"
                "[Environment]::SetEnvironmentVariable('Path', $userPath, 'User')\r\n"
                "Write-Host 'Tool paths added to User PATH.'\r\n"
            )
            tmp_path = _tf3.NamedTemporaryFile(
                mode='w', suffix='.ps1', delete=False,
                encoding='utf-8', prefix='twinvine_up_'
            )
            tmp_path.write(user_path_script)
            tmp_path.close()
            for l in _run_cmd(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp_path.name],
                cwd=d
            ): self._log(l)
            try:
                _os4.unlink(tmp_path.name)
            except Exception:
                pass

            # Log what's now in C:\Tools\bin
            found = [p.name for p in tools_bin.glob("*.exe")] if tools_bin.exists() else []
            self._log(f"C:\\Tools\\bin contents: {found}")

            self._step("tools", "done")
            self.progress.emit(0.50, "Media tools installed.")

            # ── Step 3: uv ─────────────────────────────────────────────────
            self._step("uv", "active")
            self._log("── STEP 3: uv package manager")

            def find_uv() -> str | None:
                """Search all likely locations for uv.exe — never assumes PATH."""
                search_dirs = []

                # 1. Saved path from a previous install (most reliable)
                try:
                    saved = load_config().get("uv_exe", "")
                    if saved and Path(saved).exists():
                        return saved
                except Exception:
                    pass

                # 2. sys.executable and related dirs
                # When running under venv Python, sys.base_prefix points to the
                # real system Python — uv was pip-installed there, not in the venv.
                for prefix in {sys.prefix, sys.base_prefix,
                               str(Path(sys.executable).parent.parent)}:
                    search_dirs += [
                        Path(prefix) / "Scripts" / "uv.exe",
                        Path(prefix) / "uv.exe",
                    ]

                # 3. Common uv install locations
                appdata = os.environ.get("APPDATA", "")
                localappdata = os.environ.get("LOCALAPPDATA", "")
                home = Path(os.path.expanduser("~"))
                search_dirs += [
                    Path(appdata) / "uv" / "bin" / "uv.exe",
                    Path(localappdata) / "uv" / "bin" / "uv.exe",
                    home / ".cargo" / "bin" / "uv.exe",
                    home / ".local" / "bin" / "uv.exe",
                ]

                for c in search_dirs:
                    if c.exists():
                        return str(c)

                # 4. Every dir on the current PATH
                for p in os.environ.get("PATH", "").split(os.pathsep):
                    c = Path(p) / "uv.exe"
                    if c.exists():
                        return str(c)

                # 5. shutil.which (may miss non-PATH locations but worth trying)
                return shutil.which("uv")

            uv_exe = find_uv()
            if uv_exe:
                self._log(f"uv already available at: {uv_exe}")
            else:
                # Install uv using the SYSTEM Python (not the venv Python which
                # has no pip). Find the system Python next to uv's expected location.
                self._log("uv not found — installing...")
                # Try PowerShell installer (doesn't need pip at all)
                import tempfile as _tf_uv
                uv_ps = (
                    "irm https://github.com/astral-sh/uv/releases/latest/download/"
                    "uv-installer.ps1 | iex"
                )
                for l in _run_cmd(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-Command", uv_ps]
                ): self._log(l)

                uv_exe = find_uv()
                if not uv_exe:
                    # Last resort: pip on the system Python
                    # Walk up from sys.executable to find a Python with pip
                    for py_candidate in [
                        sys.executable,
                        str(Path(sys.base_prefix) / "python.exe"),
                        "python",
                    ]:
                        try:
                            import subprocess as _sp
                            result = _sp.run(
                                [py_candidate, "-m", "pip", "install", "uv"],
                                capture_output=True, text=True
                            )
                            self._log(result.stdout)
                            uv_exe = find_uv()
                            if uv_exe:
                                break
                        except Exception:
                            continue

            if not uv_exe:
                raise RuntimeError(
                    "uv could not be found or installed. "
                    "Please install manually: pip install uv"
                )
            # Make sure uv's directory is on PATH for subprocesses
            uv_dir = str(Path(uv_exe).parent)
            if uv_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = uv_dir + os.pathsep + os.environ.get("PATH", "")
            self._step("uv", "done")
            self.progress.emit(0.65, "uv ready.")

            # ── Step 4: uv lock + sync ─────────────────────────────────────
            self._step("sync", "active")
            self._log("── STEP 4: uv lock + uv sync")
            # Find the system Python (not venv python, not pythonw — uv needs
            # the real python.exe to pin the venv to the correct version,
            # preventing a version mismatch relaunch that causes terminal windows)
            import shutil as _sh2
            sys_python = None
            # Walk PATH to find a python.exe that isn't inside our venv
            for candidate in _sh2.which("python", mode=os.F_OK) and [_sh2.which("python")] or []:
                if candidate and ".venv" not in candidate and str(d) not in candidate:
                    try:
                        if Path(candidate).stat().st_size > 0:
                            sys_python = candidate
                            break
                    except Exception:
                        pass
            # Fallback: use sys.executable if it's not the venv python
            if not sys_python:
                if ".venv" not in sys.executable and str(d) not in sys.executable:
                    sys_python = sys.executable
            # Write a .python-version file so uv uses exactly the system Python.
            # This is the correct uv mechanism — it pins the venv to the exact
            # version string, preventing uv from downloading cpython-3.13.0
            # when 3.13.13 is installed, which would cause a mismatch relaunch
            # and a terminal window on every subsequent launch.
            # Patch pyproject.toml to accept the system Python version.
            # TwinVine requires <=3.13 but 3.13.13 > 3.13 in semver.
            # We widen it to <=3.99 so any current Python works without
            # uv downloading its own cached Python.
            # Also delete any stale .python-version file which causes uv
            # to ignore --python and pick its cached version instead.
            for stale in [d / ".python-version"]:
                try:
                    if stale.exists():
                        stale.unlink()
                        self._log(f"Removed stale: {stale.name}")
                except Exception:
                    pass

            # Patch requires-python in all workspace pyproject.toml files
            # Backs up original before patching
            import re as _re
            for toml_path in list(d.rglob("pyproject.toml")):
                try:
                    text = toml_path.read_text(encoding="utf-8")
                    # Match any upper bound <=3.x that might block newer Python
                    import re as _re_toml
                    _patched = _re_toml.sub(
                        r'(requires-python\s*=\s*">=3\.\d+,\s*<=3\.)(\d+)(")',
                        r'\g<1>99\3',
                        text
                    )
                    if _patched != text:
                        bak = toml_path.with_suffix(".toml.bak")
                        if not bak.exists():
                            bak.write_text(text, encoding="utf-8")
                        toml_path.write_text(_patched, encoding="utf-8")
                        self._log(f"Patched requires-python in {toml_path.name} (backup: {bak.name})")
                except Exception as e:
                    self._log(f"Note: could not patch {toml_path}: {e}")

            # Skip pyproject.toml patch if venv is already functional
            _venv_python = d / ".venv" / "Scripts" / "python.exe"
            _venv_working = False
            if _venv_python.exists():
                try:
                    import subprocess as _sp_check
                    _r = _sp_check.run(
                        [str(_venv_python), "-c", "import vinefeeder; import envied"],
                        capture_output=True, timeout=15,
                        creationflags=_sp_check.CREATE_NO_WINDOW
                    )
                    _venv_working = (_r.returncode == 0)
                except Exception:
                    pass

            if _venv_working:
                self._log("Existing venv is functional — skipping pyproject.toml patch.")
            else:
                # Patch requires-python only if venv isn't working yet
                import re as _re2
                for toml_path in list(d.rglob("pyproject.toml")):
                    try:
                        text = toml_path.read_text(encoding="utf-8")
                        import re as _re_toml2
                        _patched2 = _re_toml2.sub(
                            r'(requires-python\s*=\s*">=3\.\d+,\s*<=3\.)(\d+)(")',
                            r'\g<1>99\3',
                            text
                        )
                        if _patched2 != text:
                            bak = toml_path.with_suffix(".toml.bak")
                            if not bak.exists():
                                bak.write_text(text, encoding="utf-8")
                            toml_path.write_text(_patched2, encoding="utf-8")
                            self._log(f"Patched requires-python in {toml_path.name}")
                    except Exception as e:
                        self._log(f"Note: could not patch {toml_path}: {e}")

            # Use system python.exe directly so uv doesn't download its own
            sys_py = sys.executable
            if ".venv" in sys_py or str(d) in sys_py:
                import shutil as _sh3
                sys_py = _sh3.which("python") or sys.executable
            self._log(f"uv will use: {sys_py}")

            # ── Delete uv.lock from cloned repo before patching
            # The cloned repo ships with uv.lock pinning brotli==1.1.0
            # We must delete it so uv re-resolves after we patch pyproject.toml
            for _lock in [d / "uv.lock"]:
                if _lock.exists():
                    try:
                        _lock.unlink()
                        self._log("Deleted repo uv.lock for fresh resolution")
                    except Exception as _le:
                        self._log(f"Note: could not delete uv.lock: {_le}")
            # ── Patch utilities.py FPS class for Python 3.14 compatibility ──────
            # ast.Num was removed in Python 3.14 — add visit_Constant as replacement
            _utils_path = d / "packages/envied/src/envied/core/utilities.py"
            if _utils_path.exists():
                try:
                    _utils_txt = _utils_path.read_text(encoding="utf-8")
                    if "def visit_Num" in _utils_txt and "def visit_Constant" not in _utils_txt:
                        _utils_bak = _utils_path.with_name("utilities.py.bak")
                        if not _utils_bak.exists():
                            _utils_bak.write_text(_utils_txt, encoding="utf-8")
                        _old_method = "    def visit_Num(self, node: ast.Num) -> complex:\n        return node.n"
                        _new_method = _old_method + "\n\n    def visit_Constant(self, node: ast.Constant) -> complex:\n        return node.value"
                        _utils_txt = _utils_txt.replace(_old_method, _new_method)
                        _utils_path.write_text(_utils_txt, encoding="utf-8")
                        self._log("Patched utilities.py: added visit_Constant for Python 3.14")
                except Exception as _ue:
                    self._log(f"Note: could not patch utilities.py: {_ue}")

            # ── Pre-patch: replace brotli with brotlicffi in pyproject.toml files
            # ── Pre-patch: replace brotli with brotlicffi in pyproject.toml files
            # brotli requires C++ Build Tools on Python 3.14+ — brotlicffi is pure Python
            _brotli_patched = False
            for _toml in list(d.rglob("pyproject.toml")):
                try:
                    _txt = _toml.read_text(encoding="utf-8")
                    # Replace all brotli dependency entries (with or without version specifier)
                    _new_txt = _txt
                    for _old, _new in [
                        ('"brotli"', '"brotlicffi"'),
                        ("'brotli'", "'brotlicffi'"),
                        ('"brotli>=', '"brotlicffi>='),
                        ('"brotli==', '"brotlicffi=='),
                        ('"brotli<', '"brotlicffi<'),
                        ("'brotli>=", "'brotlicffi>="),
                        ("'brotli==", "'brotlicffi=="),
                    ]:
                        _new_txt = _new_txt.replace(_old, _new)
                    if _new_txt != _txt:
                        _bak = _toml.with_name(_toml.stem + "_brotli.toml.bak")
                        if not _bak.exists():
                            _bak.write_text(_txt, encoding="utf-8")
                        _toml.write_text(_new_txt, encoding="utf-8")
                        self._log(f"Patched brotli to brotlicffi in {_toml.name}")
                        _brotli_patched = True
                except Exception as _be:
                    self._log(f"Note: could not patch brotli in {_toml}: {_be}")

            # uv.lock already deleted above before patching


            for l in _run_cmd([uv_exe, "lock"], cwd=d): self._log(l)
            for l in _run_cmd([uv_exe, "sync", "--python", sys_py], cwd=d):
                self._log(l)


            self._step("sync", "done")
            self.progress.emit(0.85, "Packages synced.")

            # ── Step 5: YAML config ────────────────────────────────────────
            self._step("yaml", "active")
            src = d / "packages/envied/src/envied/envied-working-example.yaml"
            dst = d / "packages/envied/src/envied/envied.yaml"
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                self._log("Copied envied example YAML.")
            else:
                self._log("envied.yaml already present — skipped.")

            # ── Patch vaults path to absolute so it works from any cwd ────────
            vaults_abs = d / "packages/envied/src/envied/vaults"
            if dst.exists():
                try:
                    yaml_text = dst.read_text(encoding="utf-8")
                    # Simple string replace — no regex to avoid \1 control char issue
                    vaults_posix = vaults_abs.as_posix() + "/"
                    if "  vaults: vaults/" in yaml_text:
                        # Back up original before patching
                        bak_yaml = dst.with_suffix(".yaml.bak")
                        if not bak_yaml.exists():
                            bak_yaml.write_text(yaml_text, encoding="utf-8")
                        yaml_text = yaml_text.replace(
                            "  vaults: vaults/",
                            f"  vaults: {vaults_posix}",
                            1
                        )
                        dst.write_text(yaml_text, encoding="utf-8")
                        self._log(f"Patched vaults path to: {vaults_posix} (backup: {bak_yaml.name})")
                    else:
                        self._log("vaults path already patched — skipped.")
                except Exception as _e:
                    self._log(f"Warning: could not patch vaults path: {_e}")

            self._step("yaml", "done")
            self._step("done", "done")
            self.progress.emit(1.0, "Done ✓")
            # Persist uv path so _qt_runsubprocess can find it on restart
            self.uv_exe_path = uv_exe
            self.finished.emit(True, "")

        except Exception as exc:
            import traceback
            self._log(f"INSTALL ERROR: {exc}")
            self._log(traceback.format_exc())
            self.finished.emit(False, str(exc))


# ── Main Window ───────────────────────────────────────────────────────────────

class TwinVineLauncher(QMainWindow):

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.install_dir = Path(self.cfg["install_dir"])
        self._service_worker: ServiceWorker | None = None
        self._install_worker: InstallWorker | None = None

        # Register our log callback
        global _log_fn
        _log_fn = self._append_log

        # Download panel signals — defined here so QApplication exists first
        from PyQt6.QtCore import QObject as _QObject, pyqtSignal as _pyqtSignal
        class _DlSignals(_QObject):
            line     = _pyqtSignal(str)
            progress = _pyqtSignal(int)
            episode  = _pyqtSignal(str)
            done     = _pyqtSignal(bool)
        self._dl_signals = _DlSignals()
        self._dl_signals.line.connect(self._dl_append_line)
        self._dl_signals.progress.connect(self._dl_update_progress)
        self._dl_signals.episode.connect(self._dl_update_episode)
        self._dl_signals.done.connect(self._dl_finished)

        # Set module-level reference for download panel signals
        global _main_window
        _main_window = self

        # Initialise the thread-safe dialog bridge (must be on main thread)
        _init_bridge()

        self.setWindowTitle(APP_NAME)
        # Set window icon (title bar + taskbar)
        import sys as _sys
        from PyQt6.QtGui import QIcon
        from pathlib import Path as _Path
        if getattr(_sys, 'frozen', False):
            # PyInstaller bundles assets into sys._MEIPASS temp folder
            _base = _Path(getattr(_sys, '_MEIPASS', str(_Path(_sys.executable).parent)))
            _icon_path = _base / "assets" / "icon.ico"
            # Fallback: next to the exe (for portable/extracted builds)
            if not _icon_path.exists():
                _icon_path = _Path(_sys.executable).parent / "assets" / "icon.ico"
        else:
            # Running as script — look next to the script
            _icon_path = _Path(__file__).parent / "assets" / "icon.ico"
        if _icon_path.exists():
            self.setWindowIcon(QIcon(str(_icon_path)))
        self.resize(1100, 820)
        self._apply_palette()
        self._build_ui()

        # Try to load VineFeeder now if already installed
        if self._is_installed():
            self._load_vinefeeder()

    def _apply_palette(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {C['bg']};
                color: {C['text']};
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }}
            QPushButton {{
                background: {C['overlay']};
                color: {C['text']};
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C['green']}; color: {C['bg']}; }}
            QPushButton:disabled {{ background: {C['surface']}; color: {C['border']}; }}
            QLineEdit {{
                background: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 3px;
                padding: 5px;
            }}
            QLineEdit:focus {{ border-color: {C['green']}; }}
            QScrollBar:vertical {{
                background: {C['surface']}; width: 10px; border: none;
            }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 4px; }}
            QLabel {{ color: {C['text']}; }}
            QCheckBox {{ color: {C['text']}; spacing: 6px; }}
            QSlider::groove:horizontal {{
                border: 1px solid {C['border']}; height: 5px;
                background: {C['overlay']}; margin: 2px 0;
            }}
            QSlider::handle:horizontal {{
                background: {C['green']}; border: none;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 3px;
            }}
            QProgressBar {{
                background: {C['surface']}; border: 1px solid {C['border']};
                border-radius: 4px; text-align: center; color: {C['text']};
            }}
            QProgressBar::chunk {{ background: {C['green']}; border-radius: 3px; }}
            QFrame[frameShape="4"], QFrame[frameShape="5"] {{
                color: {C['border']};
            }}
        """)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background:{C['surface']};border-right:1px solid {C['border']};")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        # Logo
        logo = QLabel("TwinVine")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(f"""
            font-size:16px;font-weight:bold;color:{C['green']};
            padding:20px 0 4px 0;
        """)
        sb_layout.addWidget(logo)
        ver = QLabel(f"Launcher v{APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"font-size:9px;color:{C['border']};padding-bottom:12px;")
        sb_layout.addWidget(ver)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        sb_layout.addWidget(line)

        # Nav buttons
        self._nav_btns = {}
        for key, label in [
                ("download",        "Home"),
                ("downloads_folder","My Downloads"),
                ("install",         "Install / Update"),
                ("hellyes",         "HellYes"),
                ("log",             "Log"),
                ("help",            "Help"),
                ("about",           "About"),
            ]:
            b = QPushButton(f"  {label}")
            b.setStyleSheet(f"""
                QPushButton {{
                    background:transparent; color:{C['subtext']};
                    border:none; padding:10px 16px; text-align:left;
                    font-size:12px; border-radius:0;
                }}
                QPushButton:hover {{background:{C['overlay']};color:{C['text']};}}
            """)
            b.clicked.connect(lambda _, k=key: self._show_page(k))
            sb_layout.addWidget(b)
            self._nav_btns[key] = b

        sb_layout.addStretch()

        # ── Batch Mode in sidebar — all on one row ────────────────────────────
        line_b = QFrame(); line_b.setFrameShape(QFrame.Shape.HLine)
        sb_layout.addWidget(line_b)

        batch_sb = QFrame()
        batch_sb.setStyleSheet(f"background:{C['surface']};border:none;")
        batch_sb_layout = QVBoxLayout(batch_sb)
        batch_sb_layout.setContentsMargins(10, 8, 9, 8)
        batch_sb_layout.setSpacing(4)

        # Single row: Batch Mode | slider | Run Batch
        batch_row = QHBoxLayout()
        batch_row.setSpacing(6)
        self._batch_label = QLabel("Batch Mode")
        self._batch_label.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        batch_row.addWidget(self._batch_label)
        self._batch_slider = QSlider(Qt.Orientation.Horizontal)
        self._batch_slider.setRange(0, 1)
        self._batch_slider.setFixedWidth(44)
        self._batch_slider.valueChanged.connect(self._toggle_batch)
        batch_row.addWidget(self._batch_slider)
        self._run_batch_btn = QPushButton("Run Batch")
        self._run_batch_btn.setEnabled(False)
        self._run_batch_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};border:none;"
            f"padding:3px 8px;font-size:10px;border-radius:3px;")
        self._run_batch_btn.clicked.connect(self._run_batch)
        batch_row.addWidget(self._run_batch_btn)
        batch_sb_layout.addLayout(batch_row)

        # Batch file indicator below
        self._batch_file_lbl = QLabel("")
        self._batch_file_lbl.setStyleSheet(
            f"color:{C['green']};border:none;font-size:9px;")
        batch_sb_layout.addWidget(self._batch_file_lbl)

        batch_container = QHBoxLayout()
        batch_container.setContentsMargins(0, 0, 0, 0)
        batch_container.setSpacing(0)
        batch_container.addWidget(batch_sb)
        vline = QFrame()
        vline.setFixedWidth(1)
        vline.setStyleSheet(f"background:{C['border']};border:none;")
        batch_container.addWidget(vline)
        sb_layout.addLayout(batch_container)

        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine)
        sb_layout.addWidget(line2)
        self._status_badge = QLabel("● Not installed")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setStyleSheet(f"color:{C['red']};font-size:9px;padding:8px;")
        sb_layout.addWidget(self._status_badge)

        root.addWidget(sidebar)

        # ── Right: stacked pages ──
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._pages = {
            "download": self._build_download_page(),
            "install":  self._build_install_page(),
            "log":      self._build_log_page(),
            "help":     self._build_help_page(),
            "about":    self._build_about_page(),
            # hellyes is built lazily on first visit (needs venv imports)
        }
        for page in self._pages.values():
            self._stack.addWidget(page)

        self._show_page("download")
        self._refresh_status()

    def _show_page(self, key: str):
        if key == "downloads_folder":
            self._open_downloads_folder()
            return
        if key == "hellyes":
            # Build hellyes page on first visit
            if "hellyes" not in self._pages:
                self._pages["hellyes"] = self._build_hellyes_page()
                self._stack.addWidget(self._pages["hellyes"])
        if key not in self._pages:
            return
        self._stack.setCurrentWidget(self._pages[key])
        for k, b in self._nav_btns.items():
            active = (k == key)
            b.setStyleSheet(f"""
                QPushButton {{
                    background:{''+C['overlay'] if active else 'transparent'};
                    color:{C['text'] if active else C['subtext']};
                    border:none; padding:10px 16px; text-align:left;
                    font-size:12px; border-radius:0;
                    {'border-left:3px solid '+C['green']+';' if active else ''}
                }}
                QPushButton:hover {{background:{C['overlay']};color:{C['text']};}}
            """)
    # ── Download page ─────────────────────────────────────────────────────────

    def _build_download_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Header row: "Download" title + HellYes + Envied Config right-aligned ──
        hdr_row = QHBoxLayout()
        hdr = QLabel("Download")
        hdr.setStyleSheet(f"font-size:20px;font-weight:bold;color:{C['green']};")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()

        btn_style = (f"QPushButton{{background:{C['surface']};color:{C['pink']};"
                     f"border:1px solid {C['border']};padding:4px 10px;"
                     f"border-radius:3px;font-size:11px;}}"
                     f"QPushButton:hover{{background:{C['green']};color:{C['bg']};}}")
        self._ec_btn = QPushButton("Envied Config")
        self._ec_btn.setStyleSheet(btn_style)
        self._ec_btn.clicked.connect(self._open_envied_config)
        hdr_row.addWidget(self._ec_btn)

        layout.addLayout(hdr_row)

        sub = QLabel("Search for a show, paste a URL, or browse by category.")
        sub.setStyleSheet(f"color:{C['subtext']};padding-bottom:8px;")
        layout.addWidget(sub)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # ── Status banner + HLG toggle ──
        status_row = QHBoxLayout()
        self._dl_status = QLabel("TwinVine not loaded — go to Install tab")
        self._dl_status.setStyleSheet(
            f"color:{C['red']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")
        status_row.addWidget(self._dl_status, stretch=1)

        self._hlg_cb = QCheckBox("HLG")
        self._hlg_cb.setChecked(True)
        self._hlg_cb.setToolTip(
            "HLG (High Dynamic Range) — enabled by default.\n\n"
            "⚠  If your download fails with:\n"
            "    'Selection unavailable in UHD'\n"
            "    or a resolution/quality error,\n\n"
            "→  UNTICK this box before retrying.\n\n"
            "Not all content or services support HLG/HDR streams.\n"
            "Unticking forces SDR (standard definition range), which\n"
            "works on every service."
        )
        self._hlg_cb.setStyleSheet(
            "QCheckBox{color:#f9e2af;font-size:11px;font-weight:bold;padding:0 8px;}"
            "QCheckBox::indicator:unchecked{border:1px solid #a6adc8;}")
        status_row.addWidget(self._hlg_cb)
        layout.addLayout(status_row)

        # ── Search box ──
        search_lbl = QLabel("URL or Search")
        search_lbl.setStyleSheet(f"color:{C['subtext']};margin-top:8px;")
        layout.addWidget(search_lbl)
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText(
            "Enter keyword(s) to search, or paste a direct video URL")
        layout.addWidget(self._search_entry)

        # ── Service buttons ──
        svc_lbl = QLabel("Services")
        svc_lbl.setStyleSheet(f"color:{C['subtext']};margin-top:8px;font-size:10px;")
        layout.addWidget(svc_lbl)

        self._svc_frame = QFrame()
        self._svc_frame.setStyleSheet(
            f"border:1px solid {C['border']};border-radius:4px;"
            f"background:{C['surface']};")
        self._svc_layout = QVBoxLayout(self._svc_frame)
        self._svc_layout.setContentsMargins(8, 8, 8, 8)

        self._svc_placeholder = QLabel(
            "Service buttons will appear here once TwinVine is installed.\n"
            "Go to the Install tab to set up TwinVine.")
        self._svc_placeholder.setStyleSheet(
            f"color:{C['border']};padding:16px;border:none;")
        self._svc_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._svc_layout.addWidget(self._svc_placeholder)

        # Scroll area for service buttons
        svc_scroll = QScrollArea()
        svc_scroll.setWidget(self._svc_frame)
        svc_scroll.setWidgetResizable(True)
        svc_scroll.setMaximumHeight(220)
        svc_scroll.setStyleSheet("border:none;")
        layout.addWidget(svc_scroll)

        # ── Inline selection panel (hidden until needed) ────────────────────
        self._sel_panel = QFrame()
        self._sel_panel.setStyleSheet(
            f"background:{C['surface']};border:1px solid {C['green']};"
            f"border-radius:6px;")
        sel_layout = QVBoxLayout(self._sel_panel)
        sel_layout.setContentsMargins(12, 10, 12, 10)
        sel_layout.setSpacing(6)

        # Title
        self._sel_title = QLabel("Select")
        self._sel_title.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        sel_layout.addWidget(self._sel_title)

        # Series range input (shown only for series selection)
        self._sel_range_widget = QWidget()
        range_layout = QHBoxLayout(self._sel_range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_lbl = QLabel("Series (e.g. 1, 2..4, 0=all):")
        range_lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        range_layout.addWidget(range_lbl)
        self._sel_range_input = QLineEdit()
        self._sel_range_input.setPlaceholderText("0 for all, or 1, 2..4")
        self._sel_range_input.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};padding:4px;")
        range_layout.addWidget(self._sel_range_input)
        self._sel_range_widget.setVisible(False)
        sel_layout.addWidget(self._sel_range_widget)

        # Scrollable list
        self._sel_scroll = QScrollArea()
        self._sel_scroll.setWidgetResizable(True)
        self._sel_scroll.setMaximumHeight(280)
        self._sel_scroll.setStyleSheet(
            f"background:{C['bg']};border:1px solid {C['border']};")
        self._sel_list_widget = QWidget()
        self._sel_list_layout = QVBoxLayout(self._sel_list_widget)
        self._sel_list_layout.setContentsMargins(6, 6, 6, 6)
        self._sel_list_layout.setSpacing(2)
        self._sel_scroll.setWidget(self._sel_list_widget)
        sel_layout.addWidget(self._sel_scroll)

        # Confirm/Cancel buttons
        sel_btn_row = QHBoxLayout()
        self._sel_confirm_btn = QPushButton("✓  Confirm")
        self._sel_confirm_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};font-weight:bold;"
            f"border:none;padding:6px 18px;border-radius:3px;")
        sel_btn_row.addWidget(self._sel_confirm_btn)
        self._sel_cancel_btn = QPushButton("✕  Cancel")
        self._sel_cancel_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 18px;border-radius:3px;")
        sel_btn_row.addWidget(self._sel_cancel_btn)
        sel_btn_row.addStretch()
        # Select All/None — right side, shown only during multi-select
        sa_style = (f"background:{C['overlay']};color:{C['subtext']};"
                    f"border:none;padding:6px 14px;font-size:11px;border-radius:3px;")
        self._sel_all_btn = QPushButton("Select All")
        self._sel_all_btn.setStyleSheet(sa_style)
        self._sel_all_btn.setVisible(False)
        sel_btn_row.addWidget(self._sel_all_btn)
        self._sel_none_btn = QPushButton("Select None")
        self._sel_none_btn.setStyleSheet(sa_style)
        self._sel_none_btn.setVisible(False)
        sel_btn_row.addWidget(self._sel_none_btn)
        sel_layout.addLayout(sel_btn_row)

        self._sel_panel.setVisible(False)
        layout.addWidget(self._sel_panel)

        # ── Download Options panel ────────────────────────────────────────────
        self._opts_panel = QFrame()
        self._opts_panel.setObjectName('optsPanel')
        self._opts_panel.setStyleSheet(
            f"QFrame#optsPanel{{background:{C['surface']};border:1px solid {C['green']};"
            f"border-radius:6px;}}")
        opts_layout = QVBoxLayout(self._opts_panel)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        opts_layout.setSpacing(8)

        opts_title = QLabel("Download Options")
        opts_title.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        opts_layout.addWidget(opts_title)
        opts_hint = QLabel(
            "Best available, 2160p, 1080p and 720p work reliably on all modern streaming services. "
            "For older content or non-standard resolutions use Best available, or use "
            "Download by URL to see exactly what tracks are available first."
        )
        opts_hint.setWordWrap(True)
        opts_hint.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        opts_layout.addWidget(opts_hint)
        opts_hint = QLabel(
            "Defaults work for most downloads."
        )
        opts_hint.setWordWrap(True)
        opts_hint.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        opts_layout.addWidget(opts_hint)

        opts_grid = QHBoxLayout()
        opts_grid.setSpacing(16)

        # Quality
        q_col = QVBoxLayout()
        q_col.setSpacing(3)
        q_lbl = QLabel("Quality")
        q_lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        q_col.addWidget(q_lbl)
        self._opts_quality = QComboBox()
        self._opts_quality.addItems(["Best available", "2160p", "1080p", "720p"])
        self._opts_quality.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};"
            f"padding:3px 6px;border-radius:3px;")
        q_col.addWidget(self._opts_quality)
        opts_grid.addLayout(q_col)



        opts_grid.addStretch()
        opts_layout.addLayout(opts_grid)

        # Checkboxes row
        chk_row = QHBoxLayout()
        chk_row.setSpacing(20)
        chk_style = (
            "QCheckBox{color:#cdd6f4;font-size:12px;font-weight:bold;}"
            "QCheckBox::indicator:unchecked{border:1px solid #a6adc8;}"
        )
        self._opts_no_subs = QCheckBox("No subtitles")
        self._opts_no_subs.setStyleSheet(chk_style)
        self._opts_no_subs.setToolTip("Disable subtitle download entirely.")
        chk_row.addWidget(self._opts_no_subs)
        self._opts_slow = QCheckBox("Slow mode")
        self._opts_slow.setStyleSheet(chk_style)
        chk_row.addWidget(self._opts_slow)
        # Min/max delay fields — enabled only when slow mode is ticked
        _slow_lbl = QLabel("delay:")
        _slow_lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        chk_row.addWidget(_slow_lbl)
        self._opts_slow_min = QLineEdit("10")
        self._opts_slow_min.setFixedWidth(36)
        self._opts_slow_min.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opts_slow_min.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};"
            f"border-radius:3px;padding:2px 4px;font-size:11px;")
        chk_row.addWidget(self._opts_slow_min)
        _slow_to = QLabel("–")
        _slow_to.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        chk_row.addWidget(_slow_to)
        self._opts_slow_max = QLineEdit("60")
        self._opts_slow_max.setFixedWidth(36)
        self._opts_slow_max.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opts_slow_max.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};"
            f"border-radius:3px;padding:2px 4px;font-size:11px;")
        chk_row.addWidget(self._opts_slow_max)
        _slow_sec = QLabel("secs")
        _slow_sec.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        chk_row.addWidget(_slow_sec)
        # Dim the fields when slow mode is off
        for _w in [_slow_lbl, self._opts_slow_min, _slow_to,
                   self._opts_slow_max, _slow_sec]:
            _w.setEnabled(False)
        self._opts_slow.toggled.connect(
            lambda on: [_w.setEnabled(on) for _w in [
                _slow_lbl, self._opts_slow_min, _slow_to,
                self._opts_slow_max, _slow_sec]])
        chk_row.addStretch()
        opts_layout.addLayout(chk_row)

        # Buttons row
        opts_btn_row = QHBoxLayout()
        self._opts_download_btn = QPushButton("✓  Download")
        self._opts_download_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};font-weight:bold;"
            f"border:none;padding:6px 18px;border-radius:3px;")
        opts_btn_row.addWidget(self._opts_download_btn)
        self._opts_cancel_btn = QPushButton("✕  Cancel")
        self._opts_cancel_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 18px;border-radius:3px;")
        self._opts_cancel_btn.clicked.connect(self._opts_cancel)
        opts_btn_row.addWidget(self._opts_cancel_btn)
        opts_btn_row.addStretch()
        opts_layout.addLayout(opts_btn_row)

        self._opts_panel.setVisible(False)
        layout.addWidget(self._opts_panel)

        # ── URL Download panel ────────────────────────────────────────────────
        self._url_panel = QFrame()
        self._url_panel.setObjectName('urlPanel')
        self._url_panel.setStyleSheet(
            f"QFrame#urlPanel{{background:{C['surface']};border:1px solid {C['green']};"
            f"border-radius:6px;}}")
        url_layout = QVBoxLayout(self._url_panel)
        url_layout.setContentsMargins(12, 10, 12, 10)
        url_layout.setSpacing(8)

        url_title = QLabel("Download by URL")
        url_title.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        url_layout.addWidget(url_title)

        self._url_display = QLabel("")
        self._url_display.setWordWrap(True)
        self._url_display.setStyleSheet(
            f"color:{C['subtext']};font-size:11px;border:none;")
        url_layout.addWidget(self._url_display)

        # Track results area — hidden until Fetch Tracks runs
        self._url_tracks_widget = QWidget()
        url_tracks_layout = QVBoxLayout(self._url_tracks_widget)
        url_tracks_layout.setContentsMargins(0, 0, 0, 0)
        url_tracks_layout.setSpacing(4)

        url_q_row = QHBoxLayout()
        url_q_lbl = QLabel("Quality:")
        url_q_lbl.setFixedWidth(80)
        url_q_lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        url_q_row.addWidget(url_q_lbl)
        self._url_quality = QComboBox()
        self._url_quality.addItems(["Best available"])
        self._url_quality.setStyleSheet(
            "QComboBox{background:#181825;color:#cdd6f4;"
            "border:1px solid #45475a;padding:3px 6px;border-radius:3px;}"
            "QComboBox::drop-down{width:18px;}"
            "QComboBox QAbstractItemView{background:#181825;color:#cdd6f4;"
            "selection-background-color:#a6e3a1;selection-color:#1e1e2e;}")
        url_q_row.addWidget(self._url_quality)
        url_q_row.addStretch()
        url_tracks_layout.addLayout(url_q_row)


        self._url_tracks_widget.setVisible(False)
        url_layout.addWidget(self._url_tracks_widget)

        self._url_fetch_status = QLabel(
            "Click ‘Fetch Tracks’ to see what’s available, "
            "or ‘Download’ to start immediately with best quality."
        )
        self._url_fetch_status.setWordWrap(True)
        self._url_fetch_status.setStyleSheet(
            f"color:{C['subtext']};font-size:11px;border:none;font-style:italic;")
        url_layout.addWidget(self._url_fetch_status)

        # Buttons
        url_btn_row = QHBoxLayout()
        self._url_download_btn = QPushButton("✓  Download")
        self._url_download_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};font-weight:bold;"
            f"border:none;padding:6px 18px;border-radius:3px;")
        url_btn_row.addWidget(self._url_download_btn)
        self._url_cancel_btn = QPushButton("✕  Cancel")
        self._url_cancel_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 18px;border-radius:3px;")
        url_btn_row.addWidget(self._url_cancel_btn)
        url_btn_row.addStretch()
        self._url_fetch_btn = QPushButton("🔍  Fetch Tracks")
        self._url_fetch_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 14px;font-size:11px;border-radius:3px;")
        url_btn_row.addWidget(self._url_fetch_btn)
        url_layout.addLayout(url_btn_row)

        # No subtitles + Slow mode — always visible
        url_chk_style = (
            "QCheckBox{color:#cdd6f4;font-size:12px;font-weight:bold;}"
            "QCheckBox::indicator:unchecked{border:1px solid #a6adc8;}"
        )
        url_chk_row = QHBoxLayout()
        url_chk_row.setSpacing(20)
        self._url_no_subs = QCheckBox("No subtitles")
        self._url_no_subs.setStyleSheet(url_chk_style)
        self._url_no_subs.setToolTip("Skip subtitle download.")
        url_chk_row.addWidget(self._url_no_subs)
        self._url_slow = QCheckBox("Slow mode")
        self._url_slow.setStyleSheet(url_chk_style)
        url_chk_row.addWidget(self._url_slow)
        _url_slow_lbl = QLabel("delay:")
        _url_slow_lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        url_chk_row.addWidget(_url_slow_lbl)
        self._url_slow_min = QLineEdit("10")
        self._url_slow_min.setFixedWidth(36)
        self._url_slow_min.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_slow_min.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};"
            f"border-radius:3px;padding:2px 4px;font-size:11px;")
        url_chk_row.addWidget(self._url_slow_min)
        _url_slow_to = QLabel("–")
        _url_slow_to.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        url_chk_row.addWidget(_url_slow_to)
        self._url_slow_max = QLineEdit("60")
        self._url_slow_max.setFixedWidth(36)
        self._url_slow_max.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_slow_max.setStyleSheet(
            f"background:{C['bg']};color:{C['text']};border:1px solid {C['border']};"
            f"border-radius:3px;padding:2px 4px;font-size:11px;")
        url_chk_row.addWidget(self._url_slow_max)
        _url_slow_sec = QLabel("secs")
        _url_slow_sec.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        url_chk_row.addWidget(_url_slow_sec)
        for _w in [_url_slow_lbl, self._url_slow_min, _url_slow_to,
                   self._url_slow_max, _url_slow_sec]:
            _w.setEnabled(False)
        self._url_slow.toggled.connect(
            lambda on: [_w.setEnabled(on) for _w in [
                _url_slow_lbl, self._url_slow_min, _url_slow_to,
                self._url_slow_max, _url_slow_sec]])
        url_chk_row.addStretch()
        url_layout.addLayout(url_chk_row)

        self._url_panel.setVisible(False)
        layout.addWidget(self._url_panel)

        # ── Action chooser (inline) ───────────────────────────────────────────
        self._action_widget = QWidget()
        self._action_widget.setVisible(False)
        action_outer = QVBoxLayout(self._action_widget)
        action_outer.setContentsMargins(0, 8, 0, 0)
        action_outer.setSpacing(6)
        action_lbl = QLabel("Choose action")
        action_lbl.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        action_outer.addWidget(action_lbl)
        action_btn_style = (
            f"QPushButton{{background:{C['surface']};color:{C['text']};"
            f"border:1px solid {C['border']};border-radius:4px;"
            f"padding:10px 16px;text-align:left;font-size:12px;}}"
            f"QPushButton:hover{{background:{C['overlay']};color:{C['text']};}}"
        )
        self._action_btns = {}
        for _lbl in ["Search by keyword(s)", "Greedy Search by URL",
                     "Download by URL", "Browse by Category"]:
            _btn = QPushButton(_lbl)
            _btn.setStyleSheet(action_btn_style)
            action_outer.addWidget(_btn)
            self._action_btns[_lbl] = _btn
        _action_close_btn = QPushButton("✕  Close")
        _action_close_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C['subtext']};"
            f"border:none;padding:4px 0px;text-align:left;font-size:11px;}}"
            f"QPushButton:hover{{color:{C['text']};}}"
        )
        _action_close_btn.clicked.connect(
            lambda: self._action_widget.setVisible(False))
        action_outer.addWidget(_action_close_btn)
        layout.addWidget(self._action_widget)

        # Text input row — shown after Search/Greedy/Download action selected
        self._action_input_widget = QWidget()
        self._action_input_widget.setVisible(False)
        ai_layout = QHBoxLayout(self._action_input_widget)
        ai_layout.setContentsMargins(0, 4, 0, 0)
        ai_layout.setSpacing(8)
        self._action_input_lbl = QLabel("Enter text:")
        self._action_input_lbl.setStyleSheet(
            f"color:{C['subtext']};font-size:11px;border:none;")
        ai_layout.addWidget(self._action_input_lbl)
        self._action_input = QLineEdit()
        self._action_input.setStyleSheet(
            f"background:{C['surface']};color:{C['text']};"
            f"border:1px solid {C['border']};border-radius:3px;padding:6px;")
        ai_layout.addWidget(self._action_input, stretch=1)
        self._action_go_btn = QPushButton("Go")
        self._action_go_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};font-weight:bold;"
            f"border:none;padding:6px 16px;border-radius:3px;")
        ai_layout.addWidget(self._action_go_btn)
        self._action_cancel_btn = QPushButton("Cancel")
        self._action_cancel_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 12px;border-radius:3px;")
        ai_layout.addWidget(self._action_cancel_btn)
        layout.addWidget(self._action_input_widget)

        # ── Download output panel ─────────────────────────────────────────
        self._dl_panel = QWidget()
        self._dl_panel.setVisible(False)
        dl_panel_layout = QVBoxLayout(self._dl_panel)
        dl_panel_layout.setContentsMargins(0, 8, 0, 0)
        dl_panel_layout.setSpacing(6)
        self._dl_ep_label = QLabel("Preparing download...")
        self._dl_ep_label.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        dl_panel_layout.addWidget(self._dl_ep_label)
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setValue(0)
        self._dl_progress.setTextVisible(True)
        self._dl_progress.setFixedHeight(20)
        self._dl_progress.setStyleSheet(
            f"QProgressBar{{background:{C['surface']};border:1px solid {C['border']};"
            f"border-radius:3px;color:{C['text']};font-size:11px;}}"
            f"QProgressBar::chunk{{background:{C['green']};border-radius:3px;}}"
        )
        dl_panel_layout.addWidget(self._dl_progress)
        self._dl_log = QPlainTextEdit()
        self._dl_log.setReadOnly(True)
        self._dl_log.setStyleSheet(
            f"background:{C['bg']};color:{C['subtext']};"
            f"border:1px solid {C['border']};border-radius:3px;"
            f"font-family:monospace;font-size:10px;padding:4px;")
        dl_panel_layout.addWidget(self._dl_log)
        self._dl_cancel_btn = QPushButton("\u2715  Cancel Download")
        self._dl_cancel_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};"
            f"border:none;padding:6px 16px;border-radius:3px;")
        dl_panel_layout.addWidget(
            self._dl_cancel_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._dl_panel)
        self._dl_proc = None
        self._opts_extra_args = []
        self._url_panel_url = None  # current download subprocess

        layout.addStretch()

        # Poll batch file
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._update_batch_indicator)
        self._batch_timer.start(2000)

        return page

    def _toggle_batch(self, value):
        enabled = (value == 1)
        self._batch_label.setStyleSheet(
            f"color:{C['green']};border:none;" if enabled
            else f"color:{C['text']};border:none;")
        self._run_batch_btn.setEnabled(enabled)
        # Persist to VineFeeder config
        if _VF_LOADED:
            try:
                from vinefeeder.config_loader import load_config_with_fallback, save_project_config
                cfg, _ = load_config_with_fallback()
                cfg["BATCH_DOWNLOAD"] = enabled
                save_project_config(cfg)
            except Exception:
                pass
            # Also patch BaseLoader directly — it reads config once at __init__
            # so we must update the class attribute live
            try:
                from vinefeeder.base_loader import BaseLoader
                BaseLoader.BATCH_DOWNLOAD = enabled
                self._append_log(f"[batch] BATCH_DOWNLOAD set to {enabled}")
            except Exception:
                pass

    def _update_batch_indicator(self):
        # batch.txt is written to cwd which is install_dir after bootstrap
        batch_path = self.install_dir / "batch.txt"
        # Also check cwd in case it differs
        cwd_path = Path(os.getcwd()) / "batch.txt"
        if batch_path.exists() or cwd_path.exists():
            found = batch_path if batch_path.exists() else cwd_path
            try:
                lines = found.read_text(encoding="utf-8").strip().splitlines()
                count = len([l for l in lines if l.strip()])
            except Exception:
                count = 0
            self._batch_file_lbl.setText(f"✅ batch.txt — {count} episode(s) queued")
            self._batch_file_lbl.setStyleSheet(f"color:{C['green']};border:none;")
        else:
            self._batch_file_lbl.setText("")

    def _run_batch(self):
        if _VF_LOADED:
            # Visual feedback — turn green and show "Starting..."
            self._run_batch_btn.setText("Starting...")
            self._run_batch_btn.setEnabled(False)
            self._run_batch_btn.setStyleSheet(
                f"background:{C['green']};color:{C['bg']};font-weight:bold;"
                f"border:none;padding:3px 8px;font-size:10px;border-radius:3px;")
            # Reset button after 3 seconds
            from PyQt6.QtCore import QTimer
            def _reset_btn():
                self._run_batch_btn.setText("Run Batch")
                self._run_batch_btn.setEnabled(False)
                self._run_batch_btn.setStyleSheet(
                    f"background:{C['overlay']};color:{C['text']};border:none;"
                    f"padding:3px 8px;font-size:10px;border-radius:3px;")
            QTimer.singleShot(3000, _reset_btn)
            threading.Thread(target=self._do_run_batch, daemon=True).start()

    def _do_run_batch(self):
        """Run batch.txt through the download panel."""
        batch_path = self.install_dir / "batch.txt"
        if not batch_path.exists():
            batch_path = Path(os.getcwd()) / "batch.txt"
        if not batch_path.exists():
            self._append_log("[batch] batch.txt not found")
            return
        try:
            lines = [l.strip() for l in batch_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception as e:
            self._append_log(f"[batch] Could not read batch.txt: {e}")
            return
        if not lines:
            self._append_log("[batch] batch.txt is empty")
            return
        self._append_log(f"[batch] Running {len(lines)} queued download(s)")
        # Build episode list for _launch_all_powershell
        # Each line in batch.txt is a full command string
        import shlex as _sl
        episode_list = []
        for line in lines:
            try:
                cmd = _sl.split(line)
                episode_list.append((cmd, str(self.install_dir)))
            except Exception:
                pass
        if episode_list:
            # Delete batch.txt after reading
            try:
                batch_path.unlink()
            except Exception:
                pass
            _launch_all_powershell(episode_list)

    def _populate_service_buttons(self):
        """Called after VineFeeder is loaded — creates a button per service."""
        # Clear placeholder
        while self._svc_layout.count():
            item = self._svc_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            # Import VineFeeder's service-discovery machinery directly.
            # We build a minimal stub object so we can call load_services()
            # without instantiating the full PyQt6 VineFeeder window.
            # This avoids a second QApplication / double-window situation.
            from vinefeeder.__main__ import VineFeeder as _VF, derive_loader_class_name
            import pkgutil, importlib, yaml
            from importlib import resources as _res

            class _ServiceStub:
                """Minimal stand-in for VineFeeder — only needs the dicts."""
                def __init__(self):
                    self.available_services            = {}
                    self.available_service_media_dict  = {}
                    self.available_services_hlg_status = {}
                    self.available_services_options    = {}

            self._vf_instance = _ServiceStub()
            # Call load_services as a plain function, passing stub as self.
            # Do NOT assign it as a class attribute first — that would make
            # Python treat it as a bound method and pass self twice.
            _VF.load_services(self._vf_instance)

            # Build buttons
            grid_layout = QHBoxLayout()
            grid_layout.setSpacing(6)
            col = 0
            row_layout = grid_layout

            services = sorted(self._vf_instance.available_services.keys())
            if not services:
                self._svc_placeholder.show()
                return

            # Use a flow-like grid: 4 buttons per row
            outer = QVBoxLayout()
            outer.setSpacing(4)
            row = QHBoxLayout()
            row.setSpacing(6)
            count = 0
            for svc in services:
                btn = QPushButton(svc)
                btn.setFixedHeight(32)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:{C['overlay']};color:{C['text']};
                        border:none;padding:4px 8px;border-radius:3px;
                        font-size:11px;
                    }}
                    QPushButton:hover {{background:{C['green']};color:{C['bg']};}}
                """)
                btn.clicked.connect(lambda _, s=svc: self._on_service_clicked(s))
                row.addWidget(btn)
                count += 1
                if count % 5 == 0:
                    outer.addLayout(row)
                    row = QHBoxLayout()
                    row.setSpacing(6)

            if count % 5 != 0:
                row.addStretch()
                outer.addLayout(row)

            # Wrap in a widget and add to frame
            wrapper = QWidget()
            wrapper.setStyleSheet("border:none;")
            wrapper.setLayout(outer)
            self._svc_layout.addWidget(wrapper)

            self._dl_status.setText("✓ TwinVine loaded — click a service button to start")
            self._dl_status.setStyleSheet(
                f"color:{C['green']};background:{C['surface']};padding:8px;"
                f"border:1px solid {C['border']};border-radius:3px;")

        except Exception as e:
            import traceback
            self._append_log(f"[service load error] {e}")
            self._append_log(traceback.format_exc())
            self._dl_status.setText(f"Service load error: {e} — check Log tab")

    def _opts_cancel(self):
        """Cancel from options panel — go back to service buttons."""
        self._opts_panel.setVisible(False)
        self._opts_extra_args = []
        self._action_widget.setVisible(False)
        self._action_input_widget.setVisible(False)
        self._dl_status.setText("✓ Ready — click a service button to start")
        self._dl_status.setStyleSheet(
            f"color:{C['green']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")

    def _opts_show(self, pending_confirm_fn, cancel_fn=None):
        """Show the Download Options panel. pending_confirm_fn resumes the download."""
        self._opts_extra_args = []
        self._sel_panel.setVisible(False)
        # Reset all options to defaults on each show
        self._opts_quality.setCurrentIndex(0)  # Best
        self._opts_no_subs.setChecked(False)
        self._opts_slow.setChecked(False)
        self._opts_slow_min.setText("10")
        self._opts_slow_max.setText("60")

        def _on_download():
            args = []
            q = self._opts_quality.currentText()
            if q != "Best available":
                args += ["-q", q.replace("p", "")]
            if self._opts_no_subs.isChecked():
                args += ["--no-subs"]
            self._opts_extra_args = args
            self._opts_panel.setVisible(False)
            pending_confirm_fn()

        def _on_cancel():
            self._opts_panel.setVisible(False)
            self._opts_extra_args = []
            # Reset status
            self._dl_status.setText("✓ Ready — click a service button to start")
            self._dl_status.setStyleSheet(
                f"color:{C['green']};background:{C['surface']};padding:8px;"
                f"border:1px solid {C['border']};border-radius:3px;")
            if cancel_fn:
                cancel_fn()

        try:
            self._opts_download_btn.clicked.disconnect()
            self._opts_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self._opts_download_btn.clicked.connect(_on_download)
        self._opts_cancel_btn.clicked.connect(_on_cancel)
        self._opts_panel.setVisible(True)

    def _show_url_panel(self, url: str):
        """Show the URL Download panel."""
        self._url_panel_url = url
        self._url_display.setText(f"URL: {url[:90]}{'...' if len(url) > 90 else ''}")
        self._url_tracks_widget.setVisible(False)
        self._url_fetch_status.setText(
            "Click ‘Fetch Tracks’ to see what’s available, "
            "or ‘Download’ to start immediately with best quality."
        )
        self._url_fetch_status.setStyleSheet(
            f"color:{C['subtext']};font-size:11px;border:none;font-style:italic;")
        self._url_quality.clear()
        self._url_quality.addItems(["Best available"])
        self._url_no_subs.setChecked(False)
        self._url_slow.setChecked(False)
        self._url_slow_min.setText("10")
        self._url_slow_max.setText("60")
        try:
            self._url_download_btn.clicked.disconnect()
            self._url_cancel_btn.clicked.disconnect()
            self._url_fetch_btn.clicked.disconnect()
        except Exception:
            pass
        self._url_download_btn.clicked.connect(self._url_do_download)
        self._url_cancel_btn.clicked.connect(self._url_do_cancel)
        self._url_fetch_btn.clicked.connect(self._url_fetch_tracks)
        self._action_widget.setVisible(False)
        self._action_input_widget.setVisible(False)
        self._sel_panel.setVisible(False)
        self._opts_panel.setVisible(False)
        self._url_panel.setVisible(True)

    def _url_fetch_tracks(self):
        """Fetch available tracks using FetchTracksWorker."""
        url = getattr(self, '_url_panel_url', None)
        if not url:
            return
        svc = getattr(self, '_pending_service', None)
        if not svc:
            self._url_fetch_status.setText("Error: service not known — click a service button first")
            return
        # Find uv.exe
        import shutil as _sh
        from pathlib import Path as _P
        uv_exe = None
        for candidate in [_P.home() / ".local" / "bin" / "uv.exe"]:
            if candidate.exists():
                uv_exe = str(candidate)
                break
        if not uv_exe:
            uv_exe = _sh.which("uv") or "uv"

        self._url_fetch_status.setText("⏳ Fetching available tracks…")
        self._url_fetch_status.setStyleSheet(
            f"color:{C['yellow']};font-size:11px;border:none;font-style:italic;")
        self._url_fetch_btn.setEnabled(False)

        self._fetch_worker = FetchTracksWorker(uv_exe, self.install_dir, svc, url)
        self._fetch_worker.log_line.connect(self._append_log)
        self._fetch_worker.error.connect(self._url_fetch_error)
        self._fetch_worker.finished.connect(self._url_fetch_done)
        self._fetch_worker.start()

    def _url_fetch_error(self, err: str):
        self._url_fetch_status.setText(f"Error: {err}")
        self._url_fetch_status.setStyleSheet(
            f"color:{C['red']};font-size:11px;border:none;")
        self._url_fetch_btn.setEnabled(True)

    def _url_fetch_done(self, output: str):
        """Parse track output and populate dropdowns."""
        import re as _re

        # Parse unique heights from video lines: | 1920x1080 @ ...
        qualities = ["Best available"]
        seen_q = set()
        for m in _re.finditer(r'\|\s*\d+x(\d+)\s*@', output):
            h = int(m.group(1))
            label = f"{h}p"
            if label not in seen_q:
                qualities.append(label)
                seen_q.add(label)

        # Parse subtitle options
        subs = ["All available", "None"]
        seen_s = set()
        in_subs = False
        for line in output.splitlines():
            if _re.search(r'\d+\s+Subtitle', line):
                in_subs = True
            if in_subs and ('├' in line or '└' in line):
                m = _re.search(r'\[([^\]]+)\]\s*\|\s*([a-z]{2,3})(.*?)(?:\||$)', line)
                if m:
                    lang = m.group(2)
                    extra = m.group(3).strip()
                    label = f"{lang} SDH" if 'SDH' in extra else lang
                    if label not in seen_s:
                        subs.append(label)
                        seen_s.add(label)

        self._url_quality.clear()
        self._url_quality.addItems(qualities)
        self._url_tracks_widget.setVisible(True)

        if len(qualities) > 1:
            self._url_fetch_status.setText(
                f"✓ Found {len(qualities)-1} resolution(s). "
                "Select your preference then click Download."
            )
            self._url_fetch_status.setStyleSheet(
                f"color:{C['green']};font-size:11px;border:none;font-style:normal;")
        else:
            self._url_fetch_status.setText(
                "Could not parse tracks — see Log tab. "
                "You can still Download with best quality."
            )
            self._url_fetch_status.setStyleSheet(
                f"color:{C['yellow']};font-size:11px;border:none;font-style:italic;")
        self._url_fetch_btn.setEnabled(True)

    def _url_do_download(self):
        """Start download with selected options."""
        url = getattr(self, '_url_panel_url', None)
        if not url:
            return
        args = []
        q = self._url_quality.currentText()
        if q != "Best available":
            args += ["-q", q.replace("p", "")]
        if self._url_no_subs.isChecked():
            args += ["--no-subs"]
        self._opts_extra_args = args
        self._url_panel.setVisible(False)
        self._launch_service(1, url, None)

    def _url_do_cancel(self):
        """Cancel URL panel — return to clean home state."""
        self._url_panel.setVisible(False)
        self._action_widget.setVisible(False)
        self._opts_extra_args = []
        self._dl_status.setText(
            "✓ Ready — click a service button to start")
        self._dl_status.setStyleSheet(
            f"color:{C['green']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")

    def closeEvent(self, event):
        """Clean up background processes before closing."""
        # Kill any running download process
        if hasattr(self, '_dl_proc') and self._dl_proc:
            try:
                self._dl_proc.terminate()
            except Exception:
                pass
        # Kill any running install worker
        if hasattr(self, '_install_worker') and self._install_worker:
            try:
                self._install_worker.terminate()
                self._install_worker.wait(2000)
            except Exception:
                pass
        # Kill any running service worker
        if hasattr(self, '_svc_worker') and self._svc_worker:
            try:
                self._svc_worker.terminate()
                self._svc_worker.wait(2000)
            except Exception:
                pass
        event.accept()

    def _open_downloads_folder(self):
        """Open the downloads folder in Windows Explorer."""
        downloads = None
        try:
            cfg = self.install_dir / "packages" / "envied" / "src" / "envied" / "envied.yaml"
            if cfg.exists():
                import yaml as _yaml
                data = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
                # envied.yaml stores download dir under directories.downloads
                dirs = (data or {}).get("directories", {}) or {}
                dl = dirs.get("downloads", "")
                if dl:
                    # Path may be relative to install_dir
                    dl_path = Path(dl) if Path(dl).is_absolute() else self.install_dir / dl
                    if dl_path.exists():
                        downloads = dl_path
        except Exception:
            pass
        if not downloads:
            # Fall back to the Downloads folder inside TwinVine
            fallback = self.install_dir / "Downloads"
            fallback.mkdir(exist_ok=True)
            downloads = fallback
        subprocess.Popen(["explorer", str(downloads)])


    def _open_envied_config(self):
        cfg_path = self.install_dir / "packages/envied/src/envied/envied.yaml"
        if cfg_path.exists():
            subprocess.Popen(["notepad.exe", str(cfg_path)])
        else:
            QMessageBox.warning(self, APP_NAME, f"envied.yaml not found at:\n{cfg_path}")

    def _on_service_clicked(self, service_name: str):
        """Handle a service button click — mirrors VineFeeder's load_service()."""
        if self._service_worker and self._service_worker.isRunning():
            QMessageBox.information(self, APP_NAME,
                "A download is already in progress. Please wait.")
            return
        if hasattr(self, '_dl_panel') and self._dl_panel.isVisible():
            QMessageBox.information(self, APP_NAME,
                "A download is in progress. Please wait or cancel it first.")
            return

        global _qt_parent
        _qt_parent = self

        meta = self._vf_instance.available_services.get(service_name)
        if not meta:
            self._append_log(f"Service {service_name} not found")
            return

        hlg_status = self._vf_instance.available_services_hlg_status.get(service_name, False)
        # Respect user's HLG toggle — if unchecked, force SDR regardless of service default
        if not self._hlg_cb.isChecked():
            hlg_status = False
        self._append_log(f"[debug] {service_name} hlg_status={hlg_status!r} (HLG checkbox={self._hlg_cb.isChecked()})")
        options    = self._vf_instance.available_services_options.get(service_name, {})
        text       = self._search_entry.text().strip()

        # Import loader class first — needed whether text is present or not
        import importlib
        try:
            import sys as _sys
            mod_name = meta["module"]
            # Force a fresh reload each time — prevents stale module-level state
            # from a previous failed attempt poisoning the next run
            if mod_name in _sys.modules:
                module = importlib.reload(_sys.modules[mod_name])
            else:
                module = importlib.import_module(mod_name)
            loader_cls = getattr(module, meta["loader_class"])
        except Exception as e:
            self._append_log(f"[error] Cannot load {service_name}: {e}")
            return

        # Determine inx and text_to_pass — mirrors VineFeeder.load_service()
        if text:
            if "http" in text:
                self._pending_service    = service_name
                self._pending_loader_cls = loader_cls
                self._pending_hlg        = hlg_status
                self._pending_options    = options
                self._search_entry.clear()
                self._show_url_panel(text)
                return
            else:
                inx, text_to_pass, found = 3, text, None
            self._search_entry.clear()
        else:
            # Show inline action chooser — store context for _on_action_chosen
            self._pending_service    = service_name
            self._pending_loader_cls = loader_cls
            self._pending_hlg        = hlg_status
            self._pending_options    = options

            def _make_handler(lbl):
                def _h():
                    self._action_widget.setVisible(False)
                    for b in self._action_btns.values():
                        try: b.clicked.disconnect()
                        except Exception: pass
                    self._on_action_chosen(lbl)
                return _h

            for lbl, btn in self._action_btns.items():
                try: btn.clicked.disconnect()
                except Exception: pass
                btn.clicked.connect(_make_handler(lbl))

            self._action_widget.setVisible(True)
            return


        self._dl_status.setText(f"⏳ Loading {service_name}…")
        self._dl_status.setStyleSheet(
            f"color:{C['yellow']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")
        # Stay on download page — user can check Log tab manually if needed

        # Reset queue for new download session
        import threading as _th3
        if hasattr(_qt_runsubprocess, "_timer") and _qt_runsubprocess._timer:
            _qt_runsubprocess._timer.cancel()
        if not hasattr(_qt_runsubprocess, "_lock"):
            _qt_runsubprocess._lock = _th3.Lock()
        with _qt_runsubprocess._lock:
            _qt_runsubprocess._queue = []
            _qt_runsubprocess._timer = None

        self._service_worker = ServiceWorker(
            loader_cls, inx, text_to_pass, found, hlg_status, options)
        self._service_worker.log_line.connect(self._append_log)
        self._service_worker.finished.connect(self._on_service_done)
        self._service_worker.error.connect(lambda e: self._append_log(f"[error] {e}"))
        self._service_worker.start()

    def _on_action_chosen(self, action: str):
        """Called when user clicks one of the inline action buttons."""
        service_name = self._pending_service
        loader_cls   = self._pending_loader_cls
        # Re-read HLG checkbox here so unticking before retry works without restart
        hlg_status   = self._pending_hlg
        if not self._hlg_cb.isChecked():
            hlg_status = False
        options      = self._pending_options

        # Search/Greedy/Download — show inline text input
        if "Browse" not in action:
            # Check Greedy before Search — "Greedy Search" contains both words
            if "Greedy" in action:
                hint = "Enter a URL for greedy search..."
            elif "Download" in action:
                hint = "Enter a URL for direct download..."
            else:
                hint = "Enter keyword(s) to search..."
            self._action_input_lbl.setText(hint)
            self._action_input.clear()
            self._action_input.setPlaceholderText(hint)
            self._action_input_widget.setVisible(True)
            self._action_input.setFocus()

            def _go():
                val = self._action_input.text().strip()
                if not val:
                    return
                self._action_input_widget.setVisible(False)
                try:
                    self._action_go_btn.clicked.disconnect()
                    self._action_cancel_btn.clicked.disconnect()
                    self._action_input.returnPressed.disconnect()
                except Exception:
                    pass
                if "Greedy" in action:
                    self._launch_service(0, val, None)
                elif "Download" in action:
                    self._show_url_panel(val)
                else:
                    self._launch_service(3, val, None)

            def _cancel_input():
                self._action_input_widget.setVisible(False)
                try:
                    self._action_go_btn.clicked.disconnect()
                    self._action_cancel_btn.clicked.disconnect()
                    self._action_input.returnPressed.disconnect()
                except Exception:
                    pass

            try:
                self._action_go_btn.clicked.disconnect()
                self._action_cancel_btn.clicked.disconnect()
                self._action_input.returnPressed.disconnect()
            except Exception:
                pass
            self._action_go_btn.clicked.connect(_go)
            self._action_cancel_btn.clicked.connect(_cancel_input)
            self._action_input.returnPressed.connect(_go)
            return

        inx, text_to_pass, found = None, None, None

        if "Browse" in action:
            try:
                media_dict = self._vf_instance.available_service_media_dict.get(service_name, {})
                cats = list(media_dict.keys())
                if not cats:
                    QMessageBox.information(self, APP_NAME,
                        f"{service_name} has no browse categories available.")
                    return
                cat = _qt_select(cats, _title=f"Browse {service_name} categories")
                if not cat:
                    return
                inx, text_to_pass, found = 2, media_dict[cat], cat
            except _UserCancelled:
                return
            except Exception as _e:
                self._append_log(f"[browse error] {_e}")
                return

        elif "Search" in action:
            kw, ok = QInputDialog.getText(self, "Search", "Enter keyword(s):")
            if not ok or not kw.strip():
                return
            inx, text_to_pass, found = 3, kw.strip(), None

        else:
            return

        self._launch_service(inx, text_to_pass, found)

    def _launch_service(self, inx, text_to_pass, found):
        """Launch the service worker using stored pending context."""
        service_name = self._pending_service
        loader_cls   = self._pending_loader_cls
        # Always re-read HLG checkbox so unticking before retry takes effect immediately
        hlg_status   = self._pending_hlg
        if not self._hlg_cb.isChecked():
            hlg_status = False
        options      = self._pending_options

        self._dl_status.setText(f"⏳ Loading {service_name}…")
        self._dl_status.setStyleSheet(
            f"color:{C['yellow']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")

        _qt_runsubprocess._queue = []
        _qt_runsubprocess._runner_thread = None

        self._service_worker = ServiceWorker(
            loader_cls, inx, text_to_pass, found, hlg_status, options)
        self._service_worker.log_line.connect(self._append_log)
        self._service_worker.finished.connect(self._on_service_done)
        self._service_worker.error.connect(lambda e: self._append_log(f"[error] {e}"))
        self._service_worker.start()

    # ── Download panel slots ──────────────────────────────────────────────────
    def _dl_append_line(self, line: str):
        self._dl_log.appendPlainText(line)
        sb = self._dl_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _dl_update_progress(self, pct: int):
        self._dl_progress.setValue(pct)
        # Change % text colour at 50% so it stays readable against the green fill
        if pct >= 50:
            self._dl_progress.setStyleSheet(
                f"QProgressBar{{background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:3px;color:{C['bg']};font-size:11px;font-weight:bold;}}"
                f"QProgressBar::chunk{{background:{C['green']};border-radius:3px;}}"
            )
        else:
            self._dl_progress.setStyleSheet(
                f"QProgressBar{{background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:3px;color:{C['text']};font-size:11px;}}"
                f"QProgressBar::chunk{{background:{C['green']};border-radius:3px;}}"
            )

    def _dl_update_episode(self, label: str):
        self._dl_ep_label.setText(label)

    def _dl_finished(self, success: bool):
        self._dl_cancel_btn.setText("✓  Close")
        try:
            self._dl_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self._dl_cancel_btn.clicked.connect(self._dl_close_panel)
        if success:
            self._dl_ep_label.setText("✓  All downloads complete! — Click Close to start a new download.")
            self._dl_ep_label.setStyleSheet(
                f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
            self._dl_progress.setValue(100)
        else:
            self._dl_ep_label.setText("Download stopped. — Click Close to start a new download.")
            self._dl_ep_label.setStyleSheet(
                f"color:{C['red']};font-size:13px;font-weight:bold;border:none;")

    def _dl_close_panel(self):
        self._dl_panel.setVisible(False)
        self._dl_proc = None
        try:
            self._dl_cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self._dl_status.setText("✓ Ready — click another service to continue")
        self._dl_status.setStyleSheet(
            f"color:{C['green']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")

    def _dl_cancel(self):
        """Cancel the running download."""
        if self._dl_proc and self._dl_proc.poll() is None:
            try:
                self._dl_proc.terminate()
            except Exception:
                pass
            try:
                import subprocess as _sp
                si = _sp.STARTUPINFO()
                si.dwFlags |= _sp.STARTF_USESHOWWINDOW
                si.wShowWindow = _sp.SW_HIDE
                _sp.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._dl_proc.pid)],
                    startupinfo=si,
                    capture_output=True,
                )
            except Exception:
                pass
        self._dl_proc = None
        self._dl_signals.done.emit(False)

    def _on_service_done(self):
        self._dl_status.setText("✓ Ready — click another service to continue")
        self._dl_status.setStyleSheet(
            f"color:{C['green']};background:{C['surface']};padding:8px;"
            f"border:1px solid {C['border']};border-radius:3px;")

    # ── Install page ─────────────────────────────────────────────────────────

    def _build_install_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        hdr = QLabel("Install / Update")
        hdr.setStyleSheet(f"font-size:20px;font-weight:bold;color:{C['green']};")
        layout.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Directory
        dir_frame = QFrame()
        dir_frame.setStyleSheet(
            f"background:{C['surface']};border:1px solid {C['border']};border-radius:4px;")
        df = QVBoxLayout(dir_frame)
        df.setContentsMargins(14, 12, 14, 12)
        QLabel("Install directory").setStyleSheet(f"color:{C['subtext']};")
        lbl = QLabel("Install directory")
        lbl.setStyleSheet(f"color:{C['subtext']};font-weight:bold;")
        df.addWidget(lbl)
        dir_row = QHBoxLayout()
        self._dir_entry = QLineEdit(str(self.install_dir))
        dir_row.addWidget(self._dir_entry)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        df.addLayout(dir_row)
        layout.addWidget(dir_frame)

        # Warning about install time
        warn = QLabel("⚠ Check the Log tab for a detailed view of the current installation.")
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{C['yellow']};font-size:11px;padding:6px 0 2px 0;")
        layout.addWidget(warn)

        # Pointer to help page
        help_note = QLabel(
            "ℹ️  Before installing, see the <b>Help</b> page for full details of what this will do."
        )
        help_note.setWordWrap(True)
        help_note.setStyleSheet(f"color:{C['subtext']};font-size:11px;padding:2px 0 4px 0;")
        layout.addWidget(help_note)

        # Buttons
        btn_row = QHBoxLayout()
        self._install_btn = QPushButton("▶  Install TwinVine & Tools")
        self._install_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};font-weight:bold;"
            f"padding:10px 20px;font-size:13px;border-radius:4px;")
        self._install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self._install_btn)
        self._update_btn = QPushButton("🔄  Check for Updates")
        self._update_btn.clicked.connect(self._check_updates)
        self._update_btn.setVisible(self._is_installed())
        btn_row.addWidget(self._update_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Build EXE section — only shown when installed
        self._build_frame = QFrame()
        self._build_frame.setStyleSheet(
            f"QFrame#buildFrame{{background:{C['surface']};border:1px solid {C['border']};"
            f"border-radius:4px;}}")
        self._build_frame.setObjectName('buildFrame')
        self._build_frame.setVisible(self._is_installed())
        bf = QVBoxLayout(self._build_frame)
        bf.setContentsMargins(14, 12, 14, 12)
        bf.setSpacing(6)
        build_hdr = QLabel("Build Standalone EXE")
        build_hdr.setStyleSheet(
            f"color:{C['green']};font-size:13px;font-weight:bold;border:none;")
        bf.addWidget(build_hdr)
        build_note = QLabel(
            "Builds TwinVineLauncher.exe — a convenient alternative to running "
            "the app via the batch file. Once built, you can place a shortcut to "
            "the exe on your desktop or taskbar for easy access. "
            "Output is saved to the dist\\ folder next to the launcher. "
            "To create a full installer for distributing to other machines, "
            "use Inno Setup with twinvine_launcher.iss — see the Setup & Installation guide."
        )
        build_note.setWordWrap(True)
        build_note.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        bf.addWidget(build_note)
        build_btn_row = QHBoxLayout()
        self._build_btn = QPushButton("🔨  Build EXE")
        self._build_btn.setStyleSheet(
            f"background:{C['overlay']};color:{C['text']};font-weight:bold;"
            f"padding:8px 18px;border-radius:4px;border:none;")
        self._build_btn.clicked.connect(self._start_build_exe)
        build_btn_row.addWidget(self._build_btn)
        build_btn_row.addStretch()
        bf.addLayout(build_btn_row)
        self._build_status = QLabel("")
        self._build_status.setWordWrap(True)
        self._build_status.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;")
        bf.addWidget(self._build_status)
        layout.addWidget(self._build_frame)

        # Progress
        prog_frame = QFrame()
        prog_frame.setStyleSheet(
            f"background:{C['surface']};border:1px solid {C['border']};border-radius:4px;")
        pf = QVBoxLayout(prog_frame)
        pf.setContentsMargins(14, 10, 14, 10)
        self._prog_lbl = QLabel("Ready.")
        self._prog_lbl.setStyleSheet(f"color:{C['subtext']};")
        pf.addWidget(self._prog_lbl)
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        pf.addWidget(self._prog_bar)
        layout.addWidget(prog_frame)

        # Step list
        steps_frame = QFrame()
        steps_frame.setStyleSheet(
            f"background:{C['surface']};border:1px solid {C['border']};border-radius:4px;")
        sf = QVBoxLayout(steps_frame)
        sf.setContentsMargins(14, 12, 14, 12)
        QLabel("STEPS").setStyleSheet(f"color:{C['border']};font-size:9px;")
        hdr2 = QLabel("STEPS")
        hdr2.setStyleSheet(f"color:{C['border']};font-size:9px;font-weight:bold;")
        sf.addWidget(hdr2)
        self._step_labels = {}
        for key, desc in [
            ("git",   "Install git (if needed) & clone / update TwinVine repository"),
            ("tools", "Install media tools (FFmpeg, MKVToolNix, Bento4…)"),
            ("uv",    "Install uv package manager"),
            ("sync",  "uv lock & uv sync (Python packages)"),
            ("yaml",  "Copy example YAML config"),
            ("done",  "All done ✓"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel("○")
            lbl.setStyleSheet(f"color:{C['border']};font-size:14px;min-width:20px;")
            row.addWidget(lbl)
            row.addWidget(QLabel(desc))
            row.addStretch()
            sf.addLayout(row)
            self._step_labels[key] = lbl
        layout.addWidget(steps_frame)
        layout.addStretch()
        return page

    def _start_build_exe(self):
        """Install PyInstaller if needed, generate a spec, and build the EXE."""
        import subprocess as _sp
        import sys as _sys
        import os as _os
        import threading as _th

        venv_python = self.install_dir / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            QMessageBox.warning(self, APP_NAME,
                "TwinVine venv not found. Please run Install TwinVine & Tools first.")
            return

        launcher_py = Path(_os.path.abspath(_sys.argv[0]))
        launcher_dir = launcher_py.parent
        assets_dir = launcher_dir / "assets"
        icon_path = assets_dir / "icon.ico"

        self._build_btn.setEnabled(False)
        self._build_status.setStyleSheet(f"color:{C['yellow']};font-size:11px;border:none;")
        self._build_status.setText("⏳  Installing PyInstaller…")
        QApplication.processEvents()

        def _run_build():
            try:
                cf = dict(creationflags=_sp.CREATE_NO_WINDOW)

                # Step 1 — install PyInstaller via uv (venv has no pip by default)
                uv_exe = self.cfg.get("uv_exe") or shutil.which("uv")
                if not uv_exe:
                    # fallback — look in the standard uv install location
                    uv_exe = str(Path.home() / ".local" / "bin" / "uv.exe")
                r = _sp.run(
                    [uv_exe, "pip", "install", "--quiet", "pyinstaller",
                     "--python", str(venv_python)],
                    capture_output=True, text=True, cwd=str(launcher_dir), **cf)
                if r.returncode != 0:
                    raise RuntimeError(f"PyInstaller install failed:\n{r.stderr}")

                self._build_status.setText("⏳  Building EXE…")
                QApplication.processEvents()

                # Step 2 — build args (no spec file needed)
                build_args = [
                    str(venv_python), "-m", "PyInstaller",
                    "--noconfirm",
                    "--onefile",
                    "--windowed",
                    "--name", "TwinVineLauncher",
                    "--hidden-import", "PyQt6",
                    "--hidden-import", "PyQt6.QtWidgets",
                    "--hidden-import", "PyQt6.QtCore",
                    "--hidden-import", "PyQt6.QtGui",
                    "--hidden-import", "PyQt6.sip",
                    "--hidden-import", "requests",
                    "--hidden-import", "urllib3",
                    "--hidden-import", "certifi",
                    "--hidden-import", "xmlrpc",
                    "--hidden-import", "xmlrpc.client",
                    "--hidden-import", "xmlrpc.server",
                    "--hidden-import", "defusedxml",
                    "--hidden-import", "defusedxml.xmlrpc",
                    "--collect-submodules", "xmlrpc",
                    "--exclude-module", "tkinter",
                    "--exclude-module", "test",
                ]
                if assets_dir.exists():
                    build_args += ["--add-data", f"{assets_dir};assets"]
                if icon_path.exists():
                    build_args += ["--icon", str(icon_path)]
                build_args.append(str(launcher_py))

                r2 = _sp.run(
                    build_args, capture_output=True, text=True,
                    cwd=str(launcher_dir), **cf)
                if r2.returncode != 0:
                    raise RuntimeError(f"PyInstaller build failed:\n{r2.stderr[-2000:]}")

                exe_path = launcher_dir / "dist" / "TwinVineLauncher.exe"
                if exe_path.exists():
                    self._build_status.setStyleSheet(
                        f"color:{C['green']};font-size:11px;border:none;")
                    self._build_status.setText(
                        f"✓  Build complete: {exe_path}")
                else:
                    raise RuntimeError("Build finished but EXE not found in dist\\")

            except Exception as e:
                self._build_status.setStyleSheet(
                    f"color:{C['red']};font-size:11px;border:none;")
                self._build_status.setText(f"✗  {e}")
            finally:
                self._build_btn.setEnabled(True)

        _th.Thread(target=_run_build, daemon=True).start()

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose install directory",
                                             self._dir_entry.text())
        if d:
            self._dir_entry.setText(d)

    def _set_step(self, key, state):
        icons  = {"pending": "○", "active": "◉", "done": "✓", "error": "✗"}
        colors = {"pending": C['border'], "active": C['yellow'],
                  "done": C['green'], "error": C['red']}
        lbl = self._step_labels.get(key)
        if lbl:
            lbl.setText(icons.get(state, "○"))
            lbl.setStyleSheet(f"color:{colors.get(state, C['border'])};font-size:14px;min-width:20px;")

    def _start_install(self):
        # Confirmation dialog explaining what will happen
        msg = QMessageBox(self)
        msg.setWindowTitle("Install TwinVine Tools")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("<b>This will set up TwinVine-Launcher-Core on your machine.</b>")
        msg.setInformativeText(
            "The following will happen:\n\n"
            "\u2022 Clone the TwinVine-Launcher-Core repository from GitHub\n"
            "\u2022 Download and install media tools (~500MB total)\n"
            "\u2022 Create a Python virtual environment\n"
            "\u2022 Patch configuration files (backups are kept)\n\n"
            "Note: some tools are installed outside the TwinVine folder:\n"
            "\u2022 uv \u2192 your user profile (~/.local/bin)\n"
            "\u2022 FFmpeg, MKVToolNix, N_m3u8DL-RE, Bento4 \u2192 C:\\Tools\\bin\n"
            "\u2022 Git for Windows \u2192 system-wide (if not already installed)\n\n"
            "See the Help page for full uninstall details.\n\n"
            "Do you want to continue?"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self.install_dir = Path(self._dir_entry.text())
        self.cfg["install_dir"] = str(self.install_dir)
        save_config(self.cfg)
        for k in self._step_labels:
            self._set_step(k, "pending")
        self._install_btn.setEnabled(False)
        self._install_btn.setText("Installing…")
        self._prog_bar.setValue(0)
        # Stay on install page — progress bar and step indicators show progress

        self._install_worker = InstallWorker(self.install_dir)
        self._install_worker.log_line.connect(self._append_log)
        self._install_worker.step_done.connect(self._set_step)
        self._install_worker.progress.connect(self._update_install_progress)
        self._install_worker.finished.connect(self._on_install_done)
        self._install_worker.start()

    def _venv_python(self) -> str | None:
        """Return path to the venv Python executable if it exists."""
        # Check TWINVINE_VENV env var first (set by .bat on launch)
        venv_from_env = os.environ.get("TWINVINE_VENV", "")
        candidates = []
        if venv_from_env:
            candidates.append(Path(venv_from_env))
        candidates.append(self.install_dir / ".venv")
        for venv_root in candidates:
            for name in ("pythonw.exe", "python.exe"):
                p = venv_root / "Scripts" / name
                if p.exists():
                    return str(p)
        return None

    def _do_relaunch(self):
        """Relaunch via the .bat file — uses system pythonw for clean windowless start."""
        launcher_dir = Path(__file__).resolve().parent
        bat = launcher_dir / "TwinVine Launcher.bat"
        launcher_script = str(Path(__file__).resolve())

        # Set TWINVINE_VENV so the relaunched process knows where the venv is
        venv_py = self._venv_python()
        env = os.environ.copy()
        if venv_py:
            env["TWINVINE_VENV"] = str(Path(venv_py).parent.parent)

        # Use system pythonw.exe — always properly windowless unlike venv copies
        sys_pythonw = shutil.which("pythonw")
        if sys_pythonw:
            subprocess.Popen(
                [sys_pythonw, launcher_script],
                cwd=str(launcher_dir),
                env=env,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            QApplication.quit()
            return

        # Fallback: use the bat
        if bat.exists():
            subprocess.Popen(
                ["cmd.exe", "/c", str(bat)],
                cwd=str(launcher_dir),
                env=env,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            QApplication.quit()
            return

        QMessageBox.warning(self, APP_NAME,
            "Restart complete. Please close and reopen the launcher manually.")

    def _update_install_progress(self, v: float, m: str):
        pct = int(v * 100)
        self._prog_bar.setValue(pct)
        self._prog_lbl.setText(m)
        if pct >= 50:
            self._prog_bar.setStyleSheet(
                f"QProgressBar{{background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:3px;color:{C['bg']};font-size:11px;font-weight:bold;}}"
                f"QProgressBar::chunk{{background:{C['green']};border-radius:3px;}}"
            )
        else:
            self._prog_bar.setStyleSheet(
                f"QProgressBar{{background:{C['surface']};border:1px solid {C['border']};"
                f"border-radius:3px;color:{C['text']};font-size:11px;}}"
                f"QProgressBar::chunk{{background:{C['green']};border-radius:3px;}}"
            )

    def _on_install_done(self, success: bool, msg: str):
        self._install_btn.setEnabled(True)
        self._install_btn.setText("▶  Install TwinVine & Tools")
        if success:
            commit = self._get_remote_commit()
            self.cfg.update({
                "installed": True,
                "install_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "last_commit": commit,
                "uv_exe": getattr(self._install_worker, "uv_exe_path", None),
            })
            save_config(self.cfg)
            self._refresh_status()
            self._update_btn.setVisible(True)
            if hasattr(self, '_build_frame'):
                self._build_frame.setVisible(True)

            # Load VineFeeder directly — no relaunch needed.
            # The sys.path eviction in bootstrap_vinefeeder handles version
            # differences between the launcher Python and the venv Python.
            self._load_vinefeeder()
            self._append_log("=" * 60)
            self._append_log("INSTALLATION COMPLETE — service buttons are available.")
            self._append_log("=" * 60)
            self._prog_lbl.setText("✓ Complete! Go to Home tab.")
            self._prog_lbl.setStyleSheet(f"color:{C['green']};font-weight:bold;")
            if hasattr(self, "_mini_log"):
                self._mini_log.appendPlainText("✓ Done — check Log tab for any warnings.")
        else:
            # Show failure in log (don't hide it with a popup)
            self._append_log("=" * 60)
            self._append_log(f"INSTALLATION FAILED: {msg}")
            self._append_log("=" * 60)
            QMessageBox.critical(self, APP_NAME, f"Installation failed:\n{msg}")

    def _check_updates(self):
        if not REQUESTS_AVAILABLE:
            QMessageBox.warning(self, APP_NAME, "pip install requests to enable update checks.")
            return
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Checking…")
        # Use a QThread (not threading.Thread) so QTimer.singleShot works correctly
        self._update_thread = _UpdateCheckThread(self.cfg.get("last_commit"))
        self._update_thread.result_ready.connect(self._on_update_result)
        self._update_thread.start()

    def _on_update_result(self, remote: str, local: str):
        """Called on main thread when update check completes."""
        self._update_btn.setEnabled(True)
        self._update_btn.setText("🔄  Check for Updates")
        if not remote:
            QMessageBox.warning(self, APP_NAME,
                "Could not reach GitHub. Check your internet connection.")
            return
        if remote == local:
            QMessageBox.information(self, APP_NAME, "✓ TwinVine Launcher is up to date!")
        else:
            ans = QMessageBox.question(self, APP_NAME,
                "A new version of the TwinVine Launcher is available.\n\n"
                "Download and install the update now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans == QMessageBox.StandardButton.Yes:
                self._download_launcher_update(remote)

    def _download_launcher_update(self, new_sha: str):
        """Download the latest launcher .py from GitHub and replace this file."""
        import urllib.request as _urlreq
        import sys as _sys
        import os as _os

        # Raw URL to the launcher file on the main branch
        raw_url = (
            f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/"
            "twinvine_launcher.py"
        )
        current_file = _os.path.abspath(_sys.argv[0])
        backup_file  = current_file + ".bak"

        self._update_btn.setEnabled(False)
        self._update_btn.setText("Downloading…")
        QApplication.processEvents()

        try:
            with _urlreq.urlopen(raw_url, timeout=30) as resp:
                new_content = resp.read()

            # Back up current file before overwriting
            with open(current_file, "rb") as f:
                old_content = f.read()
            with open(backup_file, "wb") as f:
                f.write(old_content)

            # Write new launcher file
            with open(current_file, "wb") as f:
                f.write(new_content)

            # Save new commit SHA so next check knows we're up to date
            self.cfg["last_commit"] = new_sha
            self._save_cfg()

            QMessageBox.information(self, APP_NAME,
                "✓ Update downloaded successfully.\n\n"
                "Please close and reopen the launcher for the changes to take effect.\n\n"
                f"A backup of the previous version has been saved as:\n{backup_file}")

        except Exception as e:
            QMessageBox.warning(self, APP_NAME,
                f"Update download failed:\n{e}\n\n"
                "You can download the latest version manually from:\n"
                f"{LAUNCHER_URL}")
        finally:
            self._update_btn.setEnabled(True)
            self._update_btn.setText("🔄  Check for Updates")

    def _get_remote_commit(self) -> str | None:
        if not REQUESTS_AVAILABLE:
            return None
        try:
            r = requests.get(GITHUB_API, timeout=10,
                             headers={"Accept": "application/vnd.github.v3+json"})
            if r.ok:
                return r.json().get("sha", "")[:12]
        except Exception:
            pass
        return None

    # ── Log page ─────────────────────────────────────────────────────────────

    def _build_log_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        hdr_row = QHBoxLayout()
        hdr = QLabel("Log")
        hdr.setStyleSheet(f"font-size:20px;font-weight:bold;color:{C['green']};")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_log)
        hdr_row.addWidget(clear_btn)
        back_btn = QPushButton("← Back to Home")
        back_btn.clicked.connect(lambda: self._show_page("download"))
        hdr_row.addWidget(back_btn)
        layout.addLayout(hdr_row)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(
            f"background:#070910;color:#a6e3a1;font-family:Consolas,monospace;"
            f"font-size:10px;border:1px solid {C['border']};")
        layout.addWidget(self._log_view)
        return page

    def _append_log(self, msg: str):
        # Mirror key lines to mini install log
        if hasattr(self, "_mini_log"):
            if any(x in msg for x in ["── STEP", "INSTALL", "ERROR", "WARNING",
                                        "Downloading", "Installed", "skipped",
                                        "already", "FFmpeg", "uv sync", "Done"]):
                self._mini_log.appendPlainText(msg)
                sb = self._mini_log.verticalScrollBar()
                sb.setValue(sb.maximum())
        ts = datetime.now().strftime("%H:%M:%S")
        # Must be called on main thread for Qt safety — use invokeMethod pattern
        def _do():
            self._log_view.moveCursor(QTextCursor.MoveOperation.End)
            self._log_view.insertPlainText(f"[{ts}] {msg}\n")
            self._log_view.moveCursor(QTextCursor.MoveOperation.End)
        if QApplication.instance() and threading.current_thread() is threading.main_thread():
            _do()
        else:
            QTimer.singleShot(0, _do)

    def _clear_log(self):
        self._log_view.clear()

    # ── About page ────────────────────────────────────────────────────────────

    def _build_help_page(self) -> QWidget:
        """
        Help page — edit the HELP_TEXT constant below to update the content.
        Supports basic Markdown-style sections using ## for headers.
        """
        # ── EDIT THIS TEXT TO UPDATE THE HELP PAGE ────────────────────────────
        HELP_TEXT = """
## Before You Install

When you click **Install TwinVine Tools** the following will happen:

- The TwinVine-Launcher-Core repository is cloned from GitHub into a **TwinVine subfolder** next to the launcher
- Media tools are downloaded and installed: **FFmpeg** (~240MB), **MKVToolNix**, **Bento4**, **N_m3u8DL-RE** and others
- The **uv** Python package manager is installed
- A **Python virtual environment** is created and all required packages installed (~150MB)
- An example **envied.yaml** config file is copied for you to add your credentials to
- **pyproject.toml** and **envied.yaml** are patched where needed — backups are kept as .bak files

**Total download:** approximately 500MB. **Time:** 2–5 minutes on a fast connection.

**Some items are installed outside the TwinVine folder:**

- **uv** is installed to your user profile (`~/.local/bin`)
- **FFmpeg, MKVToolNix, N_m3u8DL-RE, Bento4, Shaka Packager** are installed to `C:\\Tools\\bin`
- **Git for Windows** is installed system-wide if not already present

If you delete the TwinVine folder and reinstall, tools already in `C:\\Tools\\bin` will be detected and skipped — only the TwinVine packages themselves will be re-downloaded. To fully uninstall everything, you would also need to delete `C:\\Tools\\bin` and remove uv and Git manually.

**Check for Updates** checks for new commits to the TwinVine Launcher repository — not the original TwinVine project.

---

## Getting Started

1. On first run, click **Install / Update** in the sidebar and then **Install TwinVine Tools**. You can check the **Log** tab for a more detailed view of the installation.
2. Once installed, return to **Home** and search for your desired title, or paste a URL directly into the search box, then click a service button (BBC, ITVX, etc.).
3. You can also click a service button first and then choose how to search — by keyword, URL, or browse by category.
4. Select the series and episodes you want, then click **Confirm**.
5. Before downloading you can set a few options:
5a. **Quality** — Best available will always try to grab the highest quality stream. If you know a 2160p version exists, select that specifically as Best available may not always find it.
5b. **Slow mode** — Adds a randomised delay between episode downloads. Useful for reducing the risk of being throttled. The min and max delay in seconds can be set once the box is ticked.

---

## Navigation

- **Home** — The main page. Click a service button to start, type keywords to search, or paste a direct episode URL into the search box.
- **My Downloads** — Opens your downloads folder in Windows Explorer.
- **Install / Update** — Install or update TwinVine and all media tools.
- **HellYes** — Advanced manual DRM key extraction tool.
- **Log** — Detailed output from the launcher, useful for diagnosing issues.
- **Help** — You are here.
- **About** — Information about TwinVine and its authors.

---

## Options

- **Envied Config** — Opens envied.yaml in Notepad. Edit credentials, download location, filename format, subtitle settings and more.
- **HLG** — Enables HDR/HLG streams when ticked (on by default). Untick HLG if you see a "Selection unavailable in UHD" or "Stream not available in that resolution" error.
- **Quality** — Choose from Best available, 2160p, 1080p, or 720p. For resolutions lower than 720p use the Fetch Tracks option in the URL Download panel. Note that Best available will normally fall back to the best resolution available if your chosen resolution is not found.
- **No subtitles** — Skip subtitle downloads for all selected episodes.
- **Slow mode** — Adds a randomised delay between episode downloads. Set your preferred minimum and maximum wait time in seconds once the box is ticked.
- **Fetch Tracks** — Available in the Download by URL panel. Paste an episode or series URL, click **Fetch Tracks**, and a dropdown list of all available resolutions will appear. Select your preferred resolution and click Download. Note that 2160p may not always appear in the list — if so, try Best available or use the standard Quality options instead.

---

## Downloading Episodes

When you click a service button you can choose from four actions:

- **Search by keyword** — Type a show name to find it.
- **Greedy Search by URL** — Paste a show page URL to fetch all available content.
- **Download by URL** — Paste a direct episode or series URL to download it.
- **Browse by Category** — Browse the service's categories to find content.

After searching, select the series you want, tick the episodes and click **Confirm**. Multiple episodes download sequentially — you can mix episodes from different series. Progress is shown in the download panel with a live log and a cancel option.

**2160p Downloads from BBC iPlayer** — 2160p content is not always returned by Best available or shown in Fetch Tracks. For reliable 2160p downloads, use the full programme title exactly as listed on the BBC website. See: <a href="https://www.bbc.co.uk/iplayer/help/questions/programme-availability/uhd-content">What programmes can I watch in Ultra HD?</a> — or select 2160p explicitly as your Quality choice.

---

## Batch Mode

Batch mode lets you queue episodes from multiple shows before downloading them all at once.

1. Toggle **Batch Mode** on in the sidebar — it turns green when active.
2. Search and select episodes as normal — they queue instead of downloading immediately. The sidebar shows how many episodes are queued.
3. When ready, click **Run Batch** to download everything in the queue.
4. Toggle **Batch Mode** off to return to normal single downloads.

---

## Common Errors

**"Selection unavailable in UHD"** or **"Stream not available in that resolution"** — Untick the HLG checkbox and try again.

**"No .venv found"** — Go to Install / Update and click Install TwinVine Tools.

**"patch failed / cannot import vinefeeder"** — Usually a Python version mismatch. Delete the TwinVine subfolder and click Install TwinVine Tools again.

**"Download fails with exit code 1"** — Check your credentials in Envied Config and make sure your CDM device file is in the WVDs folder.

**"unable to find vault command"** — Run Install / Update again to repair the configuration.

---

## Supported Services

- **PLease note: Some services require login credentials** - To add these you'll need to edit the envied config file a link can be found on the home page.

ALL4, BBC iPlayer, ITVX, MY5, PLEX, RTE, STV, TPTV, TVNZ (untested), U

---

## Tips

- Downloads are saved to the **TwinVine/Downloads** folder by default.
- Change the download location in **Envied Config** under the directories section.
- The **Log** tab records everything — check it first if something goes wrong.
- Login credentials for each service go in **Envied Config** under credentials.
- If a fresh install fails, delete the TwinVine subfolder and try again.
- Keep a backup copy of your **envied.yaml** somewhere safe — if you delete it you will need to re-enter all your credentials and settings from scratch.

        """
        # ─────────────────────────────────────────────────────────────────────

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)

        hdr = QLabel("Help")
        hdr.setStyleSheet(f"font-size:20px;font-weight:bold;color:{C['green']};")
        layout.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 8, 16, 8)
        content_layout.setSpacing(4)

        for raw_line in HELP_TEXT.strip().split('\n'):
            if raw_line.startswith('## '):
                lbl = QLabel(raw_line[3:])
                lbl.setStyleSheet('color:#a6e3a1;font-size:14px;font-weight:bold;padding-top:12px;')
                content_layout.addWidget(lbl)
            elif not raw_line.strip():
                sp = QLabel('')
                sp.setFixedHeight(4)
                content_layout.addWidget(sp)
            else:
                import re as _re2
                rich = _re2.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', raw_line)
                lbl = QLabel(rich)
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setWordWrap(True)
                lbl.setOpenExternalLinks(True)
                lbl.setStyleSheet('color:#a6adc8;font-size:12px;')
                content_layout.addWidget(lbl)
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        return page




    def _build_hellyes_page(self) -> QWidget:
        """HellYes — embedded DRM key fetcher. Mirrors gui.py (AllHell3App)."""
        from PyQt6.QtWidgets import QTextEdit
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(6)

        hdr = QLabel("HellYes")
        hdr.setStyleSheet(f"font-size:20px;font-weight:bold;color:{C['green']};")
        outer.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        # MPD URL
        outer.addWidget(self._hy_lbl("MPD URL"))
        self._hy_mpd = QLineEdit()
        self._hy_mpd.setStyleSheet(f"border:1px solid {C['border']};background:{C['surface']};color:{C['text']};padding:4px;")
        self._hy_mpd.setPlaceholderText("https://example.com/manifest.mpd")
        outer.addWidget(self._hy_mpd)

        # cURL
        outer.addWidget(self._hy_lbl("cURL of License Request"))
        self._hy_curl = QTextEdit()
        self._hy_curl.setMaximumHeight(80)
        self._hy_curl.setStyleSheet(f"border:1px solid {C['border']};background:{C['surface']};color:{C['text']};")
        self._hy_curl.setPlaceholderText("Paste the curl command from browser DevTools here...")
        outer.addWidget(self._hy_curl)

        # Red-bordered frame: video name + buttons
        frame = QFrame()
        frame.setStyleSheet(f"border:1px solid {C['border']};border-radius:4px;padding:4px;")
        fl = QVBoxLayout(frame)
        fl.setSpacing(6)
        fl.setContentsMargins(8, 8, 8, 8)

        fl.addWidget(self._hy_lbl("Video Name"))
        self._hy_name = QLineEdit()
        self._hy_name.setStyleSheet(f"border:1px solid {C['border']};background:{C['surface']};color:{C['text']};padding:4px;")
        fl.addWidget(self._hy_name)

        btn_style = (f"color:{C['text']};background:#4e4e4e;"
                     f"border:1px solid #6e6e6e;padding:5px 12px;")
        btn_row = QHBoxLayout()
        self._hy_btn_keys = QPushButton("Get Keys")
        self._hy_btn_keys.setStyleSheet(btn_style)
        self._hy_btn_keys.clicked.connect(self._hy_fetch_keys)
        btn_row.addWidget(self._hy_btn_keys)

        self._hy_btn_nm = QPushButton("Download Nm~RE")
        self._hy_btn_nm.setStyleSheet(btn_style)
        self._hy_btn_nm.clicked.connect(self._hy_download_nm)
        btn_row.addWidget(self._hy_btn_nm)

        self._hy_btn_dash = QPushButton("Download DASH")
        self._hy_btn_dash.setStyleSheet(btn_style)
        self._hy_btn_dash.clicked.connect(self._hy_download_dash)
        btn_row.addWidget(self._hy_btn_dash)
        fl.addLayout(btn_row)
        outer.addWidget(frame)

        # Keys output
        outer.addWidget(self._hy_lbl("Keys"))
        self._hy_keys_out = QTextEdit()
        self._hy_keys_out.setReadOnly(True)
        self._hy_keys_out.setMaximumHeight(60)
        self._hy_keys_out.setStyleSheet(f"background:{C['bg']};color:{C['green']};border:1px solid {C['border']};")
        outer.addWidget(self._hy_keys_out)

        # N_m3u8DL-RE command
        outer.addWidget(self._hy_lbl("N_m3u8DL-RE command"))
        self._hy_nm_out = QTextEdit()
        self._hy_nm_out.setMaximumHeight(50)
        self._hy_nm_out.setStyleSheet(f"background:{C['surface']};color:{C['text']};border:1px solid {C['border']};")
        outer.addWidget(self._hy_nm_out)

        # Dash-MPD-CLI command
        outer.addWidget(self._hy_lbl("Dash-MPD-CLI command"))
        self._hy_dash_out = QTextEdit()
        self._hy_dash_out.setMaximumHeight(50)
        self._hy_dash_out.setStyleSheet(f"background:{C['surface']};color:{C['text']};border:1px solid {C['border']};")
        outer.addWidget(self._hy_dash_out)

        # Reset button
        reset_row = QHBoxLayout()
        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(f"background:{C['overlay']};color:{C['text']};border:none;padding:5px 16px;border-radius:3px;")
        reset_btn.clicked.connect(self._hy_reset)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch()
        outer.addLayout(reset_row)
        outer.addStretch()

        self._hy_nm_command   = ""
        self._hy_dash_command = ""
        return page

    def _hy_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{C['subtext']};font-size:11px;border:none;margin-top:2px;")
        return lbl

    def _hy_reset(self):
        self._hy_mpd.clear()
        self._hy_curl.clear()
        self._hy_name.clear()
        self._hy_keys_out.clear()
        self._hy_nm_out.clear()
        self._hy_dash_out.clear()
        self._hy_nm_command   = ""
        self._hy_dash_command = ""

    def _hy_fetch_keys(self):
        """Fetch DRM keys — mirrors AllHell3App.fetch_keys() from gui.py."""
        import httpx as _httpx
        import re as _re
        import base64 as _b64
        import codecs as _codecs
        import urllib.parse as _ulp
        import xml.etree.ElementTree as _ET

        mpd_url  = self._hy_mpd.text().strip()
        curl_cmd = self._hy_curl.toPlainText().strip()
        vid_name = self._hy_name.text().strip()

        if not mpd_url or not curl_cmd:
            QMessageBox.warning(self, "HellYes", "Please enter both MPD URL and cURL command.")
            return

        try:
            # ── Fetch MPD ──────────────────────────────────────────────────────
            mpd_content = _httpx.get(mpd_url).text

            # ── Extract/generate PSSH (mirrors extract_or_generate_pssh) ──────
            WIDEVINE_SID = "EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED"
            ns = {"cenc": "urn:mpeg:cenc:2013", "": "urn:mpeg:dash:schema:mpd:2011"}
            try:
                root = _ET.fromstring(mpd_content)
                default_kid = None
                pssh = None
                for elem in root.findall(".//ContentProtection", ns):
                    sid = elem.attrib.get("schemeIdUri", "").upper()
                    if sid == "URN:MPEG:DASH:MP4PROTECTION:2011":
                        default_kid = elem.attrib.get("cenc:default_KID")
                    if sid == f"URN:UUID:{WIDEVINE_SID}":
                        pe = elem.find("cenc:pssh", ns)
                        if pe is not None:
                            pssh = pe.text
                if not default_kid:
                    m = _re.search(r'cenc:default_KID="([A-F0-9-]+)"', mpd_content)
                    if m:
                        default_kid = m.group(1)
                if not pssh and default_kid:
                    kid = default_kid.replace("-", "")
                    s = f"000000387073736800000000edef8ba979d64acea3c827dcd51d21ed000000181210{kid}48e3dc959b06"
                    pssh = _b64.b64encode(bytes.fromhex(s)).decode()
            except _ET.ParseError:
                pssh = None

            if not pssh:
                QMessageBox.critical(self, "HellYes", "Could not extract PSSH from MPD.\nIs this a Widevine-encrypted stream?")
                return

            # ── Parse cURL (mirrors parse_curl) ───────────────────────────────
            url_m = _re.search(r"curl\s+'(.*?)'", curl_cmd)
            lic_url = url_m.group(1) if url_m else ""
            headers = {}
            for h in _re.findall(r"-H\s+'([^:]+):\s*(.*?)'", curl_cmd):
                headers[h[0]] = h[1]
            data_m = _re.search(r"--data(?:-raw)?\s+(?:(\$?')|(\$?{?))(.*?)'", curl_cmd, _re.DOTALL)
            if data_m:
                raw_prefix = data_m.group(1)
                data = data_m.group(3)
                if raw_prefix and raw_prefix.startswith("$"):
                    data = None
                else:
                    data = data.replace("\\\\", "\\").replace("\\x", "\\\\x")
                    try:
                        data = _codecs.decode(data, "unicode_escape")
                    except Exception:
                        data = ""
            else:
                data = ""

            # ── Get keys (mirrors get_key) ────────────────────────────────────
            from pywidevine.cdm import Cdm
            from pywidevine.device import Device
            from pywidevine.pssh import PSSH as WV_PSSH

            wvd = self.install_dir / "WVDs" / "device.wvd"
            if not wvd.exists():
                QMessageBox.critical(self, "HellYes", f"WVD not found at:\n{wvd}")
                return

            device = Device.load(str(wvd))
            cdm = Cdm.from_device(device)
            sid = cdm.open()
            challenge = cdm.get_license_challenge(sid, WV_PSSH(pssh))

            # Handle data substitution exactly as gui.py does
            payload = challenge
            if data:
                if m := _re.search(r'"(CAQ=.*?)"', data):
                    payload = data.replace(m.group(1), _b64.b64encode(challenge).decode())
                elif m := _re.search(r'"(CAES.*?)"', data):
                    payload = data.replace(m.group(1), _b64.b64encode(challenge).decode())
                elif m := _re.search(r'=(CAES.*?)(&.*)?$', data):
                    payload = data.replace(m.group(1), _ulp.quote_plus(_b64.b64encode(challenge).decode()))

            lic_resp = _httpx.post(lic_url, data=payload, headers=headers)
            lic_resp.raise_for_status()
            lic_content = lic_resp.content
            try:
                m = _re.search(r'"(CAIS.*?)"', lic_resp.content.decode("utf-8"))
                if m:
                    lic_content = _b64.b64decode(m.group(1))
            except Exception:
                pass
            if isinstance(lic_content, str):
                lic_content = _b64.b64decode(lic_content)

            cdm.parse_license(sid, lic_content)
            keys = [f"--key {k.kid.hex}:{k.key.hex()}"
                    for k in cdm.get_keys(sid) if k.type == "CONTENT"]
            cdm.close(sid)

            key_str = " ".join(keys)
            self._hy_keys_out.setText("\n".join(keys))
            self._hy_nm_command   = (f"N_m3u8DL-RE '{mpd_url}' {key_str}"
                                      f" --save-name {vid_name} -mt -M:format=mkv:muxer=mkvmerge")
            self._hy_dash_command = (f'dash-mpd-cli --quality best --muxer-preference mkv:mkvmerge'
                                      f' {key_str} "{mpd_url}" --write-subs --output \'{vid_name}.mkv\'')
            self._hy_nm_out.setText(self._hy_nm_command)
            self._hy_dash_out.setText(self._hy_dash_command)

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "HellYes Error", f"{e}\n\n{traceback.format_exc()[:500]}")

    def _hy_download_nm(self):
        if not self._hy_nm_command:
            QMessageBox.warning(self, "HellYes", "Get keys first.")
            return
        import shlex as _sl
        subprocess.Popen(_sl.split(self._hy_nm_command),
                         cwd=str(self.install_dir),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _hy_download_dash(self):
        if not self._hy_dash_command:
            QMessageBox.warning(self, "HellYes", "Get keys first.")
            return
        import shlex as _sl
        subprocess.Popen(_sl.split(self._hy_dash_command),
                         cwd=str(self.install_dir),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        # ── Section 1: TwinVine original project ─────────────────────────────
        tv_title = QLabel("TwinVine")
        tv_title.setStyleSheet(
            f"font-size:18px;font-weight:bold;color:{C['green']};padding-bottom:4px;")
        layout.addWidget(tv_title)

        tv_sub = QLabel("VineFeeder + Envied")
        tv_sub.setStyleSheet(f"color:{C['subtext']};font-size:12px;padding-bottom:12px;")
        layout.addWidget(tv_sub)

        tv_info = QLabel(
            "TwinVine is an open-source project created by vinefeeder / A_n_g_e_l_a.\n\n"
            "It combines VineFeeder (a service scraper and download manager) with Envied "
            "(a DRM decryption and media processing engine) to download content from a "
            "range of streaming services including BBC iPlayer, ITVX, All4, My5, STV, "
            "RTE, TPTV, TVNZ, Plex and more.\n\n"
            "Full credit for the underlying technology goes to the original authors. "
            "Without their work this launcher would not exist."
        )
        tv_info.setWordWrap(True)
        tv_info.setStyleSheet(
            f"color:{C['text']};font-size:12px;line-height:1.6;padding-bottom:12px;")
        layout.addWidget(tv_info)

        tv_btn = QPushButton("TwinVine on GitHub")
        tv_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};padding:8px 20px;"
            f"border-radius:4px;font-weight:bold;border:none;")
        tv_btn.clicked.connect(lambda: webbrowser.open("https://github.com/vinefeeder/TwinVine"))
        tv_btn.setFixedWidth(200)
        layout.addWidget(tv_btn)

        # ── Divider ───────────────────────────────────────────────────────────
        layout.addSpacing(30)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{C['border']};margin:0;")
        layout.addWidget(div)
        layout.addSpacing(30)

        # ── Section 2: TwinVine Launcher ─────────────────────────────────────
        lnch_title = QLabel("TwinVine Launcher")
        lnch_title.setStyleSheet(
            f"font-size:20px;font-weight:bold;color:{C['green']};padding-bottom:4px;")
        layout.addWidget(lnch_title)

        lnch_ver = QLabel(f"Version {APP_VERSION}")
        lnch_ver.setStyleSheet(
            f"color:{C['subtext']};font-size:12px;padding-bottom:12px;")
        layout.addWidget(lnch_ver)

        lnch_info = QLabel(
            "TwinVine Launcher is a Windows GUI application that makes TwinVine "
            "accessible to everyone — no terminal, no command line, no technical "
            "knowledge required.\n\n"
            "It handles the complete setup automatically: installing Git, FFmpeg, "
            "MKVToolNix, Bento4 and all other required tools, then setting up the "
            "Python environment. Once installed, you simply click a service button, "
            "search for a show, select your episodes, and download.\n\n"
            "Features include a live download panel with progress tracking, batch "
            "mode for queuing multiple downloads, the HellYes DRM key tool, and a "
            "built-in update checker. Everything runs in one clean dark-themed window."
        )
        lnch_info.setWordWrap(True)
        lnch_info.setStyleSheet(
            f"color:{C['text']};font-size:12px;line-height:1.6;padding-bottom:12px;")
        layout.addWidget(lnch_info)

        lnch_btn = QPushButton("TwinVine Launcher on GitHub")
        lnch_btn.setStyleSheet(
            f"background:{C['green']};color:{C['bg']};padding:8px 20px;"
            f"border-radius:4px;font-weight:bold;border:none;")
        lnch_btn.clicked.connect(lambda: webbrowser.open(LAUNCHER_URL))
        lnch_btn.setFixedWidth(240)
        layout.addWidget(lnch_btn)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)
        return outer

    # ── Status helpers ────────────────────────────────────────────────────────

    def _is_installed(self) -> bool:
        return bool(self.cfg.get("installed")) and self.install_dir.exists()

    def _refresh_status(self):
        installed = self._is_installed()
        if installed:
            self._status_badge.setText("● Installed")
            self._status_badge.setStyleSheet(
                f"color:{C['green']};font-size:9px;padding:8px;")
            # Show all steps as done when already installed
            if hasattr(self, "_step_labels"):
                for k in self._step_labels:
                    self._set_step(k, "done")
            if hasattr(self, "_prog_bar"):
                self._prog_bar.setValue(100)
            if hasattr(self, "_prog_lbl"):
                self._prog_lbl.setText("✓ TwinVine is installed.")
                self._prog_lbl.setStyleSheet(f"color:{C['green']};")
        else:
            self._status_badge.setText("● Not installed")
            self._status_badge.setStyleSheet(
                f"color:{C['red']};font-size:9px;padding:8px;")
            if hasattr(self, "_step_labels"):
                for k in self._step_labels:
                    self._set_step(k, "pending")
            if hasattr(self, "_prog_bar"):
                self._prog_bar.setValue(0)
            if hasattr(self, "_prog_lbl"):
                self._prog_lbl.setText("Ready.")
                self._prog_lbl.setStyleSheet(f"color:{C['subtext']};")

    def _load_vinefeeder(self):
        """Bootstrap the VineFeeder Python environment and patch base_loader."""
        ok, reason = bootstrap_vinefeeder(self.install_dir)
        if ok:
            if patch_base_loader():
                self._populate_service_buttons()
            else:
                self._dl_status.setText(
                    "VineFeeder loaded but patch failed — check Log tab.")
        else:
            # Show the real reason in both the status banner and the log
            self._dl_status.setText(
                f"Could not load VineFeeder: {reason.splitlines()[0]}")
            self._append_log(f"[bootstrap error] {reason}")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    # High-DPI support
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = TwinVineLauncher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
