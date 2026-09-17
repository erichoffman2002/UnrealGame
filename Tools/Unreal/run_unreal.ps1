<#
.SYNOPSIS
    Run a Python script against this Unreal project. All path discovery lives
    here, so the scripts themselves hard-code nothing.

.EXAMPLE
    .\run_unreal.ps1 -Script build_test_scene -Editor
    .\run_unreal.ps1 -Script verify_scene

.NOTES
    Exit codes: 0 ok, 1 script failed, 2 setup error, 3 editor already running.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Script,
    [string] $Params = '',
    [string] $Project = '',
    [string] $EngineRoot = '',
    # Full editor (real RHI + a world that can render). Needed for screenshots.
    # Without it: headless UnrealEditor-Cmd commandlet with -NullRHI.
    [switch] $Editor,
    [switch] $AllowEditorRunning,
    [int] $TimeoutSeconds = 3600
)

$ErrorActionPreference = 'Stop'
$ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogsDir = Join-Path $ToolsDir 'logs'
$ConfigFile = Join-Path $ToolsDir 'unreal_config.json'

function Fail { param([string] $Message, [int] $Code = 2)
    Write-Host "ERROR: $Message" -ForegroundColor Red; exit $Code }

# ---------------------------------------------------------------- config ----
$Config = [pscustomobject]@{}
if (Test-Path $ConfigFile) {
    try { $Config = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json }
    catch { Fail "unreal_config.json is not valid JSON: $($_.Exception.Message)" }
}
function Get-ConfigValue { param([string] $Name)
    $prop = $Config.PSObject.Properties[$Name]
    if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
    return [string] $prop.Value
}

# --------------------------------------------------------------- project ----
function Resolve-ProjectFile {
    foreach ($candidate in @($Project, $env:UE_PROJECT_FILE, (Get-ConfigValue 'project_file'))) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $resolved = $candidate
        if (-not [System.IO.Path]::IsPathRooted($resolved)) { $resolved = Join-Path $ToolsDir $resolved }
        $resolved = [System.IO.Path]::GetFullPath($resolved)
        if (Test-Path -PathType Leaf $resolved) { return $resolved }
        Fail "configured project file does not exist: $resolved"
    }
    # Nearest .uproject searching upward from Tools/Unreal.
    $dir = Get-Item $ToolsDir
    while ($null -ne $dir) {
        $found = @(Get-ChildItem -Path $dir.FullName -Filter '*.uproject' -File -ErrorAction SilentlyContinue)
        if ($found.Count -eq 1) { return $found[0].FullName }
        if ($found.Count -gt 1) { Fail "several .uproject files in $($dir.FullName); pass -Project" }
        $dir = $dir.Parent
    }
    Fail 'no .uproject found above Tools/Unreal; pass -Project'
}

