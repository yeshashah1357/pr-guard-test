from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://prguard:prguard@localhost:5432/prguard"
    redis_url: str = "redis://localhost:6379/0"

    # No defaults on purpose: the app refuses to start without real secrets.
    jwt_secret: SecretStr = Field(min_length=32)
    github_webhook_secret: SecretStr = Field(min_length=16)
    github_token: SecretStr | None = None

    jwt_expire_minutes: int = 60
    login_rate_limit_per_minute: int = 10
    cors_origins: list[str] = ["http://localhost:5173"]

    github_api_url: str = "https://api.github.com"
    # Off by default so the project runs at zero cost; Ruff and Bandit are free and always run.
    llm_review_enabled: bool = False
    anthropic_model: str = "claude-opus-5-5"
    max_files_per_review: int = 100
    max_review_comments: int = 30
    # Diffs above this size are skipped by the LLM pass rather than truncated.
    max_llm_diff_chars: int = 150_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
