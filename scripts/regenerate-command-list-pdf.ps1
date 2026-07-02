# Regenerate docs/COMMAND-LIST.pdf from docs/COMMAND-LIST.html (Edge headless).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Html = Join-Path $Root "docs\COMMAND-LIST.html"
$Pdf = Join-Path $Root "docs\COMMAND-LIST.pdf"

if (-not (Test-Path $Html)) {
    Write-Error "Missing HTML file. Run: python scripts/generate-command-list.py"
}

$Edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $Edge)) {
    $Edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}
if (-not (Test-Path $Edge)) {
    Write-Error "Microsoft Edge not found for PDF generation."
}

$Resolved = (Resolve-Path $Html).Path
$Uri = "file:///" + ($Resolved -replace '\\', '/')
& $Edge --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$Pdf" $Uri 2>$null
Start-Sleep -Seconds 2

if (-not (Test-Path $Pdf)) {
    Write-Error "PDF was not created."
}
Write-Host "Wrote PDF:" $Pdf
