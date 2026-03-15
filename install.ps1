<#
.SYNOPSIS
Installs or updates ProContext from source on Windows.

.DESCRIPTION
Ensures git and uv are available, clones or refreshes a ProContext checkout,
syncs dependencies with uv, and optionally runs the one-time registry setup.
This is the canonical Windows installer entrypoint for ProContext.

.PARAMETER InstallDir
Directory for the managed ProContext source checkout.

.PARAMETER RepoUrl
Git repository URL to clone or refresh.

.PARAMETER InstallRef
Git branch, tag, or commit to install. Defaults to "main".
Can also be passed as `-Version` for compatibility with older installers.

.PARAMETER NoSetup
Skip the one-time `procontext setup` step.

.PARAMETER DryRun
Print the planned commands without executing them.
#>

param(
    [string]$InstallDir,
    [string]$RepoUrl,
    [Alias("Version")]
    [string]$InstallRef,
    [switch]$NoSetup,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:InstallDir = $InstallDir
$script:RepoUrl = $RepoUrl
$script:InstallRef = $InstallRef
$script:NoSetup = [bool]$NoSetup
$script:DryRun = [bool]$DryRun
$script:SetupStatus = "skipped"
$script:DefaultRepoUrl = "https://github.com/procontexthq/procontext.git"
$script:DefaultRef = "main"
$script:OriginalUserPath = [Environment]::GetEnvironmentVariable("Path", "User")

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Failure {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Kv {
    param(
        [string]$Label,
        [string]$Value
    )
    Write-Host ("  {0,-15} {1}" -f $Label, $Value) -ForegroundColor DarkGray
}

function Assert-SupportedPowerShell {
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Failure "PowerShell 5+ is required (found $($PSVersionTable.PSVersion))."
        Write-Failure "Update PowerShell and rerun this installer."
        exit 1
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    if ($DryRun) {
        Write-Host ("[dry-run] " + ($Command -join " ")) -ForegroundColor DarkCyan
        return
    }

    $exe = $Command[0]
    $args = @()
    if ($Command.Length -gt 1) {
        $args = $Command[1..($Command.Length - 1)]
    }

    & $exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
}

function Add-ToProcessPath {
    param([string]$PathEntry)

    if ([string]::IsNullOrWhiteSpace($PathEntry) -or -not (Test-Path $PathEntry)) {
        return
    }

    $entries = @($env:Path -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($entries | Where-Object { $_ -ieq $PathEntry }) {
        return
    }

    $env:Path = "$PathEntry;$env:Path"
}

function Add-ToUserPath {
    param([string]$PathEntry)

    if ([string]::IsNullOrWhiteSpace($PathEntry) -or -not (Test-Path $PathEntry)) {
        return
    }

    Add-ToProcessPath $PathEntry

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @("$userPath" -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($entries | Where-Object { $_ -ieq $PathEntry }) {
        return
    }

    if ($DryRun) {
        Write-Info "Would add $PathEntry to user PATH if needed"
        return
    }

    $newUserPath = $PathEntry
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $newUserPath = "$userPath;$PathEntry"
    }

    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Refresh-SystemPath
    Write-Info "Added $PathEntry to user PATH"
}

function Warn-UserPathMissing {
    param(
        [string]$PathEntry,
        [string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($PathEntry) -or -not (Test-Path $PathEntry)) {
        return
    }

    $entries = @("$script:OriginalUserPath" -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($entries | Where-Object { $_ -ieq $PathEntry }) {
        return
    }

    Write-Warn "PATH may be missing $Label ($PathEntry) in new PowerShell sessions."
    Write-Warn "Reopen PowerShell after install, or add it to the user PATH manually."
}

function Refresh-SystemPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pieces = @($env:Path, $userPath, $machinePath) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    }
    $env:Path = ($pieces -join ";")
}

function Refresh-UserBinPath {
    Add-ToProcessPath (Join-Path $HOME ".local\bin")
    Add-ToProcessPath (Join-Path $HOME ".cargo\bin")
}

function Invoke-ChocolateyRefresh {
    try {
        $chocoProfile = "$env:ChocolateyInstall\helpers\chocolateyProfile.psm1"
        if (Test-Path $chocoProfile) {
            Import-Module $chocoProfile -Force
            refreshenv | Out-Null
        }
    } catch {
    }
}

function Finalize-UvPath {
    $uvPath = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($uvPath)) {
        return
    }

    $uvBinDir = Split-Path -Parent $uvPath
    $userHome = [Environment]::GetFolderPath("UserProfile")
    if ($uvBinDir.StartsWith($userHome, [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-ToUserPath $uvBinDir
        Warn-UserPathMissing -PathEntry $uvBinDir -Label "uv"
    }
}

function Get-PortableGitRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        return (Join-Path $env:LOCALAPPDATA "ProContext\deps\portable-git")
    }
    return (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".procontext-portable-git")
}

function Get-PortableGitCommandPath {
    $root = Get-PortableGitRoot
    foreach ($candidate in @(
        (Join-Path $root "mingw64\bin\git.exe"),
        (Join-Path $root "cmd\git.exe"),
        (Join-Path $root "bin\git.exe"),
        (Join-Path $root "git.exe")
    )) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Use-PortableGitIfPresent {
    $gitExe = Get-PortableGitCommandPath
    if (-not $gitExe) {
        return $false
    }

    $portableRoot = Get-PortableGitRoot
    foreach ($pathEntry in @(
        (Join-Path $portableRoot "mingw64\bin"),
        (Join-Path $portableRoot "usr\bin"),
        (Split-Path -Parent $gitExe)
    )) {
        Add-ToProcessPath $pathEntry
    }

    return [bool](Get-Command git -ErrorAction SilentlyContinue)
}

function Get-DefaultInstallDir {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        return (Join-Path $env:LOCALAPPDATA "procontext-source")
    }
    return (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".procontext-source")
}

function Resolve-Configuration {
    $resolvedRepoUrl = $RepoUrl
    if ([string]::IsNullOrWhiteSpace($resolvedRepoUrl)) {
        $resolvedRepoUrl = [Environment]::GetEnvironmentVariable("PROCONTEXT_REPO_URL")
    }
    if ([string]::IsNullOrWhiteSpace($resolvedRepoUrl)) {
        $resolvedRepoUrl = $script:DefaultRepoUrl
    }
    $script:RepoUrl = $resolvedRepoUrl

    $resolvedInstallRef = $InstallRef
    if ([string]::IsNullOrWhiteSpace($resolvedInstallRef)) {
        $resolvedInstallRef = [Environment]::GetEnvironmentVariable("PROCONTEXT_INSTALL_REF")
    }
    if ([string]::IsNullOrWhiteSpace($resolvedInstallRef)) {
        $resolvedInstallRef = [Environment]::GetEnvironmentVariable("PROCONTEXT_VERSION")
    }
    if ([string]::IsNullOrWhiteSpace($resolvedInstallRef)) {
        $resolvedInstallRef = $script:DefaultRef
    }
    $script:InstallRef = $resolvedInstallRef

    $resolvedInstallDir = $InstallDir
    if ([string]::IsNullOrWhiteSpace($resolvedInstallDir)) {
        $resolvedInstallDir = [Environment]::GetEnvironmentVariable("PROCONTEXT_INSTALL_DIR")
    }
    if ([string]::IsNullOrWhiteSpace($resolvedInstallDir)) {
        $resolvedInstallDir = Get-DefaultInstallDir
    }
    $script:InstallDir = $resolvedInstallDir

    if (-not $PSBoundParameters.ContainsKey("NoSetup") -and
        [Environment]::GetEnvironmentVariable("PROCONTEXT_NO_SETUP") -eq "1") {
        $script:NoSetup = $true
    }
    if (-not $PSBoundParameters.ContainsKey("DryRun") -and
        [Environment]::GetEnvironmentVariable("PROCONTEXT_DRY_RUN") -eq "1") {
        $script:DryRun = $true
    }
}

function Resolve-PortableGitDownload {
    $releaseApi = "https://api.github.com/repos/git-for-windows/git/releases/latest"
    $headers = @{
        "User-Agent" = "procontext-installer"
        "Accept" = "application/vnd.github+json"
    }
    $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers
    if (-not $release -or -not $release.assets) {
        throw "Could not resolve the latest git-for-windows release metadata."
    }

    $asset = $release.assets |
        Where-Object { $_.name -match '^MinGit-.*-64-bit\.zip$' -and $_.name -notmatch 'busybox' } |
        Select-Object -First 1

    if (-not $asset) {
        throw "Could not find a MinGit zip asset in the latest git-for-windows release."
    }

    return @{
        Tag = $release.tag_name
        Name = $asset.name
        Url = $asset.browser_download_url
    }
}

function Install-PortableGit {
    if (Use-PortableGitIfPresent) {
        return
    }

    Write-Info "Git not found; bootstrapping user-local portable Git"

    $download = Resolve-PortableGitDownload
    $portableRoot = Get-PortableGitRoot
    $portableParent = Split-Path -Parent $portableRoot
    $tmpZip = Join-Path $env:TEMP $download.Name
    $tmpExtract = Join-Path $env:TEMP ("procontext-portable-git-" + [guid]::NewGuid().ToString("N"))

    New-Item -ItemType Directory -Force -Path $portableParent | Out-Null
    if (Test-Path $portableRoot) {
        Remove-Item -Recurse -Force $portableRoot
    }
    if (Test-Path $tmpExtract) {
        Remove-Item -Recurse -Force $tmpExtract
    }
    New-Item -ItemType Directory -Force -Path $tmpExtract | Out-Null

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $download.Url -OutFile $tmpZip
        Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force
        Move-Item -Path (Join-Path $tmpExtract "*") -Destination $portableRoot -Force
    } finally {
        if (Test-Path $tmpZip) {
            Remove-Item -Force $tmpZip
        }
        if (Test-Path $tmpExtract) {
            Remove-Item -Recurse -Force $tmpExtract
        }
    }

    if (-not (Use-PortableGitIfPresent)) {
        throw "Portable Git bootstrap completed, but git is still unavailable."
    }
}

function Print-Plan {
    Write-Host ""
    Write-Host "ProContext Installer" -ForegroundColor Cyan
    Write-Host ""
    Write-Kv "Source repo" $script:RepoUrl
    Write-Kv "Install dir" $script:InstallDir
    Write-Kv "Git ref" $script:InstallRef
    Write-Kv "Run setup" ($(if ($script:NoSetup) { "no" } else { "yes" }))
    Write-Kv "Dry run" ($(if ($script:DryRun) { "yes" } else { "no" }))
    Write-Host ""
}

function Ensure-Git {
    if (Use-PortableGitIfPresent) {
        $version = (& git --version)
        Write-Success "git already available: $version"
        return
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $version = (& git --version)
        Write-Success "git already available: $version"
        return
    }

    Write-Info "git not found; attempting installation"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Step -Command @(
            "winget", "install", "--id", "Git.Git", "-e", "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements"
        )
        Refresh-SystemPath
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        Invoke-Step -Command @("choco", "install", "git", "-y")
        Invoke-ChocolateyRefresh
        Refresh-SystemPath
    } elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
        Invoke-Step -Command @("scoop", "install", "git")
        Refresh-SystemPath
    }

    if ($DryRun) {
        Write-Success "git would be installed"
        return
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue) -and -not $DryRun) {
        try {
            Install-PortableGit
        } catch {
            Write-Warn "Portable Git bootstrap failed: $($_.Exception.Message)"
        }
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Failure "git is required to install ProContext from source."
        Write-Failure "Install it with `winget install Git.Git` or Git for Windows, then rerun."
        exit 1
    }

    $version = (& git --version)
    Write-Success "git ready: $version"
}

