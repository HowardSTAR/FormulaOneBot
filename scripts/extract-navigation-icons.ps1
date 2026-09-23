param([Parameter(Mandatory = $true)][string]$Source)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$outputDirectory = Join-Path $PSScriptRoot '../front/src/assets/navigation'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$frames = @{
 home = @(269,143,103,102); calendar = @(406,143,103,102)
 results = @(544,143,103,102); peloton = @(682,143,103,102)
 analytics = @(820,143,103,102); wiki = @(958,143,103,102)
 account = @(269,305,103,102); notifications = @(406,305,103,102)
 contact = @(544,305,103,102); games = @(682,305,103,102)
 admin = @(820,305,103,102); vote = @(958,305,103,102)
 favorite = @(269,462,103,102); settings = @(406,462,103,102)
 practice = @(281,671,91,88); sprintQuali = @(417,671,91,88)
 sprint = @(552,671,91,88); quali = @(686,671,91,88); race = @(822,671,91,88)
 drivers = @(280,861,91,86); teams = @(416,861,91,86)
 compare = @(280,1032,91,86); predictions = @(416,1032,91,86)
 predictionAnalytics = @(551,1032,91,86)
 reaction = @(280,1212,91,87); grid = @(416,1212,91,87); arcade = @(551,1212,91,87)
}
$sourceImage = [System.Drawing.Bitmap]::FromFile((Resolve-Path -LiteralPath $Source))
try {
 if ($sourceImage.Width -ne 1122 -or $sourceImage.Height -ne 1402) { throw 'Expected 1122 x 1402 source artwork' }
 foreach ($name in $frames.Keys) {
  $frame = $frames[$name]
  $rectangle = [System.Drawing.Rectangle]::new($frame[0], $frame[1], $frame[2], $frame[3])
  $icon = $sourceImage.Clone($rectangle, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  try { $icon.Save((Join-Path $outputDirectory "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png) }
  finally { $icon.Dispose() }
 }
} finally { $sourceImage.Dispose() }
Write-Output "Extracted $($frames.Count) icons into $outputDirectory"
