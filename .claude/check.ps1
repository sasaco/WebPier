[CmdletBinding()]
param(
    [string]$ProjectRoot = '',
    [switch]$AllowNoGates,
    [string[]]$AllowProductPath = @()
)

# Scope comparison belongs to the calling skill; this gate runs the full suite under coverage
# (python -m webpier children included, pyproject.toml [tool.coverage]) and then checks the line+branch
# coverage of each package against its target (decision 15). Below target is a gate failure.
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
# Windows PowerShell 5.1 leaves $PSScriptRoot empty in a param default under -File, so the root is derived here.
if (-not $ProjectRoot) {
    $taskScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $ProjectRoot = Split-Path -Parent $taskScriptDir
}
$taskLog = $null
$taskTargets = [ordered]@{ core = 100; inputs = 100; calc = 100; export = 100; pipeline = 100; reporting = 95; gui = 85 }
$taskPreviousCoverageFile = $env:COVERAGE_FILE
try {
    $ErrorActionPreference = 'Stop'
    $taskProject = $ProjectRoot
    $taskTests = Join-Path $taskProject 'tests'
    $taskLogDir = Join-Path $ProjectRoot 'tmp\quality-gates'
    New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
    $taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fffffff'
    $taskLog = Join-Path $taskLogDir ('pytest-' + $taskStamp + '.log')
    $taskCoverageDir = Join-Path $taskLogDir ('coverage-' + $taskStamp)
    New-Item -ItemType Directory -Path $taskCoverageDir -Force | Out-Null
    # An absolute data file, so the child processes that run in a test's temporary directory write here too.
    $env:COVERAGE_FILE = Join-Path $taskCoverageDir '.coverage'
    $taskUv = (Get-Command uv -ErrorAction Stop).Source
    $taskPython = @('run', '--project', $taskProject, '--locked', '--group', 'dev', 'python', '-X', 'utf8')
    Push-Location -LiteralPath $ProjectRoot
    try {
        $ErrorActionPreference = 'Continue'
        & $taskUv @taskPython -m coverage run -m pytest $taskTests -q -rs 2>&1 |
            Out-File -LiteralPath $taskLog -Encoding utf8
        $taskExit = $LASTEXITCODE
        # [string]: a line of Get-Content carries PSPath etc., which ConvertTo-Json would write out.
        $taskSummary = [string](Get-Content -LiteralPath $taskLog -Encoding utf8 | Select-Object -Last 1)
        & $taskUv @taskPython -m coverage combine -q 2>&1 | Out-File -LiteralPath $taskLog -Encoding utf8 -Append
        if ($LASTEXITCODE -ne 0) { throw "coverage combine が失敗しました（終了コード $LASTEXITCODE）" }
        & $taskUv @taskPython -m coverage report 2>&1 | Out-File -LiteralPath $taskLog -Encoding utf8 -Append
        $taskPackages = [ordered]@{}
        foreach ($taskName in $taskTargets.Keys) {
            $taskText = (& $taskUv @taskPython -m coverage report --include "webpier/$taskName/*" --format=total --precision=2 2>&1 |
                Select-Object -Last 1)
            if ($LASTEXITCODE -ne 0) { throw "coverage report（webpier/$taskName）が失敗しました: $taskText" }
            $taskPercent = [double]::Parse("$taskText".Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
            $taskPackages[$taskName] = [ordered]@{
                percent = $taskPercent
                target = $taskTargets[$taskName]
                status = if ($taskPercent -ge $taskTargets[$taskName]) { 'pass' } else { 'fail' }
            }
        }
    }
    finally {
        Pop-Location
        $ErrorActionPreference = 'Stop'
    }
    $taskStatus = if ($taskExit -eq 0) { 'pass' } else { 'fail' }
    $taskCoverageStatus = if (@($taskPackages.Values | Where-Object { $_.status -ne 'pass' }).Count -eq 0) { 'pass' } else { 'fail' }
    $taskOverall = if ($taskStatus -eq 'pass' -and $taskCoverageStatus -eq 'pass') { 'pass' } else { 'fail' }
    [ordered]@{
        overall = $taskOverall
        tools = [ordered]@{
            pytest = [ordered]@{ status = $taskStatus; exit_code = $taskExit; summary = $taskSummary }
            coverage = [ordered]@{ status = $taskCoverageStatus; data_file = $env:COVERAGE_FILE; packages = $taskPackages }
        }
        log_file = $taskLog
    } | ConvertTo-Json -Depth 6
    if ($taskOverall -eq 'pass') { exit 0 }
    exit 2
}
catch {
    @{ overall = 'no_gates'; error = $_.Exception.Message; log_file = $taskLog } | ConvertTo-Json
    exit 3
}
finally {
    $env:COVERAGE_FILE = $taskPreviousCoverageFile
}
