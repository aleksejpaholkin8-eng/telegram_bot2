import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = os.getenv("BOT_TOKEN", "")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    bot_mode: str = os.getenv("BOT_MODE", "polling")
    default_tariff: str = os.getenv("DEFAULT_TARIFF", "lite")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    xai_api_key: str = os.getenv("XAI_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")


settings = Settings()
