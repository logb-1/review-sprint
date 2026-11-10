param(
  [string]$Destination = (Join-Path $env:USERPROFILE ".dsh\skills\review-sprint")
)
$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
if (Test-Path $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -LiteralPath (Join-Path $source "SKILL.md") -Destination $Destination
Copy-Item -LiteralPath (Join-Path $source "SECURITY.md") -Destination $Destination
Copy-Item -LiteralPath (Join-Path $source "scripts") -Destination $Destination -Recurse
Copy-Item -LiteralPath (Join-Path $source "references") -Destination $Destination -Recurse
Get-ChildItem $Destination -Recurse -Directory -Filter "__pycache__" | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Write-Host "Installed review-sprint skill body to $Destination"
