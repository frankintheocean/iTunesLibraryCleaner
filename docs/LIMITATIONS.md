# Release scope and limitations

This is an implemented source integration, not a certified production Windows release. The entire master prompt is not claimed complete.

## Platform validation outstanding

The real source COM acceptance script passed on Apple-distributed iTunes 12.13.11.1. Packaged live COM, Windows modal-dialog behavior, Windows locks/long paths/UNC/disconnected storage, multi-monitor/high-DPI behavior, Windows 10/11 clean-machine acceptance, code signing and manual Windows taskbar integration remain outstanding. The Windows Server 2022 hosted runner passed the frozen backend, NSIS install, packaged Electron workflow, repair and uninstall/reinstall checks. Linux cannot build a Windows Python bundle through PyInstaller. An unsigned Windows preview installer is published separately from the source ZIP. Repair is reinstall-based tooling; a dedicated installed Repair UI and optional settings purge are not implemented.

## Preserved through original interfaces

Full Cleaner options, processed-cache migration/maintenance, original force-rescan/lookup credentials, native notifications, detailed failure retry and original undo logs remain in the retained Cleaner. Consolidator advanced permanent exclusions, restore points, health growth/diffs, audio preview and rebuild/undo/live duplicate removal remain in the retained Consolidator. Their exact original UIs/themes are launchable; not every original dialog is redesigned into React. Original irreversible actions are subject to their original confirmations/backup behavior.

## New master-prompt features not complete

Approximate/offset-tolerant audio fingerprint similarity beyond exact optional Chromaprint fingerprints, audio-quality-aware cross-library reconciliation beyond the original matching and file hashes, duplicate artwork cleanup, empty-folder removal and duplicate-artwork cleanup, automatic disconnected-drive classification, proprietary Apple Music database import, full preservation-style/custom-variable folder templates, playlist comparison and live playlist repair, automatic full historical database conversion, managed backup/restore of unified app state, job dependency graphs, Retry All, mid-file byte/speed/ETA checkpoints, localization, update/notification settings, clipboard-derived actions and drag/drop are not fully implemented in the unified shell. The queue has one fixed mutation worker and item-boundary cancellation; not arbitrary concurrent mutators. Folder scans cache tags using size/mtime and still walk directories. XML/live snapshots are loaded for algorithms; the UI is virtualized/paginated but snapshots are not a disk-only streaming domain model.

Conditional field-level undo is implemented for live COM and supported file tags; full-file backup paths remain available for manual recovery. Artwork undo currently uses those backups. Artwork replacement supports MP3 with ID3, MP4/M4A and FLAC; other formats may be inspect-only. General easy-tag editing depends on Mutagen's format support; unsupported fields/formats fail explicitly without bypassing verification. Scan metadata validation is not an exhaustive audio decoding integrity check. Offline/missing statuses are snapshots, never instructions for automatic removal.

Moving/quarantining may break iTunes references. The unified service does not silently delete live duplicate entries or force a proprietary-library rebuild. A supported export/import/relink workflow is required; advanced original rebuild/sync remains opt-in in the legacy interface. The exact preservation and new-feature boundaries are documented in FEATURE_PARITY.md.
