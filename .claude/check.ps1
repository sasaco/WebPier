[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$AllowNoGates,
    [string[]]$AllowProductPath = @()
)

# Scope comparison belongs to the calling skill; this gate runs the full suite.
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskLog = $null
try {
    $ErrorActionPreference = 'Stop'
    $taskProject = Join-Path $ProjectRoot '.'
    $taskTests = Join-Path $taskProject 'tests'
    $taskLogDir = Join-Path $ProjectRoot 'tmp\quality-gates'
    New-Item -ItemType Directory -Path $taskLogDir -Force | Out-Null
    $taskLog = Join-Path $taskLogDir ('pytest-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff') + '.log')
    $taskUv = (Get-Command uv -ErrorAction Stop).Source
    Push-Location -LiteralPath $ProjectRoot
    try {
        $ErrorActionPreference = 'Continue'
        & $taskUv run --project $taskProject --locked --group dev python -X utf8 -m pytest $taskTests -q -rs 2>&1 |
            Out-File -LiteralPath $taskLog -Encoding utf8
        $taskExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
        $ErrorActionPreference = 'Stop'
    }
    $taskStatus = if ($taskExit -eq 0) { 'pass' } else { 'fail' }
    $taskSummary = (Get-Content -LiteralPath $taskLog -Encoding utf8 | Select-Object -Last 1)
    [ordered]@{
        overall = $taskStatus
        tools = @{ pytest = @{ status = $taskStatus; exit_code = $taskExit; summary = $taskSummary } }
        log_file = $taskLog
    } | ConvertTo-Json -Depth 5
    if ($taskExit -eq 0) { exit 0 }
    exit 2
}
catch {
    @{ overall = 'no_gates'; error = $_.Exception.Message; log_file = $taskLog } | ConvertTo-Json
    exit 3
}
