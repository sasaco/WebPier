param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('read', 'enter')]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [int]$TargetPid
)

$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'ConsoleAutomation.cs')
if ($Action -eq 'read') {
    $value = [JrsnapConsoleAutomation]::ReadTail($TargetPid, 12)
    [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($value))
} else {
    [JrsnapConsoleAutomation]::SendEnter($TargetPid)
}
