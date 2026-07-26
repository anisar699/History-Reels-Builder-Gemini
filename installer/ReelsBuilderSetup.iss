#define MyAppName "History Reels Builder"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "History Reels Builder"
#define MyAppExeName "installer\launch_dashboard.vbs"

[Setup]
AppId={{8BDB4702-BE6F-4AB2-9D05-96C7A70A58A5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\History Reels Builder
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\assets\app_icon.ico
OutputDir=..\dist
OutputBaseFilename=ReelsBuilderSetup
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=One-click installer for History Reels Builder
VersionInfoCompany={#MyAppPublisher}
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env*,.git\*,.github\*,.agents\*,.venv\*,venv\*,__pycache__\*,*.pyc,.pytest_cache\*,.ruff_cache\*,.staging\*,staging_reports\*,dist\*,tests\*,scripts\*,app_source.zip,AGENTS.md,install.py,patch.py,patch2.py,download_bg_music.py,extract_zemtv_voice_large.py,packages.txt,dashboard_preview.jpg,installer\build_installer.ps1,installer\ReelsBuilderSetup.iss,*.mp4,*.mp3,*.wav,*.db,*.sqlite3,.streamlit\secrets.toml"
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  PowerShellPath: String;
  ScriptPath: String;
  Parameters: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Installing Python packages and FFmpeg. This may take several minutes...';
    PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant('{app}\installer\install_runtime.ps1');
    Parameters :=
      '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath +
      '" -InstallDir "' + ExpandConstant('{app}') + '"';

    if (not Exec(PowerShellPath, Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      MsgBox(
        'Runtime setup failed. Review this log and run Setup again:' + #13#10 +
        ExpandConstant('{app}\runtime\logs\setup.log'),
        mbError,
        MB_OK
      );
      RaiseException('Runtime setup failed with exit code ' + IntToStr(ResultCode) + '.');
    end;
  end;
end;
