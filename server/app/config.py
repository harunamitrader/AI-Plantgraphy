from functools import lru_cache
from pathlib import Path
import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
LOG_DIR = DATA_DIR / "logs"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "plants.sqlite"
DEFAULT_GEMINI_MODEL_OPTIONS = (
    "auto-gemini-3",
    "auto-gemini-2.5",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
GEMINI_MODEL_LABELS = {
    "auto-gemini-3": "Auto (Gemini 3)",
    "auto-gemini-2.5": "Auto (Gemini 2.5)",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
}


class Settings(BaseSettings):
    api_key: str = "change-me"
    base_url: str = "http://127.0.0.1:8000"
    server_name: str = socket.gethostname()
    shared_frontend_url: str = "https://harunamitrader.github.io/AI-Plantgraphy/app/"
    gemini_enabled: bool = False
    gemini_command: str = "gemini"
    gemini_model: str = "gemini-3-flash-preview"
    gemini_model_options: str = ",".join(DEFAULT_GEMINI_MODEL_OPTIONS)
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


def gemini_model_options() -> list[str]:
    settings = get_settings()
    options = [item.strip() for item in settings.gemini_model_options.split(",") if item.strip()]
    if settings.gemini_model and settings.gemini_model not in options:
        options.insert(0, settings.gemini_model)
    return options


def gemini_model_choices() -> list[dict]:
    return [
        {
            "value": option,
            "label": GEMINI_MODEL_LABELS.get(option, option),
        }
        for option in gemini_model_options()
    ]


def ensure_data_dirs() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
