; SteamPACC Installer Script
; Inno Setup script for creating Windows installer
; Encoding: UTF-8

[Setup]
; Main installer settings
AppName=SteamPACC
AppVersion=0.1.5
AppPublisher=Stintik-123
AppPublisherURL=https://github.com/Stintik-123/SteamPACC
AppSupportURL=https://github.com/Stintik-123/SteamPACC/issues
AppUpdatesURL=https://github.com/Stintik-123/SteamPACC/releases
DefaultDirName={pf}\SteamPACC
DefaultGroupName=SteamPACC
OutputDir=..\dist
OutputBaseFilename=SteamPACC-Setup-{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
InternalCompressLevel=ultra64

; Language
[Languages]
Name: "russian"; MessagesFile: "compilator:Languages\Russian.isl"
Name: "english"; MessagesFile: "compilator:Languages\English.isl"

; Setup types
[Types]
Name: "full"; Description: "Full installation"
Name: "compact"; Description: "Compact installation"
Name: "custom"; Description: "Custom installation"; Flags: IsCustom

; Components
[Components]
Name: "main"; Description: "Main program"; Types: full compact custom; Flags: Fixed
Name: "desktop"; Description: "Desktop shortcut"; Types: full custom
Name: "startmenu"; Description: "Start Menu shortcut"; Types: full compact custom; Flags: Fixed
Name: "autostart"; Description: "Auto-start with Windows"; Types: full custom

; Files
[Files]
; Main executable
Source: "..\dist\SteamPACC.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "..\dist\SteamPACC-Console.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion

; License
Source: "..\LICENSE"; DestDir: "{app}"; Flags: isreadme

; Icon
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "..\README.md"; DestDir: "{app}"; Flags: isreadme

; Default config
Source: "default_config.json"; DestDir: "{app}"; Flags: ignoreversion

; Icons
[Icons]
; Desktop shortcut
Name: "{group}\SteamPACC"; Filename: "{app}\SteamPACC.exe"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Components: desktop

; Start Menu shortcut
Name: "{group}\SteamPACC"; Filename: "{app}\SteamPACC.exe"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Components: startmenu
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Components: startmenu

; Auto-start shortcut
Name: "{commondesktop}\SteamPACC"; Filename: "{app}\SteamPACC.exe"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Components: autostart; Flags: onlyifdoesntexist; Parameters: "--autostart"

; Uninstall
[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: files; Name: "{commondesktop}\SteamPACC.lnk"
Type: files; Name: "{commonstartmenu}\SteamPACC.lnk"

; Registry
[Registry]
; Auto-start
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SteamPACC"; ValueData: "{app}\SteamPACC.exe --autostart"; Components: autostart; Flags: uninsdeletevalue

; Custom messages for Russian
[CustomMessages]
Russian.AppName=SteamPACC
Russian.AppVersion=Версия {#AppVersion}
Russian.InfoBeforeLabel=Добро пожаловать!
Russian.InfoBeforeText=SteamPACC - программа для отображения цен игр в Steam в разных валютах.\n\nОна работает как оверлей поверх окна Steam и показывает цены автоматически при наведении на игру.
Russian.InfoAfterLabel=Установка завершена!
Russian.InfoAfterText=SteamPACC установлен и готов к работе.\n\nЧтобы начать:\n1. Запустите Steam\n2. Запустите SteamPACC\n3. Наведите на любую игру - цены появятся автоматически\n\nДля настройки: кликните правой кнопкой на иконку в трее

; English messages
[Messages]
InfoBeforeLabel=Welcome!
InfoBeforeText=SteamPACC displays game prices in different currencies as an overlay on Steam window.\n\nIt works automatically - just hover over any game in Steam to see prices.
InfoAfterLabel=Setup Complete!
InfoAfterText=SteamPACC has been successfully installed.\n\nTo start using:\n1. Launch Steam\n2. Launch SteamPACC\n3. Hover over any game - prices will appear automatically\n\nTo configure: right-click the tray icon
