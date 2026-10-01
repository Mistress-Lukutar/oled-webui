<#
File:    setup.ps1
Brief:   One-time installer for LuminaFlowUI on a fresh Windows machine.
Author:  Mistress-Lukutar
Date:    2026-10-01
Version: v0.5.2

Prepares everything start.bat needs:
  - Python 3.11+ (winget, manual fallback)
  - Node.js LTS (winget, manual fallback)
  - Python venv + backend package install (pip install -e .)
  - Frontend production build (npm run build -> static/dist/)
  - ffmpeg (winget Gyan.FFmpeg, else a static build in tools/ffmpeg)
  - PawnIO driver (GitHub release installer, needed by OpenRGB for SMBus)
  - OpenRGB (existing install, else a portable download into tools/OpenRGB)
  - .env wired to OpenRGB (task or exe)
  - Task Scheduler entries: "LuminaFlowUI" (logon supervisor loop) and
    "LuminaFlowUI OpenRGB" (elevated, on-demand SDK server)

Anything that cannot be done automatically is collected and reported at
the end as a manual step with a download URL; after completing those
steps the user re-runs setup.bat. Steps that already pass are skipped,
so re-running is always safe.

Usage (see setup.bat for the double-click entry point):
  setup.bat                  # normal run; elevated terminal preferred
  setup.bat -SkipTasks       # prepare environment, touch no scheduled tasks
  setup.bat -SkipDownloads   # check and report only, install nothing
#>

param(
    [switch]$SkipTasks,
    [switch]$SkipDownloads
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    # GitHub and GitLab require TLS 1.2 on Windows PowerShell 5.1.
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.ServicePointManager]::SecurityProtocol -bor
        [Net.SecurityProtocolType]::Tls12
} catch {}

$Root = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $Root 'tools'
$DownloadsDir = Join-Path $ToolsDir 'downloads'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$AppTaskName = 'LuminaFlowUI'
$OpenRgbTaskName = 'LuminaFlowUI OpenRGB'
$FfmpegBin = Join-Path $ToolsDir 'ffmpeg\bin'
$OpenRgbDir = Join-Path $ToolsDir 'OpenRGB'

# Manual steps that could not be automated; printed at the end.
$script:ManualSteps = New-Object System.Collections.Generic.List[string]

function Add-ManualStep([string]$message) {
    $script:ManualSteps.Add($message)
}

function Write-Step([string]$text) {
    Write-Host "`n== $text" -ForegroundColor Cyan
}

function Write-Ok([string]$text) {
    Write-Host "   OK: $text" -ForegroundColor Green
}

function Write-WarnLine([string]$text) {
    Write-Host "   !! $text" -ForegroundColor Yellow
}

function Update-SessionPath {
    # Rebuild PATH from the registry so freshly installed tools are visible
    # without restarting the shell.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-TaskExists([string]$name) {
    # Run through cmd so that schtasks' stderr never becomes a terminating
    # error record under $ErrorActionPreference = 'Stop'.
    cmd.exe /c "schtasks /query /tn `"$name`" >nul 2>&1"
    return ($LASTEXITCODE -eq 0)
}

function Download-File([string]$url, [string]$dest) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    Write-Host "   Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
}

function Test-Winget {
    return $null -ne (Get-Command winget.exe -ErrorAction SilentlyContinue)
}

function Invoke-WingetInstall([string]$packageId) {
    Write-Host "   Installing via winget ($packageId)..."
    winget install --id $packageId -e --silent `
        --accept-package-agreements --accept-source-agreements
    Update-SessionPath
}

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

function Get-PythonExe {
    # Prefer the py launcher, then whatever python.exe is on PATH; the
    # interpreter must be 3.11+.
    $candidates = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $exe = & py.exe -3 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += ([string]$exe).Trim() }
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    foreach ($exe in $candidates) {
        if (-not $exe -or -not (Test-Path $exe)) { continue }
        $ver = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])"
        if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
        $parts = ([string]$ver).Trim().Split('.')
        if ([int]$parts[0] -gt 3 -or
            ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) {
            return $exe
        }
    }
    return $null
}

