param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [ValidateSet('V52', 'V53')]
    [string] $Version,

    [switch] $ConvertS6,
    [switch] $Execute,
    [ValidateRange(5, 300)]
    [int] $TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
$item = Get-Item -LiteralPath $Path
$files = if ($item.PSIsContainer) {
    @(Get-ChildItem -LiteralPath $item.FullName -Recurse -File -Filter '*.ndu')
} elseif ($item.Extension -ieq '.ndu') {
    @($item)
} else {
    throw 'Path must be an .ndu file or a directory.'
}
if ($files.Count -eq 0) { throw 'No .ndu files found.' }

$executables = @{
    V52 = 'C:\RTRI_Program\JRSNAP(Ver5.2-L03)\JRSNAP_Input.exe'
    V53 = 'C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)\JRSNAP_Input.exe'
}
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$source = Join-Path $PSScriptRoot 'roundtrip.cs'
foreach ($required in @($executables[$Version], $compiler, $source)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

$stage = Join-Path $env:TEMP ('jrsnap-ndu-save-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
$runners = @{}
$config = '<?xml version="1.0" encoding="utf-8"?><configuration><runtime><loadFromRemoteSources enabled="true"/></runtime><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.7.2"/></startup></configuration>'

function Get-Runner([string] $release) {
    if ($runners.ContainsKey($release)) { return $runners[$release] }
    $runner = Join-Path $stage ("RoundTrip$release.exe")
    & $compiler /nologo /platform:x86 /reference:System.Windows.Forms.dll "/define:$release" "/out:$runner" $source
    if ($LASTEXITCODE -ne 0) { throw "Could not compile $release reader/writer." }
    [IO.File]::WriteAllText("$runner.config", $config, [Text.Encoding]::UTF8)
    $runners[$release] = $runner
    return $runner
}

function Invoke-RoundTrip([string] $release, [string] $nduInput, [string] $output) {
    if (Test-Path -LiteralPath $output) { throw "Staged output already exists: $output" }
    $runner = Get-Runner $release
    $arguments = @('"' + $executables[$release] + '"', '"' + $nduInput + '"', '"' + $output + '"')
    $process = Start-Process -FilePath $runner -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$output.stdout" -RedirectStandardError "$output.stderr"
    try {
        $process | Wait-Process -Timeout $TimeoutSeconds -ErrorAction Stop
    } catch {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        throw "JRSNAP $release read/write timed out for $nduInput. Logs: $output.stderr"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $output)) {
        $detail = if (Test-Path -LiteralPath "$output.stderr") { Get-Content -LiteralPath "$output.stderr" -Raw } else { '' }
        throw "JRSNAP $release read/write failed for $nduInput (exit $($process.ExitCode)): $detail"
    }
}

function Read-Lines([string] $file) {
    return ,([IO.File]::ReadAllLines($file, [Text.Encoding]::GetEncoding(932)))
}

$prepared = New-Object System.Collections.Generic.List[object]
$number = 0
foreach ($file in $files) {
    $number++
    $original = Join-Path $stage ("case$number.original.ndu")
    $nduInput = Join-Path $stage ("case$number.input.ndu")
    $output = Join-Path $stage ("case$number.saved.ndu")
    Copy-Item -LiteralPath $file.FullName -Destination $original
    Copy-Item -LiteralPath $file.FullName -Destination $nduInput
    $beforeHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $beforeLines = Read-Lines $original
    $beforeHeader = $beforeLines[0]
    if ($beforeHeader -notmatch '^Virsion=\d+\.\d+\.\d+\.S\.(\d+)$') {
        throw "Unknown NDU header: $($file.FullName): $beforeHeader"
    }
    $common = [int] $Matches[1]
    $converted = $false
    if ($Version -eq 'V52' -and $common -eq 6) {
        if (-not $ConvertS6) { throw "S.6 requires -ConvertS6: $($file.FullName)" }
        $bytes = [IO.File]::ReadAllBytes($nduInput)
        $headerPosition = $beforeHeader.IndexOf('S.6', [StringComparison]::Ordinal)
        if ($headerPosition -lt 0) { throw 'Could not locate S.6 in NDU header.' }
        $bytes[$headerPosition + 2] = [byte][char]'5'
        [IO.File]::WriteAllBytes($nduInput, $bytes)
        $converted = $true
    } elseif (($Version -eq 'V52' -and $common -gt 5) -or ($Version -eq 'V53' -and $common -gt 6)) {
        throw "NDU format is newer than ${Version}: $($file.FullName)"
    }

    Invoke-RoundTrip $Version $nduInput $output
    $afterLines = Read-Lines $output
    $expectedHeader = if ($Version -eq 'V52') { '^Virsion=5\.2\.3\.S\.[1-5]$' } else { '^Virsion=5\.3\.1\.S\.6$' }
    if ($afterLines[0] -notmatch $expectedHeader) { throw "Unexpected saved header: $($afterLines[0])" }

    if ($converted) {
        $baseline = Join-Path $stage ("case$number.v53-baseline.ndu")
        Invoke-RoundTrip V53 $original $baseline
        $baselineLines = Read-Lines $baseline
        if ($baselineLines.Length -ne $afterLines.Length) { throw "V52/V53 body line count differs: $($file.FullName)" }
        for ($i = 1; $i -lt $afterLines.Length; $i++) {
            if ($afterLines[$i] -cne $baselineLines[$i]) {
                throw "V52/V53 body differs at line $($i + 1): $($file.FullName)"
            }
        }
    }

    $second = Join-Path $stage ("case$number.second.ndu")
    Invoke-RoundTrip $Version $output $second
    $afterHash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $second -Algorithm SHA256).Hash -ne $afterHash) {
        throw "Second save differs: $($file.FullName)"
    }

    $changed = [Math]::Abs($beforeLines.Length - $afterLines.Length)
    for ($i = 1; $i -lt [Math]::Min($beforeLines.Length, $afterLines.Length); $i++) {
        if ($beforeLines[$i] -cne $afterLines[$i]) { $changed++ }
    }
    $prepared.Add([pscustomobject]@{
        Path = $file.FullName
        BeforeHash = $beforeHash
        AfterHash = $afterHash
        BeforeHeader = $beforeHeader
        AfterHeader = $afterLines[0]
        ConvertedS6 = $converted
        BodyChangedLines = $changed
        StageOriginal = $original
        StageOutput = $output
    })
}

