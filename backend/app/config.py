from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    database_url: SecretStr
    gemini_api_key: SecretStr
    gemini_chat_model: str = Field(min_length=1)
    gemini_fallback_chat_model: str = Field(min_length=1)
    gemini_reasoning_effort: Literal["none", "low", "medium", "high"]
    gemini_embedding_model: str
    gemini_embedding_dimensions: int = Field(gt=0, le=3072)
    allowed_origins: Annotated[list[str], NoDecode] = Field(min_length=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_pool_size: int = Field(default=5, gt=0)
    database_max_overflow: int = Field(default=10, ge=0)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def require_distinct_chat_models(self) -> "Settings":
        if self.gemini_chat_model == self.gemini_fallback_chat_model:
            raise ValueError("Gemini primary and fallback chat models must differ")
        return self


settings = Settings()
