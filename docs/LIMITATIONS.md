# 🚧 Known limits

This is a working integration and a Windows testing preview. Automated test success is not a claim that every live iTunes workflow has been manually tested.

## 🪟 Platform checks

The real source-level iTunes test passed on version 12.13.11.1. A Windows Server 2022 build passed backend, installer, packaged-app, repair, and uninstall/reinstall checks.

Still needed: live editing through the installed app; Windows 10/11 clean-machine tests; open iTunes dialogs and restarts; locked files, long paths, network shares and disconnected drives; multiple monitors and display scaling; manual taskbar and shortcut checks; and code signing.

Linux cannot build the Windows Python bundle with PyInstaller. Source ZIPs and unsigned Windows installers are separate downloads. Repair uses reinstallation; there is no separate Repair screen or optional settings-delete action.

## 🏛️ Features kept in the original tools

Cleaner retains detailed cleanup options, cache maintenance, lookup credentials, force-rescan options, notifications, failure retries, and old undo logs.

Consolidator retains advanced exclusions, restore points, growth and change reports, audio preview, rebuild/undo, and live duplicate removal. These original screens remain available in Settings; not all have been rebuilt in the new interface. Their irreversible actions still use their original confirmations and backups.

## 🧩 Features not complete in the new interface

- 🎚️ Audio matching that tolerates offsets or small differences beyond optional exact Chromaprint matches, and quality-based matching across libraries beyond the original rules and file hashes.
- 🖼️ Duplicate-artwork cleanup, empty-folder removal, and automatic detection of disconnected drives.
- 🍎 Importing Apple Music's private database, full custom-variable folder templates, playlist comparison, and live playlist repair.
- 🔁 Full migration of all old history/caches, managed backup/restore of the new app state, dependent jobs, and Retry All.
- 📊 Progress saved midway through a file, transfer-speed measurements, translations, and update/notification settings.
- 🏛️ Some advanced rebuild, sync, and cleanup options remain in the original Cleaner and Consolidator tools rather than the new interface.

The new Current Library already supports in-app copy/paste selection and playlist reordering can use drag-and-drop. Those are not missing features; playlist reorder still depends on the safe methods exposed by classic iTunes COM.

## 🧩 Missing Tracks and playlist pictures

Missing Tracks reads the entire indexed library in batches and uses album track-number/count metadata to infer likely gaps. It cannot infer tracks when those metadata are absent or incorrect, and it does not prove that a file is physically missing from every possible location.

Custom playlist pictures are saved and displayed in iTunes Manager. Classic iTunes COM and standard library XML do not expose a consistent playlist-picture write method, so the app only attempts live synchronization if the installed COM object exposes a suitable setter. Song artwork is never changed to simulate a playlist picture.

## ✍️ Tags and undo

Undo works for supported live fields and file tags only when their values still match the app's last write. Full-file backups support manual recovery and artwork undo.

Artwork replacement supports MP3 with ID3, MP4/M4A, and FLAC. Other formats may be view-only. Other tag fields depend on Mutagen support; unsupported edits fail without bypassing checks. A tag scan is not a full audio-decoding test. Missing/offline statuses are observations, not instructions to delete files.

## 📁 Moving files

Moving or quarantining files may break iTunes references. The new service does not silently delete live duplicates or rebuild Apple's private databases. Use export/import/relink steps. Advanced original rebuild and sync actions remain choices in the original tools.

## ⏱️ Queue and artwork

Queue estimates count down using previous task times and progress. They pause with the task and say “Taking longer than estimated” if work runs past the estimate. They cannot predict every slow file or iTunes call. Artwork loading can fall back to an icon for missing or unsupported covers. The new Windows live-artwork path still needs a real iTunes check; Linux tests cover embedded artwork.

## ⚡ Speed and live identity

Version 3 reduces repeated parsing, search work, and playlist ID calls. Real iTunes speed still depends on its library, storage, and open dialogs. A live scan reads the actual COM library and checks its identity and track count at both ends; it does not substitute a guessed XML file. A changed library or missing track ID is reported without writing to another song. Full snapshots are still saved after verified metadata changes, so a one-song edit is not always instant.

## 🎧 Last.fm and large scans

Last.fm is an optional, read-only public-data connection. It needs your API key, username, and internet access. Private-data authorization and scrobbling are not supported. Last.fm may not supply some pictures. When its API has no artist photo, the app tries the public Last.fm page; site access or page changes can still prevent a picture. The key is stored locally without database encryption; disconnect removes it. See the [Last.fm guide](LASTFM.md).

The extended live-scan deadline is tested with simulated timing and 48,000 generated track IDs. A fresh large-library scan against real classic iTunes still needs Windows user validation. The scan stops after 15 minutes without forward progress or a six-hour total limit. Live metadata write deadlines and field records remain unchanged.