function Ensure-Uv {
    Refresh-SystemPath
    Refresh-UserBinPath
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Finalize-UvPath
        $version = (& uv --version)
        Write-Success "uv already available: $version"
        return
    }

    Write-Info "uv not found; attempting installation"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            Invoke-Step -Command @(
                "winget", "install", "--id", "Astral-sh.uv", "-e", "--source", "winget",
                "--accept-package-agreements", "--accept-source-agreements"
            )
            Refresh-SystemPath
            Refresh-UserBinPath
        } catch {
            Write-Warn "winget uv install failed; falling back to the official installer"
        }
        if ($DryRun) {
            Write-Success "uv would be installed"
            return
        }
    }

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        try {
            Invoke-Step -Command @("choco", "install", "uv", "-y")
            Invoke-ChocolateyRefresh
            Refresh-SystemPath
            Refresh-UserBinPath
        } catch {
            Write-Warn "Chocolatey uv install failed; falling back to the official installer"
        }
        if ($DryRun) {
            Write-Success "uv would be installed"
            return
        }
    }

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv -and (Get-Command scoop -ErrorAction SilentlyContinue)) {
        try {
            Invoke-Step -Command @("scoop", "install", "uv")
            Refresh-SystemPath
            Refresh-UserBinPath
        } catch {
            Write-Warn "scoop uv install failed; falling back to the official installer"
        }
        if ($DryRun) {
            Write-Success "uv would be installed"
            return
        }
    }

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Finalize-UvPath
        $version = (& uv --version)
        Write-Success "uv ready: $version"
        return
    }

    if ($DryRun) {
        Write-Host "[dry-run] download and run https://astral.sh/uv/install.ps1" -ForegroundColor DarkCyan
        Write-Success "uv would be installed"
        return
    }

    $tempScript = Join-Path $env:TEMP ("install-uv-" + [guid]::NewGuid().ToString("N") + ".ps1")
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $tempScript
        & powershell -NoProfile -ExecutionPolicy Bypass -File $tempScript
    } finally {
        if (Test-Path $tempScript) {
            Remove-Item -Force $tempScript
        }
    }

    Refresh-SystemPath
    Refresh-UserBinPath
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Failure "uv installation did not complete successfully."
        Write-Failure "Try https://docs.astral.sh/uv/getting-started/installation/ and rerun."
        exit 1
    }

    Finalize-UvPath
    $version = (& uv --version)
    Write-Success "uv ready: $version"
}

