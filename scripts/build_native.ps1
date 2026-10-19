$ErrorActionPreference='Stop'
$workspace=Split-Path -Parent $PSScriptRoot
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $installation){throw 'The C++ build tools are required to build the native preview engine.'}
$developer=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$output=Join-Path $workspace 'assets/native'
$intermediate=Join-Path $workspace 'build/native-engine'
New-Item -ItemType Directory -Force -Path $output,$intermediate | Out-Null
$script=Join-Path $intermediate 'compile.cmd'
@"
@echo off
call "$developer" >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /MT /LD "$workspace/native/kinetic_engine.cpp" /Fo"$intermediate/kinetic_engine.obj" /Fe"$output/kinetic_engine.dll" /link /IMPLIB:"$intermediate/kinetic_engine.lib"
exit /b %errorlevel%
"@ | Set-Content -LiteralPath $script -Encoding ASCII
& cmd.exe /d /c $script
if($LASTEXITCODE -ne 0){throw 'Native engine compilation failed.'}
