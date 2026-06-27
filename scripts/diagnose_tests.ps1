# Diagnose hanging / failing tests by running each test file in its OWN
# pytest process with a hard wall-clock timeout. A file that exceeds the
# timeout is the hang culprit; one that returns non-zero is a failure.
#
# Usage:  pwsh -NoProfile -File scripts/diagnose_tests.ps1 [timeoutSeconds]
# Output: a summary table (RESULT  secs  file) printed at the end.

param([int]$TimeoutSec = 90)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path $PSScriptRoot -Parent)

$logDir = Join-Path $env:TEMP "bellbird_diag"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$files = Get-ChildItem -Recurse -Path "tests" -Filter "test_*.py" |
    Sort-Object FullName
Write-Host ("Found {0} test files. Per-file timeout: {1}s`n" -f $files.Count, $TimeoutSec)

$results = @()
foreach ($f in $files) {
    $rel = Resolve-Path -Relative $f.FullName
    $safe = ($rel -replace '[\\/:]', '_')
    $out  = Join-Path $logDir "$safe.log"
    $sw   = [System.Diagnostics.Stopwatch]::StartNew()

    # Own process so cross-file pollution can't mask the culprit.
    $p = Start-Process -FilePath "uv" `
        -ArgumentList @("run","pytest",$rel,"-o","addopts=","-q","-p","no:cacheprovider") `
        -PassThru -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError "$out.err"

    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        try { $p.Kill($true) } catch {}
        $sw.Stop()
        $status = "TIMEOUT"
    } else {
        $sw.Stop()
        $status = if ($p.ExitCode -eq 0) { "PASS" } else { "FAIL($($p.ExitCode))" }
    }
    $secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    $line = "{0,-10} {1,7}s  {2}" -f $status, $secs, $rel
    Write-Host $line
    $results += [pscustomobject]@{ Status = $status; Secs = $secs; File = $rel; Log = $out }
}

Write-Host "`n===================== SUMMARY (problems first) ====================="
$results |
    Sort-Object @{ Expression = { $_.Status -eq "PASS" } }, @{ Expression = { -$_.Secs } } |
    ForEach-Object { Write-Host ("{0,-10} {1,7}s  {2}" -f $_.Status, $_.Secs, $_.File) }

$bad = $results | Where-Object { $_.Status -ne "PASS" }
Write-Host ("`n{0} problem file(s). Logs in: {1}" -f $bad.Count, $logDir)
