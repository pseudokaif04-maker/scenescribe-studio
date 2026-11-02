#requires -Version 5.1
<#
.SYNOPSIS
    Start the SceneScribe local caption studio.

.DESCRIPTION
    Creates a local virtual environment on first run, installs dependencies,
    checks for ffmpeg, and starts the Starlette app on localhost.

.PARAMETER Port
    Local port to listen on. Defaults to 8000.

.PARAMETER NoBrowser
    Do not open the studio in the default browser after startup.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Port 8080 -NoBrowser
#>
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating a local virtual environment..." -ForegroundColor Cyan
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 was not found. Install it from https://www.python.org/downloads/ and run this script again."
    }
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg was not found on PATH. Install it with 'winget install Gyan.FFmpeg' and restart the terminal."
}

if (-not $NoBrowser) {
    $url = "http://127.0.0.1:$Port"
    Start-Job -ScriptBlock {
        param($target)
        Start-Sleep -Seconds 2
        Start-Process $target
    } -ArgumentList $url | Out-Null
}

Write-Host ""
Write-Host "  SceneScribe" -ForegroundColor White
Write-Host "  Local caption studio - http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $python -m uvicorn app:app --host 127.0.0.1 --port $Port
