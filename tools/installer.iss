#define AppName "BudgetPlanner"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "CRTCLerr"
#define AppExeName "BudgetPlanner.exe"
#define AppId "{D6B0E1ED-6B84-4A58-BE8A-0F2BF8E30E72}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\BudgetPlanner
DefaultGroupName=BudgetPlanner
OutputDir=..\dist
OutputBaseFilename=BudgetPlanner-Setup-windows-x86_64
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
Name: "{autoprograms}\BudgetPlanner"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\BudgetPlanner"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch BudgetPlanner"; Flags: nowait postinstall skipifsilent
