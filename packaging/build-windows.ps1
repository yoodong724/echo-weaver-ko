param([Parameter(Mandatory = $true)][string]$Version)
$ErrorActionPreference = 'Stop'
$Project = [IO.Path]::GetFullPath((Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath)
$Venv = Join-Path $Project 'runtime\build-venv'
$Python = Join-Path $Venv 'Scripts\python.exe'
$Snapshot = (Get-Content (Join-Path $Project 'config\project.json') -Raw -Encoding UTF8 | ConvertFrom-Json).source.snapshot
$Record = Join-Path $Project "data\review\$Snapshot\release-$Version"
New-Item -ItemType Directory -Force $Record | Out-Null
$env:PYTHONUTF8 = '1'
# Native stderr carries normal pip/PyInstaller logs; use process exit codes.
$ErrorActionPreference = 'Continue'
if (-not (Test-Path $Python)) {
    & py -3.11 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 venv creation failed' }
}
& $Python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt') > (Join-Path $Record 'pip.stdout.txt') 2> (Join-Path $Record 'pip.stderr.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed; see pip log' }
& $Python (Join-Path $PSScriptRoot 'build_windows.py') $Version > (Join-Path $Record 'build.stdout.txt') 2> (Join-Path $Record 'build.stderr.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build failed; see build log' }
Get-Content (Join-Path $Record 'build.stdout.txt') -Tail 1
