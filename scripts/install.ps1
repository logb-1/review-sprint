#requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Test-Python([string]$exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $false }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

$candidates = @()
if ($env:DSH_PYTHON) { $candidates += $env:DSH_PYTHON }

$dshRoot = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes"
if (Test-Path -LiteralPath $dshRoot) {
    $bundled = Get-ChildItem $dshRoot -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\dependencies\\python\\python\.exe$" } |
        Select-Object -First 1
    if ($bundled) { $candidates += $bundled.FullName }
}

foreach ($name in @("python", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { $candidates += $cmd.Source }
}

if (Test-Path -LiteralPath "$env:LOCALAPPDATA\Programs\Python") {
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
}

foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-Python $candidate) {
        & $candidate -X utf8 (Join-Path $root "scripts\install.py") @args
        exit $LASTEXITCODE
    }
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pyLauncher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if ($ok) {
        & $pyLauncher.Source -3 -X utf8 (Join-Path $root "scripts\install.py") @args
        exit $LASTEXITCODE
    }
}

Write-Host "Python 3.10+ was not found."
Write-Host "Install Python from https://www.python.org/downloads/ or set DSH_PYTHON."
exit 127
