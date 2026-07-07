# Build do BMO: gera dist\BMO\ (PyInstaller) e o instalador (Inno Setup).
# Uso:  powershell -ExecutionPolicy Bypass -File instalador\build.ps1
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$python = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "venv nao encontrado em $python" }

Write-Host '[1/4] Ícone...' -ForegroundColor Cyan
& $python instalador\gerar_icone.py
if ($LASTEXITCODE -ne 0) { throw 'geração do ícone falhou' }

Write-Host '[2/5] Tkinter...' -ForegroundColor Cyan
& $python -c "import tkinter as tk; r = tk.Tk(); r.withdraw(); r.update_idletasks(); r.destroy(); print('Tkinter OK')"
if ($LASTEXITCODE -ne 0) {
    throw 'Tkinter/Tcl indisponivel neste Python. Recrie a .venv com uma instalacao normal do Python para nao gerar um pacote sem tela de configuracao.'
}

Write-Host '[3/5] PyInstaller...' -ForegroundColor Cyan
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$workPath = Join-Path $raiz "build\pyinstaller-$stamp"
$specPath = Join-Path $raiz "build\spec-$stamp"

# Caminhos do --add-data/--icon são resolvidos relativos à pasta do .spec.
# Como usamos --specpath em build\spec-<stamp>, passamos caminhos ABSOLUTOS
# para o PyInstaller achar os arquivos na raiz do projeto.
$icone = Join-Path $raiz 'instalador\bmo.ico'
$dataModelos = (Join-Path $raiz 'modelos') + ';modelos'
$dataIcone = $icone + ';.'

& $python -m PyInstaller --noconfirm --noconsole --name BMO `
    --workpath $workPath `
    --specpath $specPath `
    --distpath (Join-Path $raiz 'dist') `
    --icon $icone `
    --add-data $dataModelos `
    --add-data $dataIcone `
    --exclude-module pandas `
    --exclude-module openpyxl `
    --exclude-module matplotlib `
    --exclude-module scipy `
    --exclude-module pytest `
    --exclude-module IPython `
    --exclude-module jinja2 `
    --exclude-module torch `
    --exclude-module tensorflow `
    --exclude-module speech_recognition.recognizers.pocketsphinx `
    --exclude-module speech_recognition.recognizers.whisper_api `
    --exclude-module speech_recognition.recognizers.whisper_local `
    --exclude-module speech_recognition.pocketsphinx-data `
    main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou' }

$sr = Join-Path $raiz 'dist\BMO\_internal\speech_recognition'
$lixoRuntime = @(
    (Join-Path $sr 'pocketsphinx-data'),
    (Join-Path $sr 'flac-linux-x86'),
    (Join-Path $sr 'flac-linux-x86_64'),
    (Join-Path $sr 'flac-mac')
)
foreach ($item in $lixoRuntime) {
    if (Test-Path $item) { Remove-Item -Recurse -Force $item }
}

Write-Host '[4/5] Testes rapidos do exe...' -ForegroundColor Cyan
if (-not (Test-Path "$raiz\dist\BMO\BMO.exe")) { throw 'BMO.exe nao foi gerado' }

Write-Host '[5/5] Instalador (Inno Setup)...' -ForegroundColor Cyan
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
