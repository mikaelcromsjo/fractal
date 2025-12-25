# app/infrastructure/db/session.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "development"
    DATABASE_URL: str  # will be read from .env or environment variable
    TEST_DATABASE_URL: str
    GROUP_SIZE_DEFAULT: int = 4
    PROPOSALS_PER_USER_DEFAULT: int = 3
    ROUND_TIME_DEFAULT: int = 300
#    public_base_url: str = "https://temptingly-breechless-venessa.ngrok-free.dev"
#    public_base_wss_url: str = "wss://temptingly-breechless-venessa.ngrok-free.dev"
    public_base_url: str = "https://fractal.ia-ai.se"
    public_base_wss_url: str = "wss://fractal.ia-ai.se"
    bot_username: str = "FractalCircleBot"
    bot_token: str
    

    class Config:
        env_file = ".env"

settings = Settings()