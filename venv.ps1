param(
    [switch]$Activate
)

$ErrorActionPreference = "Stop"

$venvDir = Join-Path $PSScriptRoot ".venv"
$venvExists = Test-Path $venvDir

Write-Host "=====================================================" -ForegroundColor Cyan
if ($venvExists) {
    Write-Host " Checking & syncing existing .venv (uv)" -ForegroundColor Cyan
} else {
    Write-Host " Creating new uv virtual environment (.venv)" -ForegroundColor Cyan
}
Write-Host "=====================================================" -ForegroundColor Cyan

function Find-Uv {
    $cmd = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

$uvExe = Find-Uv

if (-not $uvExe) {
    Write-Host "[ERROR] 'uv' is not installed or not on PATH." -ForegroundColor Red
    Write-Host "Please install uv first:" -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor Yellow
    Write-Host "Docs: https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Using uv: $uvExe" -ForegroundColor Green

Push-Location $PSScriptRoot
try {
    if ($venvExists) {
        Write-Host "`nSyncing .venv with pyproject.toml and uv.lock..." -ForegroundColor Cyan
    } else {
        Write-Host "`nCreating .venv and installing dependencies..." -ForegroundColor Cyan
    }

    & $uvExe sync
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] 'uv sync' failed with exit code $LASTEXITCODE." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"

Write-Host "`n=====================================================" -ForegroundColor Cyan
if ($venvExists) {
    Write-Host " Environment Up-to-Date!" -ForegroundColor Green
} else {
    Write-Host " Environment Created!" -ForegroundColor Green
}
if (Test-Path $venvPython) {
    $pyVer = & $venvPython --version 2>&1
    Write-Host " Python : $pyVer ($venvPython)" -ForegroundColor Cyan
}
Write-Host " Run    : uv run python live_ble_receiver.py" -ForegroundColor Cyan
Write-Host " Deploy : .\deploy_all.ps1" -ForegroundColor Cyan
Write-Host " Activate manually: .\.venv\Scripts\Activate.ps1" -ForegroundColor DarkGray
Write-Host "=====================================================" -ForegroundColor Cyan

if ($Activate -and (Test-Path $activateScript)) {
    & $activateScript
}