function Test-RepoDirty {
    $status = (& git -C $InstallDir status --porcelain 2>$null)
    return -not [string]::IsNullOrWhiteSpace(($status | Out-String).Trim())
}

function Validate-ExistingCheckout {
    $gitDir = Join-Path $InstallDir ".git"
    if (-not (Test-Path $gitDir)) {
        Write-Failure "$InstallDir exists but is not a git checkout."
        Write-Failure "Choose a different -InstallDir or remove the existing directory."
        exit 1
    }

    $pyprojectPath = Join-Path $InstallDir "pyproject.toml"
    if (-not (Test-Path $pyprojectPath)) {
        Write-Failure "$InstallDir does not look like a ProContext checkout."
        exit 1
    }
    if (-not (Select-String -Path $pyprojectPath -Pattern '^name = "procontext"$' -Quiet)) {
        Write-Failure "$InstallDir does not look like a ProContext checkout."
        exit 1
    }
}

function Update-CheckoutRef {
    param([bool]$FreshClone = $false)

    if (Test-RepoDirty) {
        Write-Warn "Checkout has local changes; skipping git update and using the existing files."
        return
    }

    try {
        Invoke-Step -Command @("git", "-C", $InstallDir, "fetch", "--tags", "origin")
    } catch {
        if ($FreshClone) {
            throw
        }
        Write-Warn "Git fetch failed; continuing with the existing checkout."
        return
    }

    & git -C $InstallDir ls-remote --exit-code --heads origin $InstallRef *> $null
    $isRemoteBranch = ($LASTEXITCODE -eq 0)

    try {
        Invoke-Step -Command @("git", "-C", $InstallDir, "checkout", $InstallRef)
        if ($isRemoteBranch) {
            Invoke-Step -Command @("git", "-C", $InstallDir, "pull", "--ff-only", "origin", $InstallRef)
        }
    } catch {
        if ($FreshClone) {
            throw
        }
        Write-Warn "Could not move the checkout to '$InstallRef'; continuing with the existing checkout."
    }
}

