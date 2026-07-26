param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$RuntimeDir = Join-Path $InstallDir "runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$LogPath = Join-Path $LogDir "setup.log"
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.13.5/python-3.13.5-amd64.exe"
$FfmpegZipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Start-Transcript -LiteralPath $LogPath -Append | Out-Null

function Write-Status {
    param([string]$Message)
    Write-Host "[Reels Builder Setup] $Message"
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @()
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE."
    }
}

function Test-CompatiblePython {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    try {
        & $Path -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)"
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Find-CompatiblePython {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )

    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand -and $PythonCommand.Source -notlike "*\WindowsApps\python.exe") {
        $Candidates += $PythonCommand.Source
    }

    $PyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        foreach ($Version in @("3.13", "3.12", "3.11")) {
            try {
                $Resolved = (& $PyLauncher.Source "-$Version" -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
                if ($Resolved) {
                    $Candidates += $Resolved.Trim()
                }
            }
            catch {
            }
        }
    }

    foreach ($Candidate in $Candidates | Select-Object -Unique) {
        if (Test-CompatiblePython $Candidate) {
            return [IO.Path]::GetFullPath($Candidate)
        }
    }
    return $null
}

function Install-Python {
    Write-Status "Compatible Python was not found. Installing Python 3.13 for this user..."
    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($Winget) {
        & $Winget.Source install --id Python.Python.3.13 --exact --scope user --silent `
            --accept-source-agreements --accept-package-agreements --disable-interactivity |
            Out-Host
        if ($LASTEXITCODE -eq 0) {
            $Detected = Find-CompatiblePython
            if ($Detected) {
                return $Detected
            }
        }
        Write-Status "winget Python installation did not complete; using the official installer fallback."
    }

    $InstallerPath = Join-Path $RuntimeDir "python-installer.exe"
    Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $InstallerPath -UseBasicParsing | Out-Null
    $Process = Start-Process -FilePath $InstallerPath -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_launcher=1",
        "Include_test=0",
        "SimpleInstall=1"
    ) -Wait -PassThru
    if ($Process.ExitCode -ne 0) {
        throw "The official Python installer exited with code $($Process.ExitCode)."
    }
    Remove-Item -LiteralPath $InstallerPath -Force -ErrorAction SilentlyContinue
    $Detected = Find-CompatiblePython
    if (-not $Detected) {
        throw "Python installation completed, but a compatible python.exe could not be located."
    }
    return $Detected
}

function Test-FfmpegPair {
    param([string]$FfmpegPath)
    if (-not $FfmpegPath -or -not (Test-Path -LiteralPath $FfmpegPath -PathType Leaf)) {
        return $false
    }
    $FfprobePath = Join-Path (Split-Path -Parent $FfmpegPath) "ffprobe.exe"
    if (-not (Test-Path -LiteralPath $FfprobePath -PathType Leaf)) {
        return $false
    }
    try {
        & $FfmpegPath -version *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Find-Ffmpeg {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\ffmpeg.exe"),
        (Join-Path $RuntimeDir "ffmpeg\bin\ffmpeg.exe")
    )
    $FfmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($FfmpegCommand) {
        $Candidates += $FfmpegCommand.Source
    }
    $Candidates += Get-ChildItem -LiteralPath (Join-Path $RuntimeDir "ffmpeg") `
        -Filter ffmpeg.exe -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName

    foreach ($Candidate in $Candidates | Select-Object -Unique) {
        if (Test-FfmpegPair $Candidate) {
            return [IO.Path]::GetFullPath($Candidate)
        }
    }
    return $null
}

function Install-Ffmpeg {
    Write-Status "FFmpeg was not found. Installing the FFmpeg essentials build..."
    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($Winget) {
        & $Winget.Source install --id Gyan.FFmpeg --exact --scope user --silent `
            --accept-source-agreements --accept-package-agreements --disable-interactivity |
            Out-Host
        if ($LASTEXITCODE -eq 0) {
            $Detected = Find-Ffmpeg
            if ($Detected) {
                return $Detected
            }
        }
        Write-Status "winget FFmpeg installation did not complete; using the ZIP fallback."
    }

    $ZipPath = Join-Path $RuntimeDir "ffmpeg.zip"
    $ExtractPath = Join-Path $RuntimeDir "ffmpeg"
    New-Item -ItemType Directory -Path $ExtractPath -Force | Out-Null
    Invoke-WebRequest -Uri $FfmpegZipUrl -OutFile $ZipPath -UseBasicParsing | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractPath -Force
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    $Detected = Find-Ffmpeg
    if (-not $Detected) {
        throw "FFmpeg was downloaded, but ffmpeg.exe and ffprobe.exe could not be located."
    }
    return $Detected
}

try {
    Write-Status "Preparing runtime folders..."
    $PythonPath = Find-CompatiblePython
    if (-not $PythonPath) {
        $PythonPath = Install-Python
    }
    Write-Status "Using Python: $PythonPath"

    $FfmpegPath = Find-Ffmpeg
    if (-not $FfmpegPath) {
        $FfmpegPath = Install-Ffmpeg
    }
    $FfmpegBin = Split-Path -Parent $FfmpegPath
    Set-Content -LiteralPath (Join-Path $RuntimeDir "ffmpeg-path.txt") -Value $FfmpegBin -Encoding UTF8
    Write-Status "Using FFmpeg: $FfmpegPath"

    $VenvDir = Join-Path $InstallDir ".venv"
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        Write-Status "Creating an isolated Python environment..."
        Invoke-Checked -FilePath $PythonPath -Arguments @("-m", "venv", $VenvDir)
    }

    Write-Status "Installing dashboard dependencies. This can take several minutes..."
    Invoke-Checked -FilePath $VenvPython -Arguments @(
        "-m", "pip", "install", "--disable-pip-version-check",
        "--no-warn-script-location", "-r", (Join-Path $InstallDir "requirements.txt")
    )

    $EnvPath = Join-Path $InstallDir ".env"
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        Copy-Item -LiteralPath (Join-Path $InstallDir ".env.example") -Destination $EnvPath
    }

    $PicturesDir = Join-Path ([Environment]::GetFolderPath("MyPictures")) "history videos"
    New-Item -ItemType Directory -Path (Join-Path $PicturesDir "bg_music") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $PicturesDir "fonts") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $PicturesDir "verification_reports") -Force | Out-Null

    $env:PATH = "$FfmpegBin;$env:PATH"
    Write-Status "Validating the installed dashboard..."
    Invoke-Checked -FilePath $VenvPython -Arguments @(
        "-c",
        "import streamlit, PIL, history_reels; print('Runtime validation passed.')"
    )
    Invoke-Checked -FilePath $FfmpegPath -Arguments @("-version")

    $Marker = [ordered]@{
        installed_at = [DateTime]::UtcNow.ToString("o")
        python = $PythonPath
        virtual_environment = $VenvDir
        ffmpeg = $FfmpegPath
        output_directory = $PicturesDir
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $RuntimeDir "install-complete.json") -Value $Marker -Encoding UTF8
    Write-Status "Runtime setup completed successfully."
    Stop-Transcript | Out-Null
    exit 0
}
catch {
    Write-Error $_
    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
    exit 1
}
