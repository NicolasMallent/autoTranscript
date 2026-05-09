# AutoTranscript - Installateur Windows 11
# Clic droit sur ce fichier > "Executer avec PowerShell"
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $AppDir ".venv"

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  AutoTranscript - Installation" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Verifier / installer Python ---
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.") {
            $python = $candidate
            Write-Host "[OK] Python detecte : $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "[...] Python non trouve. Installation via winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.11 --source winget --silent --accept-package-agreements --accept-source-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $python = "python"
    Write-Host "[OK] Python installe." -ForegroundColor Green
}

# --- 2. Creer le venv ---
if (-not (Test-Path $VenvDir)) {
    Write-Host "[...] Creation de l'environnement virtuel..." -ForegroundColor Yellow
    & $python -m venv $VenvDir
    Write-Host "[OK] Environnement virtuel cree." -ForegroundColor Green
} else {
    Write-Host "[OK] Environnement virtuel existant detecte." -ForegroundColor Green
}

$pip = Join-Path $VenvDir "Scripts\pip.exe"
$pythonVenv = Join-Path $VenvDir "Scripts\python.exe"

# --- 3. Installer les dependances ---
Write-Host "[...] Installation des dependances (peut prendre plusieurs minutes)..." -ForegroundColor Yellow
& $pip install --upgrade pip --quiet
& $pip install -r (Join-Path $AppDir "requirements.txt") --quiet
Write-Host "[OK] Dependances installees." -ForegroundColor Green

# --- 4. Creer le lanceur .bat ---
$launcherPath = Join-Path $AppDir "lancer.bat"
$appMainPath = Join-Path $AppDir "app\main.py"
@"
@echo off
"$pythonVenv" "$appMainPath"
"@ | Set-Content -Path $launcherPath -Encoding ASCII
Write-Host "[OK] Lanceur cree : $launcherPath" -ForegroundColor Green

# --- 5. Raccourci bureau ---
try {
    $desktop = [System.Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "AutoTranscript.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherPath
    $shortcut.WorkingDirectory = $AppDir
    $shortcut.Description = "AutoTranscript - Transcription audio avec Whisper AI"
    $shortcut.Save()
    Write-Host "[OK] Raccourci cree sur le bureau." -ForegroundColor Green
} catch {
    Write-Host "[!]  Raccourci non cree (non bloquant) : $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Installation terminee !" -ForegroundColor Cyan
Write-Host "  Lancez l'application depuis :" -ForegroundColor Cyan
Write-Host "  - Le raccourci sur le bureau" -ForegroundColor Cyan
Write-Host "  - Ou double-clic sur lancer.bat" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
