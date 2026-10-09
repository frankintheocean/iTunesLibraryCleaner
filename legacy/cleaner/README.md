# 🧹 LibraryCleaner 3.0

Clean genre tags and repair split albums in classic iTunes for Windows. This is the original Cleaner, available from the new app’s Settings.

## ✨ Features

- Normalize genres with built-in or custom rules, and import rules as CSV.
- Look up blank genres online and mark foreign-language tracks as International.
- Review split albums before merging their metadata.
- Choose playlists to include or exclude, preview runs and retry failed changes.
- Pause/resume, keep logs and undo the latest genre changes.

## 🛡️ Before running

**Live cleanup can permanently delete junk-named tracks. Undo does not restore deleted tracks.** Back up your library and use Dry run before confirming a live run. Album merges have their own review and cancellation; they are separate from cleanup undo.

Online lookups send search details to their providers. Last.fm needs your own API key; the shared key was removed. Lookup and language checks can be disabled.

## 🚀 Run from source

Requires Windows, classic iTunes, Python 3.9+ and the dependencies in `requirements.txt`. From this folder:

```powershell
pip install -r requirements.txt
python main.py
```

To build the original standalone app, run `build\build.bat`. It creates `GenreCleanup.exe`; with Inno Setup, it can also create `dist_installer\GenreCleanup-Setup.exe`. The unified installer has [separate build steps](../../BUILD.md).

## 🎚️ Use Cleaner

1. Open classic iTunes and choose your library or playlist scope.
2. Set lookup options and start with **Dry run**.
3. Review proposed genre edits and deletions before a live run.
4. Use **Pause** to keep your place. **Stop** ends the run; the next run starts again.
5. Review failures and use **Retry failed** where needed. **Undo Last Run** restores supported genre edits only.
6. For split albums, open **Merge Albums**, optionally enable online confirmation, scan, review groups and merge only genuine matches. Cancel stops after the current track.

## 💾 Settings and records

Settings controls fonts, themes, genre rules, output folders and advanced options. Custom rules run before built-in rules. The rule test warns when an earlier rule takes priority. CSV rules use `pattern,target`.

The output folder holds `changelog.txt`, `GenreCleanup_UndoLog.csv`, the processed-track cache and `GenreCleanup_Debug.log`. Settings and custom rules stay in the app folder. The default output folder is the install folder; choose a writable location. The unified app launches a writable copy under user data.

The old processed CSV is migrated to SQLite when needed. The cache has no automatic size limit; use Settings to clear it or reclaim space. Force full re-scan ignores the cache. The default deletion refresh batch is 20, adjustable under General → Advanced.

Optional `win10toast` adds native completion notifications. Without it, the app uses its fallback notification behavior.

## 📚 Further details

[Release history](CHANGELOG.md) · [Full original guide](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/v1.0/legacy/cleaner/README.md). The historical guide describes the original shared-key fallback; that key is no longer included.
