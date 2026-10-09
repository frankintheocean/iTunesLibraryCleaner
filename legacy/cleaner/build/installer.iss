; Inno Setup script for GenreCleanup
; Build with Inno Setup Compiler (iscc.exe) AFTER running PyInstaller.
; Expects the PyInstaller output at dist\GenreCleanup.exe (relative to
; project root) - a single onefile exe, not an onedir folder.
;
; Usage (from project root, after `pyinstaller build\genrecleanup.spec`):
;   iscc build\installer.iss
;
; Output installer will be placed in dist_installer\GenreCleanup-Setup.exe

#define MyAppName "GenreCleanup"
#define MyAppVersion "2.1"
#define MyAppPublisher "GenreCleanup"
#define MyAppExeName "GenreCleanup.exe"

[Setup]
AppId={{D4C3B2A1-7F6E-4A3B-9C2A-GENRECLEANUP1}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=GenreCleanup-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Onefile build - a single exe, not a folder tree, so this only needs one
; line (whiteboard's installer.iss uses recursesubdirs/createallsubdirs
; because WhiteBoard is an onedir build with a folder of DLLs/data next to
; the exe; GenreCleanup has no such folder).
Source: "..\dist\GenreCleanup.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
