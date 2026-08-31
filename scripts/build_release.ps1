param(
    [switch]$OneFile
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$cardImages = Join-Path $projectRoot 'SV_WB_Cards'
$catalogCsv = Join-Path $projectRoot 'src\shadowverse_tracker\data\SV_WB_Cards.csv'
$versionProfiles = Join-Path $projectRoot 'src\shadowverse_tracker\version_profiles'

if (-not (Test-Path -LiteralPath $cardImages)) {
    throw "未找到卡图资源：$cardImages"
}
if (-not (Test-Path -LiteralPath $catalogCsv)) {
    throw "未找到卡牌数据：$catalogCsv"
}
if (-not (Test-Path -LiteralPath $versionProfiles)) {
    throw "未找到版本配置：$versionProfiles"
}

python -m pip install pyinstaller Pillow

$arguments = @(
    '--noconfirm',
    '--clean',
    '--name', 'ShadowverseTracker',
    '--add-data', "$cardImages;SV_WB_Cards",
    '--add-data', "$catalogCsv;shadowverse_tracker\\data",
    '--add-data', "$versionProfiles;shadowverse_tracker\\version_profiles",
    '--hidden-import', 'shadowverse_tracker.version_profiles',
    '--exclude-module', 'numpy',
    '--paths', (Join-Path $projectRoot 'src')
)
if ($OneFile) {
    $arguments += '--onefile'
} else {
    $arguments += '--onedir'
}
$arguments += (Join-Path $projectRoot 'run_tracker.py')

Push-Location $projectRoot
try {
    # Codex's own image runtimes can be present in PATH while developing.
    # Their CRT DLLs are unrelated to the tracker and cause PyInstaller to
    # collect a duplicate ucrtbase.dll on Windows.
    $originalPath = $env:PATH
    $env:PATH = (($originalPath -split ';') | Where-Object {
        $_ -notmatch '[\\/]codex-runtimes[\\/]'
    }) -join ';'
    python -m PyInstaller @arguments
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
