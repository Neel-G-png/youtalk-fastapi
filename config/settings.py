import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    ALLOWED_ORIGINS: list = ["*"]

# Instantiate settings
settings = Settings()