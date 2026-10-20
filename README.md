# SteamPACC
SteamPACC (Steam Price and currency conversion), программа, которая показывает цену игры в Steam в разных валютах, рядом с ценой в регионе Steam. Сделано специально для себя и для друзей.

## Возможности

- Прозрачный оверлей поверх окна клиента Steam: цены в других валютах появляются рядом с ценой региона.
- Любой набор валют: пользователь сам выбирает, какие валюты показывать (USD, EUR, RUB, TRY, KZT, UAH и другие).
- Цены берутся из официального Store API Steam, поэтому совпадают с тем, что видит сам клиент.
- Дисковое кэширование цен: повторные запросы не уходят в сеть, программа не тормозит.
- Программа сворачивается в трей и почти не потребляет ресурсов.
- Русскоязычный установщик, настройка автозапуска вместе с Windows.

## Установка

1. Скачайте установщик `SteamPACC-Setup-<версия>.exe` из раздела [Releases](https://github.com/Stintik-123/SteamPACC/releases).
2. Запустите установщик и пройдите мастер установки.
3. SteamPACC запускается автоматически и живёт в трее (значок рядом с часами).
4. При первом запуске откройте настройки из трея: выберите валюты и откалибруйте положение оверлея поверх окна Steam.

Требуется Windows 10/11 x64. Программа устанавливается в `C:\Program Files\SteamPACC`.

## Сборка из исходников

Нужны Python 3.11 и Inno Setup 6.

```bash
git clone https://github.com/Stintik-123/SteamPACC.git
cd SteamPACC
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pyinstaller --noconfirm --clean --onefile --windowed --name SteamPACC --paths src src/steampacc/__main__.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\SteamPACC.iss
```

Готовый установщик появится в папке `dist`.

Те же действия выполняет CI: каждый push в `main` собирает установщик, а тег вида `v0.1.0` дополнительно публикует релиз.

## Структура проекта

- `src/steampacc/` — исходники программы.
- `tests/` — автотесты (pytest).
- `installer/SteamPACC.iss` — сценарий установщика Inno Setup.
- `.github/workflows/build.yml` — сборка установщика в CI.
- `docs/DESIGN.md` — проектный документ: модули, источники цен, риски.

## Статус

Проект в разработке: собран каркас, установщик и CI, реализуется ядро данных и оверлей.

## Лицензия

MIT — см. файл [LICENSE](LICENSE).
