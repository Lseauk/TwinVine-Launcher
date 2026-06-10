# TwinVine Launcher — V1.0.3 Changelog

## Bug Fixes

### Episode Label — SS1 Display Error
Episodes were occasionally showing a double `S` prefix (e.g. `SS1 · Episode 1`) instead of the correct `S1 · Episode 1`. 

### Selection Panel — Small Results Box
When the first search of a session returned only a small number of results (e.g. 2–3 items), the selection panel would size itself to fit those results and remain that small for all subsequent searches — making episode and series selection difficult. Fixed by setting a minimum height on the selection scroll area so the panel is always a usable size regardless of how many results are returned.

### Service Buttons — Collapsing When Results Panel Opens
Adjusting spacing between the service buttons area and the selection results panel was causing the service buttons box to collapse into a scroll list when results were shown. Fixed by setting a fixed height on the service buttons container so it cannot be compressed by the layout regardless of what appears below it.

---

## Download Progress

### Merging Phase & Multiplexing Banner Messaging
Added a Merging video & Multiplexing status timer banners, to give a better feedback on what is happening when downloading. 


---

## Cancel Download

### Processes Not Terminating
Clicking Cancel would display the cancellation message but the download would continue running in the background.
Now fixed

### Temp Files Left Behind After Cancel
Subtitle files and partial video segments were sometimes being left in the `Temp` folder after a cancelled download. 
The launcher now clears the contents of the `Temp` folder after every cancelled download.