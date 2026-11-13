# EmpleoIA — Servidor (uvicorn + FastAPI)
# Uso: .\scripts\start_server.ps1
# Entry point canónico: uvicorn main:app (también usado por Docker)

param(
    [int]$Port    = 5000,
    [string]$ServerHost = "127.0.0.1"
)

# Detectar directorio del script y subir un nivel (raiz del proyecto)
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Set-Location $projectRoot

# Activar entorno virtual si existe
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

Write-Host "Iniciando EmpleoIA con uvicorn (main:app)..." -ForegroundColor Cyan
Write-Host "   Host   : $ServerHost" -ForegroundColor Gray
Write-Host "   Puerto : $Port" -ForegroundColor Gray
Write-Host ""

& $venvPython -m uvicorn main:app --host $ServerHost --port $Port
