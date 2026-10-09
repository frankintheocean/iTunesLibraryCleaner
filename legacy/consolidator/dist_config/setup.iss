; Inno Setup script for iTunes Library Consolidator.
;
; Produces a standard Windows installer (setup .exe) that:
;   - Installs the already-built app (dist\iTunesLibraryConsolidator\,
;     a standalone folder from build_windows.bat / build.spec containing
;     iTunesLibraryConsolidator.exe and its dependent files) into
;     Program Files.
;   - Adds a Start Menu shortcut (and an optional Desktop shortcut).
;   - Registers a proper uninstaller in "Apps & features".
;   - Optionally associates .xml files with the app, via a distinct
;     ProgId (not by silently overriding the user's existing default .xml
;     handler) -- this is an unchecked-by-default task, so nothing about
;     how the user's other .xml files open changes unless they opt in.
;   - Runs and completes silently: no console/cmd windows are shown at any
;     point during installation or uninstallation (Inno Setup's installer
;     itself is a GUI wizard, not a console app, and no [Run]/[UninstallRun]
;     entry below launches a visible console).
;
; Build with Inno Setup 6 (https://jrsoftware.org/isinfo.php), on Windows,
; AFTER running dist_config\build_windows.bat so
; dist\iTunesLibraryConsolidator\iTunesLibraryConsolidator.exe already
; exists (build_windows.bat also copies it to the project root for
; convenience, but this script packages straight from dist\, so building
; is still a prerequisite either way):
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
; Output: dist_config\Output\iTunesLibraryConsolidator-Setup-<version>.exe

; This build is v2.0 (see src/changelog.py APP_VERSION). MyAppVersion is
; kept as a plain numeric version (not e.g. "1.5-pre") because Inno
; Setup's own upgrade/downgrade detection compares AppVersion as a
; version number -- a non-numeric suffix there risks breaking "is this
; an upgrade?" logic on the next install.
#define MyAppName "iTunes Library Consolidator"
#define MyAppVersion "2.0"
#define MyAppPublisher "iTunes Library Consolidator"
#define MyAppExeName "iTunesLibraryConsolidator.exe"
; PyInstaller's onedir output folder name (see build.spec's COLLECT
; `name=`) -- distinct from MyAppExeName since [Files] below needs to
; source the whole standalone folder, not just the .exe inside it.
#define MyAppDistFolder "iTunesLibraryConsolidator"
; Fixed GUID so upgrades over an existing install are detected correctly
; instead of Inno Setup treating each version as an unrelated install.
#define MyAppId "{{9B7B6C9E-6E2C-4B7B-9C8A-6C7C0B7A0B4A}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install by default (no admin prompt needed) since this app only
; ever writes to the user's own AppData cache/backups and the user's own
; chosen library files -- nothing it does requires machine-wide install.
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=iTunesLibraryConsolidator-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Never show a console/cmd window at any point during install or uninstall.
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
; Unchecked by default -- associating .xml is a meaningful system change
; (other apps may already own that extension), so it's opt-in, not forced.
Name: "associatexml"; Description: "Associate .xml files with {#MyAppName} (lets you double-click a Library.xml to open it here)"; GroupDescription: "File association:"; Flags: unchecked

[Files]
; Standalone-folder build (see build.spec): everything under
; dist\iTunesLibraryConsolidator\ (the .exe plus its dependent DLLs/
; resources) is installed as a unit -- recurses subdirectories so nothing
; PyInstaller placed there is left behind.
Source: "..\dist\{#MyAppDistFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "..\assets\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; Microsoft Visual C++ Redistributable (x64) bootstrapper. python313.dll
; (bundled in the standalone folder above) depends on VCRUNTIME140.dll
; and the api-ms-win-crt-*.dll API Set stubs, which come from this
; redistributable, not from Python or PyInstaller -- a machine that
; doesn't already have it installed (common on a clean/minimal Windows
; setup) fails to launch the built .exe with "Failed to load Python DLL
; ... LoadLibrary: The specified module could not be found", even though
; python313.dll itself is present and undamaged. Download the real
; bootstrapper yourself before building the installer -- it is NOT
; committed to this repo (it's a ~25MB Microsoft-signed binary, and
; redistributing a stale copy would silently skip Microsoft's own updates
; to it) -- from:
;     https://aka.ms/vs/17/release/vc_redist.x64.exe
; and save it as dist_config\vc_redist.x64.exe before running ISCC. If
; that file is missing, ISCC.exe fails the build immediately with a clear
; "source file not found" error rather than silently shipping an
; installer that hits the same DLL failure this is meant to fix.
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
; Silently installs the VC++ Redistributable before the app can be
; launched. /install /quiet /norestart: no UI, no forced reboot (matches
; this installer's own silent, no-console-window behavior above). Check:
; skips this entirely if a compatible x64 VC++ 14.x runtime is already
; present (Microsoft's own installer records this under this registry
; value -- see docs for VC_REDIST_INSTALLED below), so re-running this
; installer, or installing on a machine that already has it (Visual
; Studio, another app's installer, Windows Update, etc.), never
; reinstalls/repairs it unnecessarily.
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing required Visual C++ Runtime..."; Check: not VCRedistInstalled; Flags: waituntilterminated
; Optional "launch after install" checkbox, standard Inno Setup pattern.
; nowait + postinstall + skipifsilent: never blocks the installer wizard
; on the app closing, and is skipped entirely for silent/unattended installs.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Detects an already-installed Visual C++ 2015-2022 x64 runtime via the
// registry key Microsoft's own vc_redist.x64.exe writes on success, so
// the [Run] entry above can skip re-running the ~25MB bootstrapper on a
// machine that already has it (a very common case -- this same runtime
// is shared by many other apps). Absence of the key (or the key present
// but "Installed" not set to 1, e.g. a partial/failed prior install) is
// treated as "not installed", which is the safe default: it just means
// the bootstrapper runs and either installs cleanly or itself detects
// and no-ops against a newer version already present -- Microsoft's own
// installer already handles that "same or newer version present" case
// correctly, so there's no double-guard needed here beyond this check.
function VCRedistInstalled(): Boolean;
var
  installed: Cardinal;
begin
  Result := RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64', 'Installed', installed) and (installed = 1);
end;

[Registry]
; Distinct ProgId under the app's own name -- registered unconditionally
; (harmless: it doesn't change what opens .xml unless the extension is
; also pointed at it below), which only happens if the user checked the
; associatexml task above.
Root: HKCU; Subkey: "Software\Classes\iTunesLibraryConsolidator.xml"; ValueType: string; ValueName: ""; ValueData: "iTunes/Apple Music Library XML"; Flags: uninsdeletekey; Tasks: associatexml
Root: HKCU; Subkey: "Software\Classes\iTunesLibraryConsolidator.xml\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\app_icon.ico"; Tasks: associatexml
Root: HKCU; Subkey: "Software\Classes\iTunesLibraryConsolidator.xml\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatexml
; Per-user association (HKCU, not HKLM) so this only affects the
; installing user's own file associations, consistent with the per-user
; install above, and is what Windows' "Open with" UI expects for a
; user-scoped choice.
Root: HKCU; Subkey: "Software\Classes\.xml\OpenWithProgids"; ValueType: string; ValueName: "iTunesLibraryConsolidator.xml"; ValueData: ""; Tasks: associatexml; Flags: uninsdeletevalue
