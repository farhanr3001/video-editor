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
#ifdef UninstallerRepair
DisableReadyPage=yes
#endif

[Types]
Name: "standard"; Description: "Editor and captions"
Name: "custom"; Description: "Choose optional downloads"; Flags: iscustom

[Components]
Name: "main"; Description: "Editor, FFmpeg and caption generation (always included)"; Types: standard custom; Flags: fixed
#ifndef UninstallerRepair
Name: "vision"; Description: "Face / background tools (+{#VisionMB} MB)"; ExtraDiskSpaceRequired: {#VisionBytes}
Name: "vocals"; Description: "Vocal separation (+{#VocalsMB} MB)"; ExtraDiskSpaceRequired: {#VocalsBytes}
#endif

[Files]
Source: "..\build\cleanup_phone_helpers.exe"; DestDir: "{app}\_internal"; Flags: ignoreversion
#ifndef UninstallerRepair
#ifdef Migration
Source: "..\build\incremental-update\migration\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
Source: "..\release\KineticCut-Baseline-1.1.0.json"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\KineticCutUpdater.exe"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\_update.json"; Flags: dontcopy
Source: "..\build\distribution-stage\KineticCut\_update-files.txt"; Flags: dontcopy
#else
Source: "..\build\distribution-stage\KineticCut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
#endif
#endif

[Icons]
#ifndef UninstallerRepair
#ifndef TestingSetup
Name: "{group}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"
Name: "{autodesktop}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"; Tasks: desktopicon
#endif
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Messages]
ConfirmUninstall=Remove %1 and all of its application data?%n%nThis includes Power Bins, presets, settings, recovery files, optional components, caches and files in the default Kinetic Cut download folder.
#ifdef UninstallerRepair
WelcomeLabel1=Repair Kinetic Cut uninstaller
WelcomeLabel2=This repairs the uninstaller in your existing Kinetic Cut installation without changing the editor.%n%nAfter the repair, uninstall Kinetic Cut through Windows Installed apps. The repaired uninstaller removes all application data, including Power Bins and default downloads.
#endif

[Run]
#ifndef UninstallerRepair
Filename: "{app}\KineticCut.exe"; Description: "Open Kinetic Cut"; Flags: nowait postinstall skipifsilent
#endif

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
  Log('Repair target: ' + ExpandConstant('{app}'));
#ifndef UninstallerRepair
  if WizardIsComponentSelected('vision') then Result := Result + 'vision,';
  if WizardIsComponentSelected('vocals') then Result := Result + 'vocals,';
  if Length(Result) > 0 then Delete(Result, Length(Result), 1);
#endif
end;

procedure UpdateSizeLabel();
var Installed, Downloads: Extended;
begin
  Installed := {#CoreBytes}; Downloads := 0;
#ifndef UninstallerRepair
  if WizardIsComponentSelected('vision') then begin Installed := Installed + {#VisionBytes}; Downloads := Downloads + {#VisionDownload}; end;
  if WizardIsComponentSelected('vocals') then begin Installed := Installed + {#VocalsBytes}; Downloads := Downloads + {#VocalsDownload}; end;
#endif
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
#ifndef UninstallerRepair
  WizardForm.ComponentsList.Height := WizardForm.ComponentsList.Height - ScaleY(65);
  SizeLabel := TNewStaticText.Create(WizardForm);
  SizeLabel.Parent := WizardForm.SelectComponentsPage;
  SizeLabel.Left := WizardForm.ComponentsList.Left;
  SizeLabel.Top := WizardForm.ComponentsList.Top + WizardForm.ComponentsList.Height + ScaleY(8);
  SizeLabel.Width := WizardForm.ComponentsList.Width;
  SizeLabel.Height := ScaleY(58);
  WizardForm.ComponentsList.OnClickCheck := @ComponentsChanged;
#endif
end;

procedure CurPageChanged(CurPageID: Integer);
begin
#ifndef UninstallerRepair
  if CurPageID = wpSelectComponents then UpdateSizeLabel();
#endif
end;

#ifdef UninstallerRepair
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not FileExists(ExpandConstant('{app}\unins000.dat')) then
    Result := 'Select the existing Kinetic Cut installation folder. This repair replaces its uninstaller without changing the editor.';
end;
#endif

function StopOwnedHelpers(): Boolean;
var Arguments, Home: String; Code: Integer;
begin
  Home := GetEnv('KINETIC_CUT_HOME');
#ifdef TestingSetup
  if Home = '' then begin Result := False; Exit; end;
#endif
  if Home <> '' then begin
    Home := RemoveBackslashUnlessRoot(ExpandFileName(Home));
    if Length(Home) <= Length(ExtractFileDrive(Home)) + 1 then begin Result := False; Exit; end;
    Arguments := '"' + AddBackslash(Home) + 'data" "' + AddBackslash(Home) + 'cache"';
  end else Arguments := '"' + ExpandConstant('{localappdata}\KineticCut') + '" "' + ExpandConstant('{userappdata}\KineticCut') + '"';
  Arguments := Arguments + ' "' + ExpandConstant('{app}') + '"';
  Result := Exec(ExpandConstant('{app}\_internal\cleanup_phone_helpers.exe'), Arguments, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
  if not Result and (Code = 740) then
    Result := ShellExec('runas', ExpandConstant('{app}\_internal\cleanup_phone_helpers.exe'), Arguments, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
  if not Result then Log('App-owned helper/service cleanup failed: ' + IntToStr(Code));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Keys: String; ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    if not StopOwnedHelpers() then RaiseException('Could not stop app-owned legacy helpers. Close Kinetic Cut and retry setup.');
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

function FileAttributes(Path: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function WriteFileAttributes(Path: String; Attributes: LongWord): Boolean;
  external 'SetFileAttributesW@kernel32.dll stdcall';
function NativeLastError(): LongWord;
  external 'GetLastError@kernel32.dll stdcall';

function RemoveOwnedTree(Path: String): Boolean;
var Attributes, Error: LongWord; FindRec: TFindRec; Child: String;
begin
  Attributes := FileAttributes(Path);
  Error := NativeLastError();
  Result := True;
  if Attributes = $FFFFFFFF then begin
    Result := (Error = 2) or (Error = 3);
    if not Result then Log('Cannot inspect app-owned path: ' + Path + ' (' + IntToStr(Error) + ')');
    Exit;
  end;
  // Remove junction/symlink entries themselves, never their external targets.
  if (Attributes and $10) <> 0 then begin
    if (Attributes and $400) = 0 then begin
      if FindFirst(AddBackslash(Path) + '*', FindRec) then begin
        try
          repeat
            if (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
              Child := AddBackslash(Path) + FindRec.Name;
              if not RemoveOwnedTree(Child) then Result := False;
            end;
          until not FindNext(FindRec);
        finally FindClose(FindRec); end;
      end;
    end;
    if not RemoveDir(Path) then Result := False;
  end else begin
    if (Attributes and $1) <> 0 then WriteFileAttributes(Path, Attributes and $FFFFFFFE);
    if not DeleteFile(Path) then Result := False;
  end;
  if not Result then Log('Could not remove app-owned path: ' + Path);
end;

function RemoveApplicationData(): Boolean;
var Home: String;
begin
  Home := GetEnv('KINETIC_CUT_HOME');
  Result := True;
#ifdef TestingSetup
  // Test uninstallers must never touch the owner's ordinary application data.
  if Home = '' then begin Result := False; Exit; end;
#endif
  if Home <> '' then begin
    Home := RemoveBackslashUnlessRoot(ExpandFileName(Home));
    if Length(Home) <= Length(ExtractFileDrive(Home)) + 1 then begin Result := False; Exit; end;
    if not RemoveOwnedTree(AddBackslash(Home) + 'data') then Result := False;
    if not RemoveOwnedTree(AddBackslash(Home) + 'cache') then Result := False;
    if not RemoveOwnedTree(AddBackslash(Home) + 'config') then Result := False;
    RemoveDir(Home);
  end else begin
    if not RemoveOwnedTree(ExpandConstant('{localappdata}\KineticCut')) then Result := False;
    if not RemoveOwnedTree(ExpandConstant('{userappdata}\KineticCut')) then Result := False;
    if not RemoveOwnedTree(AddBackslash(GetEnv('USERPROFILE')) + 'Downloads\Kinetic Cut') then Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Index: Integer; Name, Folder, AppRoot: String;
begin
  if CurUninstallStep = usUninstall then begin
    if LoadStringsFromFile(ExpandConstant('{app}\_update-files.txt'), ManagedFiles) then
      Log('Current application inventory loaded: ' + IntToStr(GetArrayLength(ManagedFiles)))
    else Log('Current application inventory unavailable');
    // Cleanup belongs to the uninstaller, independent of Python/Qt, missing
    // application DLLs and malformed Power Bin JSON. Power Bins are removed.
    while not (StopOwnedHelpers() and RemoveApplicationData()) do begin
      if UninstallSilent() then RaiseException('Application data is in use. Close Kinetic Cut and retry uninstalling.');
      if MsgBox('Some Kinetic Cut files are still in use. Close Kinetic Cut and its background tasks, then choose Retry to finish removing all application data.', mbError, MB_RETRYCANCEL) <> IDRETRY then
        RaiseException('Uninstall cancelled: close Kinetic Cut and retry.');
    end;
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
    RemoveOwnedTree(ExpandConstant('{app}\_internal'));
    RemoveOwnedTree(ExpandConstant('{app}\.kinetic-update'));
  end;
end;
