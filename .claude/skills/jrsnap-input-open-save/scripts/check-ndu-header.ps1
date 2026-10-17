param(
    [Parameter(Mandatory = $true)]
    [string] $Path,

    [Parameter(Mandatory = $true)]
    [ValidateSet('V52', 'V53')]
    [string] $Version
)

$ErrorActionPreference = 'Stop'
$item = Get-Item -LiteralPath $Path
$limit = if ($Version -eq 'V52') { 5 } else { 6 }
$files = if ($item.PSIsContainer) {
    @(Get-ChildItem -LiteralPath $item.FullName -Recurse -File -Filter '*.ndu')
} elseif ($item.Extension -ieq '.ndu') {
    @($item)
} else {
    throw 'Path must be an .ndu file or a directory.'
}

foreach ($file in $files) {
    $header = Get-Content -LiteralPath $file.FullName -Encoding Default -TotalCount 1
    $common = $null
    $canPass = $false
    if ($header -match '^Virsion=\d+\.\d+\.\d+\.S\.(\d+)$') {
        $common = [int] $Matches[1]
        $canPass = $common -le $limit
    }
    [pscustomobject]@{
        Path = $file.FullName
        Header = $header
        Target = $Version
        Common = $common
        CanPassHeaderCheck = $canPass
    }
}
