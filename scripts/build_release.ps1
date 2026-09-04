param(
    [switch]$OneFile
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$cardImages = Join-Path $projectRoot 'SV_WB_Cards'
$catalogCsv = Join-Path $projectRoot 'src\shadowverse_tracker\data\SV_WB_Cards.csv'
$cardEffects = Join-Path $projectRoot 'src\shadowverse_tracker\data\card_effects_chs.json'
$cnCardIds = Join-Path $projectRoot 'src\shadowverse_tracker\data\cn_card_ids.json'
$versionProfiles = Join-Path $projectRoot 'src\shadowverse_tracker\version_profiles'
$appAssets = Join-Path $projectRoot 'src\shadowverse_tracker\assets'
$appIcon = Join-Path $appAssets 'kandima_icon.ico'
$chinaLauncherScript = Join-Path $PSScriptRoot 'launch_china_shadowverse.ps1'

if (-not (Test-Path -LiteralPath $cardImages)) {
    throw "未找到卡图资源：$cardImages"
}
if (-not (Test-Path -LiteralPath $catalogCsv)) {
    throw "未找到卡牌数据：$catalogCsv"
}
if (-not (Test-Path -LiteralPath $cardEffects)) {
    throw "未找到卡牌效果数据：$cardEffects"
}
if (-not (Test-Path -LiteralPath $cnCardIds)) {
    throw "未找到国服卡牌 ID 映射：$cnCardIds"
}
if (-not (Test-Path -LiteralPath $versionProfiles)) {
    throw "未找到版本配置：$versionProfiles"
}
if (-not (Test-Path -LiteralPath $appIcon)) {
    throw "未找到应用图标：$appIcon"
}
if (-not (Test-Path -LiteralPath $chinaLauncherScript)) {
    throw "未找到国服启动脚本：$chinaLauncherScript"
}

python -m pip install pyinstaller Pillow PySide6 PySide6-Fluent-Widgets

$arguments = @(
    '--noconfirm',
    '--clean',
    '--name', 'ShadowverseTracker',
    '--add-data', "$cardImages;SV_WB_Cards",
    '--add-data', "$catalogCsv;shadowverse_tracker\\data",
    '--add-data', "$cardEffects;shadowverse_tracker\\data",
    '--add-data', "$cnCardIds;shadowverse_tracker\\data",
    '--add-data', "$versionProfiles;shadowverse_tracker\\version_profiles",
    '--add-data', "$appAssets;shadowverse_tracker\\assets",
    '--icon', $appIcon,
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

# The helper is intentionally kept beside the executable: it can start the
# CN Windows player directly or fall back to MuMu without being bundled into
# the Python runtime.  Copy it for both onedir and onefile release layouts.
$releaseDirectory = Join-Path $projectRoot 'dist'
$releaseDestination = if ($OneFile) {
    $releaseDirectory
} else {
    Join-Path $releaseDirectory 'ShadowverseTracker'
}
New-Item -ItemType Directory -Path $releaseDestination -Force | Out-Null
Copy-Item -LiteralPath $chinaLauncherScript -Destination $releaseDestination -Force
