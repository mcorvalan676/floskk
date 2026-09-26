param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("dev", "deploy", "dry-run")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$WranglerArgs
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is required to keep the uv environment outside the Worker bundle."
}

$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA "ConectaTalento\uv-env"
$python = (Get-Command python -ErrorAction Stop).Source
& $python -m uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE."
}

& $python -m uv run pywrangler sync
if ($LASTEXITCODE -ne 0) {
    throw "PyWrangler dependency sync failed with exit code $LASTEXITCODE."
}

$temporaryRoot = Join-Path $env:TEMP ("conectatalento-wrangler-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
$movedDirectories = @()

try {
    foreach ($directoryName in @(".venv", ".venv-workers")) {
        $source = Join-Path $projectRoot $directoryName
        if (Test-Path -LiteralPath $source) {
            $destination = Join-Path $temporaryRoot $directoryName
            Move-Item -LiteralPath $source -Destination $destination
            $movedDirectories += [pscustomobject]@{
                Source = $source
                Destination = $destination
            }
        }
    }

    $npx = (Get-Command npx.cmd -ErrorAction Stop).Source
    if ($Command -eq "dry-run") {
        & $npx --yes wrangler deploy --dry-run @WranglerArgs
    }
    else {
        & $npx --yes wrangler $Command @WranglerArgs
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Wrangler $Command failed with exit code $LASTEXITCODE."
    }
}
finally {
    foreach ($directory in $movedDirectories) {
        if (Test-Path -LiteralPath $directory.Destination) {
            if (Test-Path -LiteralPath $directory.Source) {
                throw "Cannot restore $($directory.Source): the path was recreated during the Wrangler command."
            }
            Move-Item -LiteralPath $directory.Destination -Destination $directory.Source
        }
    }

    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot
    }
}
