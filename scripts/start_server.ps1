# EmpleoIA — Servidor de Producción (uvicorn)
# Uso: .\scripts\start_server.ps1 [-Port 5000] [-Workers 1] [-ServerHost 0.0.0.0]
# Sirve main:app (FastAPI + Flask montado): parte de la API vive solo en FastAPI, así que no alcanza con app:app.

param(
    [int]$Port    = 5000,
    [int]$Workers = 1,   # job_status de scraping vive en memoria: más de 1 worker requiere SCRAPER_BACKEND=celery
    [string]$ServerHost = "0.0.0.0"
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

Write-Host "🚀 Iniciando EmpleoIA con uvicorn..." -ForegroundColor Cyan
Write-Host "   Host   : $ServerHost" -ForegroundColor Gray
Write-Host "   Puerto : $Port" -ForegroundColor Gray
Write-Host "   Workers: $Workers" -ForegroundColor Gray
Write-Host ""

& $venvPython -m uvicorn main:app --host $ServerHost --port $Port --workers $Workers
