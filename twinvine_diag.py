"""
TwinVine Launcher - Diagnostic Tool
Run this on both PCs and share the output so we can compare.

Usage: python twinvine_diag.py
Output saved to: twinvine_diag.txt (in the same folder)
"""
import sys
import os
import subprocess
import shutil
import platform
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
OUT  = HERE / "twinvine_diag.txt"

lines = []

def log(msg=""):
    print(msg)
    lines.append(msg)

def section(title):
    log()
    log("=" * 60)
    log(f"  {title}")
    log("=" * 60)

def run(cmd, shell=False):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=10, shell=shell)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"ERROR: {e}"


log(f"TwinVine Diagnostic Report")
log(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── Windows version ───────────────────────────────────────────────────────────
section("Windows Version")
log(f"platform.version()    : {platform.version()}")
log(f"platform.release()    : {platform.release()}")
log(f"platform.machine()    : {platform.machine()}")
log(f"platform.processor()  : {platform.processor()}")
log(run(["powershell", "-Command",
         "(Get-WmiObject Win32_OperatingSystem).Caption + ' ' + "
         "(Get-WmiObject Win32_OperatingSystem).Version"]))


# ── Python installations ──────────────────────────────────────────────────────
section("Python Installations")
log(f"sys.executable        : {sys.executable}")
log(f"sys.version           : {sys.version}")
log(f"sys.prefix            : {sys.prefix}")
log(f"sys.base_prefix       : {sys.base_prefix}")

log("\n-- where python --")
log(run(["where", "python"]))

log("\n-- where pythonw --")
log(run(["where", "pythonw"]))

log("\n-- where py --")
log(run(["where", "py"]))


# ── pythonw.exe file comparison ───────────────────────────────────────────────
section("pythonw.exe Analysis")

py_path  = shutil.which("python")
pyw_path = shutil.which("pythonw")

if py_path and pyw_path:
    py_p  = Path(py_path)
    pyw_p = Path(pyw_path)
    log(f"python.exe   : {py_p}")
    log(f"pythonw.exe  : {pyw_p}")
    try:
        py_size  = py_p.stat().st_size
        pyw_size = pyw_p.stat().st_size
        log(f"python.exe size  : {py_size:,} bytes")
        log(f"pythonw.exe size : {pyw_size:,} bytes")
        log(f"Sizes match      : {py_size == pyw_size}  "
            f"({'BROKEN - same binary' if py_size == pyw_size else 'OK - different binaries'})")
    except Exception as e:
        log(f"Size check error: {e}")
    log(f"Same directory   : {py_p.parent == pyw_p.parent}")
else:
    log(f"python.exe  found: {py_path is not None} ({py_path})")
    log(f"pythonw.exe found: {pyw_path is not None} ({pyw_path})")


# ── venv pythonw analysis ─────────────────────────────────────────────────────
section("TwinVine Venv pythonw Analysis")

venv_root = HERE / "TwinVine" / ".venv"
if venv_root.exists():
    venv_py  = venv_root / "Scripts" / "python.exe"
    venv_pyw = venv_root / "Scripts" / "pythonw.exe"
    log(f"venv python.exe  : {venv_py} (exists={venv_py.exists()})")
    log(f"venv pythonw.exe : {venv_pyw} (exists={venv_pyw.exists()})")
    if venv_py.exists() and venv_pyw.exists():
        try:
            py_size  = venv_py.stat().st_size
            pyw_size = venv_pyw.stat().st_size
            log(f"venv python.exe size  : {py_size:,} bytes")
            log(f"venv pythonw.exe size : {pyw_size:,} bytes")
            log(f"Sizes match           : {py_size == pyw_size}  "
                f"({'BROKEN - same binary' if py_size == pyw_size else 'OK - different binaries'})")
        except Exception as e:
            log(f"Size check error: {e}")

    # Check pyvenv.cfg
    cfg = venv_root / "pyvenv.cfg"
    if cfg.exists():
        log(f"\npyvenv.cfg contents:")
        for line in cfg.read_text().splitlines():
            log(f"  {line}")
else:
    log("TwinVine venv not found (not installed yet)")


# ── uv Python cache ───────────────────────────────────────────────────────────
section("uv Python Cache")

for base_env in ["APPDATA", "LOCALAPPDATA"]:
    base = os.environ.get(base_env, "")
    if not base:
        continue
    uv_python = Path(base) / "uv" / "python"
    log(f"\n{base_env}\\uv\\python: {uv_python} (exists={uv_python.exists()})")
    if uv_python.exists():
        for d in sorted(uv_python.glob("cpython-*-windows-x86_64-none")):
            pyw = d / "pythonw.exe"
            py  = d / "python.exe"
            if pyw.exists() and py.exists():
                try:
                    py_sz  = py.stat().st_size
                    pyw_sz = pyw.stat().st_size
                    status = "OK - real pythonw" if py_sz != pyw_sz else "BROKEN - same binary"
                    log(f"  {d.name}")
                    log(f"    python.exe   : {py_sz:,} bytes")
                    log(f"    pythonw.exe  : {pyw_sz:,} bytes")
                    log(f"    Status       : {status}")
                except Exception as e:
                    log(f"  {d.name} - error: {e}")


# ── Tools ─────────────────────────────────────────────────────────────────────
section("Media Tools (C:\\Tools\\bin)")

tools_bin = Path("C:/Tools/bin")
if tools_bin.exists():
    exes = sorted(p.name for p in tools_bin.glob("*.exe"))
    log(f"Found {len(exes)} .exe files:")
    for exe in exes:
        log(f"  {exe}")
else:
    log("C:\\Tools\\bin does not exist")

mkv = Path("C:/Program Files/MKVToolNix/mkvmerge.exe")
log(f"\nMKVToolNix mkvmerge.exe: {'FOUND' if mkv.exists() else 'NOT FOUND'} ({mkv})")

se = Path("C:/Tools/SubtitleEdit/SubtitleEdit.exe")
log(f"SubtitleEdit.exe       : {'FOUND' if se.exists() else 'NOT FOUND'} ({se})")


# ── Environment variables ─────────────────────────────────────────────────────
section("Relevant Environment Variables")
for var in ["PATH", "PYTHONPATH", "APPDATA", "LOCALAPPDATA", "USERPROFILE"]:
    val = os.environ.get(var, "(not set)")
    if var == "PATH":
        # Split PATH for readability
        log("PATH entries:")
        for p in val.split(os.pathsep):
            log(f"  {p}")
    else:
        log(f"{var}: {val}")


# ── PyQt6 ─────────────────────────────────────────────────────────────────────
section("PyQt6 Installation")
try:
    import PyQt6
    import PyQt6.QtCore
    log(f"PyQt6 version    : {PyQt6.QtCore.PYQT_VERSION_STR}")
    log(f"Qt version       : {PyQt6.QtCore.QT_VERSION_STR}")
    log(f"PyQt6 location   : {PyQt6.__file__}")
except ImportError as e:
    log(f"PyQt6 NOT found  : {e}")


# ── uv ────────────────────────────────────────────────────────────────────────
section("uv")
log(run(["uv", "--version"]))
log(f"uv location: {shutil.which('uv')}")


# ── Save output ───────────────────────────────────────────────────────────────
output = "\n".join(lines)
OUT.write_text(output, encoding="utf-8")
print()
print(f"{'='*60}")
print(f"Diagnostic saved to: {OUT}")
print(f"Please share this file.")
print(f"{'='*60}")
