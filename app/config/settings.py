# app/infrastructure/db/session.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "development"
    DATABASE_URL: str  # will be read from .env or environment variable
    TEST_DATABASE_URL: str
    GROUP_SIZE_DEFAULT: int = 8 
    PROPOSALS_PER_USER_DEFAULT: int = 3
    DELIBERATION_SECONDS_DEFAULT: int = 3600
    public_base_url: str = "https://temptingly-breechless-venessa.ngrok-free.dev"
    public_base_wss_url: str = "wss://temptingly-breechless-venessa.ngrok-free.dev"
    bot_username: str = "FractalCircleBot"
    bot_token: str

    class Config:
        env_file = ".env"

settings = Settings()