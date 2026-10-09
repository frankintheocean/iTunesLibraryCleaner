# 🎵 iTunes Manager 3.1.1

## 🐛 Fixes

- Fetch Last.fm pictures through checked redirects and decode valid binary image responses.
- Recover missing profile pictures, song and album covers. Use public Last.fm artist photos when the API has none.
- Retry failed pictures with Refresh and use sharper profile thumbnails.
- Measure actual scan speed before showing time left. Large live scans no longer inherit a short estimate from defaults or tiny XML scans.
- Show the saving phase clearly until the library is ready.

## 🧭 Choose your library

The library picker appears only in **Overview**. That selection applies to every library tool. Libraries still lets you add, open and remove collections.

## 📥 Downloads

Choose the **Windows installer**, **complete Windows app ZIP** or **source ZIP**. Extract the whole app ZIP before opening `iTunes Manager.exe`. Settings and backups keep the same AppData folder. Close the old app before upgrading.

Windows 10/11 x64 and classic iTunes are required for live editing. The installer is unsigned. Picture availability depends on Last.fm. Automated checks use image and page fixtures; a real-account picture check and a fresh large live-iTunes scan remain pending. See [Last.fm](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/LASTFM.md), [test results](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/main/docs/VALIDATION.md) and the attached Windows report.
