$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$project = Split-Path $PSScriptRoot -Parent
$source = Join-Path $project 'front/src/assets/navigation'
$target = Join-Path $project 'app/assets/navigation'
$archivePath = Join-Path $project 'app-assets.zip'
$icons = @(Get-ChildItem -LiteralPath $source -Filter '*.png' -File)
if ($icons.Count -ne 27) { throw 'Expected all 27 navigation icons' }
$temporary = Join-Path $project ('.app-assets-navigation-' + [guid]::NewGuid() + '.tmp.zip')
Copy-Item -LiteralPath $archivePath -Destination $temporary
function Get-EntryHash($entry) {
 $stream = $entry.Open()
 $sha = [Security.Cryptography.SHA256]::Create()
 try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
 finally { $sha.Dispose(); $stream.Dispose() }
}
$preserved = @{}
$zip = [IO.Compression.ZipFile]::Open($temporary, [IO.Compression.ZipArchiveMode]::Update)
try {
 foreach ($entry in $zip.Entries) {
  if (-not $entry.FullName.StartsWith('app/assets/navigation/')) {
   $preserved[$entry.FullName] = Get-EntryHash $entry
  }
 }
 foreach ($icon in $icons) {
  $entryName = 'app/assets/navigation/' + $icon.Name
  $existing = $zip.GetEntry($entryName)
  if ($existing) { $existing.Delete() }
  [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $icon.FullName, $entryName, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
 }
} finally { $zip.Dispose() }
$zip = [IO.Compression.ZipFile]::OpenRead($temporary)
try {
 foreach ($name in $preserved.Keys) {
  if ((Get-EntryHash $zip.GetEntry($name)) -ne $preserved[$name]) { throw "Changed existing entry: $name" }
 }
 foreach ($icon in $icons) {
  if ((Get-EntryHash $zip.GetEntry('app/assets/navigation/' + $icon.Name)) -ne (Get-FileHash -LiteralPath $icon.FullName -Algorithm SHA256).Hash) {
   throw "Icon verification failed: $($icon.Name)"
  }
 }
} finally { $zip.Dispose() }
# Keep the extracted tree in sync so scripts/pack_assets.sh retains the icons.
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($icon in $icons) { Copy-Item -LiteralPath $icon.FullName -Destination (Join-Path $target $icon.Name) }
$backup = Join-Path ([IO.Path]::GetTempPath()) ('f1hub-assets-backup-' + [guid]::NewGuid() + '.zip')
Copy-Item -LiteralPath $archivePath -Destination $backup
[IO.File]::Move($temporary, $archivePath, $true)
Write-Output "Packed $($icons.Count) icons; verified $($preserved.Count) preserved entries. Backup: $backup"