# ---------------------------------------------------------------- engine ----
function Test-EngineRoot { param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    return Test-Path -PathType Leaf (Join-Path $Path 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') }

function Resolve-EngineRoot { param([string] $ProjectFile)
    foreach ($candidate in @($EngineRoot, $env:UE_ENGINE_ROOT, (Get-ConfigValue 'engine_root'))) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $normalized = $candidate.Replace('/', '\').TrimEnd('\')
        if (Test-EngineRoot $normalized) { return $normalized }
        Fail "no UnrealEditor-Cmd.exe under configured engine root: $normalized"
    }

    # From the .uproject's EngineAssociation: a GUID is a registered build,
    # a version string like "5.8" is a Launcher install.
    try { $association = [string] (Get-Content -Raw -Path $ProjectFile | ConvertFrom-Json).EngineAssociation }
    catch { $association = '' }

    if ($association -match '^\{.*\}$') {
        $key = 'HKCU:\SOFTWARE\Epic Games\Unreal Engine\Builds'
        if (Test-Path $key) {
            $prop = (Get-ItemProperty -Path $key).PSObject.Properties[$association]
            if ($null -ne $prop) {
                $candidate = ([string] $prop.Value).Replace('/', '\')
                if (Test-EngineRoot $candidate) { return $candidate }
            }
        }
    } elseif (-not [string]::IsNullOrWhiteSpace($association)) {
        $key = "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$association"
        if (Test-Path $key) {
            $candidate = (Get-ItemProperty -Path $key).InstalledDirectory
            if (Test-EngineRoot $candidate) { return $candidate }
        }
        # Recent Launcher versions register engines only in LauncherInstalled.dat,
        # not under HKLM per-version keys.
        $manifest = Join-Path $env:ProgramData 'Epic\UnrealEngineLauncher\LauncherInstalled.dat'
        if (Test-Path $manifest) {
            try {
                foreach ($entry in (Get-Content -Raw -Path $manifest | ConvertFrom-Json).InstallationList) {
                    if ($entry.AppName -ne "UE_$association") { continue }
                    if (Test-EngineRoot $entry.InstallLocation) { return $entry.InstallLocation }
                }
            } catch { }
        }
    }

    # Last resort: highest UE_x.y under the search roots.
    $roots = @()
    $configured = $Config.PSObject.Properties['engine_search_roots']
    if ($null -ne $configured -and $null -ne $configured.Value) { $roots += @($configured.Value) }
    $roots += @((Join-Path $env:ProgramFiles 'Epic Games'), 'C:\Program Files\Epic Games')
    $best = ''; $bestVersion = [version]'0.0'
    foreach ($root in $roots) {
        if ([string]::IsNullOrWhiteSpace($root)) { continue }
        $root = $root.Replace('/', '\')
        if (-not (Test-Path $root)) { continue }
        foreach ($dir in Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue) {
            if ($dir.Name -notmatch '^UE_(\d+)\.(\d+)') { continue }
            if (-not (Test-EngineRoot $dir.FullName)) { continue }
            $version = [version]("$($Matches[1]).$($Matches[2])")
            if ($version -gt $bestVersion) { $bestVersion = $version; $best = $dir.FullName }
        }
    }
    if (Test-EngineRoot $best) { return $best }
    Fail 'could not locate an Unreal Engine install; pass -EngineRoot'
}

# ---------------------------------------------------------------- script ----
function Resolve-ScriptPath {
    if (Test-Path -PathType Leaf $Script) { return (Resolve-Path $Script).Path }
    $name = $Script
    if (-not $name.EndsWith('.py')) { $name = "$name.py" }
    $inScripts = Join-Path (Join-Path $ToolsDir 'scripts') $name
    if (Test-Path -PathType Leaf $inScripts) { return $inScripts }
    $available = @(Get-ChildItem -Path (Join-Path $ToolsDir 'scripts') -Filter '*.py' -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.BaseName }) -join ', '
    Fail "script '$Script' not found. Available: $available"
}

# -------------------------------------------------------------- resolve -----
$ProjectFile = Resolve-ProjectFile
$ProjectDir = Split-Path -Parent $ProjectFile
$EngineRootResolved = Resolve-EngineRoot -ProjectFile $ProjectFile
$ScriptPath = Resolve-ScriptPath
if ([string]::IsNullOrWhiteSpace($Params)) { $Params = '{}' }
else { try { $null = $Params | ConvertFrom-Json } catch { Fail "-Params is not valid JSON" } }

$running = @(Get-Process -Name 'UnrealEditor' -ErrorAction SilentlyContinue)
if ($running.Count -gt 0 -and -not $AllowEditorRunning) {
    Fail 'UnrealEditor.exe is already running. Close it first, or pass -AllowEditorRunning.' 3
}

if (-not (Test-Path $LogsDir)) { $null = New-Item -ItemType Directory -Path $LogsDir -Force }
$scriptName = [System.IO.Path]::GetFileNameWithoutExtension($ScriptPath)
$RunId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $scriptName
$UnrealLog  = Join-Path $LogsDir "$RunId.unreal.log"
$StdOutFile = Join-Path $LogsDir "$RunId.stdout.log"
$StdErrFile = Join-Path $LogsDir "$RunId.stderr.log"
$ResultFile = Join-Path $LogsDir "$RunId.result.json"

# --------------------------------------------------------------- command ----
# Built as one verbatim string: Unreal needs the quotes INSIDE the -script= /
# -abslog= tokens, which PowerShell's own argument quoting would break.
if ($Editor) {
    $Exe = Join-Path $EngineRootResolved 'Engine\Binaries\Win64\UnrealEditor.exe'
    # -ExecCmds="py <file>" rather than -ExecutePythonScript: the latter quits
    # the editor the moment the script returns, which kills any tick-driven
    # work (screenshots, streaming). Scripts run this way must call
    # unreal.SystemLibrary.quit_editor() themselves.
    $argList = @(('"{0}"' -f $ProjectFile), ('-ExecCmds="py {0}"' -f $ScriptPath))
} else {
    $Exe = Join-Path $EngineRootResolved 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
    $argList = @(('"{0}"' -f $ProjectFile), '-run=pythonscript', ('-script="{0}"' -f $ScriptPath), '-NullRHI')
}
$argList += @('-unattended', '-nopause', '-nosplash', '-nosound', '-stdout',
              '-FullStdOutLogOutput', '-AllowStdOutLogVerbosity',
              '-LogCmds="LogPython Verbose"', ('-abslog="{0}"' -f $UnrealLog))

# Context reaches the script through environment variables, not argv: Unreal's
# -script= handling mangles extra quoted arguments.
$env:UE_TOOLS_DIR = $ToolsDir
$env:UE_PROJECT_FILE = $ProjectFile
$env:UE_PROJECT_DIR = $ProjectDir
$env:UE_ENGINE_ROOT = $EngineRootResolved
$env:UE_RUN_ID = $RunId
$env:UE_RESULT_FILE = $ResultFile
$env:UE_AUTOMATION_PARAMS_JSON = $Params

$modeLabel = if ($Editor) { 'full editor' } else { 'headless commandlet' }
Write-Host "engine : $EngineRootResolved"
Write-Host "project: $ProjectFile"
Write-Host "script : $ScriptPath  ($modeLabel)"
Write-Host "run id : $RunId"
Write-Host 'running unreal...' -ForegroundColor Cyan

$startedAt = Get-Date
$process = Start-Process -FilePath $Exe -ArgumentList ($argList -join ' ') `
    -NoNewWindow -PassThru -RedirectStandardOutput $StdOutFile -RedirectStandardError $StdErrFile
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    try { $process.Kill() } catch { }
    Fail "unreal did not finish within $TimeoutSeconds s (killed). Log: $UnrealLog"
}
$elapsed = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
Write-Host "unreal exited with code $($process.ExitCode) after ${elapsed}s" -ForegroundColor Cyan

# ---------------------------------------------------------------- result ----
$result = $null
if (Test-Path $ResultFile) {
    try { $result = Get-Content -Raw -Path $ResultFile | ConvertFrom-Json } catch { }
}
if ($null -eq $result) {
    Write-Host 'ERROR: no result payload; the script may have crashed before running.' -ForegroundColor Red
}
else {
    Get-Content -Raw -Path $ResultFile | Write-Output
}

if ($null -ne $result -and $result.status -eq 'ok') {
    Write-Host "OK ($($result.duration_seconds)s)" -ForegroundColor Green
    exit 0
}

# Failure: surface the interesting log lines instead of a 100k-line log.
if ($null -ne $result) {
    foreach ($err in $result.errors) { Write-Host "  $err" -ForegroundColor Red }
    if ($result.traceback) { Write-Host $result.traceback -ForegroundColor DarkRed }
}
foreach ($file in @($StdErrFile, $UnrealLog)) {
    if (-not (Test-Path $file)) { continue }
    $lines = @(Select-String -Path $file -Pattern 'Error:|LogPython|Traceback' -ErrorAction SilentlyContinue |
        Select-Object -Last 30)
    if ($lines.Count -eq 0) { continue }
    Write-Host "--- $([System.IO.Path]::GetFileName($file)) ---" -ForegroundColor Yellow
    foreach ($line in $lines) { Write-Host "  $($line.Line)" }
}
Write-Host "full log: $UnrealLog" -ForegroundColor Yellow
if ($null -eq $result) { exit 2 }
exit 1
