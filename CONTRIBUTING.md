# Участие в разработке / Contributing

## Русский

Спасибо за интерес к SteamPACC!

- **Ошибки и идеи** — создайте [Issue](https://github.com/Stintik-123/SteamPACC/issues): опишите шаги воспроизведения, версию Windows и версию SteamPACC (окно программы или `SteamPACC.exe --version`).
- **Отчёт диагностики** — правый клик по значку в трее → «Отчёт о системе»; приложите файл `otchet.txt` к Issue.
- **Изменения кода** — форкните репозиторий, создайте ветку, сделайте изменения. Перед отправкой:
  ```bash
  pip install -r requirements.txt -r requirements-dev.txt
  python -m pytest -q        # все тесты должны проходить
  ```
- Код, комментарии и сообщения коммитов — на русском языке (как и весь проект). Публичные строки интерфейса — на двух языках (`STRINGS` в `src/steampacc/app.py`, `TEXT` в `src/steampacc/inject.py`).
- Не добавляйте зависимости без необходимости: программа держится на PySide6 и стандартной библиотеке.
- Сборка проверяется CI на каждый пуш; тег `v*` публикует релиз с установщиком и контрольными суммами.

## English

Thanks for your interest in SteamPACC!

- **Bugs and ideas** — open an [Issue](https://github.com/Stintik-123/SteamPACC/issues) with reproduction steps, Windows version and SteamPACC version (app window or `SteamPACC.exe --version`).
- **Diagnostic report** — tray icon right-click → "System report"; attach `otchet.txt` to the issue.
- **Code changes** — fork, branch, change. Before submitting:
  ```bash
  pip install -r requirements.txt -r requirements-dev.txt
  python -m pytest -q        # all tests must pass
  ```
- Code comments and commit messages are in Russian (project convention). UI strings ship in two languages (`STRINGS` in `src/steampacc/app.py`, `TEXT` in `src/steampacc/inject.py`).
- Avoid new dependencies: the app relies on PySide6 and the standard library only.
- CI builds on every push; a `v*` tag publishes a release with the installer and checksums.
