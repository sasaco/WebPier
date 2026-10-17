param(
    [Parameter(Mandatory = $true)]
    [string[]]$NdtPath,

    [string]$InstallDir = 'C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)',

    [switch]$Execute,

    [ValidateRange(1, 2147483)]
    [int]$TimeoutSeconds = 1800
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installDir = (Resolve-Path -LiteralPath $InstallDir -ErrorAction Stop).Path
$version53Dir = 'C:\RTRI_Program\JRSNAP(Ver5.3-L01体験版2)'
$version52Dir = 'C:\RTRI_Program\JRSNAP(Ver5.2-L03)'
if ($installDir -ieq $version53Dir) {
    $licenseArgument = 'LicenseOptNo111111199999999999999Ver.5.3-L00'
} elseif ($installDir -ieq $version52Dir) {
    $licenseArgument = 'LicenseOptNo111111199999999999999Ver.5.2-L03'
} else {
    throw "未対応のインストール先です: $installDir"
}
$analysisExe = Join-Path $installDir 'S_ANALYSIS.exe'
$workFile = Join-Path $installDir 'work.wk3'
$sequenceFile = Join-Path $installDir 'renzoku.flg'
$directoryFile = Join-Path $installDir 'nrwork.dir'
$shiftJis = [System.Text.Encoding]::GetEncoding(932)
$dialogHelper = Join-Path $PSScriptRoot 'DialogAutomation.cs'
$consoleTool = Join-Path $PSScriptRoot 'console-control.ps1'

if (-not (Test-Path -LiteralPath $analysisExe -PathType Leaf)) {
    throw "解析エンジンが見つかりません: $analysisExe"
}

$inputFiles = @()
$seenPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($path in $NdtPath) {
    $inputFile = (Resolve-Path -LiteralPath $path -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $inputFile -PathType Leaf)) {
        throw "解析データではありません: $inputFile"
    }
    if ([System.IO.Path]::GetExtension($inputFile) -ine '.ndt') {
        throw 'このスクリプトは既存の .NDT ファイルだけを対象にします。'
    }
    if ([System.IO.Path]::GetFileNameWithoutExtension($inputFile).EndsWith(' ')) {
        throw 'ファイル名の末尾が空白の .NDT は解析できません。'
    }
    if ($shiftJis.GetByteCount($inputFile) -gt 250) {
        throw '解析データのフルパスが Shift-JIS で 250 バイトを超えます。'
    }
    if (-not $seenPaths.Add($inputFile)) {
        throw "同じ .NDT を重複指定できません: $inputFile"
    }
    $inputFiles += $inputFile
}
if ($inputFiles.Count -eq 0) { throw '.NDT を1件以上指定してください。' }
if ($inputFiles.Count -gt 1) {
    $directory = [System.IO.Path]::GetDirectoryName($inputFiles[0])
    foreach ($inputFile in $inputFiles) {
        if ([System.IO.Path]::GetDirectoryName($inputFile) -ine $directory) {
            throw '複数解析では同じフォルダーの .NDT を指定してください。'
        }
    }
}

$controlLines = @()
for ($index = 0; $index -lt $inputFiles.Count; $index++) {
    $controlLines += [string]($index + 1)
    $controlLines += $inputFiles[$index]
    $controlLines += '応答変位法支援プログラム連携ファイル='
    $controlLines += '抗土圧構造物設計プログラム連携ファイル='
    $controlLines += '外部非線形データ連携ファイル='
}

