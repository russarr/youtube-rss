import os

from dotenv import load_dotenv

_conf_path = "./config/.env" if os.getenv("DEV_STATUS") is True else "./config/.dev.env"

load_dotenv(_conf_path)


def _get_env(key: str) -> str:
    if not (value := os.getenv(key)):
        msg = f"Environment variable {key} not found"
        # TODO: add logger
        raise AttributeError(msg)
    return value


MONGO_INITDB_ROOT_USERNAME: str = _get_env("MONGO_INITDB_ROOT_USERNAME")
MONGO_INITDB_ROOT_PASSWORD: str = _get_env("MONGO_INITDB_ROOT_PASSWORD")
DB_HOST: str = _get_env("DB_HOST")
DB_PORT: int = int(_get_env("DB_PORT"))
BACKEND_PORT: int = int(_get_env("BACKEND_PORT"))
PROJECT_NAME: str = _get_env("PROJECT_NAME")
LOG_FILE: str = _get_env("LOG_FILE")
DEBUG_MODE: bool = _get_env("DEBUG_MODE").lower() in ("true", "1", "t")

TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID")
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN")

