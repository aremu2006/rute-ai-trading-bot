$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\RUTE_Backend.lnk")
$Shortcut.TargetPath = "D:\RUTE\START_RUTE_BACKEND.bat"
$Shortcut.WorkingDirectory = "D:\RUTE\backend"
$Shortcut.WindowStyle = 1
$Shortcut.Description = "RUTE AI Trading Backend"
$Shortcut.Save()
Write-Host "Startup shortcut created successfully!"
