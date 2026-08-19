param(
    [int]$Days = 30,
    [int]$VideosPerCreator = 10,
    [int]$CommentPages = 1,
    [switch]$SkipCollection,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraCollectorArgs
)

$ErrorActionPreference = 'Stop'
$PipelineDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $PipelineDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $PipelineDir '.env'
$EnvExample = Join-Path $PipelineDir '.env.example'

function Test-FfmpegAvailable {
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        return $true
    }

    $wingetPackages = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    return [bool](Get-ChildItem -Path $wingetPackages -Filter 'ffmpeg.exe' -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'Gyan\.FFmpeg_.+\\bin\\ffmpeg\.exe$' } |
        Select-Object -First 1)
}

function Install-FfmpegIfNeeded {
    if (Test-FfmpegAvailable) {
        Write-Host 'FFmpeg: available'
        return
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'FFmpeg is required, but WinGet was not found. Install FFmpeg (for example: winget install --id Gyan.FFmpeg --exact), then run again.'
    }

    Write-Host 'FFmpeg: installing with WinGet...'
    & $winget.Source install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0 -or -not (Test-FfmpegAvailable)) {
        throw 'FFmpeg installation failed. Install Gyan.FFmpeg manually, then run again.'
    }
}

if (-not (Test-Path $EnvFile)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    throw ".env was created at $EnvFile. Add YOUTUBE_API_KEY, then run this command again."
}

Install-FfmpegIfNeeded

if (-not (Test-Path $VenvPython)) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $PythonLauncher) { throw 'Python 3.11 or 3.12 is required. Install it, then run again.' }
    & py -3.11 -m venv (Join-Path $PipelineDir '.venv')
    if ($LASTEXITCODE -ne 0) { & py -3 -m venv (Join-Path $PipelineDir '.venv') }
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $PipelineDir 'requirements.txt')
}

Push-Location $PipelineDir
try {
    if (-not $SkipCollection) {
        & $VenvPython .\youtube_crawler\run.py --days $Days --videos-per-creator $VideosPerCreator --comment-pages $CommentPages @ExtraCollectorArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $VenvPython .\youtube_crawler\whisper_transcriber.py
    exit $LASTEXITCODE
}
finally { Pop-Location }
