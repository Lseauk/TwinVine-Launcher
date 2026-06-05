# TwinVine Launcher — Setup & Installation

## Running the app (no build required)

1. Install Python 3.12 or 3.13 from https://python.org
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

### Step 1 — Install PyInstaller into the TwinVine venv

Open a terminal in the `twinvine-launcher` folder and run:

```powershell
& "C:\Users\YourName\.local\bin\uv.exe" pip install pyinstaller --python "C:\Users\YourName\Downloads\twinvine-launcher\TwinVine\.venv\Scripts\python.exe"
```

> Replace `YourName` with your Windows username. The `uv.exe` path is where uv
> was installed during the TwinVine tools setup.

---

### Step 2 — Build the exe with PyInstaller

Still in the `twinvine-launcher` folder, run, remember to change `YourName` with your Windows username:

```powershell
& "C:\Users\YourName\Downloads\twinvine-launcher\TwinVine\.venv\Scripts\python.exe" -m PyInstaller twinvine_launcher.spec
```

This takes 2–5 minutes. Output appears at:

```
twinvine-launcher\dist\TwinVineLauncher.exe
```

> You can ignore the warnings about missing modules — these are optional dependencies
> that are not needed for the launcher to function.

---

### Step 3 — Build the installer with Inno Setup

1. Open **Inno Setup Compiler**
2. Go to **File → Open** and select `twinvine_launcher.iss`
3. Press **F9** (or click **Build → Compile**)
4. The installer appears at:

```
twinvine-launcher\installer_output\TwinVineLauncher-Setup-1.0.0-BETA.exe
```

---

### Step 4 — Install on another machine

Copy `TwinVineLauncher-Setup-1.0.0-BETA.exe` to the target machine and run it.
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
  twinvine_launcher.spec        ← PyInstaller build spec
  twinvine_launcher.iss         ← Inno Setup installer script
  assets\
    icon.ico                    ← app icon
  dist\
    TwinVineLauncher.exe        ← built by PyInstaller (Step 2)
  installer_output\
    TwinVineLauncher-Setup-1.0.0-BETA.exe  ← built by Inno Setup (Step 3)
  TwinVine\                     ← created by Install / Update
    .venv\
    packages\
    Downloads\
```
