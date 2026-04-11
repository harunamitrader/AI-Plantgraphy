from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "plants.sqlite"


class Settings(BaseSettings):
    api_key: str = "change-me"
    base_url: str = "http://127.0.0.1:8000"
    gemini_enabled: bool = False
    gemini_command: str = "gemini"
    gemini_timeout_seconds: int = 180
    discord_webhook_url: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_prefix="PLANT_DEX_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_data_dirs() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
