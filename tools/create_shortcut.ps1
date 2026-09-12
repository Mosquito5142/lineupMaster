$rootDir = (Resolve-Path "$PSScriptRoot\..").Path
$targetBat = Join-Path $rootDir "run.bat"
$iconPath = Join-Path $rootDir "assets\icon.ico"
$wsh = New-Object -ComObject WScript.Shell

# 1. Create shortcut in project root
$shortcutPath = Join-Path $rootDir "LineupMaster.lnk"
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetBat
$shortcut.WorkingDirectory = $rootDir
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "LineupMaster - Valorant Lineup Assistant"
$shortcut.Save()
Write-Host "[OK] Created shortcut in project folder: $shortcutPath" -ForegroundColor Green

# 2. Create shortcut on Desktop as well
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktop "LineupMaster.lnk"
$desktopShortcut = $wsh.CreateShortcut($desktopShortcutPath)
$desktopShortcut.TargetPath = $targetBat
$desktopShortcut.WorkingDirectory = $rootDir
$desktopShortcut.IconLocation = "$iconPath,0"
$desktopShortcut.Description = "LineupMaster - Valorant Lineup Assistant"
$desktopShortcut.Save()
Write-Host "[OK] Created shortcut on Desktop: $desktopShortcutPath" -ForegroundColor Green
