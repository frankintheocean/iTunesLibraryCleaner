# 🚧 Known limits

This is a working integration and a Windows testing preview. It does not include every requested feature or claim full production readiness.

## 🪟 Platform checks

The real source-level iTunes test passed on version 12.13.11.1. A Windows Server 2022 build passed backend, installer, packaged app, repair and uninstall/reinstall checks.

Still needed: live editing through the installed app; Windows 10/11 clean-machine tests; open iTunes dialogs and restarts; locked files, long paths, network shares and disconnected drives; multiple monitors and display scaling; manual taskbar and shortcut checks; and code signing.

Linux cannot build the Windows Python bundle with PyInstaller. Source ZIPs and unsigned Windows installers are separate downloads. Repair uses reinstallation; there is no separate Repair screen or optional settings-delete action.

## 🏛️ Features kept in the original tools

Cleaner retains its detailed cleanup options, cache maintenance, lookup credentials, force-rescan options, notifications, failure retries and old undo logs.

Consolidator retains advanced exclusions, restore points, growth and change reports, audio preview, rebuild/undo and live duplicate removal. These original screens remain available in Settings; not all have been rebuilt in the new interface. Their irreversible actions still use their original confirmations and backups.

## 🧩 Features not complete in the new interface

- Audio matching that tolerates offsets or small differences beyond optional exact Chromaprint matches; quality-based matching across libraries beyond the original rules and file hashes.
- Duplicate-artwork cleanup, empty-folder removal and automatic detection of disconnected drives.
- Importing Apple Music’s private database, full custom-variable folder templates, playlist comparison and live playlist repair.
- Automatic conversion of all old history and caches, managed backup/restore of new app state, dependent jobs and Retry All.
- Progress saved midway through a file, transfer-speed and time-left estimates, translations, update/notification settings, clipboard actions and drag-and-drop.

One worker applies changes, with cancellation between items. Scans reuse cached tags based on size and modification time but still walk folders. Matching uses library snapshots in memory; paged tables do not mean the whole scan runs from disk alone.

## ✍️ Tags and undo

Undo works for supported live fields and file tags only when their values still match the app’s last write. Full-file backups support manual recovery and artwork undo.

Artwork replacement supports MP3 with ID3, MP4/M4A and FLAC. Other formats may be view-only. Other tag fields depend on Mutagen’s support; unsupported edits fail without bypassing checks. A tag scan is not a full audio-decoding test. Missing/offline statuses are observations, not instructions to delete files.

## 📁 Moving files

Moving or quarantining files may break iTunes references. The new service does not silently delete live duplicates or rebuild Apple’s private databases. Use export/import/relink steps. Advanced original rebuild and sync actions remain choices in the original tools.

See [feature coverage](FEATURE_PARITY.md) for the exact boundaries.
