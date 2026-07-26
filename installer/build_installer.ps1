param(
    [switch]$InstallCompiler
)

$ErrorActionPreference = "Stop"
$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = [IO.Path]::GetFullPath((Join-Path $InstallerDir ".."))
$DistDir = Join-Path $ProjectDir "dist"
$IssPath = Join-Path $InstallerDir "ReelsBuilderSetup.iss"
$SetupPath = Join-Path $DistDir "ReelsBuilderSetup.exe"

function Test-IsExcludedPackagePath {
    param([string]$RelativePath)
    $Normalized = $RelativePath.Replace("/", "\")
    $Segments = $Normalized.Split("\")
    $ExcludedDirectories = @(
        ".git", ".github", ".agents", ".venv", "venv", "__pycache__",
        ".pytest_cache", ".ruff_cache", ".staging", "staging_reports",
        "dist", "tests", "scripts"
    )
    if ($Segments | Where-Object { $_ -in $ExcludedDirectories }) {
        return $true
    }
    $Name = [IO.Path]::GetFileName($Normalized)
    if ($Name -like ".env*" -and $Name -ne ".env.example") {
        return $true
    }
    if ($Name -in @(
        "app_source.zip", "secrets.toml", "AGENTS.md", "install.py",
        "patch.py", "patch2.py", "download_bg_music.py",
        "extract_zemtv_voice_large.py", "packages.txt", "dashboard_preview.jpg",
        "build_installer.ps1", "ReelsBuilderSetup.iss"
    )) {
        return $true
    }
    if ([IO.Path]::GetExtension($Name).ToLowerInvariant() -in @(
        ".pyc", ".mp4", ".mp3", ".wav", ".db", ".sqlite3"
    )) {
        return $true
    }
    return $false
}

Write-Host "Auditing files that will be eligible for packaging..."
$PackageFiles = Get-ChildItem -LiteralPath $ProjectDir -File -Recurse -Force |
    Where-Object {
        $Relative = [IO.Path]::GetRelativePath($ProjectDir, $_.FullName)
        -not (Test-IsExcludedPackagePath $Relative)
    }

$UnsafeFiles = $PackageFiles | Where-Object {
    $_.Name -eq ".env" -or
    $_.Name -eq "secrets.toml" -or
    $_.Extension.ToLowerInvariant() -in @(".pem", ".pfx", ".key", ".sqlite3", ".db")
}
if ($UnsafeFiles) {
    $List = ($UnsafeFiles.FullName -join [Environment]::NewLine)
    throw "Sensitive/local files would be packaged:`n$List"
}
if (-not ($PackageFiles | Where-Object { $_.Name -eq ".env.example" })) {
    throw ".env.example is missing from the package manifest."
}
if (-not ($PackageFiles | Where-Object { $_.Name -eq "app.py" })) {
    throw "app.py is missing from the package manifest."
}

$SecretPatterns = [ordered]@{
    "OpenAI-style key" = '(?i)\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}'
    "Google API key" = '\bAIza[0-9A-Za-z_-]{20,}'
    "Groq API key" = '\bgsk_[A-Za-z0-9_-]{20,}'
    "OpenRouter API key" = '\bsk-or-v1-[A-Za-z0-9_-]{20,}'
}
$TextExtensions = @(
    ".py", ".ps1", ".vbs", ".iss", ".md", ".toml", ".json",
    ".yaml", ".yml", ".ini", ".cfg", ".example"
)
$SecretFindings = @()
foreach ($File in $PackageFiles) {
    if ($File.Extension.ToLowerInvariant() -notin $TextExtensions -and $File.Name -ne ".env.example") {
        continue
    }
    $Content = Get-Content -LiteralPath $File.FullName -Raw -ErrorAction SilentlyContinue
    foreach ($PatternName in $SecretPatterns.Keys) {
        if ($Content -match $SecretPatterns[$PatternName]) {
            $Relative = [IO.Path]::GetRelativePath($ProjectDir, $File.FullName)
            $SecretFindings += "$Relative ($PatternName)"
        }
    }
}
if ($SecretFindings) {
    throw "Possible API secrets detected in package files:`n$($SecretFindings -join "`n")"
}

$TotalBytes = ($PackageFiles | Measure-Object -Property Length -Sum).Sum
Write-Host "Package audit passed: $($PackageFiles.Count) files, $TotalBytes bytes before compression."

$CompilerCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

$Compiler = $CompilerCandidates | Select-Object -First 1
if (-not $Compiler -and $InstallCompiler) {
    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Inno Setup is missing and winget is unavailable."
    }
    Write-Host "Installing Inno Setup compiler via winget..."
    & $Winget.Source install --id JRSoftware.InnoSetup --exact --scope user --silent `
        --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install Inno Setup (exit code $LASTEXITCODE)."
    }
    $CompilerCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $Compiler = $CompilerCandidates | Select-Object -First 1
}
if (-not $Compiler) {
    throw "Inno Setup 6 is not installed. Run this script with -InstallCompiler."
}

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
Write-Host "Compiling ReelsBuilderSetup.exe..."
& $Compiler $IssPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $SetupPath -PathType Leaf)) {
    throw "Compiler completed without creating $SetupPath"
}

$Hash = Get-FileHash -LiteralPath $SetupPath -Algorithm SHA256
$HashLine = "$($Hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($SetupPath))"
Set-Content -LiteralPath "$SetupPath.sha256" -Value $HashLine -Encoding ASCII
Write-Host "Built: $SetupPath"
Write-Host "SHA256: $($Hash.Hash)"
