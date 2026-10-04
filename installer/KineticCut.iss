#include "sizes.iss"
#ifndef AppIdentity
#define AppIdentity "{{EB1F3D12-5AF0-481F-9CAB-3F8438E2D0B4}"
#endif

[Setup]
AppId={#AppIdentity}
AppName=Kinetic Cut
AppVersion={#AppVersion}
AppPublisher=Kinetic Cut
AppPublisherURL=https://github.com/farhanr3001/video-editor
AppUpdatesURL=https://github.com/farhanr3001/video-editor/releases
DefaultDirName={localappdata}\Programs\KineticCut
DefaultGroupName=Kinetic Cut
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\KineticCut.exe
OutputDir=..\release
#ifdef Migration
OutputBaseFilename=KineticCut-Setup-{#AppVersion}
#else
OutputBaseFilename=KineticCut-FullSetup-{#AppVersion}
#endif
SetupIconFile=..\assets\kinetic-cut.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
ShowComponentSizes=yes
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
MinVersion=10.0

[Types]
Name: "standard"; Description: "Editor and captions"
Name: "custom"; Description: "Choose optional downloads"; Flags: iscustom

[Components]
Name: "main"; Description: "Editor, FFmpeg and caption generation (always included)"; Types: standard custom; Flags: fixed
Name: "android"; Description: "Android mirroring (+{#AndroidMB} MB)"; ExtraDiskSpaceRequired: {#AndroidBytes}
Name: "iphone"; Description: "iPhone mirroring (+{#IPhoneMB} MB)"; ExtraDiskSpaceRequired: {#IPhoneBytes}
Name: "vision"; Description: "Face / background tools (+{#VisionMB} MB)"; ExtraDiskSpaceRequired: {#VisionBytes}
Name: "vocals"; Description: "Vocal separation (+{#VocalsMB} MB)"; ExtraDiskSpaceRequired: {#VocalsBytes}

[Files]
#ifdef Migration
Source: "..\build\incremental-update\migration\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
Source: "..\release\KineticCut-Baseline-1.1.0.json"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\KineticCutUpdater.exe"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\_update.json"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\_update-files.txt"; Flags: dontcopy
#else
Source: "..\build\distribution-stage\KineticCut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
#endif

[Icons]
#ifndef TestingSetup
Name: "{group}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"
Name: "{autodesktop}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"; Tasks: desktopicon
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\KineticCut.exe"; Description: "Open Kinetic Cut"; Flags: nowait postinstall skipifsilent

[Code]
var
  SizeLabel: TNewStaticText;
  ManagedFiles: TArrayOfString;
#ifdef Migration
  MigrationPrepared, MigrationCommitted: Boolean;

function MigrationHelper(Command: String): Boolean;
var ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{tmp}\KineticCutUpdater.exe'), Command + ' "' + ExpandConstant('{app}') + '" --no-restart', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ResultCode: Integer; Parameters: String;
begin
  ExtractTemporaryFile('KineticCutUpdater.exe');
  ExtractTemporaryFile('KineticCut-Baseline-1.1.0.json');
  ExtractTemporaryFile('_update.json'); ExtractTemporaryFile('_update-files.txt');
  Parameters := 'native-prepare "' + ExpandConstant('{app}') + '" --manifest "' + ExpandConstant('{tmp}\_update.json') + '" --baseline "' + ExpandConstant('{tmp}\KineticCut-Baseline-1.1.0.json') + '" --no-restart';
  if not Exec(ExpandConstant('{tmp}\KineticCutUpdater.exe'), Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    Result := 'This small update requires an unchanged Kinetic Cut 1.1.0 installation. Close the editor first. For a new installation or repair, download KineticCut-FullSetup-{#AppVersion}.exe from the GitHub release.'
  else begin MigrationPrepared := True; Result := ''; end;
end;

procedure DeinitializeSetup();
begin
  if MigrationPrepared and not MigrationCommitted then MigrationHelper('native-rollback');
end;
#endif

function SelectedKeys(): String;
begin
  Result := '';
  if WizardIsComponentSelected('android') then Result := Result + 'android,';
  if WizardIsComponentSelected('iphone') then Result := Result + 'iphone,';
  if WizardIsComponentSelected('vision') then Result := Result + 'vision,';
  if WizardIsComponentSelected('vocals') then Result := Result + 'vocals,';
  if Length(Result) > 0 then Delete(Result, Length(Result), 1);
end;

procedure UpdateSizeLabel();
var Installed, Downloads: Extended;
begin
  Installed := {#CoreBytes}; Downloads := 0;
  if WizardIsComponentSelected('android') then begin Installed := Installed + {#AndroidBytes}; Downloads := Downloads + {#AndroidDownload}; end;
  if WizardIsComponentSelected('iphone') then begin Installed := Installed + {#IPhoneBytes}; Downloads := Downloads + {#IPhoneDownload}; end;
  if WizardIsComponentSelected('vision') then begin Installed := Installed + {#VisionBytes}; Downloads := Downloads + {#VisionDownload}; end;
  if WizardIsComponentSelected('vocals') then begin Installed := Installed + {#VocalsBytes}; Downloads := Downloads + {#VocalsDownload}; end;
  SizeLabel.Caption := 'Total installed size: ' + Format('%.1f MB', [Installed / 1000000]) + #13#10 +
    'Optional downloads: ' + Format('%.1f MB', [Downloads / 1000000]) + #13#10 +
    'Downloads can also be added later from File > Optional downloads.';
end;

procedure ComponentsChanged(Sender: TObject);
begin
  UpdateSizeLabel();
end;

procedure InitializeWizard();
begin
  WizardForm.ComponentsList.Height := WizardForm.ComponentsList.Height - ScaleY(65);
  SizeLabel := TNewStaticText.Create(WizardForm);
  SizeLabel.Parent := WizardForm.SelectComponentsPage;
  SizeLabel.Left := WizardForm.ComponentsList.Left;
  SizeLabel.Top := WizardForm.ComponentsList.Top + WizardForm.ComponentsList.Height + ScaleY(8);
  SizeLabel.Width := WizardForm.ComponentsList.Width;
  SizeLabel.Height := ScaleY(58);
  WizardForm.ComponentsList.OnClickCheck := @ComponentsChanged;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then UpdateSizeLabel();
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Keys: String; ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
#ifdef Migration
    if not MigrationHelper('native-commit') then begin
      MigrationHelper('native-rollback');
      RaiseException('The update failed verification and application files were restored. Details are in update-error.log.');
    end;
    MigrationCommitted := True;
#endif
    Keys := SelectedKeys();
    if Keys <> '' then begin
      WizardForm.StatusLabel.Caption := 'Downloading and installing selected optional components...';
      if not Exec(ExpandConstant('{app}\KineticCut.exe'), '--install-components ' + Keys + ' "' + ExpandConstant('{src}') + '"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
        MsgBox('An optional download could not finish. The editor and captions are installed. Retry from File > Optional downloads. Details are in the KineticCut component-install.log.', mbError, MB_OK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var ResultCode, Index: Integer; Name, Folder, AppRoot: String;
begin
  if CurUninstallStep = usUninstall then begin
    if LoadStringsFromFile(ExpandConstant('{app}\_update-files.txt'), ManagedFiles) then
      Log('Current application inventory loaded: ' + IntToStr(GetArrayLength(ManagedFiles)))
    else Log('Current application inventory unavailable');
    if not Exec(ExpandConstant('{app}\KineticCut.exe'), '--uninstall-data', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException('Could not clean application data safely. Power Bin data has been preserved. Close Kinetic Cut and try again.');
  end;
  if CurUninstallStep = usPostUninstall then begin
    Log('Cleaning current application inventory: ' + IntToStr(GetArrayLength(ManagedFiles)));
    // Incremental updates may add files absent from the original Inno ownership log.
    // Only explicit application inventory paths are removed; never recurse over user folders.
    for Index := 0 to GetArrayLength(ManagedFiles) - 1 do begin
      Name := ManagedFiles[Index];
      if (Pos('..', Name) = 0) and (Pos(':', Name) = 0) and (Pos('\', Name) = 0) and
         ((Copy(Name, 1, 10) = '_internal/') or (Name = 'KineticCut.exe') or (Name = 'KineticCutUpdater.exe') or (Name = '_update.json') or (Name = '_update-files.txt')) then
      begin
        Name := ExpandConstant('{app}\') + Name;
        StringChangeEx(Name, '/', '\', True); DeleteFile(Name);
        Folder := ExtractFileDir(Name); AppRoot := ExpandConstant('{app}');
        while (Length(Folder) > Length(AppRoot)) do begin
          if not RemoveDir(Folder) then Break;
          Folder := ExtractFileDir(Folder);
        end;
      end;
    end;
  end;
end;
