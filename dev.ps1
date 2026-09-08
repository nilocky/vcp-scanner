$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

Write-Host "Starting backend (uvicorn on :8000)..."
$backend = Start-Process -FilePath "uv" -WorkingDirectory $backendDir `
  -ArgumentList @("run", "uvicorn", "app.main:app", "--reload", "--port", "8000") `
  -WindowStyle Hidden -PassThru

Write-Host "Starting frontend (vite on :5173)..."
$frontend = Start-Process -FilePath "npm.cmd" -WorkingDirectory $frontendDir `
  -ArgumentList @("run", "dev") `
  -WindowStyle Hidden -PassThru

Write-Host ""
Write-Host "Backend:  http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:5173"
Write-Host "Press Ctrl+C to stop both."
Write-Host ""

try {
  while ($true) { Start-Sleep -Seconds 1 }
} finally {
  Stop-Process -Id $backend.Id, $frontend.Id -Force -ErrorAction SilentlyContinue
  Write-Host "Stopped."
}