# 📥 Original Consolidator installer

This optional Inno Setup 6 installer packages the original standalone app. The unified app uses a [different installer](../../../INSTALL.md).

## 🪟 Installation

The default folder is `%LocalAppData%\Programs\iTunes Library Consolidator`. The installer creates a Start Menu shortcut and uninstall entry. A Desktop shortcut and `.xml` association are optional and unchecked by default.

The XML association is per-user and changes how XML files open only if selected. Installation also supplies the x64 Visual C++ runtime when needed; it may request permission if the runtime installer requires it. Without that runtime, the bundled Python DLL may not load.

## 🔨 Build

1. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php).
2. Run `dist_config\build_windows.bat` from the Consolidator folder. Keep the whole output folder, including DLLs and resources.
3. Download Microsoft’s x64 runtime from https://aka.ms/vs/17/release/vc_redist.x64.exe and save it as `dist_config\vc_redist.x64.exe`. It is not included in the repository. A missing file stops the installer build.
4. From the Consolidator folder, run:

   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist_config\setup.iss
   ```

5. Find `dist_config\Output\iTunesLibraryConsolidator-Setup-<version>.exe`.

Installation and removal use the Inno Setup wizard. [Full original details](https://github.com/frankintheocean/iTunesLibraryCleaner/blob/v1.0/legacy/consolidator/dist_config/installer_README.md).
