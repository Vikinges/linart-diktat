# Builds the exe (PyInstaller) and the offline installer (Inno Setup).
# Usage:  powershell -ExecutionPolicy Bypass -File build\build.ps1 [-Version 2.0.0] [-Python "C:\Program Files\Python312\python.exe"] [-Iscc path\ISCC.exe]
param(
    [string]$Version = "2.0.0",
    [string]$Python = "python",
    [string]$Iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Build = $PSScriptRoot
Set-Location $Build

# 1) clean build venv
if (-not (Test-Path "$Build\venv\Scripts\python.exe")) { & $Python -m venv "$Build\venv" }
$Py = "$Build\venv\Scripts\python.exe"
& $Py -m pip install --disable-pip-version-check -q -r "$Root\requirements.txt" pyinstaller
if ($LASTEXITCODE) { throw "pip failed" }

# 2) icon + exe
& $Py "$Build\make_icon.py" "$Build\icon.ico"
& $Py -m PyInstaller --noconfirm --clean --windowed --name LinArtDiktat --icon "$Build\icon.ico" `
    --paths "$Root\app" --hidden-import pystray._win32 `
    --distpath "$Build\dist" --workpath "$Build\work" --specpath "$Build\work" "$Root\app\linart_diktat.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# 3) stage: app + engines + models (engines/models come from download_engines.ps1)
$Stage = "$Build\stage"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force "$Stage\app", "$Stage\engines", "$Stage\models", "$Stage\docs" | Out-Null
Copy-Item "$Build\dist\LinArtDiktat\*" "$Stage\app" -Recurse
Copy-Item "$Root\engines\*" "$Stage\engines" -Recurse
foreach ($m in "ggml-large-v3-turbo-q8_0.bin", "translategemma-4b-it-Q4_K_M.gguf") {
    if (-not (Test-Path "$Root\models\$m")) { throw "missing model $m - run build\download_engines.ps1 first" }
    cmd /c mklink /H "$Stage\models\$m" "$Root\models\$m" | Out-Null
    if (-not (Test-Path "$Stage\models\$m")) { Copy-Item "$Root\models\$m" "$Stage\models\$m" }
}
Copy-Item "$Root\LICENSE", "$Root\NOTICE", "$Root\THIRD_PARTY_NOTICES.md" "$Stage\docs"

# 4) installer
& $Iscc "/DAppVersion=$Version" "$Build\installer.iss"
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-ChildItem "$Build\output" | ForEach-Object { "{0,14:N0}  {1}" -f $_.Length, $_.Name }
