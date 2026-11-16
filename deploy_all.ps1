param(
    [string]$ScriptPath = "agent_robot.py",
    [int[]]$RobotIds = 1..10,
    [string]$HubNamePrefix = "Held-"
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " Deploying '$ScriptPath' to $($RobotIds.Count) Pybricks Hubs" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# Check if pybricksdev is installed
if (-not (Get-Command "pybricksdev" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] 'pybricksdev' CLI not found. Installing via pip..." -ForegroundColor Yellow
    pip install pybricksdev
}

$Success = @()
$Failed  = @()

foreach ($id in $RobotIds) {
    $hubName = "$HubNamePrefix$id"
    Write-Host "`n[$id/$($RobotIds.Count)] Connecting to '$hubName' over BLE..." -ForegroundColor Cyan

    # --no-wait uploads the script to the hub, starts it (entering Standby mode),
    # and immediately disconnects so we can move on to the next robot.
    pybricksdev run ble --name "$hubName" --no-wait "$ScriptPath"

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
    Write-Host "  .\deploy_all.ps1 -RobotIds $retryIds" -ForegroundColor Yellow
}
