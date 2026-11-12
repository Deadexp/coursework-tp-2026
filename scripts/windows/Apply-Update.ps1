#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectPath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$backupRoot = $null
$copyStarted = $false

function Get-NormalizedHash {
    param([string]$LiteralPath)
    $text = $script:Utf8.GetString([System.IO.File]::ReadAllBytes($LiteralPath))
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
        $text = $text.Substring(1)
    }
    $text = $text.Replace("`r`n", "`n")
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $algorithm.ComputeHash($script:Utf8.GetBytes($text))
        return ([System.BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

function Get-ChildPath {
    param([string]$Root, [string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        [System.IO.Path]::IsPathRooted($RelativePath) -or
        $RelativePath.Contains('\') -or $RelativePath.Contains(':')) {
        throw 'Manifest paths must be relative paths using forward slashes.'
    }
    foreach ($part in $RelativePath.Split('/')) {
        if ([string]::IsNullOrWhiteSpace($part) -or $part -eq '.' -or $part -eq '..' -or
            $part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$') {
            throw 'Manifest contains an unsafe Windows path.'
        }
        if ($part -ieq '.git' -or $part -ieq 'docker-compose.yml' -or
            $part -ieq '.env' -or
            (($part -ilike '.env.*') -and ($part -ine '.env.example'))) {
            throw 'Manifest must not contain Git metadata, local environment files, or docker-compose.yml.'
        }
    }
    $nativePath = $RelativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $fullPath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($Root, $nativePath))
    $prefix = $Root.TrimEnd([char[]]'\/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Manifest path leaves the selected directory.'
    }
    return $fullPath
}

function Assert-PlainPath {
    param([string]$Root, [string]$FullPath)
    # Do not follow junctions or symbolic links into a different folder.
    $paths = [System.Collections.Generic.List[string]]::new()
    $paths.Add($Root)
    $relative = $FullPath.Substring($Root.Length).TrimStart([char[]]'\/')
    $cursor = $Root
    foreach ($part in $relative.Split([System.IO.Path]::DirectorySeparatorChar)) {
        if ($part.Length -eq 0) { continue }
        $cursor = [System.IO.Path]::Combine($cursor, $part)
        $paths.Add($cursor)
    }
    foreach ($candidate in $paths) {
        $item = Get-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) { continue }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'A symbolic link or junction was found in an update path.'
        }
        if ($candidate -ne $FullPath -and -not $item.PSIsContainer) {
            throw 'An update parent path is a file, not a directory.'
        }
    }
}

try {
    $project = Get-Item -LiteralPath $ProjectPath -Force
    if (-not $project.PSIsContainer) { throw 'ProjectPath must be a directory.' }
    if ($null -eq [System.IO.Directory]::GetParent($project.FullName)) {
        throw 'Choose the project directory, not a drive root.'
    }
    $projectRoot = [System.IO.Path]::GetFullPath($project.FullName).TrimEnd([char[]]'\/')
    $parent = [System.IO.Directory]::GetParent($projectRoot)
    if ($null -eq $parent) { throw 'Choose the project directory, not a drive root.' }
    foreach ($required in @('backend', 'frontend')) {
        if (-not [System.IO.Directory]::Exists([System.IO.Path]::Combine($projectRoot, $required))) {
            throw ('Missing project directory: ' + $required)
        }
    }
    if (-not [System.IO.File]::Exists([System.IO.Path]::Combine($projectRoot, 'docker-compose.yml'))) {
        throw 'docker-compose.yml was not found. Select the existing project root.'
    }

    $packageRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([char[]]'\/')
    $manifestPath = [System.IO.Path]::Combine($packageRoot, 'manifest.json')
    $payloadRoot = [System.IO.Path]::Combine($packageRoot, 'files')
    Assert-PlainPath -Root $packageRoot -FullPath $manifestPath
    Assert-PlainPath -Root $packageRoot -FullPath $payloadRoot
    if (-not [System.IO.File]::Exists($manifestPath) -or
        -not [System.IO.Directory]::Exists($payloadRoot)) {
        throw 'Extract the update ZIP first. manifest.json and files must be next to this script.'
    }
    $manifest = $script:Utf8.GetString([System.IO.File]::ReadAllBytes($manifestPath)).TrimStart([char]0xFEFF) |
        ConvertFrom-Json
    if ($manifest.base_commit -isnot [string] -or
        $manifest.base_commit -notmatch '^[0-9a-fA-F]{7,40}$') {
        throw 'manifest.json contains an invalid base_commit.'
    }
    $entries = @($manifest.files)
    if ($entries.Count -eq 0) { throw 'manifest.json contains no files.' }
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $problems = [System.Collections.Generic.List[string]]::new()
    $plan = [System.Collections.Generic.List[object]]::new()
    $alreadyCurrent = 0

    foreach ($entry in $entries) {
        $relative = '<invalid entry>'
        try {
            foreach ($field in @('path', 'base_sha256', 'new_sha256')) {
                if ($entry.PSObject.Properties.Name -notcontains $field) {
                    throw ('Missing manifest field: ' + $field)
                }
            }
            if ($entry.path -isnot [string]) { throw 'Manifest path must be text.' }
            $relative = $entry.path
            $source = Get-ChildPath -Root $payloadRoot -RelativePath $relative
            $target = Get-ChildPath -Root $projectRoot -RelativePath $relative
            if (-not $seen.Add($target)) { throw 'Duplicate manifest path (case-insensitive).' }
            if ($entry.new_sha256 -isnot [string] -or $entry.new_sha256 -notmatch '^[0-9a-fA-F]{64}$') {
                throw 'Invalid new_sha256.'
            }
            if ($null -ne $entry.base_sha256 -and
                ($entry.base_sha256 -isnot [string] -or $entry.base_sha256 -notmatch '^[0-9a-fA-F]{64}$')) {
                throw 'Invalid base_sha256.'
            }
            Assert-PlainPath -Root $payloadRoot -FullPath $source
            Assert-PlainPath -Root $projectRoot -FullPath $target
            if (-not [System.IO.File]::Exists($source)) { throw 'Payload file is missing.' }
            if ((Get-NormalizedHash -LiteralPath $source) -ine $entry.new_sha256) {
                throw 'Payload hash does not match the manifest.'
            }
            if ([System.IO.Directory]::Exists($target)) { throw 'Destination is a directory.' }
            $exists = [System.IO.File]::Exists($target)
            $currentHash = $null
            if ($exists) {
                $currentHash = Get-NormalizedHash -LiteralPath $target
                if ($currentHash -ieq $entry.new_sha256) {
                    $alreadyCurrent++
                    continue
                }
                if ($null -eq $entry.base_sha256 -or $currentHash -ine $entry.base_sha256) {
                    throw 'Local changes conflict with this update; the file will not be overwritten.'
                }
            }
            elseif ($null -ne $entry.base_sha256) {
                throw 'A base file is missing locally; the deletion will not be overwritten.'
            }
            $plan.Add([pscustomobject]@{
                Relative = $relative
                Source = $source
                Target = $target
                Overwrite = $exists
                CurrentHash = $currentHash
                NewHash = $entry.new_sha256
            })
        }
        catch {
            $problems.Add($relative + ': ' + $_.Exception.Message)
        }
    }

    if ($problems.Count -gt 0) {
        Write-Host 'Preflight failed. No project files were copied:'
        foreach ($problem in $problems) { Write-Host ('  - ' + $problem) }
        exit 1
    }
    if ($plan.Count -eq 0) {
        Write-Host ('Already up to date: ' + $alreadyCurrent + ' files. No files were copied.')
        exit 0
    }

    $overwrites = @($plan | Where-Object { $_.Overwrite })
    if ($overwrites.Count -gt 0) {
        $backupName = 'coursework-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        $backupRoot = [System.IO.Path]::Combine($parent.FullName, $backupName)
        $suffix = 1
        while (Test-Path -LiteralPath $backupRoot) {
            $backupRoot = [System.IO.Path]::Combine($parent.FullName, $backupName + '-' + $suffix)
            $suffix++
        }
        [void][System.IO.Directory]::CreateDirectory($backupRoot)
        # Complete every backup before the first destination is changed.
        foreach ($item in $overwrites) {
            Assert-PlainPath -Root $projectRoot -FullPath $item.Target
            if ((Get-NormalizedHash -LiteralPath $item.Target) -ine $item.CurrentHash) {
                throw ('A file changed after preflight: ' + $item.Relative)
            }
            $backupPath = Get-ChildPath -Root $backupRoot -RelativePath $item.Relative
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($backupPath))
            [System.IO.File]::Copy($item.Target, $backupPath, $false)
            if ((Get-NormalizedHash -LiteralPath $backupPath) -ine $item.CurrentHash) {
                throw ('Backup verification failed: ' + $item.Relative)
            }
        }
        Write-Host ('Backup directory: ' + $backupRoot)
    }

    foreach ($item in $plan) {
        Assert-PlainPath -Root $payloadRoot -FullPath $item.Source
        Assert-PlainPath -Root $projectRoot -FullPath $item.Target
        if ((Get-NormalizedHash -LiteralPath $item.Source) -ine $item.NewHash) {
            throw ('A payload file changed after preflight: ' + $item.Relative)
        }
        if ($item.Overwrite) {
            if ((Get-NormalizedHash -LiteralPath $item.Target) -ine $item.CurrentHash) {
                throw ('A local file changed after preflight: ' + $item.Relative)
            }
        }
        elseif (Test-Path -LiteralPath $item.Target) {
            throw ('A new destination appeared after preflight: ' + $item.Relative)
        }
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($item.Target))
        $copyStarted = $true
        [System.IO.File]::Copy($item.Source, $item.Target, $item.Overwrite)
        if ((Get-NormalizedHash -LiteralPath $item.Target) -ine $item.NewHash) {
            throw ('Copied file verification failed: ' + $item.Relative)
        }
    }
    Write-Host ('Update applied: ' + $plan.Count + ' files; already current: ' + $alreadyCurrent + '.')
    Write-Host 'Local environment files and docker-compose.yml were not read or changed.'
    Write-Host 'Docker and Git were not run. Keep the backup until you verify the update.'
}
catch {
    Write-Host ('Update stopped: ' + $_.Exception.Message)
    if ($copyStarted) {
        Write-Host 'Some files may already have been copied. Do not delete the backup.'
        Write-Host 'Resolve the reported problem before trying again; identical updated files are skipped.'
    }
    else {
        Write-Host 'No update files were copied into the project.'
    }
    if ($null -ne $backupRoot) { Write-Host ('Backup directory: ' + $backupRoot) }
    exit 1
}
