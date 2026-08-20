# Register RUTE Tray App to run at Windows logon
# Run this script once (elevated is NOT required — uses current user context)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File register_autostart.ps1
#
# To unregister:
#   Unregister-ScheduledTask -TaskName "RUTE Backend Launcher" -Confirm:$false

$TaskName = "RUTE Backend Launcher"
$BackendDir = "D:\RUTE\backend"
$VenvPython = "$BackendDir\venv\Scripts\pythonw.exe"
$TrayScript = "$BackendDir\tray_app.py"

# Check if pythonw.exe exists (windowless Python — no console flash)
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: pythonw.exe not found at $VenvPython" -ForegroundColor Red
    Write-Host "Make sure the venv is set up: python -m venv venv"
    exit 1
}

# Check if tray_app.py exists
if (-not (Test-Path $TrayScript)) {
    Write-Host "ERROR: tray_app.py not found at $TrayScript" -ForegroundColor Red
    exit 1
}

# Remove existing task if it exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the task
$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "`"$TrayScript`"" `
    -WorkingDirectory $BackendDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # No timeout — runs forever

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Launches RUTE AI Trading Backend tray app at user logon"

Write-Host ""
Write-Host "SUCCESS: '$TaskName' registered." -ForegroundColor Green
Write-Host "The tray app will start automatically next time you log in."
Write-Host ""
Write-Host "To test now:  & `"$VenvPython`" `"$TrayScript`""
Write-Host "To remove:    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
