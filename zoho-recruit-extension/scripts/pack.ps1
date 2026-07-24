# Pack Marketplace ZIP without Node (Windows PowerShell).
# Usage: powershell -File scripts/pack.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$staging = Join-Path $root 'dist\_pack'
$zip = Join-Path $root 'dist\VoxBulk-Zoho-Recruit-Widget.zip'

if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null
Copy-Item (Join-Path $root 'plugin-manifest.json') $staging
Copy-Item -Recurse (Join-Path $root 'app') (Join-Path $staging 'app')
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $staging 'plugin-manifest.json'), (Join-Path $staging 'app') -DestinationPath $zip
Remove-Item -Recurse -Force $staging
Write-Host "Wrote $zip"
