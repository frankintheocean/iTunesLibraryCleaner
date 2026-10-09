param([Parameter(Mandatory=$true)][string]$InstallerPath)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw 'Select the original installer executable for this version.' }
if (Get-Process -Name 'Unified iTunes Library Manager','library-backend' -ErrorAction SilentlyContinue) { throw 'Close Library Manager and both legacy tools before repairing.' }
$Process = Start-Process -FilePath (Resolve-Path -LiteralPath $InstallerPath) -Wait -PassThru
if ($Process.ExitCode -ne 0) { throw "Installer exited with $($Process.ExitCode)." }
Write-Host 'Repair/reinstallation completed. User data and music are preserved.'
