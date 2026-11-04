#requires -Version 5.1
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "coach.py"

function Test-Python([string]$exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $false }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $exe -c "import sys" 2>$null | Out-Null
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
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and $py.Source -notmatch "WindowsApps") { $candidates += $py.Source }
$candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName

foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-Python $candidate) {
        & $candidate $script @args
        exit $LASTEXITCODE
    }
}
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pyLauncher.Source -3 -c "import sys" 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if ($ok) {
        & $pyLauncher.Source -3 $script @args
        exit $LASTEXITCODE
    }
}
Write-Error "Python 3 not found. Set DSH_PYTHON or install Python 3.10+."
exit 127