if ($Execute) {
    $committed = New-Object System.Collections.Generic.List[object]
    try {
        foreach ($entry in $prepared) {
            if ((Get-FileHash -LiteralPath $entry.Path -Algorithm SHA256).Hash -ne $entry.BeforeHash) {
                throw "Target changed during staging: $($entry.Path)"
            }
            $committed.Add($entry)
            Copy-Item -LiteralPath $entry.StageOutput -Destination $entry.Path -Force
            if ((Get-FileHash -LiteralPath $entry.Path -Algorithm SHA256).Hash -ne $entry.AfterHash) {
                throw "Saved bytes differ after copy: $($entry.Path)"
            }
        }
    } catch {
        foreach ($entry in $committed) {
            Copy-Item -LiteralPath $entry.StageOriginal -Destination $entry.Path -Force
        }
        throw
    }
}

$prepared | ForEach-Object {
    [pscustomobject]@{
        Path = $_.Path
        BeforeHash = $_.BeforeHash
        AfterHash = $_.AfterHash
        BeforeHeader = $_.BeforeHeader
        AfterHeader = $_.AfterHeader
        ConvertedS6 = $_.ConvertedS6
        BodyChangedLines = $_.BodyChangedLines
        Written = [bool] $Execute
        Stage = $stage
    }
}