function Ensure-Python {
    Write-Step 'Python 3.11+'
    $exe = Get-PythonExe
    if ($exe) { Write-Ok "Found $exe"; return }
    if ($SkipDownloads) {
        Add-ManualStep ('Python 3.11+ is not installed. Install it from ' +
            'https://www.python.org/downloads/ or with ' +
            "'winget install Python.Python.3.12', then re-run setup.bat.")
        return
    }
    if (Test-Winget) {
        Invoke-WingetInstall 'Python.Python.3.12'
        $exe = Get-PythonExe
        if ($exe) { Write-Ok "Installed $exe"; return }
        Write-WarnLine 'winget finished but Python is still not on PATH.'
    }
    Add-ManualStep ('Python 3.11+ could not be installed automatically. ' +
        'Install it from https://www.python.org/downloads/ (tick "Add to ' +
        'PATH"), then re-run setup.bat.')
}

# ---------------------------------------------------------------------------
# Node.js (needed only to build the frontend)
# ---------------------------------------------------------------------------

function Test-Node {
    return $null -ne (Get-Command npm.cmd -ErrorAction SilentlyContinue)
}

function Ensure-Node {
    Write-Step 'Node.js LTS (frontend build)'
    if (Test-Node) {
        $version = & npm.cmd --version
        Write-Ok "Found npm $version"
        return
    }
    if ($SkipDownloads) {
        Add-ManualStep ('Node.js is not installed (needed to build the ' +
            'frontend). Install the LTS build from https://nodejs.org/ or ' +
            "with 'winget install OpenJS.NodeJS.LTS', then re-run setup.bat.")
        return
    }
    if (Test-Winget) {
        Invoke-WingetInstall 'OpenJS.NodeJS.LTS'
        if (Test-Node) { Write-Ok 'Node.js installed'; return }
        Write-WarnLine 'winget finished but npm is still not on PATH.'
    }
    Add-ManualStep ('Node.js could not be installed automatically. Install ' +
        'the LTS build from https://nodejs.org/, then re-run setup.bat.')
}

# ---------------------------------------------------------------------------
# venv + backend package
# ---------------------------------------------------------------------------

