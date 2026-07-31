#define AppName "Budget Planner"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "CRTCLerr"
#define AppExeName "Budget Planner.exe"
#define AppId "{D6B0E1ED-6B84-4A58-BE8A-0F2BF8E30E72}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Budget Planner
DefaultGroupName=Budget Planner
OutputDir=..\dist
OutputBaseFilename=Budget-Planner-Setup-windows-x86_64
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\moneylogo.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Budget Planner"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Budget Planner"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Budget Planner"; Flags: nowait postinstall skipifsilent
