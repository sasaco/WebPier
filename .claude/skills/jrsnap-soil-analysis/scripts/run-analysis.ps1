param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$SdrPath,

    [ValidateRange(10, 3600)]
    [int]$TimeoutSeconds = 180,

    [string]$InstallDir = 'C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') {
    throw 'powershell.exe -STA で実行してください。'
}

Add-Type -AssemblyName System.Windows.Forms, Microsoft.VisualBasic
if (-not ('SoilWindows' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'SoilWindows.cs')
}

$inputFile = (Resolve-Path -LiteralPath $InputPath -ErrorAction Stop).Path
$install = (Resolve-Path -LiteralPath $InstallDir -ErrorAction Stop).Path
$exe = Join-Path $install 'SOIL-JR.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "SOIL-JR.exe が見つかりません: $exe" }
$sdrFile = [IO.Path]::GetFullPath($SdrPath)
if ([IO.Path]::GetExtension($sdrFile) -ine '.sdr') { throw 'SdrPath には .sdr ファイルを指定してください。' }
if (-not (Test-Path -LiteralPath (Split-Path $sdrFile) -PathType Container)) {
    throw "出力フォルダーが見つかりません: $(Split-Path $sdrFile)"
}
$sdcFile = [IO.Path]::ChangeExtension($sdrFile, '.sdc')
$before = @{}
foreach ($path in @($sdrFile, $sdcFile)) {
    $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    $before[$path] = if ($item) { $item.LastWriteTimeUtc } else { $null }
}

$running = @(Get-Process -Name 'SOIL-JR' -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -ieq $exe })
if ($running.Count -gt 0) {
    throw "SOIL-JR.exe が既に起動しています。別件への操作を避けるため停止しました。PID: $($running.Id -join ', ')"
}

function Get-VisibleWindows {
    @([SoilWindows]::TopLevelWindows($process.Id) | Where-Object { $_.Visible })
}

function Wait-Window([string]$title, [string]$phase) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { throw "SOIL-JR が $phase 中に終了しました。" }
        $matches = @(Get-VisibleWindows | Where-Object { $_.Title -eq $title })
        if ($matches.Count -eq 1) { return $matches[0] }
        if ($matches.Count -gt 1) { throw "$phase のウィンドウが複数あります: $title" }
        $unexpected = @(Get-VisibleWindows | Where-Object {
            $_.ClassName -eq '#32770' -and $_.Title -ne $title
        })
        if ($unexpected.Count -gt 0) {
            $messages = @([SoilWindows]::ChildWindows($unexpected[0].Handle) |
                Where-Object { $_.Visible -and $_.ClassName -eq 'Static' } |
                ForEach-Object { $_.Title })
            throw "$phase 中のダイアログ: $($unexpected[0].Title) $($messages -join ' ')"
        }
        Start-Sleep -Milliseconds 100
    }
    throw "$phase が $TimeoutSeconds 秒で完了しませんでした。"
}

function Paste-PathIntoDialog($dialog, [string]$path) {
    Start-Sleep -Seconds 2
    [System.Windows.Forms.Clipboard]::SetText($path)
    [SoilWindows]::Activate($dialog.Handle)
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait('%n')
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}

function Click-NamedButton($dialog, [string]$name) {
    $buttons = @([SoilWindows]::ChildWindows($dialog.Handle) |
        Where-Object { $_.Visible -and $_.ClassName -eq 'Button' -and $_.Title -eq $name })
    if ($buttons.Count -ne 1) { throw "ボタンを特定できません: $($dialog.Title) / $name" }
    [SoilWindows]::ClickButton($buttons[0].Handle)
}

