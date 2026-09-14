; Inno Setup Script for Scanned Documents Renamer
; Produces a dedicated Windows Setup Installer (.exe) with clean installation & uninstallation

#define MyAppName "Scanned Documents Renamer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Lumi-nary"
#define MyAppURL "https://github.com/Lumi-nary/Scanned-Documents-Renamer"
#define MyAppExeName "ScannedDocumentsRenamer.exe"

[Setup]
; Basic Application Info
AppId={{D37E8C2B-48F1-4F58-9A78-3F4A9E2198B7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Standard per-user installation directory (C:\Users\<User>\AppData\Local\Programs\Scanned Documents Renamer)
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Install cleanly without requiring Administrator UAC elevation
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

; Process management: automatically close running instances during install/uninstall
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

; Output settings
OutputDir=..\dist\installer
OutputBaseFilename=ScannedDocumentsRenamer_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Visual branding & Application Icons
DisableWelcomePage=no
SetupIconFile=..\gui\icon.ico
WizardSmallImageFile=wizard_small.bmp
WizardImageFile=wizard_large.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Distribute all files from the compiled PyInstaller bundle
Source: "..\dist\ScannedDocumentsRenamer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\gui\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\gui\icon.ico"; DestDir: "{app}\gui"; Flags: ignoreversion
Source: "..\gui\icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\gui\icon.png"; DestDir: "{app}\gui"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Delete all runtime-generated files, caches, and configuration created after install
Type: filesandordirs; Name: "{app}\EBWebView"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\settings.json"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"
Type: dirifempty; Name: "{app}"

[Code]
// Helper function executed when the uninstaller initializes
function InitializeUninstall(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  // Automatically terminate any running instances so files and DLLs are not locked
  Exec('taskkill.exe', '/F /IM ScannedDocumentsRenamer.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
  Exec('taskkill.exe', '/F /IM pythonw.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
  Sleep(500);
end;

// Cleanup any remaining runtime directories after uninstall completes
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Forcibly remove application folder if any untracked runtime files remained
    DelTree(ExpandConstant('{app}'), True, True, True);
    // Also clean up user configuration directory in LocalAppData if present
    DelTree(ExpandConstant('{localappdata}\ScannedDocumentsRenamer'), True, True, True);
  end;
end;
