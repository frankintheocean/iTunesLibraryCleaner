import re
import shutil
from pathlib import Path
from unittest.mock import patch

from src.core.rebuild_script import (
    REBUILD_STEPS,
    find_latest_rebuild_backup_pair,
    preflight_check_rebuild,
    rebuild_library_in_app,
    undo_last_rebuild,
)


def test_rebuild_library_in_app_non_windows_rejected():
    with patch("src.core.rebuild_script.is_windows", return_value=False):
        result = rebuild_library_in_app(Path("clean.xml"))
    assert result.ok is False
    assert "Windows" in result.message


def test_rebuild_library_in_app_missing_xml(tmp_path):
    missing = tmp_path / "does_not_exist.xml"
    with patch("src.core.rebuild_script.is_windows", return_value=True):
        result = rebuild_library_in_app(missing, itunes_dir=tmp_path)
    assert result.ok is False
    assert "cleaned XML" in result.message


def test_rebuild_library_in_app_missing_itunes_dir(tmp_path):
    cleaned = tmp_path / "clean.xml"
    cleaned.write_text("<plist></plist>")
    missing_dir = tmp_path / "no_such_itunes_folder"
    with patch("src.core.rebuild_script.is_windows", return_value=True):
        result = rebuild_library_in_app(cleaned, itunes_dir=missing_dir)
    assert result.ok is False
    assert "iTunes folder" in result.message


def test_rebuild_library_in_app_full_flow(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True) as mock_quit, \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen") as mock_popen:
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert mock_quit.called
    assert result.ok is True
    assert not (itunes_dir / "iTunes Library.itl").exists()
    assert result.itl_backup_path.exists()
    assert result.itl_backup_path.read_bytes() == b"old itl data"
    assert result.xml_backup_path.exists()
    assert result.xml_backup_path.read_text() == "<plist>old</plist>"
    assert (itunes_dir / "iTunes Library.xml").read_text() == "<plist>new</plist>"
    assert result.itunes_relaunched is False  # no exe found in this test
    assert not mock_popen.called
    assert any("Could not find iTunes.exe" in w for w in result.warnings)
    # Backup filenames use the day/month/year_24hr-time stamp format.
    assert re.search(r"\.bak_\d{2}-\d{2}-\d{4}_\d{6}$", result.itl_backup_path.name)
    assert re.search(r"\.bak_\d{2}-\d{2}-\d{4}_\d{6}$", result.xml_backup_path.name)


