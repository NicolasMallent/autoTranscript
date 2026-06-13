; AutoTranscript - Script Inno Setup
; Compile avec : ISCC.exe /DMyAppVersion="2.0.0" setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#define MyAppName      "AutoTranscript"
#define MyAppPublisher "UPCite - LDAR"
#define MyAppURL       "https://github.com/NicolasMallent/autoTranscript"

[Setup]
AppId={{B7E3F2A1-4C8D-4E9F-A012-3456789ABCDE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=AutoTranscript-Setup-Windows
OutputDir=..\..\dist
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Pas besoin de droits admin - installation dans AppData
PrivilegesRequired=lowest

[Languages]
Name: "french";  MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Python embeddable (standalone, pas d'installation systeme)
Source: "python-embed\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs
Source: "get-pip.py";     DestDir: "{app}\python"
; ffmpeg bundle
Source: "..\..\ffmpeg\windows\ffmpeg.exe"; DestDir: "{app}\ffmpeg\windows"
; Code de l'application
Source: "..\..\app\*";          DestDir: "{app}\app";  Flags: recursesubdirs createallsubdirs
Source: "..\..\i18n\*";         DestDir: "{app}\i18n"; Flags: recursesubdirs createallsubdirs
Source: "..\..\models.json";    DestDir: "{app}"
Source: "..\..\requirements.txt"; DestDir: "{app}"

[Icons]
Name: "{group}\{#MyAppName}";                          Filename: "{app}\AutoTranscript.bat"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}";    Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";                  Filename: "{app}\AutoTranscript.bat"; Tasks: desktopicon

[Run]
; 1. Activer site-packages dans le Python embeddable (desactive par defaut)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -Command ""Get-ChildItem '{app}\python\*.pth' | ForEach-Object {{ (Get-Content $_.FullName) -replace '#import site','import site' | Set-Content $_.FullName }}"""; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Configuration de Python..."

; 2. Bootstrap pip
Filename: "{app}\python\python.exe"; \
  Parameters: "{app}\python\get-pip.py --quiet"; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Initialisation de pip..."

; 3. Installer whisper + dependances (telechargement, peut prendre plusieurs minutes)
Filename: "{app}\python\python.exe"; \
  Parameters: "-m pip install -r ""{app}\requirements.txt"" --quiet"; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Installation des dependances IA (~3 Go, patience...)..."

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  LauncherPath, Content: string;
begin
  if CurStep = ssPostInstall then
  begin
    LauncherPath := ExpandConstant('{app}\AutoTranscript.bat');
    Content := '@echo off' + #13#10 +
               '"%~dp0python\python.exe" "%~dp0app\main.py"' + #13#10;
    SaveStringToFile(LauncherPath, Content, False);
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
