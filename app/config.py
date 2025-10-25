from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Server settings
    app_host: str = Field(default="0.0.0.0")
    app_port: Annotated[int, Field(ge=1, le=65535)] = Field(default=8000)
    log_level: str = Field(default="INFO")
    
    # Text processing limits
    max_enrich_chars: int = Field(default=8000)
    max_response_text_chars: int = Field(default=20000)

    # HTTP client settings
    http_timeout_s: Annotated[int, Field(gt=0)] = Field(default=12)
    user_agent: str = Field(default="url-insights-mini/1.0")

    # Cache settings
    cache_ttl_s: Annotated[int, Field(ge=0)] = Field(default=600)

    # Rate limiting
    rate_limit_per_min: Annotated[int, Field(gt=0)] = Field(default=60)

    # Features
    enable_robots_check: bool = Field(default=False)


# Create settings singleton instance
settings = Settings()