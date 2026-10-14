param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $SkipInstall) {
    python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
}
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
python scripts/smoke_gui.py
if ($LASTEXITCODE -ne 0) { throw 'GUI smoke test failed.' }
python scripts/smoke_theme.py
if ($LASTEXITCODE -ne 0) { throw 'Theme smoke test failed.' }
python scripts/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
$versionFile = Join-Path $PSScriptRoot 'scripts\version_info.txt'
$iconFile = Join-Path $PSScriptRoot 'assets\workshop.ico'
python -m PyInstaller --noconfirm --clean --onefile --windowed --version-file $versionFile --icon $iconFile --name LoLLootWorkshop main.py
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Write-Host 'Built: dist\LoLLootWorkshop.exe'
