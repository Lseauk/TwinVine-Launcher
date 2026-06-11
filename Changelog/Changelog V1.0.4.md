# TwinVine Launcher — V1.0.4 Changelog

## Bug Fixes

### Slow Mode Not Being Passed to Batch Mode

Fixed an issue where the **Slow Mode** and **No Subtitles** options were not being passed correctly when using **Batch Mode**.

Depending on your system and connection speed, large batch downloads could sometimes crash or hang, so **Slow Mode** has now been added as an available option for Batch Mode.

### HDR/HLG Not Always Falling Back to 1080p or "Selection Unavailable in UHD" Error

Fixed an issue where the app did not always automatically fall back to the SDR stream when encountering the **"Selection unavailable in UHD"** error.

The app will now automatically retry and download the SDR stream when this occurs, so there is no longer any need to manually tick or untick the **HLG** option.

The **HLG** checkbox has been left in place for now to ensure compatibility while monitoring for any additional stream download issues that may arise.

## Minor UI Improvements

### Status Bar

The status bar will now display **"Busy - Download in Progress"** while a download is in progress.

### Batch Mode Toggle

The **Batch Mode** toggle switch will now automatically return to the **Off** position once a batch download run has completed.
