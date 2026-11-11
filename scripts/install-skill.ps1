param(
  [ValidateSet("dsh", "claude", "codex", "cursor", "all", "custom")]
  [string]$Target = "dsh",
  [string]$Destination = ""
)
$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot

$targets = @{
  dsh    = Join-Path $env:USERPROFILE ".dsh\skills\review-sprint"
  claude = Join-Path $env:USERPROFILE ".claude\skills\review-sprint"
  codex  = Join-Path $env:USERPROFILE ".codex\skills\review-sprint"
  cursor = Join-Path $env:USERPROFILE ".cursor\skills\review-sprint"
}

function Install-One([string]$dest) {
  if (Test-Path -LiteralPath $dest) {
    Remove-Item -LiteralPath $dest -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Copy-Item -LiteralPath (Join-Path $source "SKILL.md") -Destination $dest
  Copy-Item -LiteralPath (Join-Path $source "SECURITY.md") -Destination $dest
  Copy-Item -LiteralPath (Join-Path $source "COMPATIBILITY.md") -Destination $dest
  Copy-Item -LiteralPath (Join-Path $source "requirements-optional.txt") -Destination $dest
  Copy-Item -LiteralPath (Join-Path $source "scripts") -Destination $dest -Recurse
  Copy-Item -LiteralPath (Join-Path $source "references") -Destination $dest -Recurse
  Get-ChildItem $dest -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

  # Substitute the absolute install path so the skill does not depend on $SKILL_DIR.
  $skill = Join-Path $dest "SKILL.md"
  $text = [System.IO.File]::ReadAllText($skill)
  $posix = $dest.Replace("\", "/")
  $text = $text.Replace('$SKILL_DIR', $posix)
  [System.IO.File]::WriteAllText(
    $skill,
    $text,
    (New-Object System.Text.UTF8Encoding($false))
  )
  Write-Host "Installed review-sprint skill body to $dest"
}

if ($Destination) {
  Install-One $Destination
  exit 0
}
if ($Target -eq "all") {
  foreach ($name in @("dsh", "claude", "codex", "cursor")) {
    Install-One $targets[$name]
  }
  exit 0
}
if ($Target -eq "custom") {
  throw "Custom install requires -Destination."
}
Install-One $targets[$Target]
