$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path $PSScriptRoot -Parent
$toolsRoot = Join-Path $studyRoot 'data/tools'
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $toolsRoot 'ollama'))
$archivePath = Join-Path $toolsRoot 'ollama-windows-amd64.zip'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
if (!(Test-Path -LiteralPath $archivePath)) {
    Write-Host 'Downloading official Ollama Windows archive (~1.6 GB).'
    & curl.exe --fail --location --silent --show-error --retry 0 --output $archivePath 'https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Official download failed.' }
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ollamaArchive = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($ollamaEntry in $ollamaArchive.Entries) {
        if ($ollamaEntry.FullName -ne 'ollama.exe' -and $ollamaEntry.FullName -notmatch '^lib/ollama/[^/]+$') { continue }
        $destination = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $ollamaEntry.FullName))
        if (!$destination.StartsWith($runtimeRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid archive path.' }
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($ollamaEntry,$destination,$true)
    }
} finally { $ollamaArchive.Dispose() }
if ((Get-AuthenticodeSignature (Join-Path $runtimeRoot 'ollama.exe')).Status -ne 'Valid') { throw 'Ollama executable signature could not be verified.' }
& (Join-Path $PSScriptRoot 'start-ollama.ps1')
Write-Host 'Downloading qwen3:1.7b (~1.4 GB), selected for this 8 GB RAM PC.'
& (Join-Path $runtimeRoot 'ollama.exe') pull qwen3:1.7b
if ($LASTEXITCODE -ne 0) { throw 'Local model download failed.' }
