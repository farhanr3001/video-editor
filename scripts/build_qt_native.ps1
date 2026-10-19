param([string]$QtSdk='', [string]$Clang='')
$ErrorActionPreference='Stop'
$workspace=Split-Path -Parent $PSScriptRoot
if(!$QtSdk){$QtSdk=Join-Path $workspace 'build/qt-sdk-6.11.2'}
if(!$Clang){$Clang=Join-Path $workspace 'build/llvm-native/bin/clang-cl.exe'}
if(!(Test-Path -LiteralPath $Clang)){throw 'Set -Clang to a compatible clang-cl compiler (or use MSVC2022).'}
if(!(Test-Path -LiteralPath (Join-Path $QtSdk 'include/QtQuick/QQuickWindow'))){throw 'Set -QtSdk to the matching Qt C++ SDK.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$developer=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$output=Join-Path $workspace 'assets/native'
$intermediate=Join-Path $workspace 'build/native-engine'
New-Item -ItemType Directory -Force -Path $output,$intermediate | Out-Null
$script=Join-Path $intermediate 'compile-qt.cmd'
@"
@echo off
call "$developer" >nul
if errorlevel 1 exit /b 1
"$Clang" /nologo /std:c++17 /Zc:__cplusplus /permissive- /O2 /EHsc /MT /LD /I"$QtSdk/include" /I"$QtSdk/include/QtCore" /I"$QtSdk/include/QtGui" /I"$QtSdk/include/QtGui/6.11.2/QtGui" /I"$QtSdk/include/QtQuick" /I"$QtSdk/include/QtQml" /I"$QtSdk/include/QtQmlIntegration" /I"$QtSdk/include/QtMultimedia" "$workspace/native/qt_media_engine.cpp" /Fo"$intermediate/qt_media_engine.obj" /Fe"$output/qt_media_engine.dll" /link /LIBPATH:"$QtSdk/lib" Qt6Core.lib Qt6Gui.lib Qt6Quick.lib Qt6Multimedia.lib /IMPLIB:"$intermediate/qt_media_engine.lib"
exit /b %errorlevel%
"@ | Set-Content -LiteralPath $script -Encoding ASCII
& cmd.exe /d /c $script
if($LASTEXITCODE -ne 0){throw 'Native Qt media engine compilation failed.'}
