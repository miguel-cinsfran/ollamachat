# Bellbird test runner.
#
# Runs each test directory in its OWN pytest process. This is REQUIRED:
# running core + ui + smoke in a single process accumulates wxPython global
# state and wedges the suite around ~70% (the historical "CRASH-01" hang —
# the app windows the ui tests build never fully tear down within one process).
# Every directory passes cleanly on its own, so per-directory isolation is the
# fix, not a workaround.
#
# Output streams LIVE to the console (via Tee-Object) so you can see progress
# and exactly where a run stops — the old run_tests.bat buffered everything to
# a temp file and only printed it at the end, so a hang looked like a freeze.
# The full transcript is copied to the clipboard at the end.

$ErrorActionPreference = "Continue"
Set-Location -Path (Split-Path $PSScriptRoot -Parent)

$log = Join-Path $env:TEMP ("bellbird_tests_{0}.txt" -f $PID)
if (Test-Path $log) { Remove-Item $log -Force }

# pytest dirs in their own process. addopts is cleared (-o addopts=) because the
# project default "-xvs" stops at the first failure and disables capture; here we
# want the whole group to run with concise output.
$groups = @(
    @{ Name = "core";  Path = "tests/core"  },
    @{ Name = "ui";    Path = "tests/ui"    },
    @{ Name = "smoke"; Path = "tests/smoke" }
)

$results = @()
foreach ($g in $groups) {
    $header = "`n============================================================`n  PYTEST: $($g.Path)`n============================================================"
    $header | Tee-Object -FilePath $log -Append
    & uv run pytest $g.Path -o addopts= -q -p no:cacheprovider 2>&1 | Tee-Object -FilePath $log -Append
    $ok = ($LASTEXITCODE -eq 0)
    $results += [pscustomobject]@{ Name = $g.Name; Ok = $ok; Code = $LASTEXITCODE }
}

$summary = "`n============================================================`n  RESUMEN`n============================================================"
foreach ($r in $results) {
    $tag = if ($r.Ok) { "OK  " } else { "FALLO ($($r.Code))" }
    $summary += "`n  {0,-6} {1}" -f $r.Name, $tag
}
$failed = @($results | Where-Object { -not $_.Ok })
$summary += if ($failed.Count -eq 0) { "`n`n  TODO VERDE" } else { "`n`n  {0} grupo(s) con fallos" -f $failed.Count }
$summary | Tee-Object -FilePath $log -Append

# Copy the full transcript to the clipboard for easy pasting.
try { Get-Content $log -Raw -Encoding UTF8 | Set-Clipboard; Write-Host "`n(Transcripcion copiada al portapapeles)" } catch {}
Remove-Item $log -Force -ErrorAction SilentlyContinue

if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
