param([Parameter(Mandatory = $true)][string]$Version, [string]$PreviousVersion, [string]$Snapshot)
$ErrorActionPreference = 'Stop'
$Project = [IO.Path]::GetFullPath((Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath)
$Config = Get-Content (Join-Path $Project 'config\project.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Snapshot) { $Snapshot = $Config.source.snapshot }
$Stage = Join-Path $Project "data\review\$Snapshot\release-$Version"
$Zip = Join-Path $Project "dist\EchoWeaver-KO-$Version.zip"
$Suffix = ''
if ($Version -match '-rc([1-9][0-9]*)$') { $Suffix = "-rc$($Matches[1])" }
$NamedZip = Join-Path $Project "dist\EchoWeaver-KO-$Snapshot$Suffix.zip"
if (Test-Path -LiteralPath $NamedZip) { $Zip = $NamedZip }
# Local NTFS like a real install; Korean, spaces and parentheses in the game path; a second copy without a game.
$Base = Join-Path ([IO.Path]::GetTempPath()) "ew-package-test\$Version"
$GameCopy = Join-Path $Base ([string]::Concat([char]0xAC8C, [char]0xC784, ' (test)'))
$Misplaced = Join-Path $Base 'misplaced'
$Package = Join-Path $GameCopy 'KoreanPatch'
$Data = Join-Path $GameCopy 'Echo Weaver_Data'
$Bundle = Join-Path $Data 'data.unity3d'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force $Stage | Out-Null

# Fixture: original bundle and DLL from the project backup, other Managed DLLs from the installed game.
if (Test-Path -LiteralPath $Base) { Remove-Item -LiteralPath $Base -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $Data 'Managed'), $Misplaced | Out-Null
$Backup = Join-Path $Project "backups\$Snapshot"
$InstalledManaged = Join-Path ($Config.game.root -replace '^/mnt/([a-z])/', '$1:/') 'Echo Weaver_Data\Managed'
Get-ChildItem -LiteralPath $InstalledManaged -Filter '*.dll' | Copy-Item -Destination (Join-Path $Data 'Managed')
Get-ChildItem -LiteralPath (Join-Path $Backup 'Echo Weaver_Data\Managed') -Filter '*.dll' | Copy-Item -Destination (Join-Path $Data 'Managed') -Force
Copy-Item -LiteralPath (Join-Path $Backup 'data.unity3d') -Destination $Bundle
Expand-Archive -LiteralPath $Zip -DestinationPath $GameCopy
Expand-Archive -LiteralPath $Zip -DestinationPath $Misplaced
$Patch = Get-Content (Join-Path $Package 'patch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$Original = $Patch.game.original_sha256
$Patched = $Patch.game.patched_sha256
$Specs = @($Patch.managed_files)
$PackageFiles = (Get-ChildItem -LiteralPath $Package -Recurse -File).Count

$env:PATH = Join-Path $env:SystemRoot 'System32'
$env:PYTHONHOME = Join-Path $Base 'nonexistent-python-home'
$env:PYTHONPATH = Join-Path $Base 'nonexistent-python-modules'
$env:EW_NO_PAUSE = '1'
$Results = [ordered]@{started_at=(Get-Date).ToString('o'); zip=$Zip; zip_sha256=$null; path=$env:PATH;
    game_copy=$GameCopy; runs=@()}
function Hash($Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function ManagedHashesMatch($FileSpecs, $Field) {
    foreach ($Spec in $FileSpecs) {
        $Target = Join-Path $GameCopy ($Spec.path -replace '/', '\')
        if ((Hash $Target) -ne $Spec.$Field) { return $false }
    }
    return $true
}
function NoBackupsLeft($FileSpecs) {
    if (Test-Path -LiteralPath "$Bundle.original") { return $false }
    foreach ($Spec in $FileSpecs) {
        if (Test-Path -LiteralPath ((Join-Path $GameCopy ($Spec.path -replace '/', '\')) + '.original')) { return $false }
    }
    return $true
}
function ManagedBackupsMatch($FileSpecs) {
    foreach ($Spec in $FileSpecs) {
        $Target = Join-Path $GameCopy ($Spec.path -replace '/', '\')
        if ((Hash "$Target.original") -ne $Spec.original_sha256) { return $false }
    }
    return $true
}
function Save { $Results | ConvertTo-Json -Depth 15 | Set-Content (Join-Path $Stage 'windows-test.json') -Encoding UTF8 }
function Run($Name, $Command, $Arguments) {
    Write-Output "Test: $Name"
    $Info = New-Object System.Diagnostics.ProcessStartInfo
    if ($Arguments) { $Info.FileName = $Command; $Info.Arguments = $Arguments }
    else { $Info.FileName = $env:ComSpec; $Info.Arguments = "/d /c call `"$Command`"" }
    $Info.WorkingDirectory = $Base
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.StandardOutputEncoding = $Utf8
    $Info.StandardErrorEncoding = $Utf8
    $Process = [Diagnostics.Process]::Start($Info)
    $Watch = [Diagnostics.Stopwatch]::StartNew()
    $Out = $Process.StandardOutput.ReadToEndAsync()
    $Err = $Process.StandardError.ReadToEndAsync()
    $Process.WaitForExit()
    $Watch.Stop()
    [IO.File]::WriteAllText((Join-Path $Stage "$Name.stdout.txt"), $Out.Result, $Utf8)
    [IO.File]::WriteAllText((Join-Path $Stage "$Name.stderr.txt"), $Err.Result, $Utf8)
    $Results.runs += [ordered]@{name=$Name; command=$Command; exit_code=$Process.ExitCode;
        elapsed_seconds=[Math]::Round($Watch.Elapsed.TotalSeconds, 2)}
    Save
    $script:LastCode = $Process.ExitCode
    $script:LastOut = $Out.Result
    $script:LastErr = $Err.Result
    $Process.Dispose()
}
function Expect($Condition, $Message) { if (-not $Condition) { throw $Message } }

$Results.zip_sha256 = Hash $Zip
Expect (-not (Get-Command python,python3,py -ErrorAction SilentlyContinue)) 'Python available on isolated PATH'
Expect ((Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'Game copy is not original'
$Install = Join-Path $Package 'install.cmd'
$Restore = Join-Path $Package 'restore.cmd'

# 1. Frozen runtime only loads bundled modules.
Run 'self-test' (Join-Path $Package 'bin\EchoWeaverPatch.exe') 'self-test'
Expect ($LastCode -eq 0) 'Runtime self-test failed'
$Info = $LastOut | ConvertFrom-Json
Expect $Info.frozen 'Not a frozen executable'
foreach ($Module in $Info.modules.PSObject.Properties) {
    Expect $Module.Value.file.StartsWith((Join-Path $Package 'bin\_internal'), [StringComparison]::OrdinalIgnoreCase) 'Module outside package'
}
$Results.runtime = $Info
# 2-5. Install, repeat, restore, repeat.
Run 'install' $Install
Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Patched -and (ManagedHashesMatch $Specs 'patched_sha256')) 'Install failed'
Expect ((Hash "$Bundle.original") -eq $Original -and (ManagedBackupsMatch $Specs)) 'Backups not verified'
Run 'install-repeat' $Install
Expect ($LastCode -eq 0 -and $LastOut -match 'already_installed') 'Repeated install failed'
Run 'restore' $Restore
Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'Restore failed'
Expect (NoBackupsLeft $Specs) 'Restore left .original backups in the game folder'
Run 'restore-repeat' $Restore
Expect ($LastCode -eq 0 -and $LastOut -match 'already_original') 'Repeated restore failed'
# 6. Package folder is left as extracted.
Expect ((Get-ChildItem -LiteralPath $Package -Recurse -File).Count -eq $PackageFiles) 'Files left in KoreanPatch'
# 7-8. A package without a game beside it is rejected.
foreach ($Action in @('install', 'restore')) {
    Run "misplaced-$Action" (Join-Path $Misplaced "KoreanPatch\$Action.cmd")
    Expect ($LastCode -eq 1 -and $LastErr -match 'GAME_NOT_FOUND') 'Misplaced package guard failed'
}
# 9. A running game is not patched.
$Fake = Join-Path $env:TEMP 'ew-guard\Echo Weaver.exe'
New-Item -ItemType Directory -Force (Split-Path $Fake) | Out-Null
Copy-Item (Join-Path $env:SystemRoot 'System32\PING.EXE') $Fake -Force
$Running = Start-Process -FilePath $Fake -ArgumentList '-n 120 127.0.0.1' -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Seconds 1
    Run 'running-game' $Install
    Expect ($LastCode -eq 1 -and $LastErr -match 'GAME_RUNNING' -and (Hash $Bundle) -eq $Original) 'Running game guard failed'
} finally {
    Stop-Process -Id $Running.Id -Force -ErrorAction SilentlyContinue
}
# 10. Restore the previous release before replacing its package with the new one.
if ($PreviousVersion) {
    $PreviousZip = Join-Path $Project "dist\EchoWeaver-KO-$PreviousVersion.zip"
    Expect (Test-Path -LiteralPath $PreviousZip) 'Previous release ZIP missing'
    Remove-Item -LiteralPath $Package -Recurse -Force
    Expand-Archive -LiteralPath $PreviousZip -DestinationPath $GameCopy
    $PreviousPatch = Get-Content (Join-Path $Package 'patch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($PreviousPatch.game.original_sha256 -ne $Original) {
        # A game update must reject the old patch without touching the new game or its backups.
        Run 'old-version-install-rejected' (Join-Path $Package 'install.cmd')
        Expect ($LastCode -eq 1 -and $LastErr -match 'VERSION_MISMATCH') 'Old game version install was not rejected'
        Expect ((Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'Old patch changed new game files'
        Run 'old-version-restore-rejected' (Join-Path $Package 'restore.cmd')
        Expect ($LastCode -eq 1 -and $LastErr -match 'NO_BACKUP') 'Old game version restore was not rejected'
        Expect ((Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'Old restore changed new game files'
        Expect (NoBackupsLeft $Specs) 'Old patch created backups in the new game'
        Remove-Item -LiteralPath $Package -Recurse -Force
        Expand-Archive -LiteralPath $Zip -DestinationPath $GameCopy
        $OldSnapshot = $PreviousPatch.snapshot
        if (-not $OldSnapshot) { $OldSnapshot = '1.0.2.0' }
        $OldBundle = Join-Path $Project "backups\$OldSnapshot\data.unity3d"
        Expect ((Hash $OldBundle) -eq $PreviousPatch.game.original_sha256) 'Previous game fixture hash mismatch'
        Copy-Item -LiteralPath $OldBundle -Destination $Bundle -Force
        Run 'new-version-on-old-game-rejected' (Join-Path $Package 'install.cmd')
        Expect ($LastCode -eq 1 -and $LastErr -match 'VERSION_MISMATCH') 'New patch accepted old game version'
        Expect ((Hash $Bundle) -eq $PreviousPatch.game.original_sha256 -and (ManagedHashesMatch $Specs 'original_sha256')) 'New patch changed unsupported game files'
        Copy-Item -LiteralPath (Join-Path $Backup 'data.unity3d') -Destination $Bundle -Force
        Expect ((Hash $Bundle) -eq $Original -and (NoBackupsLeft $Specs)) 'New game fixture was not restored'
        # 11. A game update leaves the previous version's .original backups: install replaces them, restore removes them.
        Copy-Item -LiteralPath $OldBundle -Destination "$Bundle.original"
        Get-ChildItem -LiteralPath (Join-Path $Project "backups\$OldSnapshot\Echo Weaver_Data\Managed") -Filter '*.dll' |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Data "Managed\$($_.Name).original") }
        Run 'install-over-previous-backups' $Install
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Patched -and (ManagedHashesMatch $Specs 'patched_sha256')) 'Install over previous backups failed'
        Expect ((Hash "$Bundle.original") -eq $Original -and (ManagedBackupsMatch $Specs)) 'Previous backups were not replaced'
        Run 'restore-after-previous-backups' $Restore
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256') -and (NoBackupsLeft $Specs)) 'Restore after previous backups failed'
        $Results.previous_version_rejected = $true
        $Results.new_patch_rejected_previous_game = $true
        $Results.previous_backups_replaced = $true
    } else {
        Run 'upgrade-old-install' (Join-Path $Package 'install.cmd')
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $PreviousPatch.game.patched_sha256) 'Previous release install failed'
        Run 'upgrade-old-restore' (Join-Path $Package 'restore.cmd')
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'Previous release restore failed'
        Remove-Item -LiteralPath $Package -Recurse -Force
        Expand-Archive -LiteralPath $Zip -DestinationPath $GameCopy
        Run 'upgrade-new-install' (Join-Path $Package 'install.cmd')
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Patched -and (ManagedHashesMatch $Specs 'patched_sha256')) 'New release install after restore failed'
        Run 'upgrade-new-restore' (Join-Path $Package 'restore.cmd')
        Expect ($LastCode -eq 0 -and (Hash $Bundle) -eq $Original -and (ManagedHashesMatch $Specs 'original_sha256')) 'New release restore after upgrade failed'
        Expect ((Get-ChildItem -LiteralPath $Package -Recurse -File).Count -eq $PackageFiles) 'Upgrade left files in KoreanPatch'
        $Results.upgrade_passed = $true
    }
    $Results.previous_version = $PreviousVersion
    $Results.previous_zip_sha256 = Hash $PreviousZip
}
$Results.checks_passed = if ($Results.previous_backups_replaced) { 11 } elseif ($PreviousVersion) { 10 } else { 9 }
$Results.passed = $true
$Results.completed_at = (Get-Date).ToString('o')
Save
Remove-Item -LiteralPath $Base -Recurse -Force
Write-Output "All $($Results.checks_passed) Windows package tests passed"
