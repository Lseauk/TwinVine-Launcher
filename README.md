<div align="center">

<img src="https://raw.githubusercontent.com/Lseauk/TwinVine-Launcher/main/assets/icon.ico" width="80" alt="TwinVine Launcher">

# TwinVine Launcher

**A Windows GUI for TwinVine (VineFeeder + Envied)**

![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue?style=flat-square)
![Version](https://img.shields.io/badge/Version-1.0.0%20Beta-green?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.12%2F3.13-blue?style=flat-square)

</div>

---

## Credits

This launcher is built on top of **[TwinVine](https://github.com/vinefeeder/TwinVine)** — an open-source project created by **vinefeeder / A_n_g_e_l_a**.

TwinVine combines VineFeeder (a service scraper and download manager) with Envied (a DRM decryption and media processing engine) to download content from a range of streaming services. Full credit for the underlying technology goes to the original authors — without their work this launcher would not exist.

---

## Why This Project Exists

TwinVine is a powerful tool but requires comfort with the command line to set up and use. I wanted to make it a little easier for me to install and use — no terminal, no technical knowledge, just a clean window where you click a service, pick your episodes, and download.

TwinVine Launcher handles everything automatically: installing all required tools, setting up the Python environment, and providing a straightforward GUI that wraps the entire TwinVine workflow.

> **⚠ Windows Only** — TwinVine Launcher is a Windows 10/11 application only.

**This is not a replacement for the original project**
- For more complex downloads and use of other services I would strongly recommend the original developers project above, this project is more geared toward the 10 main services.
---

## Known Issues & Quirks

This release. The following known issues exist — contributions and bug reports are welcome.

**1. HDR/HLG not always falling back to 1080p**
Occasionally the app does not automatically switch down to 1080p when no HDR or HLG stream is available. This has been seen with some BBC content (e.g. the show Kin). If you encounter a "Selection unavailable in UHD" error, untick the **HLG** checkbox on the Home page, and try again. This appears to be service-specific and your experience may vary.

**2. Real-time animation in the download panel**
This has been improved see Changelog v1.0.3

---

## Pre-requirements

Before installing, you will need:

- **Windows 10 or 11** (64-bit)
- **Python 3.12 or 3.13 or 3.14** — download the Windows installer (64-bit) from the official releases page:
  - [Python 3.14](https://www.python.org/downloads/release/python-3145/)
  - [Python 3.13](https://www.python.org/downloads/release/python-3130/)
  - [Python 3.12](https://www.python.org/downloads/release/python-3120/)
  
  - During installation tick **"Add Python to PATH"**
  - Do **not** use the Microsoft Store version of Python or the install manager from Python at this time.

Everything else (Git, FFmpeg, MKVToolNix, Bento4, and all Python packages) is downloaded and installed automatically by the launcher.

- **Services Credentials** - Some services like All4 require login details, username/password before they will download, please see the help page for more details after install.
---

## Installation

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

## Please check the help page of the app for more details on downloading 

### Batch Mode

Toggle **Batch Mode** on to queue episodes from multiple shows before downloading them all at once. The sidebar shows how many episodes are queued. Click **Run Batch** when ready.

---

## Screenshots

### First Run
![First Run](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/01-%20First%20Run.png?raw=true)

### Install / Update
![Initial Install](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/02%20-%20Inital%20Install.png?raw=true)

### Install Complete
![Install Complete](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/03%20-%20Install%20Complete.png?raw=true)

### Ready to Use
![Ready To Use](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/04%20-%20Ready%20To%20Use.png?raw=true)

### Searching for a Show
![Show Selection](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/05%20-%20Show%20Selection.png?raw=true)

### Service Button Actions
![Service Button Action](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/Service%20Button%20Action.png?raw=true)

### Series Selection
![Series Selection](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/06%20-%20Series%20Selection.png?raw=true)

### Episode Selection
![Episode Selection](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/07%20-%20Episode%20Selection.png?raw=true)

### Quality selection, Subtitles, Slow mode
![Quality Selection](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/Quality.png?raw=true)

### Track Selection for URL Downloads
![Fetch Tracks 01](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/Fetch%20Tracks%2001.png?raw=true)
![Fetch Tracks 02](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/Fetch%20Tracks%2002.png?raw=true)

### Download in Progress
![Download Panel](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/08%20-%20Download%20Panel.png?raw=true)

### Download Complete
![Download Complete](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/09%20-%20Download%20Complete.png?raw=true)

### Batch Mode
![Batch Mode 1](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/10%20-%20Batch%20Mode%20-%2001.png?raw=true)
![Batch Mode 2](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/11%20-%20Batch%20Mode%20-%2002.png?raw=true)
![Batch Mode 3](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/12%20-%20Batch%20Mode%20-%2003.png?raw=true)
![Batch Mode Running](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/13%20-%20Batch%20Mode%20Run.png?raw=true)
![Batch Mode Complete](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/14%20-%20Batch%20Mode%20Complete.png?raw=true)

### HellYes — Manual DRM Key Extraction
![HellYes](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/HellYes.png?raw=true)

### Help
![Help](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/Help.png?raw=true)

### About
![About](https://github.com/Lseauk/TwinVine-Launcher/blob/main/images/About.png?raw=true)

---

## Supported Services

ALL4 · BBC iPlayer · ITVX · MY5 · PLEX · RTE · STV · TPTV · TVNZ · U

---

## Building from Source

See [TwinVine Launcher — Setup & Installation.md](https://github.com/Lseauk/TwinVine-Launcher/blob/main/TwinVine%20Launcher%20%E2%80%94%20Setup%20%26%20Installation.md) for instructions on building the installer exe from source.

---

## Contributing & Feedback

TwinVine Launcher is in Beta and has so far only been tested by a small number of users. If you find a bug, have a suggestion, or want to contribute, please:

- **Open an issue** on the [GitHub Issues](https://github.com/Lseauk/TwinVine-Launcher/issues) page — bug reports, feature requests, and general feedback are all welcome
- **Submit a pull request** if you have a fix or improvement you'd like to contribute
- **Test on different services** — not all supported services have been fully tested, so reports on what works and what doesn't are particularly helpful

As this is a Beta release, there will likely be rough edges. Your feedback helps make it better for everyone.

---

## Disclaimer

This tool is intended for personal use only. You are responsible for ensuring you have the right to download any content you access. The authors of TwinVine Launcher take no responsibility for how this software is used.
