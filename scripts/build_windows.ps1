$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
Remove-Item build,dist,release -Recurse -Force -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --windowed --onedir --name ArchiveScout --collect-all truststore run_app.py
New-Item -ItemType Directory -Path release | Out-Null
$Package = Join-Path $PWD "release\ArchiveScout-Windows-x64"
New-Item -ItemType Directory -Path $Package | Out-Null
Copy-Item dist\ArchiveScout $Package\ArchiveScout -Recurse
Copy-Item packaging\windows\install.ps1 $Package
Copy-Item 'packaging\windows\Install Archive Scout.cmd' $Package
Copy-Item packaging\windows\uninstall.ps1 $Package
Copy-Item 'packaging\windows\Uninstall Archive Scout.cmd' $Package
Copy-Item README.md $Package
$Zip = Join-Path $PWD "release\ArchiveScout-Windows-x64.zip"
Compress-Archive -Path "$Package\*" -DestinationPath $Zip -CompressionLevel Optimal
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLower()
"$Hash  ArchiveScout-Windows-x64.zip" | Set-Content "release\ArchiveScout-Windows-x64.zip.sha256" -Encoding ascii
