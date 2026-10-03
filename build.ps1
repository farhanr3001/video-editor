$ErrorActionPreference = "Stop"
$env:PYTHONNOUSERSITE = '1'
# Building a staged release must never terminate an editor or another app's
# phone helpers. Close the editor voluntarily before installing into dist.
$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "py" }
$distPath = if ($env:KINETIC_CUT_DISTPATH) { $env:KINETIC_CUT_DISTPATH } else { "dist" }
$assetPath = if ($env:KINETIC_CUT_ASSETSPATH) { $env:KINETIC_CUT_ASSETSPATH } else { "assets" }
$buildOriginalPath = $env:PATH
$buildPythonBase = & $python -c "import sys; print(sys.base_prefix)"
try {
  # Do not collect unrelated DLLs from tools such as Poppler on the host PATH.
  # In particular Qt expects Windows' unversioned ICU exports, not Conda's ICU.
  $env:PATH = "$PWD\.venv\Scripts;$buildPythonBase;$env:SystemRoot\System32;$env:SystemRoot"
  & $python scripts/build_icon.py
  if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed" }
  & $python scripts/build_app.py --noconfirm --clean --windowed --name KineticCut --icon assets/kinetic-cut.ico --distpath $distPath `
    --runtime-hook scripts/runtime_hidden.py --version-file assets/windows-version.txt `
    --hidden-import PySide6.QtMultimedia --hidden-import PySide6.QtMultimediaWidgets `
    --hidden-import pymobiledevice3.osu.win_util --copy-metadata pymobiledevice3 --copy-metadata adbutils `
    --collect-data faster_whisper --collect-all edge_tts --collect-submodules fontTools.ttLib.tables `
    --copy-metadata fonttools --copy-metadata uharfbuzz --add-data "$assetPath;assets" `
    --add-data "THIRD_PARTY_NOTICES.txt;." main.py
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
  $env:PATH = $buildOriginalPath
}
Write-Host "Built $distPath/KineticCut/KineticCut.exe"
