param(
    [string]$Version = "2026.09.25"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$distRoot = Join-Path $projectRoot "dist"
$packageName = "AMAT_System_Matcher_$Version"
$stageRoot = Join-Path $distRoot $packageName
$zipPath = Join-Path $distRoot "$packageName.zip"

if (Test-Path -LiteralPath $stageRoot) {
    throw "Release staging folder already exists: $stageRoot"
}
if (Test-Path -LiteralPath $zipPath) {
    throw "Release ZIP already exists: $zipPath"
}

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

$files = @(
    "app.py",
    "README.md",
    "RELEASE_NOTES.md",
    "REQUIREMENTS.md",
    "requirements.txt",
    "setup.bat",
    "start_server.bat",
    "run_workbench.bat",
    ".env.example",
    "System_Type_WD_Template_Mapping.xlsx"
)

foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $stageRoot
}

$sourcePackage = Join-Path $projectRoot "system_type_identifier"
$targetPackage = Join-Path $stageRoot "system_type_identifier"
New-Item -ItemType Directory -Path $targetPackage -Force | Out-Null
Get-ChildItem -LiteralPath $sourcePackage -File -Filter "*.py" |
    Copy-Item -Destination $targetPackage

$sourceTests = Join-Path $projectRoot "tests"
$targetTests = Join-Path $stageRoot "tests"
New-Item -ItemType Directory -Path $targetTests -Force | Out-Null
Get-ChildItem -LiteralPath $sourceTests -File -Filter "*.py" |
    Copy-Item -Destination $targetTests

$hashLines = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($stageRoot.Length + 1)
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    "$hash  $relative"
}
Set-Content -LiteralPath (Join-Path $stageRoot "SHA256SUMS.txt") -Value $hashLines -Encoding UTF8

Compress-Archive -LiteralPath $stageRoot -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Release created: $zipPath"
