import os

from dotenv import load_dotenv

from youtube.utils.logger import conf_logger

logger = conf_logger(__name__, "D")

conf_path = (
    "./config/.prod.env" if os.getenv("DEV_STATUS") is True else "./config/.dev.env"
)

load_dotenv(conf_path)


class Config:

    def __init__(self, *args: str) -> None:
        for key in args:
            if value := os.getenv(key):
                if key.endswith("_PORT"):
                    value = int(value)
                setattr(self, key, value)

            else:
                msg = f"Environment variable {key} not found"
                logger.error(msg)
                raise AttributeError(msg)

    def __getattr__(self, item) -> str | None:
        return self.item


env = Config(
    "MONGO_INITDB_ROOT_USERNAME",
    "MONGO_INITDB_ROOT_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "BACKEND_PORT",
)