def test_rebuild_library_in_app_prunes_older_backups(tmp_path):
    """Only the most recent .itl/.xml backup is kept on disk -- an older
    backup left from a previous rebuild is deleted once a new one is
    written (user request: save storage space)."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")

    # Simulate leftover backups from a previous rebuild.
    stale_itl = itunes_dir / "iTunes Library.itl.bak_01-01-2026_000000"
    stale_xml = itunes_dir / "iTunes Library.xml.bak_01-01-2026_000000"
    stale_itl.write_bytes(b"stale itl")
    stale_xml.write_text("<plist>stale</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert not stale_itl.exists()
    assert not stale_xml.exists()
    assert result.itl_backup_path.exists()
    assert result.xml_backup_path.exists()
    itl_backups = list(itunes_dir.glob("iTunes Library.itl.bak_*"))
    xml_backups = list(itunes_dir.glob("iTunes Library.xml.bak_*"))
    assert itl_backups == [result.itl_backup_path]
    assert xml_backups == [result.xml_backup_path]


def test_rebuild_library_in_app_prunes_older_stray_xml_backups(tmp_path):
    """Same one-kept-backup pruning as the main .itl/.xml, scoped per
    stray filename so backing up one stray file doesn't touch another
    stray file's own backup history."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")
    stray = itunes_dir / "Some Old Export.xml"
    stray.write_text("<plist>stray</plist>")
    stale_stray_backup = itunes_dir / "Some Old Export.xml.bak_01-01-2026_000000"
    stale_stray_backup.write_text("<plist>stale stray</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert not stale_stray_backup.exists()
    new_backup = result.extra_xml_backups[stray]
    assert new_backup.exists()
    stray_backups = list(itunes_dir.glob("Some Old Export.xml.bak_*"))
    assert stray_backups == [new_backup]


def test_rebuild_library_in_app_reports_steps_in_order(tmp_path):
    """The optional on_step callback (used by the UI step tracker) fires
    once per stage, in the fixed REBUILD_STEPS order, on a normal run."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    seen_steps: list[str] = []

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = rebuild_library_in_app(
            cleaned, itunes_dir=itunes_dir, on_step=seen_steps.append
        )

    assert result.ok is True
    assert seen_steps == list(REBUILD_STEPS)


def test_rebuild_library_in_app_relaunches_when_exe_found(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")
    fake_exe = tmp_path / "iTunes.exe"
    fake_exe.write_bytes(b"")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=fake_exe), \
         patch("src.core.rebuild_script.subprocess.Popen") as mock_popen:
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert result.itunes_relaunched is True
    mock_popen.assert_called_once_with([str(fake_exe)])


def test_rebuild_library_in_app_stops_if_itunes_wont_quit(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=False), \
         patch("src.core.rebuild_script.subprocess.Popen") as mock_popen:
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is False
    assert "still running" in result.message
    assert not mock_popen.called
    # Nothing should have been touched.
    assert not (itunes_dir / "iTunes Library.xml").exists()


def test_rebuild_library_in_app_clears_stray_xml_files(tmp_path):
    """Any other *.xml files in the iTunes folder besides iTunes Library.xml
    are backed up (not deleted outright) and removed before relaunch, same
    treatment the .itl already gets -- see RebuildResult.extra_xml_backups."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")
    stray = itunes_dir / "Some Old Export.xml"
    stray.write_text("<plist>stray</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert not stray.exists()
    assert len(result.extra_xml_backups) == 1
    backup_path = result.extra_xml_backups[stray]
    assert backup_path.exists()
    assert backup_path.read_text() == "<plist>stray</plist>"
    assert backup_path.name.startswith("Some Old Export.xml.bak_")
    # The main iTunes Library.xml swap is unaffected by the stray cleanup.
    assert (itunes_dir / "iTunes Library.xml").read_text() == "<plist>new</plist>"


def test_rebuild_library_in_app_leaves_no_partial_xml_if_copy_fails(tmp_path):
    """If the copy step is interrupted, the folder must never be left with
    a missing/half-written iTunes Library.xml -- that's what previously
    let a relaunch rebuild a blank library. No temp file should survive
    either."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")

    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    real_copy2 = shutil.copy2

    def _copy2_fail_for_cleaned_xml(src, dst, *a, **k):
        if Path(src) == cleaned:
            raise OSError("simulated interruption")
        return real_copy2(src, dst, *a, **k)

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.shutil.copy2", side_effect=_copy2_fail_for_cleaned_xml), \
         patch("src.core.rebuild_script.subprocess.Popen") as mock_popen:
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is False
    assert not mock_popen.called  # never relaunched against a bad copy
    # No stray temp file left behind.
    assert not list(itunes_dir.glob(".iTunes Library.xml.tmp_*"))
    # The old iTunes Library.xml is untouched -- the atomic rename never
    # happened, so the pre-existing file (backed up separately above) was
    # never overwritten with a missing/partial one.
    assert (itunes_dir / "iTunes Library.xml").read_text() == "<plist>old</plist>"


def test_rebuild_library_in_app_cleaned_xml_saved_inside_itunes_folder(tmp_path):
    """Regression test: if the user saves/exports their cleaned XML
    directly inside the iTunes folder itself, the stray-XML cleanup step
    must not sweep it up and back it up out from under the copy step that
    runs right after -- that previously surfaced as a confusing WinError 2
    'could not copy the cleaned XML' failure even though the file was
    never moved by the user."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    (itunes_dir / "iTunes Library.itl").write_bytes(b"old itl data")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>old</plist>")

    # The cleaned XML lives INSIDE the iTunes folder -- exactly the
    # real-world layout that triggered the bug.
    cleaned = itunes_dir / "Library_Deduplicated.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True, result.message
    # The cleaned XML must NOT have been treated as a stray file.
    assert cleaned not in result.extra_xml_backups
    # And the main iTunes Library.xml must now contain its content.
    assert (itunes_dir / "iTunes Library.xml").read_text() == "<plist>new</plist>"


