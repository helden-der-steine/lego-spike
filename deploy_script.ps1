param(
    [string]$ScriptPath = "src\run_robot.py",
    [int[]]$RobotIds = 1..10,
    [string]$HubNamePrefix = "Held-"
)

# Ensure .venv is created and synced via uv before deploying
& (Join-Path $PSScriptRoot "venv.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pybricksdevExe = Join-Path $PSScriptRoot ".venv\Scripts\pybricksdev.exe"
if (-not (Test-Path $pybricksdevExe)) {
    Write-Host "[ERROR] 'pybricksdev.exe' not found at '$pybricksdevExe'." -ForegroundColor Red
    exit 1
}

# Sync config.toml -> src/shared/generated_config.py so hubs receive latest settings
& $venvPython -m host.config_sync
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to sync config.toml for hub deployment." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " Deploying '$ScriptPath' to $($RobotIds.Count) Pybricks Hubs" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$Success = @()
$Failed  = @()

foreach ($id in $RobotIds) {
    $hubName = "$HubNamePrefix$id"
    Write-Host "`n[$id/$($RobotIds.Count)] Connecting to '$hubName' over BLE..." -ForegroundColor Cyan

    # --no-wait uploads the script to the hub, starts it (entering Standby mode),
    # and immediately disconnects so we can move on to the next robot.
    & $pybricksdevExe run ble --name "$hubName" --no-wait "$ScriptPath"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] '$hubName' updated and running in Standby!" -ForegroundColor Green
        $Success += $hubName
    } else {
        Write-Host "  [FAIL] Could not deploy to '$hubName' (is the hub turned on and not connected to the browser?)" -ForegroundColor Red
        $Failed += $hubName
    }
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " Deployment Summary" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Succeeded ($($Success.Count)): $($Success -join ', ')" -ForegroundColor Green
if ($Failed.Count -gt 0) {
    Write-Host "Failed    ($($Failed.Count)): $($Failed -join ', ')" -ForegroundColor Red
    Write-Host "`nTip: To retry only failed robots, run:" -ForegroundColor Yellow
    $retryIds = ($Failed | ForEach-Object { $_ -replace "^$HubNamePrefix", "" }) -join ","
    Write-Host "  .\deploy_script.ps1 -RobotIds $retryIds" -ForegroundColor Yellow
}