$process = $null
$originalClipboard = [System.Windows.Forms.Clipboard]::GetDataObject()
try {
    $process = Start-Process -FilePath $exe `
        -ArgumentList 'LicenseOptNo111111199999999999999Ver.5.3-L00' `
        -WorkingDirectory $install -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($process.MainWindowHandle -eq [IntPtr]::Zero -and [DateTime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { throw 'SOIL-JR の起動に失敗しました。' }
        Start-Sleep -Milliseconds 100
        $process.Refresh()
    }
    if ($process.MainWindowHandle -eq [IntPtr]::Zero) { throw 'SOIL-JR のメイン画面を検出できません。' }
    Start-Sleep -Seconds 1
    Write-Host "SOIL-JR 起動: PID $($process.Id)"

    [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id)
    [System.Windows.Forms.SendKeys]::SendWait('%f')
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait('o')
    Write-Host '入力ファイルの選択画面を待機中'
    $open = Wait-Window 'データファイルを開く' '入力ファイル選択'
    Paste-PathIntoDialog $open $inputFile
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $process.Refresh()
        if ($process.MainWindowTitle.IndexOf($inputFile, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            -not @(Get-VisibleWindows | Where-Object { $_.Title -eq 'データファイルを開く' }).Count) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($process.MainWindowTitle.IndexOf($inputFile, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw '入力 SDT の読込を確認できません。'
    }

    [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id)
    [SoilWindows]::ClickCalculate($process.MainWindowHandle)
    $prompt = Wait-Window '連携データ作成' '計算'
    $message = @([SoilWindows]::ChildWindows($prompt.Handle) |
        Where-Object { $_.Visible -and $_.ClassName -eq 'Static' } |
        ForEach-Object { $_.Title }) -join ' '
    if ($message -notmatch '計算が終了しました') { throw "計算完了を確認できません: $message" }
    Click-NamedButton $prompt 'はい(&Y)'

    $save = Wait-Window '基礎照査連携用データの保存' '連携ファイル保存'
    Paste-PathIntoDialog $save $sdrFile
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $confirm = @(Get-VisibleWindows | Where-Object { $_.Title -eq '名前を付けて保存の確認' })
        if ($confirm.Count -eq 1) { Click-NamedButton $confirm[0] 'はい(&Y)' }
        $items = @(@($sdrFile, $sdcFile) | ForEach-Object { Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue })
        if ($items.Count -eq 2 -and $items[0] -and $items[1] -and
            $items[0].Length -gt 0 -and $items[1].Length -gt 0 -and
            (($null -eq $before[$sdrFile]) -or ($items[0].LastWriteTimeUtc -gt $before[$sdrFile])) -and
            (($null -eq $before[$sdcFile]) -or ($items[1].LastWriteTimeUtc -gt $before[$sdcFile])) -and
            -not @(Get-VisibleWindows | Where-Object { $_.Title -eq '基礎照査連携用データの保存' }).Count) { break }
        Start-Sleep -Milliseconds 100
    }

    $sdr = Get-Item -LiteralPath $sdrFile -ErrorAction Stop
    $sdc = Get-Item -LiteralPath $sdcFile -ErrorAction Stop
    if ($sdr.Length -le 0 -or $sdc.Length -le 0 -or
        ($null -ne $before[$sdrFile] -and $sdr.LastWriteTimeUtc -le $before[$sdrFile]) -or
        ($null -ne $before[$sdcFile] -and $sdc.LastWriteTimeUtc -le $before[$sdcFile])) {
        throw 'SDR・SDC の両方が今回更新されたことを確認できません。'
    }
    $encoding = [Text.Encoding]::GetEncoding(932)
    $title = [IO.File]::ReadAllLines($inputFile, $encoding)[2]
    $sdrLines = [IO.File]::ReadAllLines($sdrFile, $encoding)
    $sdcLines = [IO.File]::ReadAllLines($sdcFile, $encoding)
    if ($sdrLines[0] -notmatch '^Ver\.' -or $sdrLines[1] -cne $title -or
        $sdcLines[0] -cne '【バージョン情報】' -or $sdcLines[4] -cne $title) {
        throw '出力ファイルの版情報またはタイトルが入力 SDT と一致しません。'
    }
    [pscustomobject]@{
        Input = $inputFile
        Sdr = $sdr.FullName
        SdrBytes = $sdr.Length
        Sdc = $sdc.FullName
        SdcBytes = $sdc.Length
        Title = $title
    }
} finally {
    if ($originalClipboard) {
        try { [System.Windows.Forms.Clipboard]::SetDataObject($originalClipboard, $true) } catch { }
    }
    if ($process -and -not $process.HasExited) {
        $process.CloseMainWindow() | Out-Null
        Start-Sleep -Milliseconds 300
        $confirm = @(Get-VisibleWindows | Where-Object { $_.Title -eq '保存確認' })
        if ($confirm.Count -eq 1) {
            try { Click-NamedButton $confirm[0] 'いいえ(&N)' } catch { }
        }
        if (-not $process.WaitForExit(3000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
