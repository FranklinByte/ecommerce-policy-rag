param([int]$Port = 8010)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Run with -Port <another port>."
}
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$uv = Join-Path $projectRoot '.venv/Scripts/uv.exe'
if (-not (Test-Path $uv)) {
    & $python -m pip install uv==0.8.17
    if ($LASTEXITCODE -ne 0) { throw 'uv installation failed' }
}
& $uv sync --frozen --extra dev --native-tls
if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed' }
& $python -m policy_rag.cli download-models
if ($LASTEXITCODE -ne 0) { throw 'Pinned model download failed' }
& $python -m policy_rag.cli index
if ($LASTEXITCODE -ne 0) { throw 'Index build failed' }
Write-Host "http://127.0.0.1:$Port"
& $python -m policy_rag.cli serve --port $Port
