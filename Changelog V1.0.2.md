# TwinVine Launcher — What's New

> A Windows GUI wrapper for [TwinVine / Envied](https://github.com/vinefeeder/TwinVine) by vinefeeder.
> Source: [Lseauk/TwinVine-Launcher](https://github.com/Lseauk/TwinVine-Launcher)

---

## New Features

### Download Options Panel
After selecting episodes, a Download Options panel now appears before the download begins, giving you control over:

- **Quality** — Choose Best available, 2160p, 1080p, or 720p
- **No subtitles** — Skip subtitle downloads entirely
- **Slow mode** — Adds a randomised delay between episode downloads, useful if a service starts throttling you. Tick the box and set your own minimum and maximum wait time in seconds (defaults to 10–60s)

### Download by URL Panel
Paste any episode or series URL directly into the search box and click a service button to open the URL Download panel. From here you can:

- Click **Download** immediately for the best available quality
- Click **Fetch Tracks** to see every resolution the stream actually has available, then pick the one you want from a dropdown before downloading
- Tick **No subtitles** or **Slow mode** without going through the full search flow

### Choose Action Panel — Close Button
A **✕ Close** button has been added to the Choose Action panel (the one that appears after clicking a service button). You can now dismiss it without having to pick an action.

---

## Bug Fixes

### HLG retry now works without restarting the app
Previously, if a download failed with a "Selection unavailable in UHD" error, unticking the HLG checkbox and retrying would still fail — you had to restart the app. This is now fixed. Untick HLG and click the service button again and it will work.

### Stale service state between attempts
Related to the above — the service module was being reused between attempts, carrying over state from the previous failed run. Each attempt now gets a completely fresh module load.

### URL panel Cancel button no longer shows the wrong screen
Clicking Cancel in the URL Download panel previously brought up the Choose Action screen unexpectedly. It now correctly returns to the home state.

### Hung at sync
Fixed

### uv was locked / in use after closing
Fixed

---

## Python 3.14 Compatibility

The installer now automatically patches the TwinVine packages to work with Python 3.14:

- Removes the Python version ceiling that blocked installation on 3.14
- Replaces `brotli` with `brotlicffi` (brotli requires C++ build tools on 3.14; brotlicffi does not)
- Patches `utilities.py` to add `visit_Constant` alongside `visit_Num` (`ast.Num` was removed in Python 3.14)

All patch steps create `.bak` backups of the original files before modifying them.

---

## Install & Help Page Updates

- The install confirmation popup now accurately lists which tools are installed outside the TwinVine folder (`C:\Tools\bin` for media tools, `~/.local/bin` for uv, system-wide for Git for Windows)
- The Help page has been rewritten — to offer a clearer structure and more information about what gets installed where and how to fully uninstall and any files changes
- Added a clickable link to the BBC UHD content page for guidance on 2160p downloads
- Fixed "Check for Updates" — it now correctly checks the TwinVine Launcher repository for new versions

---

## Known Limitations

- **2160p from BBC iPlayer** — Best available and Fetch Tracks do not always find the 2160p stream. If you know a 2160p version exists, select 2160p explicitly from the Quality dropdown, or use the exact programme title as listed on the [BBC UHD content page](https://www.bbc.co.uk/iplayer/help/questions/programme-availability/uhd-content)
- **Slow mode** — The delay is applied between episodes, not between individual segment downloads within a single episode
- **More complex downloads and other services** - Outside of the main 10 services listed in the app, I'm not able to confirm which other services may work via the terminal, so I advice using the original delevopers version and not this one.

