param(
    [ValidateSet('Direct', 'MumuCli', 'Launcher')]
    [string]$Mode = 'Direct',
    [string]$GamePath,
    [string]$MumuCliPath,
    [string]$LauncherPath,
    [int]$VmIndex = 1,
    [string]$PackageName = 'com.netease.yzs.hd'
)

$ErrorActionPreference = 'Stop'

function Find-FirstExistingPath([string[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Start-PortableExecutable([string]$Path) {
    # The distributed Unity player may intentionally use an ``.o`` suffix.
    # Use CreateProcess (UseShellExecute=false) instead of file associations,
    # so the suffix does not cause an "Open With" prompt.
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Path
    $info.WorkingDirectory = Split-Path -Parent $Path
    $info.UseShellExecute = $false
    [System.Diagnostics.Process]::Start($info) | Out-Null
}

$defaultCliPaths = @(
    'D:\MuMuPlayer\nx_main\mumu-cli.exe',
    'D:\MuMuPlayerGlobal\nx_main\mumu-cli.exe',
    (Join-Path ${env:ProgramFiles(x86)} 'MuMuPlayer\nx_main\mumu-cli.exe')
)
$defaultLauncherPaths = @(
    'C:\Program Files (x86)\MuMuGamePartnership\Shadowverse\launcher.exe',
    'C:\Program Files\MuMuGamePartnership\Shadowverse\launcher.exe'
)

if ($Mode -eq 'Direct') {
    $game = Find-FirstExistingPath @($GamePath)
    if (-not $game) {
        # The CN executable uses a localized filename and, on some installs,
        # an ``.o`` suffix.  Avoid embedding a code-page-sensitive literal:
        # search the known install roots for a PE-looking MuMu player file.
        foreach ($root in @('D:\Games\Shadowverse', 'C:\Games\Shadowverse')) {
            if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
            foreach ($filter in @('MuMu*.o', 'MuMu*.exe')) {
                $game = Get-ChildItem -LiteralPath $root -Filter $filter -File -ErrorAction SilentlyContinue |
                    Select-Object -First 1 -ExpandProperty FullName
                if ($game) { break }
            }
            if ($game) { break }
        }
    }
    if ($game) {
        Write-Host "Starting CN Windows client: $game"
        Start-PortableExecutable $game
        return
    }
    Write-Warning 'CN Windows client not found; falling back to the MuMu CLI.'
    $Mode = 'MumuCli'
}

if ($Mode -eq 'MumuCli') {
    $cliCandidates = @($MumuCliPath) + $defaultCliPaths
    $cli = Find-FirstExistingPath $cliCandidates
    if (-not $cli) {
        throw 'mumu-cli.exe not found. Pass -MumuCliPath to nx_main\mumu-cli.exe.'
    }
    Write-Host "Starting MuMu VM $VmIndex and package $PackageName"
    & $cli 'control' '--vmindex' $VmIndex 'launch' '--package' $PackageName
    if ($LASTEXITCODE -ne 0) {
        throw "mumu-cli failed (exit code $LASTEXITCODE)."
    }
    return
}

$launcherCandidates = @($LauncherPath) + $defaultLauncherPaths
$launcher = Find-FirstExistingPath $launcherCandidates
if (-not $launcher) {
    throw 'CN launcher not found. Pass -LauncherPath to launcher.exe.'
}
Write-Host "Starting CN launcher: $launcher"
Start-Process -FilePath $launcher -WorkingDirectory (Split-Path -Parent $launcher)
