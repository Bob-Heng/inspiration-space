; 灵感空间 v1.0.0 安装包脚本（Inno Setup 6）
#define MyAppName "灵感空间"
#define MyAppVersion "1.3.0"
#define MyAppExeName "InspirationSpace.exe"
#define SourceDir "..\\backend\\dist\\InspirationSpace"

[Setup]
AppId={{7F3A9C2E-4B1D-4E5F-9A8B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
DefaultDirName={autopf}\InspirationSpace
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=InspirationSpace-Setup-1.3.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile=..\scripts\icon\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableDirPage=no
CloseApplications=force

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
