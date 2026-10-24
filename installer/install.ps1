# SteamPACC: установка одной командой из консоли.
#
# В PowerShell выполните:
#     irm https://raw.githubusercontent.com/Stintik-123/SteamPACC/main/installer/install.ps1 | iex
#
# Скрипт скачивает SteamPACC.exe из последнего релиза GitHub, кладёт его
# в %LOCALAPPDATA%\SteamPACC, создаёт ярлык в меню «Пуск» и предлагает
# включить автозапуск. Работает без прав администратора.

$ErrorActionPreference = 'Stop'

$repo = 'Stintik-123/SteamPACC'
$installDir = Join-Path $env:LOCALAPPDATA 'SteamPACC'
$exePath = Join-Path $installDir 'SteamPACC.exe'

Write-Host 'SteamPACC: установка' -ForegroundColor Cyan
Write-Host "Каталог установки: $installDir"

# Ищем последнюю версию на GitHub Releases.
Write-Host 'Ищу последний релиз на GitHub...'
try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ 'User-Agent' = 'SteamPACC-Installer' }
} catch {
    Write-Host "Не удалось получить список релизов: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$asset = $release.assets | Where-Object { $_.name -eq 'SteamPACC.exe' } | Select-Object -First 1
if (-not $asset) {
    # Запасной путь: портативный архив, если отдельного exe в релизе нет.
    $asset = $release.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
}
if (-not $asset) {
    Write-Host 'В последнем релизе не найден файл SteamPACC.exe.' -ForegroundColor Red
    Write-Host "Скачайте вручную: $($release.html_url)"
    exit 1
}

Write-Host "Скачиваю $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) МБ)..."
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$tempFile = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tempFile `
    -Headers @{ 'User-Agent' = 'SteamPACC-Installer' }

if ($asset.name -like '*.zip') {
    Write-Host 'Распаковываю архив...'
    Expand-Archive -Path $tempFile -DestinationPath $installDir -Force
    Remove-Item $tempFile -Force
} else {
    Move-Item -Path $tempFile -Destination $exePath -Force
}

if (-not (Test-Path $exePath)) {
    Write-Host "Файл SteamPACC.exe не найден после распаковки: $installDir" -ForegroundColor Red
    exit 1
}

# Ярлык в меню «Пуск».
try {
    $startMenu = [Environment]::GetFolderPath('Programs')
    $shortcutPath = Join-Path $startMenu 'SteamPACC.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exePath
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Save()
    Write-Host 'Ярлык создан в меню «Пуск».'
} catch {
    Write-Host "Ярлык создать не удалось (не критично): $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'Готово! SteamPACC установлен.' -ForegroundColor Green
Write-Host "Запуск: $exePath"

$answer = Read-Host 'Включить автозапуск вместе с Windows? [y/N]'
if ($answer -match '^[YyДд]') {
    Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
        -Name 'SteamPACC' -Value "`"$exePath`" --autostart"
    Write-Host 'Автозапуск включён.'
}

$answer = Read-Host 'Запустить SteamPACC сейчас? [Y/n]'
if ($answer -notmatch '^[NnН]') {
    Start-Process -FilePath $exePath
}
