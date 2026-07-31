$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "ArchiveScout"
$Destination = Join-Path $env:LOCALAPPDATA "Programs\ArchiveScout"
if (-not (Test-Path $Source)) { throw "ArchiveScout application folder was not found." }
if (Test-Path $Destination) { Remove-Item $Destination -Recurse -Force }
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item "$Source\*" $Destination -Recurse -Force
$Shell = New-Object -ComObject WScript.Shell
$DesktopShortcut = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Archive Scout.lnk"))
$DesktopShortcut.TargetPath = Join-Path $Destination "ArchiveScout.exe"
$DesktopShortcut.WorkingDirectory = $Destination
$DesktopShortcut.Save()
$StartDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Archive Scout"
New-Item -ItemType Directory -Path $StartDirectory -Force | Out-Null
$StartShortcut = $Shell.CreateShortcut((Join-Path $StartDirectory "Archive Scout.lnk"))
$StartShortcut.TargetPath = Join-Path $Destination "ArchiveScout.exe"
$StartShortcut.WorkingDirectory = $Destination
$StartShortcut.Save()
$UninstallShortcut = $Shell.CreateShortcut((Join-Path $StartDirectory "Uninstall Archive Scout.lnk"))
$UninstallShortcut.TargetPath = "powershell.exe"
$UninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Destination 'uninstall.ps1')`""
$UninstallShortcut.WorkingDirectory = $Destination
$UninstallShortcut.Save()
Copy-Item (Join-Path $PSScriptRoot "uninstall.ps1") $Destination -Force
Write-Host "Archive Scout was installed successfully."
