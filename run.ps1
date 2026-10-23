param(
    [ValidateSet('extract', 'validate', 'build', 'check', 'install', 'restore', 'test')]
    [string]$Command = 'check',
    [string]$GamePath = 'C:\Program Files (x86)\Steam\steamapps\common\Silver Pines',
    [string]$OutputPath = '',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCommand -and $pythonCommand.Source -notlike '*\WindowsApps\*') {
    $pythonCandidates += $pythonCommand.Source
}
$pythonExecutable = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonExecutable) { throw 'Python 3.10 이상을 설치하고 requirements.txt의 의존성을 설치하세요.' }

$previousPythonPath = $env:PYTHONPATH
$previousEncoding = $env:PYTHONIOENCODING
Push-Location -LiteralPath $projectRoot
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $localDependencies = Join-Path $projectRoot '.tools\pydeps'
    if (Test-Path -LiteralPath $localDependencies) {
        $env:PYTHONPATH = $localDependencies
    }
    if (-not $OutputPath) { $OutputPath = Join-Path $projectRoot 'artifacts\full-ko-v1' }
    switch ($Command) {
        'test' { $pythonArguments = @('-m', 'unittest', 'discover', '-s', 'test', '-v') }
        'extract' { $pythonArguments = @('-m', 'tool.patch', 'extract', '--game', $GamePath) }
        'validate' { $pythonArguments = @('-m', 'tool.patch', 'validate', '--game', $GamePath) }
        'build' { $pythonArguments = @('-m', 'tool.patch', 'build', '--game', $GamePath, '--output', $OutputPath) }
        'check' { $pythonArguments = @('-m', 'tool.install', '--game', $GamePath, '--patch', $OutputPath) }
        'install' {
            $pythonArguments = @('-m', 'tool.install', '--game', $GamePath, '--patch', $OutputPath)
            if ($Apply) { $pythonArguments += '--apply' }
        }
        'restore' {
            $pythonArguments = @('-m', 'tool.install', '--game', $GamePath, '--restore')
            if ($Apply) { $pythonArguments += '--apply' }
        }
    }
    & $pythonExecutable @pythonArguments
    if ($LASTEXITCODE -ne 0) { throw "작업 실패: 종료 코드 $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONIOENCODING = $previousEncoding
    Pop-Location
}
