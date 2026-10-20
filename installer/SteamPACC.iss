; Скрипт установщика SteamPACC (Inno Setup 6).
; Все тексты мастера — на русском языке.

#ifndef MyAppVersion
  #define MyAppVersion "0.1.3"
#endif
#define MyAppName "SteamPACC"
#define MyAppPublisher "Stintik-123"
#define MyAppURL "https://github.com/Stintik-123/SteamPACC"
#define MyAppExeName "SteamPACC.exe"

[Setup]
AppId={{7B1F5C8E-2C4A-4A1E-9E3D-2E9C4B8A7D31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SteamPACC-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
AppMutex=SteamPACC.SingleInstance
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
WelcomeLabel1=SteamPACC показывает цены игр в разных валютах прямо поверх клиента Steam.
WelcomeLabel2=Программа работает в трее и почти не влияет на производительность игр.
FinishedHeadingLabel=Установка завершена
FinishedLabel=SteamPACC установлен и уже запущен: окно-подсказка покажет, как им пользоваться.
FinishedLabelNoIcons=SteamPACC установлен и уже запущен: окно-подсказка покажет, как им пользоваться.
FinishedHint=Программа живёт в трее. Если значка не видно, нажмите стрелку ^ рядом с часами: там скрытые значки.

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные задачи:"
Name: "autostart"; Description: "Запускать SteamPACC вместе с Windows"; GroupDescription: "Дополнительные задачи:"

[Files]
Source: "..\dist\SteamPACC.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\USER_GUIDE.md"; DestDir: "{app}"; DestName: "Руководство.md"; Flags: ignoreversion
Source: "..\installer\diagnostika.cmd"; DestDir: "{app}"; DestName: "Диагностика.cmd"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{group}\Руководство"; Filename: "{app}\Руководство.md"
Name: "{group}\Диагностика"; Filename: "{app}\Диагностика.cmd"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Программа запускается сразу после установки, без флажка на странице
; "Готово": флажок postinstall по умолчанию снят, и программа не стартовала.
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