if (-not $Execute) {
    $inputFiles | ForEach-Object { Write-Output "解析データ: $_" }
    Write-Output "解析エンジン: $analysisExe"
    Write-Output "ライセンス引数: $licenseArgument"
    Write-Output 'モード: 事前確認のみ（ファイル作成・解析実行なし）'
    $argumentText = ($inputFiles | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ', '
    $quotedInstallDir = $installDir.Replace("'", "''")
    Write-Output "実行する場合: & '$PSCommandPath' -NdtPath $argumentText -InstallDir '$quotedInstallDir' -Execute"
    return
}

$active = @(Get-Process -Name 'JRSNAP_Input', 'S_ANALYSIS', 'nrail', 'linear', 'ConvS1', 'ConvS2' -ErrorAction SilentlyContinue |
    Where-Object {
        -not $_.Path -or [System.IO.Path]::GetDirectoryName($_.Path) -ieq $installDir
    })
if ($active.Count -gt 0) {
    $names = ($active | ForEach-Object { "$($_.ProcessName)($($_.Id))" }) -join ', '
    throw "インストール先の作業ファイルを使用中の可能性があります: $names"
}

$existingWorkFiles = @(Get-ChildItem -LiteralPath $installDir -Filter '*.wk3' -File)
if ($existingWorkFiles.Count -gt 0) {
    throw "既存の .wk3 制御ファイルがあります。解析状態を確認してください: $(($existingWorkFiles.Name) -join ', ')"
}

$originalSequence = if (Test-Path -LiteralPath $sequenceFile -PathType Leaf) {
    [System.IO.File]::ReadAllBytes($sequenceFile)
} else { $null }
$originalDirectory = if (Test-Path -LiteralPath $directoryFile -PathType Leaf) {
    [System.IO.File]::ReadAllBytes($directoryFile)
} else { $null }

if (-not ('JrsnapDialogAutomation' -as [type])) { Add-Type -Path $dialogHelper }

$process = $null
$workFileOwned = $false
try {
    [System.IO.File]::WriteAllText($sequenceFile, "$($inputFiles.Count)`r`n", $shiftJis)
    $workFileOwned = $true
    [System.IO.File]::WriteAllText($workFile, (($controlLines -join "`r`n") + "`r`n"), $shiftJis)

    $startedAtUtc = [DateTime]::UtcNow
    $process = Start-Process -FilePath $analysisExe -ArgumentList $licenseArgument -WorkingDirectory $installDir -PassThru
    Write-Output "S_ANALYSIS.exe を起動しました (PID $($process.Id))。"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $confirmedConsoles = New-Object 'System.Collections.Generic.HashSet[int]'
    $batchErrorNotice = $false
    while (-not $process.HasExited) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "${TimeoutSeconds}秒以内に終了しませんでした。エンジンは実行中のため、制御ファイルは残します。"
        }

        $childConsoles = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" |
            Where-Object { $_.Name -ieq 'nrail.exe' })
        foreach ($child in $childConsoles) {
            $childId = [int]$child.ProcessId
            if ($confirmedConsoles.Contains($childId)) { continue }
            try {
                $encoded = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $consoleTool -Action read -TargetPid $childId
                if ($LASTEXITCODE -ne 0) { throw "コンソール読取に失敗しました: Nrail.exe PID $childId" }
                $tail = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String(($encoded -join '').Trim()))
            } catch {
                if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw }
                continue
            }
            if ($tail.Contains('エンターキーを押して画面を閉じて下さい')) {
                & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $consoleTool -Action enter -TargetPid $childId
                if ($LASTEXITCODE -ne 0) { throw "Enter 送信に失敗しました: Nrail.exe PID $childId" }
                [void]$confirmedConsoles.Add($childId)
                Write-Output "Nrail.exe (PID $childId) の終了確認に Enter を送りました。"
            }
        }

        $dialogs = @([JrsnapDialogAutomation]::TopLevelWindows($process.Id) |
            Where-Object { $_.Visible })
        foreach ($dialog in $dialogs) {
            $children = @([JrsnapDialogAutomation]::ChildWindows($dialog.Handle))
            if ($dialog.Title -eq '耐力と変形性能の自動算定') {
                $button = @($children | Where-Object { $_.Visible -and $_.Title -eq '実行(&R)' })
                if ($button.Count -ne 1) { throw '自動算定ダイアログの実行ボタンを特定できません。' }
                [JrsnapDialogAutomation]::ClickButton($button[0].Handle)
                Write-Output '耐力と変形性能の自動算定を実行しました。'
            } elseif ($dialog.Title -eq '解析機能' -and
                @($children | Where-Object Title -eq '基礎照査機能を起動しますか？').Count -eq 1) {
                $button = @($children | Where-Object { $_.Visible -and $_.Title -eq 'いいえ(&N)' })
                if ($button.Count -ne 1) { throw '基礎照査確認ダイアログの「いいえ」を特定できません。' }
                [JrsnapDialogAutomation]::ClickButton($button[0].Handle)
                Write-Output '追加の基礎照査機能の起動は省略しました。'
            } elseif ($inputFiles.Count -gt 1 -and $dialog.Title -eq '解析実行' -and
                $dialog.ClassName -eq '#32770') {
                $message = @($children | Where-Object {
                    $_.ClassName -eq 'Static' -and $_.Title.StartsWith('解析が全て終了しました。')
                })
                if ($message.Count -ne 1) { continue }
                $button = @($children | Where-Object { $_.Visible -and $_.Title -eq 'OK' })
                if ($button.Count -ne 1) { throw '複数解析の完了通知の OK を特定できません。' }
                $batchErrorNotice = $message[0].Title.Contains('解析途中でエラー')
                [JrsnapDialogAutomation]::ClickDialogButton($dialog.Handle, $button[0].Handle)
                Write-Output '複数解析の完了通知を閉じました。'
            }
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Output "S_ANALYSIS.exe の終了コード: $($process.ExitCode)"
    if ($process.ExitCode -ne 0) {
        throw "S_ANALYSIS.exe が終了コード $($process.ExitCode) で終了しました。"
    }
    if ($batchErrorNotice) {
        throw '複数解析の完了通知に「解析途中でエラーが発生したデータがあります」と表示されました。解析実行Err.logを確認してください。'
    }
    foreach ($inputFile in $inputFiles) {
        $resultStem = [System.IO.Path]::Combine(
            [System.IO.Path]::GetDirectoryName($inputFile),
            [System.IO.Path]::GetFileNameWithoutExtension($inputFile))
        $resultOut = Get-Item -LiteralPath ($resultStem + '.OUT') -ErrorAction Stop
        $resultLog = Get-Item -LiteralPath ($resultStem + '.LOG') -ErrorAction Stop
        if ($resultOut.Length -eq 0 -or $resultLog.Length -eq 0 -or
            $resultOut.LastWriteTimeUtc -lt $startedAtUtc.AddSeconds(-2) -or
            $resultLog.LastWriteTimeUtc -lt $startedAtUtc.AddSeconds(-2)) {
            throw "解析エンジンは終了しましたが、.OUT または .LOG の更新を確認できません: $inputFile"
        }
        $logText = [System.IO.File]::ReadAllText($resultLog.FullName, $shiftJis)
        if (-not $logText.Contains('LOGFILE END')) {
            throw ".LOG に終了マーカーがありません: $($resultLog.FullName)"
        }
        Write-Output "結果更新を確認しました: $($resultOut.FullName), $($resultLog.FullName)"
        $highAxialWarnings = [regex]::Matches($logText, '高軸方向圧縮力を受ける要素').Count
        if ($highAxialWarnings -gt 0) {
            Write-Warning "$($resultLog.Name) に高軸方向圧縮力を受ける要素の記録が $highAxialWarnings 件あります。"
        }
    }
}
finally {
    if ($null -eq $process -or $process.HasExited) {
        if ($workFileOwned -and (Test-Path -LiteralPath $workFile -PathType Leaf)) {
            Remove-Item -LiteralPath $workFile
        }
        if ($null -ne $originalSequence) {
            [System.IO.File]::WriteAllBytes($sequenceFile, $originalSequence)
        } elseif (Test-Path -LiteralPath $sequenceFile -PathType Leaf) {
            Remove-Item -LiteralPath $sequenceFile
        }
        if ($null -ne $originalDirectory) {
            [System.IO.File]::WriteAllBytes($directoryFile, $originalDirectory)
        } elseif (Test-Path -LiteralPath $directoryFile -PathType Leaf) {
            Remove-Item -LiteralPath $directoryFile
        }
    }
}
