# TwinVine Launcher — Build Guide

## Option A: Run directly (current working method)

1. Install Python 3.13 from https://python.org (tick "Add to PATH")
2. Double-click `TwinVine Launcher.bat`
   - PyQt6 installs automatically on first run
   - App opens, click Install to set up TwinVine

Note: a brief terminal window may appear on some machines when starting via the bat.

---

## Option B: Compile to .exe (no terminal window, ever)

A compiled exe uses the Windows GUI subsystem — no terminal window on any machine.
The exe only bundles PyQt6. The TwinVine venv is still loaded from disk at runtime.

### Step 1 — Install build dependencies

```
pip install pyinstaller PyQt6 requests
```

### Step 2 — Build

```
cd twinvine-launcher
pyinstaller twinvine_launcher.spec
```

This takes 2-5 minutes. Output: `dist\TwinVine Launcher.exe`

### Step 3 — Deploy

Copy `dist\TwinVine Launcher.exe` next to `twinvine_launcher.py`.
Users double-click the exe — no bat file needed, no terminal window, ever.

The exe auto-detects the `TwinVine` subfolder next to itself for the venv.

### Size

The exe will be ~60-80 MB (bundles Python runtime + PyQt6).
No Python installation required on the target machine.

---

## Folder layout

```
twinvine-launcher\
  TwinVine Launcher.exe     <- compiled exe (or use the .bat)
  TwinVine Launcher.bat     <- bat fallback (needs Python installed)
  twinvine_launcher.py      <- source
  TwinVine\                 <- created by Install tab
    .venv\
    packages\
```