def test_rebuild_library_in_app_stops_if_itl_still_present_after_unlink(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    itl = itunes_dir / "iTunes Library.itl"
    itl.write_bytes(b"stuck itl")
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    # Simulate the .itl surviving the unlink attempt (e.g. a stuck handle
    # recreating it) by having Path.unlink do nothing.
    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch.object(Path, "unlink", lambda self, *a, **k: None), \
         patch("src.core.rebuild_script.subprocess.Popen") as mock_popen:
        result = rebuild_library_in_app(cleaned, itunes_dir=itunes_dir)

    assert result.ok is False
    assert "still present" in result.message
    assert not mock_popen.called


# -------------------------------------------------- Undo last rebuild

def test_find_latest_rebuild_backup_pair_empty_dir(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    itl, xml, stamp = find_latest_rebuild_backup_pair(itunes_dir)
    assert itl is None and xml is None and stamp is None


def test_find_latest_rebuild_backup_pair_picks_newest_matching_stamp(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    # Day/month/year_24hr-time stamp format (see
    # core.rebuild_script._BACKUP_STAMP_FORMAT). Deliberately chosen so a
    # naive string sort would get this wrong (day "02" < day "31" as
    # strings even though January 2 is chronologically before January
    # 31), to guard against find_latest_rebuild_backup_pair regressing
    # back to lexicographic comparison.
    older = "02-01-2026_010101"
    newer = "31-01-2026_020202"
    (itunes_dir / f"iTunes Library.itl.bak_{older}").write_bytes(b"old itl")
    (itunes_dir / f"iTunes Library.xml.bak_{older}").write_text("<plist>old</plist>")
    (itunes_dir / f"iTunes Library.itl.bak_{newer}").write_bytes(b"new itl")
    (itunes_dir / f"iTunes Library.xml.bak_{newer}").write_text("<plist>new</plist>")

    itl, xml, stamp = find_latest_rebuild_backup_pair(itunes_dir)
    assert stamp == newer
    assert itl.name == f"iTunes Library.itl.bak_{newer}"
    assert xml.name == f"iTunes Library.xml.bak_{newer}"


def test_find_latest_rebuild_backup_pair_ignores_unparseable_stamp(tmp_path):
    """A backup left over from before the stamp format changed (old
    "%Y%m%d_%H%M%S") is skipped rather than crashing this lookup or being
    mistaken for the newest."""
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    old_format_stamp = "20260101_010101"
    new_format_stamp = "05-01-2026_030303"
    (itunes_dir / f"iTunes Library.itl.bak_{old_format_stamp}").write_bytes(b"legacy itl")
    (itunes_dir / f"iTunes Library.itl.bak_{new_format_stamp}").write_bytes(b"current itl")

    itl, _xml, stamp = find_latest_rebuild_backup_pair(itunes_dir)
    assert stamp == new_format_stamp
    assert itl.name == f"iTunes Library.itl.bak_{new_format_stamp}"


def test_find_latest_rebuild_backup_pair_partial_pair(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    stamp = "01-01-2026_010101"
    (itunes_dir / f"iTunes Library.itl.bak_{stamp}").write_bytes(b"only itl")

    itl, xml, found_stamp = find_latest_rebuild_backup_pair(itunes_dir)
    assert found_stamp == stamp
    assert itl is not None
    assert xml is None


def test_undo_last_rebuild_non_windows_rejected():
    with patch("src.core.rebuild_script.is_windows", return_value=False):
        result = undo_last_rebuild(Path("some_dir"))
    assert result.ok is False
    assert "Windows" in result.message


def test_undo_last_rebuild_no_backup_found(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    with patch("src.core.rebuild_script.is_windows", return_value=True):
        result = undo_last_rebuild(itunes_dir=itunes_dir)
    assert result.ok is False
    assert "No rebuild backup" in result.message


def test_undo_last_rebuild_restores_backup_pair(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    stamp = "01-01-2026_010101"
    (itunes_dir / f"iTunes Library.itl.bak_{stamp}").write_bytes(b"restored itl")
    (itunes_dir / f"iTunes Library.xml.bak_{stamp}").write_text("<plist>restored</plist>")
    # Simulate current (post-rebuild) files already in place.
    (itunes_dir / "iTunes Library.itl").write_bytes(b"current itl")
    (itunes_dir / "iTunes Library.xml").write_text("<plist>current</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=True), \
         patch("src.core.rebuild_script.find_itunes_exe", return_value=None), \
         patch("src.core.rebuild_script.subprocess.Popen"):
        result = undo_last_rebuild(itunes_dir=itunes_dir)

    assert result.ok is True, result.message
    assert result.restored_itl is True
    assert result.restored_xml is True
    assert (itunes_dir / "iTunes Library.itl").read_bytes() == b"restored itl"
    assert (itunes_dir / "iTunes Library.xml").read_text() == "<plist>restored</plist>"


def test_undo_last_rebuild_itunes_still_running_blocks(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    stamp = "01-01-2026_010101"
    (itunes_dir / f"iTunes Library.itl.bak_{stamp}").write_bytes(b"restored itl")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._quit_itunes", return_value=False):
        result = undo_last_rebuild(itunes_dir=itunes_dir)

    assert result.ok is False
    assert "still running" in result.message


# ------------------------------------------------------ preflight_check_rebuild

def test_preflight_ok_on_healthy_setup(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._itunes_is_running", return_value=False):
        result = preflight_check_rebuild(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert result.problems == []
    assert result.warnings == []


def test_preflight_non_windows_rejected():
    with patch("src.core.rebuild_script.is_windows", return_value=False):
        result = preflight_check_rebuild(Path("clean.xml"))
    assert result.ok is False
    assert any("Windows" in p for p in result.problems)


def test_preflight_missing_cleaned_xml(tmp_path):
    missing = tmp_path / "does_not_exist.xml"
    with patch("src.core.rebuild_script.is_windows", return_value=True):
        result = preflight_check_rebuild(missing, itunes_dir=tmp_path)
    assert result.ok is False
    assert any("cleaned XML" in p for p in result.problems)


def test_preflight_missing_itunes_dir(tmp_path):
    cleaned = tmp_path / "clean.xml"
    cleaned.write_text("<plist></plist>")
    missing_dir = tmp_path / "no_such_itunes_folder"
    with patch("src.core.rebuild_script.is_windows", return_value=True):
        result = preflight_check_rebuild(cleaned, itunes_dir=missing_dir)
    assert result.ok is False
    assert any("iTunes folder" in p for p in result.problems)


def test_preflight_itunes_running_is_warning_not_blocker(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._itunes_is_running", return_value=True):
        result = preflight_check_rebuild(cleaned, itunes_dir=itunes_dir)

    assert result.ok is True
    assert any("currently running" in w for w in result.warnings)


def test_preflight_insufficient_disk_space_blocks(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    fake_usage = shutil.disk_usage(tmp_path)._replace(free=1024)  # 1 KB free
    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._itunes_is_running", return_value=False), \
         patch("src.core.rebuild_script.shutil.disk_usage", return_value=fake_usage):
        result = preflight_check_rebuild(cleaned, itunes_dir=itunes_dir)

    assert result.ok is False
    assert any("free space" in p for p in result.problems)


def test_preflight_write_permission_failure_blocks(tmp_path):
    itunes_dir = tmp_path / "iTunes"
    itunes_dir.mkdir()
    cleaned = tmp_path / "cleaned.xml"
    cleaned.write_text("<plist>new</plist>")

    with patch("src.core.rebuild_script.is_windows", return_value=True), \
         patch("src.core.rebuild_script._itunes_is_running", return_value=False), \
         patch.object(Path, "write_bytes", side_effect=OSError("Access is denied")):
        result = preflight_check_rebuild(cleaned, itunes_dir=itunes_dir)

    assert result.ok is False
    assert any("permission" in p for p in result.problems)
