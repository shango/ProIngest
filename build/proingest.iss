; The Windows installer, built by `python build/build.py` on Windows (docs/PACKAGING.md).
; The build passes AppVersion, SourceDir and OutputDir on the ISCC command line, so this
; file holds no version and no path of its own.
;
; Per user, with no administrator rights asked for: it installs under the user's own
; AppData\Local\Programs, as the dmg installs by a drag the user can make without one.

#ifndef AppVersion
  #error AppVersion must be defined, e.g. ISCC /DAppVersion=0.5.50
#endif

[Setup]
; The installer's identity. Do not change it once a build has reached a user: Windows
; finds the installed copy to upgrade and to uninstall by this, as macOS does by the
; bundle identifier.
AppId={{6F1D2B9E-4C7A-4E0B-9B3E-2A5C8D1F7E40}
AppName=ProIngest
AppVersion={#AppVersion}
AppVerName=ProIngest {#AppVersion}
AppPublisher=ProIngest
DefaultDirName={autopf}\ProIngest
DefaultGroupName=ProIngest
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=ProIngest-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ProIngest.exe
; A running ProIngest holds its own files open, so the installer offers to close it.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An upgrade replaces the whole folder: a file a newer build no longer ships must not be
; left behind for the old one's code to find.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\ProIngest"; Filename: "{app}\ProIngest.exe"
Name: "{autodesktop}\ProIngest"; Filename: "{app}\ProIngest.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ProIngest.exe"; Description: "{cm:LaunchProgram,ProIngest}"; Flags: nowait postinstall skipifsilent
