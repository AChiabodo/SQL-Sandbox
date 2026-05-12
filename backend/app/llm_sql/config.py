from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(str, Enum):
    OPENAI = "openai"
    AZURE = "azure"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    LM_STUDIO = "lm_studio"


class CommonModelConfig(BaseModel):
    required_fields: ClassVar[tuple[str, ...]] = ()

    default_model: str | None = None
    temperature: float = 0.0
    timeout: int = 60
    max_tokens: int | None = None

    @field_validator("max_tokens", mode="before")
    @classmethod
    def empty_max_tokens_to_none(cls, value: object) -> object:
        return None if value == "" else value

    @staticmethod
    def _is_value_set(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    @property
    def missing_required_fields(self) -> list[str]:
        return [
            name
            for name in self.required_fields
            if not self._is_value_set(getattr(self, name, None))
        ]

    @property
    def is_configured(self) -> bool:
        return not self.missing_required_fields and bool((self.default_model or "").strip())


class OpenAIConfig(CommonModelConfig):
    required_fields: ClassVar[tuple[str, ...]] = ("api_key",)
    api_key: str | None = None
    base_url: str | None = None


class AzureConfig(CommonModelConfig):
    required_fields: ClassVar[tuple[str, ...]] = ("api_key", "endpoint")
    api_key: str | None = None
    endpoint: str | None = None
    api_version: str = "2024-02-15-preview"


class AnthropicConfig(CommonModelConfig):
    required_fields: ClassVar[tuple[str, ...]] = ("api_key",)
    api_key: str | None = None
    base_url: str | None = None


class OpenRouterConfig(CommonModelConfig):
    required_fields: ClassVar[tuple[str, ...]] = ("api_key",)
    api_key: str | None = None
    base_url: str = "https://openrouter.ai/api/v1"


class LMStudioConfig(CommonModelConfig):
    required_fields: ClassVar[tuple[str, ...]] = ("base_url",)
    api_key: str = "lm-studio"
    base_url: str = "http://localhost:1234/v1"


class LlmSqlSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    default_provider: ProviderName = ProviderName.OPENAI

    openai: OpenAIConfig = Field(default_factory=lambda: OpenAIConfig(default_model="gpt-4o-mini"))
    azure: AzureConfig = Field(default_factory=lambda: AzureConfig(default_model="gpt-4o-mini"))
    anthropic: AnthropicConfig = Field(
        default_factory=lambda: AnthropicConfig(default_model="claude-3-5-haiku-latest")
    )
    openrouter: OpenRouterConfig = Field(
        default_factory=lambda: OpenRouterConfig(default_model="openai/gpt-4o-mini")
    )
    lm_studio: LMStudioConfig = Field(default_factory=lambda: LMStudioConfig(default_model="local-model"))

    agent_max_steps: int = Field(default=10, alias="LLM_AGENT_MAX_STEPS")
    preview_limit: int = Field(default=20, alias="LLM_PREVIEW_LIMIT")

    def get_provider_config(self, provider_name: str | None = None) -> CommonModelConfig:
        selected = (provider_name or self.default_provider.value).strip().lower()
        return getattr(self, selected)


@lru_cache(maxsize=1)
def get_llm_sql_settings() -> LlmSqlSettings:
    return LlmSqlSettings()
