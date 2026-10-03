param([string]$Output = 'build/installer-verification')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$check = [IO.Path]::GetFullPath((Join-Path $root $Output))
if (-not $check.StartsWith((Join-Path $root 'build') + [IO.Path]::DirectorySeparatorChar)) { throw 'Verification output must be in build' }
New-Item -ItemType Directory -Force -Path $check | Out-Null
$profile = Join-Path $check 'profile'
$appPath = Join-Path $check 'app'
$setup = Join-Path $root 'release/KineticCut-Setup-1.1.0.exe'
$exe = Join-Path $appPath 'KineticCut.exe'
$priorHome = $env:KINETIC_CUT_HOME
$report = [ordered]@{passed=$false; profile=$profile; install=$false; later_downloads=$false; upgrade=$false; uninstall=$false}
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "$File exited $($process.ExitCode)" }
}
try {
    $env:KINETIC_CUT_HOME=$profile
    Invoke-Checked $setup @('/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART',('/DIR="'+$appPath+'"'),('/LOG="'+$check+'/install.log"'),'/COMPONENTS=main,android','/TASKS=')
    if (-not (Test-Path $exe) -or -not (Test-Path "$profile/data/components/phone-android-v1/pack-ready.json")) { throw 'Installer selection did not install Android' }
    $report.install=$true
    $report.exe_sha256=(Get-FileHash $exe).Hash
    Invoke-Checked $exe @('--startup-selftest',('"'+$check+'/startup"'))
    if (-not (Get-Content "$check/startup/report.json" -Raw | ConvertFrom-Json).passed) {throw 'Installed startup failed'}
    New-Item -ItemType Directory -Force -Path "$profile/cache/tts","$profile/config" | Out-Null
    $kept="$profile/cache/tts/power-bin-source.wav"
    [IO.File]::WriteAllBytes($kept,[byte[]](1,2,3,4))
    $external=Join-Path $check 'external-user-project.kcut'
    [IO.File]::WriteAllText($external,'saved user project fixture')
    $power="$profile/data/powerbins.json"
    [IO.File]::WriteAllText($power,(@{media=@(@{media=@{path=$kept}})} | ConvertTo-Json -Depth 5))
    $settings="$profile/config/settings.json"
    [IO.File]::WriteAllText($settings,'{"verification_sentinel":"keep-on-upgrade"}')
    $powerHash=(Get-FileHash $power).Hash
    $sourceHash=(Get-FileHash $kept).Hash
    Invoke-Checked $exe @('--install-components','iphone,vision,vocals',('"'+$root+'/release"'))
    foreach ($key in @('phone-iphone-v1','vision-v1','vocal-only-v1')) {
        if (-not (Test-Path "$profile/data/components/$key/pack-ready.json")) {throw "Later download not installed: $key"}
    }
    $vision="$profile/data/components/vision-v1/python.exe"
    & $vision -B -c 'import mediapipe,cv2,numpy; print("vision runtime imports passed")'
    if ($LASTEXITCODE -ne 0) {throw 'Installed vision imports failed'}
    $vocals="$profile/data/components/vocal-only-v1/python.exe"
    & $vocals -B -c 'import torch,demucs,torchaudio; print("vocal runtime imports passed")'
    if ($LASTEXITCODE -ne 0) {throw 'Installed vocal imports failed'}
    $report.later_downloads=$true
    Invoke-Checked $setup @('/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART',('/DIR="'+$appPath+'"'),('/LOG="'+$check+'/upgrade.log"'),'/COMPONENTS=main,android,iphone,vision,vocals','/TASKS=')
    if ((Get-FileHash $power).Hash -ne $powerHash -or (Get-FileHash $kept).Hash -ne $sourceHash -or -not (Test-Path $settings)) {throw 'Upgrade lost user data'}
    $report.upgrade=$true
    Invoke-Checked (Join-Path $appPath 'unins000.exe') @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="'+$check+'/uninstall.log"'))
    if ((Get-FileHash $power).Hash -ne $powerHash -or (Get-FileHash $kept).Hash -ne $sourceHash -or -not (Test-Path $external)) {throw 'Uninstall did not preserve Power Bin or external project'}
    if ((Test-Path "$profile/data/components") -or (Test-Path $settings) -or (Test-Path $exe)) {throw 'Uninstall left app-owned components/settings/program'}
    $uninstallKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{EB1F3D12-5AF0-481F-9CAB-3F8438E2D0B4}_is1'
    if (Test-Path $uninstallKey) {throw 'Windows Apps registration remains after uninstall'}
    $report.uninstall=$true; $report.passed=$true
} finally {
    $env:KINETIC_CUT_HOME=$priorHome
    $report | ConvertTo-Json -Depth 5 | Set-Content "$check/report.json"
}
