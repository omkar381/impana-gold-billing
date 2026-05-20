; =============================================================================
; Impana Gold Billing System — Windows Installer
; Built with Inno Setup 6.x  (https://jrsoftware.org/isinfo.php)
;
; HOW TO BUILD:
;   1. Download & install Inno Setup from https://jrsoftware.org/isinfo.php
;   2. Open this file in Inno Setup Compiler
;   3. Press F9 (or Build > Compile)
;   4. Find ImpanaGold_Setup.exe in the 'dist' folder
; =============================================================================

#define AppName      "Impana Gold"
#define AppVersion   "1.0.0"
#define AppPublisher "M/S Sri Devi Industries"
#define AppURL       "http://127.0.0.1:5000"
#define AppExeName   "ImpanaGold.exe"
#define SourceDir    "D:\final impana gold billing software"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\ImpanaGold
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir={#SourceDir}\dist
OutputBaseFilename=ImpanaGold_Setup_v{#AppVersion}
SetupIconFile={#SourceDir}\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSmallImageFile=
; Require 64-bit Windows
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Show install progress
ShowLanguageDialog=no
DisableWelcomePage=no
DisableReadyPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a &Start Menu entry"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
; ── Compiled Standalone Backend (PyInstaller) ──
Source: "{#SourceDir}\dist\ImpanaServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── Launcher scripts ──
Source: "{#SourceDir}\start_impana.vbs";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\stop_impana.vbs";           DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\ImpanaGold.bat";            DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\app_icon.ico";              DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Desktop shortcut
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\start_impana.vbs"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon; Comment: "Open Impana Gold Billing System"

; Start Menu
Name: "{group}\{#AppName}";              Filename: "{app}\start_impana.vbs"; IconFilename: "{app}\app_icon.ico"; Tasks: startmenuicon
Name: "{group}\Stop {#AppName}";         Filename: "{app}\stop_impana.vbs";  Comment: "Stop the billing server"
Name: "{group}\Uninstall {#AppName}";    Filename: "{uninstallexe}"

[Run]
; Open app after install
Filename: "{app}\start_impana.vbs"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
; Kill server before uninstall
Filename: "{app}\stop_impana.vbs"; Flags: shellexec; RunOnceId: "StopServer"

[Code]
// Show welcome message with branding
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This will install Impana Gold Billing System on your computer.' + #13#10 + #13#10 +
    'M/S Sri Devi Industries' + #13#10 +
    'Manufacturing & Supply of Premium Quality Food Products' + #13#10 + #13#10 +
    'Click Next to continue.';
end;
