# run.ps1 - Levanta el stack CityBikes (G04) con UN solo comando.
# Uso (PowerShell, parado en esta carpeta):   .\run.ps1
# Si dice "running scripts is disabled":       powershell -ExecutionPolicy Bypass -File .\run.ps1

Set-Location $PSScriptRoot

Write-Host "==> Chequeando Docker..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker Desktop no esta corriendo. Abrilo, espera a que arranque y reintenta." -ForegroundColor Red
    exit 1
}

# El paso que todos se olvidan: crear el .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> .env creado desde .env.example" -ForegroundColor Green
} else {
    Write-Host "==> .env ya existe" -ForegroundColor Green
}

Write-Host "==> Levantando el stack (docker compose up --build)..." -ForegroundColor Cyan
Write-Host "    Dashboard -> http://localhost:8501   |   Airflow -> http://localhost:8080" -ForegroundColor DarkGray
docker compose up --build
