# 🧩 Feature coverage

Both uploaded projects were checked before integration. `source-inventory.json` records their files, checksums, imports and Python symbols. The Consolidator upload was a ZIP named `.7z`; Cleaner was a true 7z archive. Their tools remain in `legacy/`.

| Feature | Where to use it |
| --- | --- |
| Genre rules, custom order, CSV import and rule tests | Cleaner and Settings reuse the original rule engine |
| Live genre and metadata editing | Shared live writer handles metadata, genre cleanup and album merging |
| Split-album detection and optional online checks | Original detection with previews and shared metadata edits |
| Unknown-genre and language lookups | Original lookup, enabled only when selected |
| Junk detection, playlist scope, force scan and processed cache | Cleaner previews and the original engine; new workflows do not delete automatically |
| Pause, stop, retry, undo, logs, presets and notifications | New Queue/History and metadata undo; detailed options remain in original Cleaner |
| Original appearance, fonts and output settings | Settings import and original Cleaner |
| Exact/fuzzy duplicates and album completeness | Original detection and merge planning with confidence and playlist warnings |
| Ratings, play counts, dates and playlist links | Original merge algorithm creates a separate XML |
| Manual duplicate choices, exclusions and reports | New duplicate review; advanced controls remain in original Consolidator |
| XML parsing and cached track searches | Original parser and new SQLite index |
| Health, artwork and missing-file relinking | Original functions plus new inspection/relinking; audio preview stays in the original tool |
| Spotify import and lookup providers | Original provider and new comparison endpoint; the supplied Apple Music API stub is not functional |
| Restore points, growth reports, rebuild/undo and live duplicate removal | Original Consolidator; irreversible actions stay explicit |
| Original backup retention and scheduled checks | Original settings and interface |
| File organization and quarantine | Checked copies, collision protection, transfer records, previews and restore |
| Live and file-tag metadata edits | Supported-field checks, readback, per-field records and conditional undo |
| New desktop interface | Sandboxed Electron with a restricted bridge and authenticated local backend |

Some original screens have no equivalent in the new interface. See [known limits](LIMITATIONS.md) and [test results](VALIDATION.md).

## 🛡️ Important boundaries

Original Cleaner can delete junk tracks permanently. New operations require review and confirmation. Original tools run from writable app-data folders because Program Files may block their settings and output files.

Live multi-field edits can partly succeed. Each field is recorded before writing and read back afterward. The new COM worker uses signed persistent-ID halves and keeps its connection in one thread; the original Consolidator’s connection behavior remains in its own tool.

Apple’s private ITL/database files are not directly edited. Original rebuilding is an optional legacy action. Fuzzy matching has time and chunk limits that may miss some matches. No audio conversion or copy-protection bypass is added.

## 📥 Settings and history

Choose the old settings or custom-rule file to import. Old files are not deleted. Unknown preferences are retained. Old databases, undo logs, presets and backups remain usable in the original tools. Credentials are excluded from exports and diagnostic reports. Full automatic history conversion is not provided.

See [migration](../MIGRATION.md) and [system design](../ARCHITECTURE.md).

## 🎧 Last.fm and discovery

The Last.fm tab reads public recent plays and top songs, artists and albums with your API key and username. It shows available pictures and a large profile image. Six time periods, paging, refresh and disconnect are supported. Private-data login and scrobbling are not supported. See [Last.fm](LASTFM.md).

Discovered library paths can be hidden and restored without deleting files or unloading libraries. Large live scans continue while readings move forward, with a stall deadline and six-hour total limit.