function Ensure-Venv {
    Write-Step 'Python virtual environment and backend package'
    $exe = Get-PythonExe
    if (-not $exe) {
        Write-WarnLine 'Python is missing; skipping venv creation.'
        return
    }
    if (-not (Test-Path $VenvPython)) {
        Write-Host "   Creating .venv with $exe"
        & $exe -m venv (Join-Path $Root '.venv')
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
            Add-ManualStep ('The venv could not be created. Run ' +
                "`"$exe`" -m venv .venv in $Root, then re-run setup.bat.")
            return
        }
        Write-Ok '.venv created'
    } else {
        Write-Ok '.venv already exists'
    }
    Write-Host '   Installing backend dependencies (pip install -e .)...'
    & $VenvPython -m pip install --quiet --disable-pip-version-check `
        --upgrade pip
    & $VenvPython -m pip install --quiet --disable-pip-version-check -e $Root
    if ($LASTEXITCODE -ne 0) {
        Add-ManualStep ('Backend dependencies failed to install. Run ' +
            "'.venv\Scripts\python.exe -m pip install -e .' in $Root to see " +
            'the error, fix it, then re-run setup.bat.')
        return
    }
    Write-Ok 'Backend package installed'
}

# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------

function Ensure-Frontend {
    Write-Step 'Frontend build (static\dist)'
    if (Test-Path (Join-Path $Root 'static\dist\index.html')) {
        Write-Ok 'static\dist\index.html already exists'
        return
    }
    if (-not (Test-Node)) {
        Add-ManualStep ('The frontend is not built and Node.js is missing. ' +
            'Install Node.js, then re-run setup.bat (or run "npm install" ' +
            'and "npm run build" in frontend\ yourself).')
        return
    }
    Push-Location (Join-Path $Root 'frontend')
    try {
        Write-Host '   npm install ...'
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) {
            Add-ManualStep ('npm install failed. Run "npm install" in ' +
                'frontend\ to see the error, fix it, then re-run setup.bat.')
            return
        }
        Write-Host '   npm run build ...'
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            Add-ManualStep ('npm run build failed. Run "npm run build" in ' +
                'frontend\ to see the error, fix it, then re-run setup.bat.')
            return
        }
        if (Test-Path (Join-Path $Root 'static\dist\index.html')) {
            Write-Ok 'Frontend built into static\dist'
        } else {
            Add-ManualStep 'The build finished but static\dist\index.html is missing.'
        }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# ffmpeg (only needed for video: widgets)
# ---------------------------------------------------------------------------

function Test-FfmpegOnPath {
    return $null -ne (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)
}

function Ensure-Ffmpeg {
    Write-Step 'ffmpeg (video widget support, optional)'
    if (Test-FfmpegOnPath) {
        Write-Ok "Found $((Get-Command ffmpeg.exe).Source)"
        return
    }
    $localFfmpeg = Join-Path $FfmpegBin 'ffmpeg.exe'
    if (Test-Path $localFfmpeg) {
        Write-Ok "Found $localFfmpeg (start.bat adds it to PATH)"
        return
    }
    if ($SkipDownloads) {
        Add-ManualStep ('ffmpeg was not found (only needed for video ' +
            'widgets). Install it on PATH with ' +
            "'winget install Gyan.FFmpeg', or download " +
            'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip ' +
            "and unpack its bin\ folder into tools\ffmpeg\bin\. " +
            'Then re-run setup.bat.')
        return
    }
    if (Test-Winget) {
        Invoke-WingetInstall 'Gyan.FFmpeg'
        if (Test-FfmpegOnPath) {
            Write-Ok 'ffmpeg installed via winget'
            return
        }
        Write-WarnLine 'winget did not put ffmpeg on PATH; trying a direct download.'
    }
    $zip = Join-Path $DownloadsDir 'ffmpeg-release-essentials.zip'
    try {
        Download-File 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $zip
        $tmp = Join-Path $DownloadsDir 'ffmpeg-extract'
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $found = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe |
            Select-Object -First 1
        if (-not $found) { throw 'ffmpeg.exe not found inside the archive' }
        New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
        Copy-Item (Join-Path $found.Directory.FullName '*') $FfmpegBin -Force
        Write-Ok "ffmpeg unpacked into $FfmpegBin (start.bat adds it to PATH)"
    } catch {
        Write-WarnLine $_.Exception.Message
        Add-ManualStep ('ffmpeg could not be downloaded. Get ' +
            'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip ' +
            'yourself and unpack its bin\ folder into tools\ffmpeg\bin\ ' +
            "(or run 'winget install Gyan.FFmpeg'), then re-run setup.bat.")
    }
}

# ---------------------------------------------------------------------------
# PawnIO (driver used by OpenRGB for motherboard SMBus access)
# ---------------------------------------------------------------------------

function Test-PawnIO {
    if (Get-Service -Name 'PawnIO' -ErrorAction SilentlyContinue) { return $true }
    if (Test-Path (Join-Path $env:ProgramFiles 'PawnIO')) { return $true }
    return $false
}

function Ensure-PawnIO {
    Write-Step 'PawnIO driver (OpenRGB SMBus access, optional)'
    if (Test-PawnIO) { Write-Ok 'PawnIO is installed'; return }
    if ($SkipDownloads) {
        Add-ManualStep ('PawnIO is not installed (used by OpenRGB to reach ' +
            'motherboard LED controllers). Download and install ' +
            'https://github.com/namazso/PawnIO/releases/latest/download/PawnIO-setup.exe, ' +
            'then re-run setup.bat.')
        return
    }
    $installer = Join-Path $DownloadsDir 'PawnIO-setup.exe'
    try {
        Download-File 'https://github.com/namazso/PawnIO/releases/latest/download/PawnIO-setup.exe' $installer
        Write-Host '   Running PawnIO-setup.exe /S ...'
        if (Test-Admin) {
            Start-Process -FilePath $installer -ArgumentList '/S' -Wait
        } else {
            # Driver installs need elevation; trigger a single UAC prompt.
            Start-Process -FilePath $installer -ArgumentList '/S' -Verb RunAs -Wait
        }
        if (Test-PawnIO) {
            Write-Ok 'PawnIO installed'
        } else {
            throw 'PawnIO is still not detected after the installer ran'
        }
    } catch {
        Write-WarnLine $_.Exception.Message
        Add-ManualStep ('PawnIO could not be installed automatically. ' +
            'Download https://github.com/namazso/PawnIO/releases/latest/download/PawnIO-setup.exe, ' +
            'run it, then re-run setup.bat.')
    }
}

# ---------------------------------------------------------------------------
# OpenRGB
# ---------------------------------------------------------------------------

function Find-OpenRgbExe {
    $candidates = @(
        (Join-Path $OpenRgbDir 'OpenRGB.exe'),
        (Join-Path $env:ProgramFiles 'OpenRGB\OpenRGB.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'OpenRGB\OpenRGB.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\OpenRGB\OpenRGB.exe'),
        'C:\OpenRGB\OpenRGB.exe'
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    $cmd = Get-Command OpenRGB.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Ensure-OpenRgb {
    Write-Step 'OpenRGB (ARGB lighting, optional)'
    $exe = Find-OpenRgbExe
    if ($exe) { Write-Ok "Found $exe"; return $exe }
    if ($SkipDownloads) {
        Add-ManualStep ('OpenRGB was not found (only needed for ARGB ' +
            'lighting). Download the Windows 64-bit build from ' +
            'https://gitlab.com/CalcProgrammer1/OpenRGB/-/releases and ' +
            "unpack it so that tools\OpenRGB\OpenRGB.exe exists, then " +
            're-run setup.bat.')
        return $null
    }
    try {
        Write-Host '   Querying the latest OpenRGB release on GitLab...'
        $api = 'https://gitlab.com/api/v4/projects/CalcProgrammer1%2FOpenRGB/releases?per_page=5'
        $release = Invoke-RestMethod -Uri $api -UseBasicParsing |
            Select-Object -First 1
        $asset = $release.assets.links |
            Where-Object { $_.url -match 'Windows.*64.*\.zip$' } |
            Select-Object -First 1
        if (-not $asset) {
            throw 'no Windows 64-bit zip asset in the latest release'
        }
        $zip = Join-Path $DownloadsDir 'openrgb-windows.zip'
        Download-File $asset.url $zip
        $tmp = Join-Path $DownloadsDir 'openrgb-extract'
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $found = Get-ChildItem -Path $tmp -Recurse -Filter OpenRGB.exe |
            Select-Object -First 1
        if (-not $found) { throw 'OpenRGB.exe not found inside the archive' }
        New-Item -ItemType Directory -Force -Path $OpenRgbDir | Out-Null
        Copy-Item (Join-Path $found.Directory.FullName '*') $OpenRgbDir -Force
        $exe = Join-Path $OpenRgbDir 'OpenRGB.exe'
        if (-not (Test-Path $exe)) { throw 'failed to copy OpenRGB.exe' }
        Write-Ok "OpenRGB unpacked into $OpenRgbDir"
        return $exe
    } catch {
        Write-WarnLine $_.Exception.Message
        Add-ManualStep ('OpenRGB could not be downloaded (' +
            "$($_.Exception.Message)). Download a Windows 64-bit build from " +
            'https://gitlab.com/CalcProgrammer1/OpenRGB/-/releases and ' +
            "unpack it so that tools\OpenRGB\OpenRGB.exe exists, then " +
            're-run setup.bat.')
        return $null
    }
}

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

function Set-EnvKey([string]$key, [string]$value) {
    # Update or append a single LUMINA_* key without touching the rest.
    $envPath = Join-Path $Root '.env'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $lines = @()
    if (Test-Path $envPath) {
        $lines = [System.IO.File]::ReadAllLines($envPath)
    }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match ("^\s*$([regex]::Escape($key))\s*=")) {
            $lines[$i] = "$key=$value"
            $found = $true
        }
    }
    if (-not $found) { $lines += "$key=$value" }
    [System.IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)
}

function Ensure-EnvFile {
    Write-Step '.env configuration'
    $envPath = Join-Path $Root '.env'
    if (Test-Path $envPath) {
        Write-Ok '.env already exists (existing values are kept)'
    } else {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText(
            $envPath,
            "# LuminaFlowUI settings (LUMINA_* prefix). See README.md.`r`n",
            $utf8NoBom)
        Write-Ok 'Created .env'
    }
}

# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------

function Register-AppTask {
    Write-Step "Task Scheduler: '$AppTaskName' (logon supervisor loop)"
    if (Test-TaskExists $AppTaskName) {
        Write-Ok "Task '$AppTaskName' already registered"
        return
    }
    # Never create a second supervisor next to an existing one.
    foreach ($legacy in @('Supervisor', 'OledWebUI', 'oled-webui')) {
        if (Test-TaskExists $legacy) {
            Write-WarnLine "An existing task '$legacy' already runs this app; skipping registration."
            return
        }
    }
    $bat = Join-Path $Root 'scripts\supervisor.bat'
    schtasks.exe /create /f /tn $AppTaskName /sc onlogon /rl limited /tr "`"$bat`""
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Registered '$AppTaskName' -> scripts\supervisor.bat (runs at logon)"
    } else {
        Add-ManualStep ("The '$AppTaskName' scheduled task could not be " +
            'registered. Register it manually as the current user: ' +
            "schtasks /create /f /tn `"$AppTaskName`" /sc onlogon " +
            "/tr `"$bat`"")
    }
}

function Register-OpenRgbTask([string]$exe) {
    if (-not $exe) {
        Write-WarnLine 'OpenRGB not found; skipping task registration.'
        return
    }
    Write-Step "Task Scheduler: '$OpenRgbTaskName' (elevated OpenRGB SDK server)"
    if (Test-TaskExists $OpenRgbTaskName) {
        Write-Ok "Task '$OpenRgbTaskName' already registered"
        Set-EnvKey 'LUMINA_OPENRGB_TASK' $OpenRgbTaskName
        return
    }
    # Highest integrity is what lets OpenRGB use PawnIO for SMBus access.
    $taskRun = "`"$exe`" --server --server-host 127.0.0.1 --server-port 6742"
    schtasks.exe /create /f /tn $OpenRgbTaskName /sc ondemand /rl highest /tr $taskRun
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Registered '$OpenRgbTaskName' (on demand, elevated)"
        Set-EnvKey 'LUMINA_OPENRGB_TASK' $OpenRgbTaskName
        Write-Ok '.env now points at LUMINA_OPENRGB_TASK'
    } else {
        Write-WarnLine 'Registration needs an elevated terminal; falling back to direct spawn.'
        Set-EnvKey 'LUMINA_OPENRGB_EXE' $exe
        Add-ManualStep ("The elevated '$OpenRgbTaskName' task could not be " +
            'registered (setup was not run as administrator). The server ' +
            'will spawn OpenRGB directly instead, which may fail for SMBus ' +
            'controllers. To fix, run setup.bat from an administrator ' +
            'terminal, or register manually: schtasks /create /f /tn ' +
            "`"$OpenRgbTaskName`" /sc ondemand /rl highest /tr `"$taskRun`"")
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

Write-Host 'LuminaFlowUI setup' -ForegroundColor Cyan
Write-Host "Project: $Root"
if ($SkipDownloads) { Write-Host 'Mode: check only (-SkipDownloads)' -ForegroundColor Cyan }
if ($SkipTasks) { Write-Host 'Mode: no scheduled tasks (-SkipTasks)' -ForegroundColor Cyan }

Ensure-Python
Ensure-Venv
Ensure-Node
Ensure-Frontend
Ensure-Ffmpeg
Ensure-PawnIO
$openRgbExe = Ensure-OpenRgb
Ensure-EnvFile
if (-not $SkipTasks) {
    Register-AppTask
    Register-OpenRgbTask $openRgbExe
}

Write-Host ''
if ($script:ManualSteps.Count -eq 0) {
    Write-Host 'Setup complete.' -ForegroundColor Green
    Write-Host ('Start the app with start.bat, or log off/on once so the ' +
        "logon task takes effect.")
} else {
    Write-Host 'Setup finished, but some steps need to be done manually:' -ForegroundColor Yellow
    foreach ($step in $script:ManualSteps) {
        Write-Host " - $step" -ForegroundColor Yellow
    }
    Write-Host ''
    Write-Host 'After completing them, re-run setup.bat.' -ForegroundColor Yellow
}
exit 0
