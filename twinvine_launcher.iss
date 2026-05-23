; TwinVine Launcher - Inno Setup Script
; Compile with Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; Build steps:
;   1. Run: pyinstaller twinvine_launcher.spec
;   2. Open this .iss file in Inno Setup and click Compile
;   Output: installer_output\TwinVine Launcher-Setup-1.0.0-Beta.exe

#define MyAppName "TwinVine Launcher"
#define MyAppVersion "1.0.0 Beta"
#define MyAppVersionFile "1.0.0"
#define MyAppPublisher "Lseauk"
#define MyAppURL "https://github.com/Lseauk/TwinVine-Launcher"
#define MyAppExeName "TwinVineLauncher.exe"
#define MyAppDescription "Windows GUI launcher for TwinVine (VineFeeder + Envied)"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}

; Install to user's local folder — no admin rights needed
DefaultDirName={userdocs}\..\Downloads\TwinVine Launcher
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest

; Output
OutputDir=installer_output
OutputBaseFilename=TwinVine Launcher-Setup-1.0.0-Beta
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=no
DisableFinishedPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable (built by PyInstaller)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
; Offer to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill process before uninstalling
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillLauncher"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
