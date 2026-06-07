# TwinVine Launcher — Setup & Installation

## Running the app (no build required)

1. Install Python 3.12, 3.13 or 3.14 from https://python.org
   - Tick **"Add Python to PATH"** during installation
   - Do **not** use the Microsoft Store version
2. Unzip `twinvine-launcher.zip` to a folder of your choice
3. Double-click `TwinVine Launcher.bat` to launch the app
   - PyQt6 installs automatically on first run if missing
   - A brief terminal window may appear while the app starts — this is normal
4. Click **Install / Update → Install TwinVine Tools** to complete the setup

> **Note:** Always use `TwinVine Launcher.bat` to run the app when launching from source.

---

## Building a distributable installer (.exe)

This produces a standalone `TwinVineLauncher-Setup.exe` that can be installed on
any Windows 10/11 machine — no Python, no bat file, no terminal window required.

### Prerequisites

- A working TwinVine installation (complete the steps above first)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) installed on your build machine

---

### Step 1 — Build the exe with PyInstaller

Open the app, go to **Install / Update** and click **🔨 Build EXE**.

This will automatically install PyInstaller into the TwinVine venv and build the executable for you — no manual commands or spec file required. The process takes 2–5 minutes.

Output appears at:

```
twinvine-launcher\dist\TwinVineLauncher.exe
```

> You can ignore any warnings about missing modules — these are optional dependencies
> not needed for the launcher to function.

---

### Step 2 — Build the installer with Inno Setup

1. Open **Inno Setup Compiler**
2. Go to **File → Open** and select `twinvine_launcher.iss`
3. Press **F9** (or click **Build → Compile**)
4. The installer appears at:

```
twinvine-launcher\installer_output\TwinVineLauncher-Setup-1.0.2.exe
```

---

### Step 3 — Install on another machine

Copy `TwinVineLauncher-Setup-1.0.2.exe` to the target machine and run it.
The installer wizard will:
- Install `TwinVineLauncher.exe` to `Downloads\TwinVine Launcher` by default
  (the user can change this location during install)
- Add a Start Menu entry
- Optionally add a desktop shortcut

On first launch, click **Install / Update → Install TwinVine Tools** to complete setup.

> **Note:** The installer only contains the launcher exe. The TwinVine tools
> (Git, FFmpeg, MKVToolNix etc.) are downloaded automatically on first run.

---

## Folder layout

```
twinvine-launcher\
  TwinVine Launcher.bat         ← use this to run from source
  twinvine_launcher.py          ← source code
  twinvine_launcher.iss         ← Inno Setup installer script
  assets\
    icon.ico                    ← app icon
  dist\
    TwinVineLauncher.exe        ← built by Step 1 (Build EXE button)
  installer_output\
    TwinVineLauncher-Setup-1.0.2.exe  ← built by Step 2 (Inno Setup)
  TwinVine\                     ← created by Install / Update
    .venv\
    packages\
    Downloads\
```
