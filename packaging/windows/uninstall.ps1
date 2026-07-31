$ErrorActionPreference = "SilentlyContinue"
$Destination = Join-Path $env:LOCALAPPDATA "Programs\ArchiveScout"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Archive Scout.lnk"
$StartDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Archive Scout"
Remove-Item $DesktopShortcut -Force
Remove-Item $StartDirectory -Recurse -Force
Start-Process powershell.exe -ArgumentList "-NoProfile -Command Start-Sleep -Seconds 2; Remove-Item -LiteralPath '$Destination' -Recurse -Force" -WindowStyle Hidden
Write-Host "Archive Scout was uninstalled. Research project folders were not removed."
