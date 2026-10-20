"""Проверки базового пакета SteamPACC."""

import steampacc


def test_version_defined():
    """Версия пакета должна быть задана."""
    assert steampacc.__version__


def test_app_dir_name():
    """Имя папки настроек — SteamPACC."""
    assert steampacc.APP_DIR_NAME == "SteamPACC"


def test_steam_window_class():
    """Класс главного окна клиента Steam используется для поиска окна."""
    assert steampacc.STEAM_WINDOW_CLASS == "STEAMMAINWINDOW"
