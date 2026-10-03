#include "sizes.iss"

[Setup]
AppId={{EB1F3D12-5AF0-481F-9CAB-3F8438E2D0B4}
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
OutputBaseFilename=KineticCut-Setup-{#AppVersion}
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
Source: "..\build\distribution-stage\KineticCut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main

[Icons]
Name: "{group}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"
Name: "{autodesktop}\Kinetic Cut"; Filename: "{app}\KineticCut.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\KineticCut.exe"; Description: "Open Kinetic Cut"; Flags: nowait postinstall skipifsilent

[Code]
var
  SizeLabel: TNewStaticText;

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
    Keys := SelectedKeys();
    if Keys <> '' then begin
      WizardForm.StatusLabel.Caption := 'Downloading and installing selected optional components...';
      if not Exec(ExpandConstant('{app}\KineticCut.exe'), '--install-components ' + Keys + ' "' + ExpandConstant('{src}') + '"', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
        MsgBox('An optional download could not finish. The editor and captions are installed. Retry from File > Optional downloads. Details are in the KineticCut component-install.log.', mbError, MB_OK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then begin
    if not Exec(ExpandConstant('{app}\KineticCut.exe'), '--uninstall-data', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException('Could not clean application data safely. Power Bin data has been preserved. Close Kinetic Cut and try again.');
  end;
end;
