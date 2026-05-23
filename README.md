<div align="center">

<img src="https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/assets/icon.ico" width="80" alt="TwinVine Launcher">

# TwinVine Launcher

**A Windows GUI for TwinVine (VineFeeder + Envied)**

![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0%20BETA-green?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.12%2F3.13-blue?style=flat-square)

</div>

---

## Credits

This launcher is built on top of **[TwinVine](https://github.com/vinefeeder/TwinVine)** — an open-source project created by **vinefeeder / A_n_g_e_l_a**.

TwinVine combines VineFeeder (a service scraper and download manager) with Envied (a DRM decryption and media processing engine) to download content from a range of streaming services. Full credit for the underlying technology goes to the original authors — without their work this launcher would not exist.

---

## Why This Project Exists

TwinVine is a powerful tool but requires comfort with the command line to set up and use. I wanted to make it accessible to everyone — no terminal, no technical knowledge, just a clean window where you click a service, pick your episodes, and download.

TwinVine Launcher handles everything automatically: installing all required tools, setting up the Python environment, and providing a straightforward GUI that wraps the entire TwinVine workflow.

> **⚠ Windows Only** — TwinVine Launcher is a Windows 10/11 application only.

---

## Pre-requirements

Before installing, you will need:

- **Windows 10 or 11** (64-bit)
- **Python 3.12 or 3.13** from [python.org](https://www.python.org/downloads/)
  - During installation tick **"Add Python to PATH"**
  - Do **not** use the Microsoft Store version of Python

Everything else (Git, FFmpeg, MKVToolNix, Bento4, and all Python packages) is downloaded and installed automatically by the launcher.

---

## Installation

### Option A — Installer (recommended)

Download `TwinVineLauncher-Setup-1.0.0-BETA.exe` from the [Releases](https://github.com/Lseauk/TwinVine-Launcher/releases) page and run it. The installer will set up the launcher in your Downloads folder and add a Start Menu entry.

### Option B — Zip

Download and unzip `twinvine-launcher.zip`, then double-click `TwinVine Launcher.bat` to launch.

---

Once the app opens, click **Install / Update → Install TwinVine Tools** and wait for the setup to complete. This downloads around 500MB of tools and takes 2–5 minutes depending on your connection. Progress is shown in the Log tab.

---

## How to Use

There are two ways to start a download:

**Option 1 — Search box first**
Type a keyword or paste a URL into the **URL or Search** box, then click a service button. The search runs immediately against that service.

**Option 2 — Service button first**
Click a service button directly and choose from four actions:
- **Search by keyword** — type a show name to find it
- **Greedy Search by URL** — paste a show page URL to fetch all available content
- **Download by URL** — paste a direct episode URL to download immediately
- **Browse by Category** — browse the service's categories

Either way, once results appear:

3. Select the series you want from the list
4. Tick the episodes you want and click Confirm
5. The download begins automatically — progress is shown in the panel below

### Batch Mode

Toggle **Batch Mode** on to queue episodes from multiple shows before downloading them all at once. The sidebar shows how many episodes are queued. Click **Run Batch** when ready.

---

## Screenshots

### First Run
![First Run](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/01-_First_Run.png)

### Install / Update
![Initial Install](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/02_-_Inital_Install.png)

### Install Complete
![Install Complete](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/03_-_Install_Complete.png)

### Ready to Use
![Ready To Use](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/04_-_Ready_To_Use.png)

### Searching for a Show
![Show Selection](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/05_-_Show_Selection.png)

### Service Button Actions
![Service Button Action](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/Service_Button_Action.png)

### Series Selection
![Series Selection](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/06_-_Series_Selection.png)

### Episode Selection
![Episode Selection](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/07_-_Episode_Selection.png)

### Download in Progress
![Download Panel](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/08_-_Download_Panel.png)

### Download Complete
![Download Complete](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/09_-_Download_Complete.png)

### Batch Mode
![Batch Mode 1](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/10_-_Batch_Mode_-_01.png)
![Batch Mode 2](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/11_-_Batch_Mode_-_02.png)
![Batch Mode 3](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/12_-_Batch_Mode_-_03.png)
![Batch Mode Running](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/13_-_Batch_Mode_Run.png)
![Batch Mode Complete](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/14_-_Batch_Mode_Complete.png)

### HellYes — Manual DRM Key Extraction
![HellYes](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/HellYes.png)

### Help
![Help](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/Help.png)

### About
![About](https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/images/About_Page.png)

---

## Supported Services

ALL4 · BBC iPlayer · ITVX · MY5 · PLEX · RTE · STV · TPTV · TVNZ · U

---

## Building from Source

See [TwinVine Launcher — Setup & Installation.md](TwinVine%20Launcher%20%E2%80%94%20Setup%20%26%20Installation.md) for instructions on building the installer exe from source.

---

## Disclaimer

This tool is intended for personal use only. You are responsible for ensuring you have the right to download any content you access. The authors of TwinVine Launcher take no responsibility for how this software is used.
