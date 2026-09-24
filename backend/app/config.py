import os
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
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
    openai_api_key: SecretStr
    openai_embedding_model: str
    openai_embedding_dimensions: int = Field(gt=0)
    allowed_origins: Annotated[list[str], NoDecode] = Field(min_length=1)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def model_post_init(self, _context: object) -> None:
        os.environ["OPENAI_API_KEY"] = self.openai_api_key.get_secret_value()


settings = Settings()
