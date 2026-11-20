$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path $PSScriptRoot -Parent
$ollamaExe = Join-Path $studyRoot 'data/tools/ollama/ollama.exe'
if (!(Test-Path -LiteralPath $ollamaExe)) { throw 'Run scripts/setup-ollama.ps1 first.' }
function Test-LocalOllama {
    try {
        $ollamaVersion = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 1
        return ![string]::IsNullOrWhiteSpace([string]$ollamaVersion.version)
    } catch { return $false }
}
function Get-OllamaListeners {
    @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
}
$existingListeners = @(Get-OllamaListeners)
if (Test-LocalOllama) {
    if ($existingListeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }) {
        throw 'Existing Ollama listener is not bound exclusively to loopback. Configure it first; no process was stopped.'
    }
    Write-Host 'Existing local Ollama detected at http://127.0.0.1:11434; no process restarted. Its startup settings were not changed.'
    return
}
if ($existingListeners.Count -gt 0) {
    throw 'Port 11434 is occupied by an unverified process. No process was stopped. See the existing listener before retrying.'
}
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $studyRoot 'data/models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
$ollamaStartId = [Guid]::NewGuid().ToString('N').Substring(0,8)
for ($ollamaStartAttempt = 1; $ollamaStartAttempt -le 3; $ollamaStartAttempt++) {
    # Recheck before every new process. Never stop or replace an unknown listener.
    if (@(Get-OllamaListeners).Count -gt 0) {
        throw 'A listener appeared on port 11434 before startup. No additional process was started or stopped.'
    }
    $ollamaLogBase = Join-Path $studyRoot "data/tools/ollama-start-$ollamaStartId-$ollamaStartAttempt"
    $ollamaErrorLog = "$ollamaLogBase.err.log"
    $ollamaProcess = Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $studyRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$ollamaLogBase.out.log" -RedirectStandardError $ollamaErrorLog
    for ($ollamaPoll = 0; $ollamaPoll -lt 20; $ollamaPoll++) {
        Start-Sleep -Milliseconds 500
        $ollamaProcess.Refresh()
        if ($ollamaProcess.HasExited) { break }
        if (Test-LocalOllama) {
            $readyListeners = @(Get-OllamaListeners)
            if ($readyListeners.Count -eq 0 -or ($readyListeners | Where-Object { $_.OwningProcess -ne $ollamaProcess.Id -or $_.LocalAddress -notin @('127.0.0.1','::1') })) {
                throw "Ollama endpoint ownership or loopback binding could not be verified. No process was stopped. Inspect PID $($ollamaProcess.Id) and $ollamaErrorLog."
            }
            Write-Host "Local Ollama ready; cloud disabled. PID $($ollamaProcess.Id)."
            return
        }
    }
    $ollamaProcess.Refresh()
    if (!$ollamaProcess.HasExited) {
        throw "Ollama startup is still running (PID $($ollamaProcess.Id)). It was not restarted. See $ollamaErrorLog."
    }
    $ollamaFailure = if (Test-Path -LiteralPath $ollamaErrorLog) { Get-Content -LiteralPath $ollamaErrorLog -Raw -ErrorAction SilentlyContinue } else { '' }
    # Windows can reject the first bind with WSAEFAULT (10014). Retry only this
    # observed startup failure, only after the owned process has exited.
    $knownPointerFailure = $ollamaFailure -match '(?i)(\b10014\b|\bWSAEFAULT\b|invalid pointer address)'
    if (!$knownPointerFailure -or $ollamaStartAttempt -eq 3) {
        throw "Ollama exited during startup (exit $($ollamaProcess.ExitCode), attempt $ollamaStartAttempt). No further retry. See $ollamaErrorLog."
    }
    Write-Host "Ollama startup encountered Windows socket error 10014; owned process exited. Retrying startup ($($ollamaStartAttempt + 1)/3)."
}
