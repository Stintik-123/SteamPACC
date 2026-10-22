; Скрипт установщика SteamPACC (Inno Setup 6).
; Все тексты мастера — на русском языке.
;
; Версию установщика можно задать при сборке, чтобы она совпадала
; с версией программы из src/steampacc/__init__.py:
;     ISCC /DMyAppVersion=0.1.5 installer\SteamPACC.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.6"
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
; {autopf} — это "Program Files" для всех пользователей, а если установка
; идёт без прав администратора — папка программ текущего пользователя
; (%LOCALAPPDATA%\Programs). Один каталог на оба случая.
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
; По умолчанию ставим без прав администратора, но пользователь может
; выбрать установку "для всех пользователей" (в Program Files).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
WelcomeLabel1=SteamPACC показывает цены игр в разных валютах прямо поверх клиента Steam.
WelcomeLabel2=Программа работает в трее и почти не влияет на производительность игр.

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные задачи:"
Name: "autostart"; Description: "Запускать SteamPACC вместе с Windows"; GroupDescription: "Дополнительные задачи:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\USER_GUIDE.md"; DestDir: "{app}"; DestName: "Руководство.md"; Flags: ignoreversion
Source: "..\installer\diagnostika.cmd"; DestDir: "{app}"; DestName: "Диагностика.cmd"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{group}\Руководство"; Filename: "{app}\Руководство.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Автозапуск для текущего пользователя: обычная установка.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: autostart; Check: not IsAdminInstallMode
; При установке для всех пользователей — общая ветка реестра.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: autostart; Check: IsAdminInstallMode

[Run]
Filename: "{cmd}"; Parameters: "/c start """"{app}\{#MyAppExeName}"""; Description: "Запустить {#MyAppName}"; Flags: nowait runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Закрываем запущенную программу, иначе файлы нельзя будет заменить.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(2000);
end;
