# EmpleoIA — Servidor de Producción (Waitress)
# Uso: .\.venv\Scripts\python.exe scripts\start_server.ps1
# O directamente: python -c "from waitress import serve; from app import app; serve(app, host='0.0.0.0', port=5000, threads=4)"

# Alternativa PowerShell:
# .\venv\Scripts\Activate.ps1
# waitress-serve --host=0.0.0.0 --port=5000 --threads=4 app:app

param(
    [int]$Port    = 5000,
    [int]$Threads = 4,
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

Write-Host "🚀 Iniciando EmpleoIA con Waitress..." -ForegroundColor Cyan
Write-Host "   Host   : $ServerHost" -ForegroundColor Gray
Write-Host "   Puerto : $Port" -ForegroundColor Gray
Write-Host "   Threads: $Threads" -ForegroundColor Gray
Write-Host ""

& $venvPython -c @"
from waitress import serve
from app import app
import logging
logging.basicConfig(level=logging.INFO)
print(f'EmpleoIA corriendo en http://localhost:$Port')
serve(app, host='$ServerHost', port=$Port, threads=$Threads)
"@
