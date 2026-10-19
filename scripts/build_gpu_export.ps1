param([string]$QtSdk='', [string]$Clang='')
$ErrorActionPreference='Stop'
$workspace=Split-Path -Parent $PSScriptRoot
if(!$QtSdk){$QtSdk=Join-Path $workspace 'build/qt-sdk-6.11.2'}
if(!$Clang){$Clang=Join-Path $workspace 'build/llvm-native/bin/clang-cl.exe'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$developer=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$intermediate=Join-Path $workspace 'build/native-engine'
$output=Join-Path $workspace 'assets/native'
New-Item -ItemType Directory -Force -Path $intermediate,$output | Out-Null
$script=Join-Path $intermediate 'compile-export.cmd'
@"
@echo off
call "$developer" >nul
if errorlevel 1 exit /b 1
"$Clang" /nologo /std:c++17 /Zc:__cplusplus /permissive- /O2 /EHsc /MT /LD /I"$QtSdk/include" /I"$QtSdk/include/QtCore" "$workspace/native/gpu_export.cpp" /Fo"$intermediate/gpu_export.obj" /Fe"$output/gpu_export.dll" /link /LIBPATH:"$QtSdk/lib" Qt6Core.lib dxgi.lib d3d11.lib d3dcompiler.lib mf.lib mfplat.lib mfreadwrite.lib mfuuid.lib ole32.lib propsys.lib windowscodecs.lib /IMPLIB:"$intermediate/gpu_export.lib"
exit /b %errorlevel%
"@ | Set-Content -LiteralPath $script -Encoding ASCII
& cmd.exe /d /c $script
if($LASTEXITCODE -ne 0){throw 'Native GPU export compilation failed.'}
