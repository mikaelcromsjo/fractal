# app/config/settings.py
"""
Application settings. Reads .env if present via pydantic BaseSettings.
"""
from pydantic import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./app.db"
    GROUP_SIZE_DEFAULT: int = 8
    PROPOSALS_PER_USER_DEFAULT: int = 3
    DELIBERATION_SECONDS_DEFAULT: int = 3600

    class Config:
        env_file = ".env"


settings = Settings()
