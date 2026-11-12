#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectPath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$createdNewRepository = $false
$script:ExpectedOrigin = 'https://github.com/Deadexp/coursework-tp-2026.git'

function Invoke-ProjectGit {
    param([string[]]$Arguments, [switch]$Capture)
    # PS 5.1 treats native stderr as ErrorRecord objects. Git writes normal progress
    # to stderr, so decide success from the exit code, not from the output stream.
    $savedPreference = $ErrorActionPreference
    $savedEncoding = [Console]::OutputEncoding
    try {
        $ErrorActionPreference = 'Continue'
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $lines = @(& $script:GitExecutable -C $script:ProjectRoot @Arguments 2>&1)
        $gitExitCode = $LASTEXITCODE
    }
    finally {
        [Console]::OutputEncoding = $savedEncoding
        $ErrorActionPreference = $savedPreference
    }
    if ($gitExitCode -ne 0) {
        foreach ($line in $lines) { Write-Host ([string]$line) }
        throw ('git ' + $Arguments[0] + ' failed with exit code ' + $gitExitCode + '.')
    }
    if ($Capture) {
        foreach ($line in $lines) { Write-Output ([string]$line) }
    }
    else {
        foreach ($line in $lines) { Write-Host ([string]$line) }
    }
}

function Assert-ProjectGitRoot {
    $top = (@(Invoke-ProjectGit -Arguments @('rev-parse', '--show-toplevel') -Capture) -join '').Trim()
    $fullTop = [System.IO.Path]::GetFullPath($top).TrimEnd([char[]]'\/')
    if (-not $fullTop.Equals($script:ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Git belongs to another directory. No reset or branch switch was performed.'
    }
}

try {
    foreach ($name in @('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY')) {
        if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($name))) {
            throw ('An environment override is set: ' + $name + '. Use a normal PowerShell session.')
        }
    }
    $project = Get-Item -LiteralPath $ProjectPath -Force
    if (-not $project.PSIsContainer) { throw 'ProjectPath must be a directory.' }
    if ($null -eq [System.IO.Directory]::GetParent($project.FullName) -or
        ($project.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Choose a normal project directory, not a drive root, junction, or symbolic link.'
    }
    $script:ProjectRoot = [System.IO.Path]::GetFullPath($project.FullName).TrimEnd([char[]]'\/')
    if (-not [System.IO.File]::Exists([System.IO.Path]::Combine($script:ProjectRoot, 'docker-compose.yml')) -or
        -not [System.IO.Directory]::Exists([System.IO.Path]::Combine($script:ProjectRoot, 'backend')) -or
        -not [System.IO.Directory]::Exists([System.IO.Path]::Combine($script:ProjectRoot, 'frontend'))) {
        throw 'Select the project root containing docker-compose.yml, backend, and frontend.'
    }
    $packageRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([char[]]'\/')
    $manifestPath = [System.IO.Path]::Combine($packageRoot, 'manifest.json')
    if (-not [System.IO.File]::Exists($manifestPath)) {
        throw 'Run this script from the extracted update ZIP, next to manifest.json.'
    }
    foreach ($path in @($packageRoot, $manifestPath)) {
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The update directory or manifest is a symbolic link or junction. It was not used.'
        }
    }
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $manifest = $utf8.GetString([System.IO.File]::ReadAllBytes($manifestPath)).TrimStart([char]0xFEFF) |
        ConvertFrom-Json
    $baseCommit = $manifest.base_commit
    if ($baseCommit -isnot [string] -or $baseCommit -notmatch '^[0-9a-fA-F]{7,40}$') {
        throw 'manifest.json contains an invalid base_commit.'
    }
    $gitCommand = Get-Command git -CommandType Application -ErrorAction Stop
    $script:GitExecutable = $gitCommand.Source
    $gitMarker = [System.IO.Path]::Combine($script:ProjectRoot, '.git')
    if (Test-Path -LiteralPath $gitMarker) {
        $marker = Get-Item -LiteralPath $gitMarker -Force
        if (($marker.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The .git path is a symbolic link or junction. It was not used.'
        }
        Assert-ProjectGitRoot
        # A previous interrupted init is not permission to reset an existing repository.
        [void](Invoke-ProjectGit -Arguments @('rev-parse', '--verify', 'HEAD') -Capture)
    }
    else {
        # Explicit init in ProjectRoot creates its own .git even inside a parent repository.
        Invoke-ProjectGit -Arguments @('init', $script:ProjectRoot)
        if (-not [System.IO.Directory]::Exists($gitMarker)) {
            throw 'Git did not create a repository in the selected project directory.'
        }
        $createdNewRepository = $true
        Assert-ProjectGitRoot
    }

    $remotes = @(Invoke-ProjectGit -Arguments @('remote') -Capture)
    if ($remotes -contains 'origin') {
        $origin = (@(Invoke-ProjectGit -Arguments @('remote', 'get-url', 'origin') -Capture) -join '').Trim()
        $allowedOrigins = @(
            $script:ExpectedOrigin,
            'https://github.com/Deadexp/coursework-tp-2026',
            'git@github.com:Deadexp/coursework-tp-2026.git',
            'git@github.com:Deadexp/coursework-tp-2026'
        )
        if ($allowedOrigins -inotcontains $origin) {
            throw 'Existing origin points to a different repository. It was not changed.'
        }
    }
    else {
        Invoke-ProjectGit -Arguments @('remote', 'add', 'origin', $script:ExpectedOrigin)
    }
    Invoke-ProjectGit -Arguments @('fetch', 'origin', 'main')

    if ($createdNewRepository) {
        $resolvedBase = (@(Invoke-ProjectGit -Arguments @('rev-parse', '--verify', ($baseCommit + '^{commit}')) -Capture) -join '').Trim()
        Invoke-ProjectGit -Arguments @('merge-base', '--is-ancestor', $resolvedBase, 'refs/remotes/origin/main')
        # Only this invocation's newly created repository may have its index reset.
        # --mixed leaves all existing working files in place.
        Invoke-ProjectGit -Arguments @('reset', '--mixed', $resolvedBase)
    }

    $names = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($name in @(Invoke-ProjectGit -Arguments @('for-each-ref', '--format=%(refname:short)', 'refs/heads/') -Capture)) {
        [void]$names.Add($name.Trim())
    }
    $current = (@(Invoke-ProjectGit -Arguments @('branch', '--show-current') -Capture) -join '').Trim()
    if ($current) { [void]$names.Add($current) }
    $branch = 'feature/coursework-completion'
    if ($names.Contains($branch)) {
        $prefix = $branch + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        $branch = $prefix
        $suffix = 1
        while ($names.Contains($branch)) {
            $branch = $prefix + '-' + $suffix
            $suffix++
        }
    }
    Assert-ProjectGitRoot
    Invoke-ProjectGit -Arguments @('switch', '-c', $branch)
    Write-Host ('Prepared branch: ' + $branch)
    Write-Host 'Working files were kept. Nothing was staged, committed, or pushed.'
    Write-Host 'Review git status and the diff before your own commit and push.'
}
catch {
    Write-Host ('Git preparation stopped: ' + $_.Exception.Message)
    if ($createdNewRepository) {
        Write-Host 'This invocation created .git. Working files were not checked out or deleted.'
        Write-Host 'Do not delete it or force-reset an existing repository to bypass an error.'
    }
    Write-Host 'No automatic commit, push, stash, force checkout, or user configuration was performed.'
    exit 1
}
