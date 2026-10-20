"""SteamPACC — оверлей цен в разных валютах поверх клиента Steam."""

__version__ = "0.1.0"

# Имя папки с настройками в профиле пользователя
APP_DIR_NAME = "SteamPACC"

# Класс главного окна клиента Steam, по которому ищется окно для оверлея
STEAM_WINDOW_CLASS = "STEAMMAINWINDOW"

__all__ = ["__version__", "APP_DIR_NAME", "STEAM_WINDOW_CLASS"]
