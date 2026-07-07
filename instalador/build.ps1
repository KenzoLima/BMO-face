# Build do BMO: gera dist\BMO\ (PyInstaller) e o instalador (Inno Setup).
# Uso:  powershell -ExecutionPolicy Bypass -File instalador\build.ps1
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$python = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "venv nao encontrado em $python" }

Write-Host '[1/3] PyInstaller...' -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean --noconsole --name BMO `
    --add-data 'modelos;modelos' `
    --collect-data speech_recognition `
    main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou' }

Write-Host '[2/3] Testes rapidos do exe...' -ForegroundColor Cyan
if (-not (Test-Path "$raiz\dist\BMO\BMO.exe")) { throw 'BMO.exe nao foi gerado' }

Write-Host '[3/3] Instalador (Inno Setup)...' -ForegroundColor Cyan
$iscc = "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) {
    & $iscc "$PSScriptRoot\bmo.iss"
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup falhou' }
    Write-Host "Instalador em: $PSScriptRoot\saida\" -ForegroundColor Green
} else {
    Write-Warning 'Inno Setup nao encontrado; gerando zip portatil.'
    Compress-Archive -Path "$raiz\dist\BMO\*" -DestinationPath "$PSScriptRoot\saida\BMO-portatil.zip" -Force
}
