param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,
    [int]$Port = 8501,
    [switch]$NoBrowser,
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$RuntimeDir = Join-Path $InstallDir "runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PythonPath = Join-Path $InstallDir ".venv\Scripts\python.exe"
$SetupScript = Join-Path $InstallDir "installer\install_runtime.ps1"
$DashboardUrl = "http://127.0.0.1:$Port"

function Show-LauncherError {
    param([string]$Message)
    $Shell = New-Object -ComObject WScript.Shell
    $Shell.Popup($Message, 0, "History Reels Builder", 16) | Out-Null
}

function Test-LocalPort {
    param([int]$Port)
    $Client = New-Object Net.Sockets.TcpClient
    try {
        $Async = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $Async.AsyncWaitHandle.WaitOne(250)) {
            return $false
        }
        $Client.EndConnect($Async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $Client.Close()
    }
}

try {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        $Result = Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$SetupScript`"",
            "-InstallDir", "`"$InstallDir`""
        ) -Wait -PassThru -WindowStyle Normal
        if ($Result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $PythonPath)) {
            throw "Runtime repair failed. See $LogDir\setup.log"
        }
    }

    $FfmpegPathFile = Join-Path $RuntimeDir "ffmpeg-path.txt"
    if (Test-Path -LiteralPath $FfmpegPathFile) {
        $FfmpegBin = (Get-Content -LiteralPath $FfmpegPathFile -Raw).Trim()
        if ($FfmpegBin -and (Test-Path -LiteralPath $FfmpegBin)) {
            $env:PATH = "$FfmpegBin;$env:PATH"
        }
    }
    $env:PYTHONUTF8 = "1"
    $env:PYTHONUNBUFFERED = "1"

    if (Test-LocalPort $Port) {
        if ($SelfTest) {
            throw "Self-test port $Port is already in use."
        }
        if (-not $NoBrowser) {
            Start-Process $DashboardUrl
        }
        exit 0
    }

    $StdoutLog = Join-Path $LogDir "dashboard-output.log"
    $StderrLog = Join-Path $LogDir "dashboard-error.log"
    $Arguments = @(
        "-m", "streamlit", "run", "app.py",
        "--server.address", "127.0.0.1",
        "--server.port", "$Port",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    )
    $Process = Start-Process -FilePath $PythonPath -ArgumentList $Arguments `
        -WorkingDirectory $InstallDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog
    Set-Content -LiteralPath (Join-Path $RuntimeDir "dashboard.pid") -Value $Process.Id -Encoding ASCII

    for ($Attempt = 0; $Attempt -lt 80; $Attempt++) {
        if ($Process.HasExited) {
            throw "Dashboard startup failed. See $StderrLog"
        }
        if (Test-LocalPort $Port) {
            if ($SelfTest) {
                $Response = Invoke-WebRequest -Uri $DashboardUrl -UseBasicParsing -TimeoutSec 10
                $SelfTestResult = [ordered]@{
                    passed = $Response.StatusCode -eq 200
                    http_status = $Response.StatusCode
                    process_id = $Process.Id
                    process_path = $Process.Path
                } | ConvertTo-Json
                Set-Content -LiteralPath (Join-Path $RuntimeDir "launcher-self-test.json") `
                    -Value $SelfTestResult -Encoding UTF8
                $Process.Kill()
                $Process.WaitForExit(10000) | Out-Null
                if ($Response.StatusCode -ne 200) {
                    throw "Dashboard self-test returned HTTP $($Response.StatusCode)."
                }
                exit 0
            }
            if (-not $NoBrowser) {
                Start-Process $DashboardUrl
            }
            exit 0
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Dashboard did not become ready in 20 seconds. See $StderrLog"
}
catch {
    Show-LauncherError $_.Exception.Message
    exit 1
}