function Sync-Repo {
    $parentDir = Split-Path -Parent $InstallDir
    if (-not [string]::IsNullOrWhiteSpace($parentDir) -and -not (Test-Path $parentDir)) {
        if ($DryRun) {
            Write-Host "[dry-run] mkdir -p $parentDir" -ForegroundColor DarkCyan
        } else {
            New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
        }
    }

    if (-not (Test-Path $InstallDir)) {
        Write-Info "Cloning ProContext into $InstallDir"
        try {
            Invoke-Step -Command @("git", "clone", $RepoUrl, $InstallDir)
            Update-CheckoutRef -FreshClone $true
        } catch {
            Write-Failure "Failed to clone $RepoUrl."
            Write-Failure "Check network access and repository permissions, then rerun."
            exit 1
        }
        return
    }

    Validate-ExistingCheckout

    $originUrl = (& git -C $InstallDir remote get-url origin 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($originUrl) -and $originUrl -ne $RepoUrl) {
        Write-Warn "Existing checkout origin is '$originUrl', not '$RepoUrl'. Continuing anyway."
    }

    Write-Info "Refreshing existing checkout in $InstallDir"
    Update-CheckoutRef -FreshClone $false
}

function Run-UvSync {
    Write-Info "Syncing runtime dependencies with uv"
    try {
        Invoke-Step -Command @("uv", "sync", "--project", $script:InstallDir, "--no-dev")
        Write-Success "Runtime dependencies are synced"
    } catch {
        Write-Failure "uv sync failed, so the installation is not usable yet."
        Write-Failure "Fix the error above, then rerun this installer or run:"
        Write-Failure "  uv sync --project `"$script:InstallDir`" --no-dev"
        Write-Failure "If Python 3.12 is missing locally, uv should provision it automatically."
        exit 1
    }
}

function Run-RegistrySetup {
    if ($script:NoSetup) {
        $script:SetupStatus = "skipped"
        Write-Warn "Skipping one-time registry setup (-NoSetup)"
        return
    }

    Write-Info "Running one-time registry setup"
    try {
        Invoke-Step -Command @("uv", "run", "--project", $script:InstallDir, "procontext", "setup")
        $script:SetupStatus = "success"
        Write-Success "Initial registry setup completed"
    } catch {
        $script:SetupStatus = "failed"
        Write-Warn "ProContext is installed, but the initial registry setup did not finish."
        Write-Warn "Retry later with:"
        Write-Warn "  uv run --project `"$script:InstallDir`" procontext setup"
        Write-Warn "If the environment looks unwell, try:"
        Write-Warn "  uv run --project `"$script:InstallDir`" procontext doctor --fix"
    }
}

function Print-NextSteps {
    Write-Host ""
    Write-Host "ProContext is installed"
    Write-Host "  Source checkout: $script:InstallDir"
    Write-Host ""
    Write-Host "Run locally:"
    Write-Host "  uv run --project `"$script:InstallDir`" procontext"
    Write-Host ""
    Write-Host "Claude Code MCP config:"
    Write-Host "{"
    Write-Host '  "mcpServers": {'
    Write-Host '    "procontext": {'
    Write-Host '      "command": "uv",'
    Write-Host "      `"args`": [`"run`", `"--project`", `"$script:InstallDir`", `"procontext`"]"
    Write-Host "    }"
    Write-Host "  }"
    Write-Host "}"

    switch ($script:SetupStatus) {
        "skipped" {
            Write-Host ""
            Write-Host "One-time registry setup was skipped."
            Write-Host "Run this when you are ready:"
            Write-Host "  uv run --project `"$script:InstallDir`" procontext setup"
        }
        "failed" {
            Write-Host ""
            Write-Host "The code is installed, but the initial registry download still needs attention."
            Write-Host "Retry:"
            Write-Host "  uv run --project `"$script:InstallDir`" procontext setup"
            Write-Host ""
            Write-Host "If the environment looks off:"
            Write-Host "  uv run --project `"$script:InstallDir`" procontext doctor --fix"
        }
    }
}

Assert-SupportedPowerShell
Resolve-Configuration
Print-Plan
Ensure-Git
Ensure-Uv
Sync-Repo
Run-UvSync
Run-RegistrySetup
Print-NextSteps
