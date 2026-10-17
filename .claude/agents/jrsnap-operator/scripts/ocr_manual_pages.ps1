<# Japanese OCR for rendered manual pages, using local Windows OCR only.
   .\ocr_manual_pages.ps1 -ImageDir <folder> -Output <json>
   OCR is evidence for locating content, not authoritative transcription.
#>
param(
    [Parameter(Mandatory=$true)][string]$ImageDir,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$ocrAwaitMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1
} | Select-Object -First 1
function Wait-OcrAsync($Operation, [type]$ResultType) {
    $task = $ocrAwaitMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}
$language = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object {$_.LanguageTag -eq 'ja'} | Select-Object -First 1
if (-not $language) { throw 'Windows Japanese OCR language is not installed.' }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
$items = [System.Collections.Generic.List[object]]::new()
$files = @(Get-ChildItem -LiteralPath $ImageDir -Filter '*.png' | Sort-Object Name)
foreach ($file in $files) {
    $storage = Wait-OcrAsync ([Windows.Storage.StorageFile]::GetFileFromPathAsync($file.FullName)) ([Windows.Storage.StorageFile])
    $stream = Wait-OcrAsync ($storage.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Wait-OcrAsync ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-OcrAsync ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $recognized = Wait-OcrAsync ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $items.Add([pscustomobject]@{file=$file.Name; text=($recognized.Lines | ForEach-Object {$_.Text}) -join "`n"})
        } finally { $bitmap.Dispose() }
    } finally { $stream.Dispose() }
    if ($items.Count % 10 -eq 0) { Write-Output ('OCR {0}/{1}' -f $items.Count,$files.Count) }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), ($items | ConvertTo-Json -Depth 4), $utf8)
Write-Output ('Saved {0} pages to {1}' -f $items.Count,$Output)
