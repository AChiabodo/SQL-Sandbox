from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.llm_sql.config import (
    AnthropicConfig,
    AzureConfig,
    CommonModelConfig,
    LlmSqlSettings,
    OpenAIConfig,
    OpenRouterConfig,
    ProviderName,
    get_llm_sql_settings,
)

Builder = Callable[[str, dict[str, Any]], BaseChatModel]


class ModelFactoryError(ValueError):
    pass


class UnsupportedProviderError(ModelFactoryError):
    pass


class MissingConfigurationError(ModelFactoryError):
    pass


@dataclass(slots=True)
class ProviderStatus:
    name: str
    is_configured: bool
    default_model: str | None
    missing: list[str]


class ModelProvider:
    def __init__(self, settings: LlmSqlSettings | None = None) -> None:
        self.settings = settings or get_llm_sql_settings()
        self._registry: dict[str, Builder] = {
            ProviderName.OPENAI.value: self._build_openai,
            ProviderName.AZURE.value: self._build_azure,
            ProviderName.ANTHROPIC.value: self._build_anthropic,
            ProviderName.OPENROUTER.value: self._build_openrouter,
            ProviderName.LM_STUDIO.value: self._build_lm_studio,
        }

    def list_providers(self) -> list[str]:
        return list(self._registry.keys())

    def list_provider_statuses(self) -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []
        for provider_name in self.list_providers():
            cfg = self.settings.get_provider_config(provider_name)
            missing = list(cfg.missing_required_fields)
            if not (cfg.default_model or "").strip():
                missing.append("default_model")
            statuses.append(
                ProviderStatus(
                    name=provider_name,
                    is_configured=not missing,
                    default_model=cfg.default_model,
                    missing=missing,
                )
            )
        return statuses

    def get_default_provider(self) -> str:
        return self.settings.default_provider.value

    def get_model(
        self,
        provider: str | None = None,
        model: str | None = None,
        **overrides: Any,
    ) -> BaseChatModel:
        provider_name = (provider or self.get_default_provider()).strip().lower()
        if provider_name not in self._registry:
            available = ", ".join(self.list_providers())
            raise UnsupportedProviderError(
                f"Unsupported provider '{provider_name}'. Available providers: {available}."
            )

        cfg = self.settings.get_provider_config(provider_name)
        selected_model = (model or cfg.default_model or "").strip()
        missing = list(cfg.missing_required_fields)
        if not selected_model:
            missing.append("default_model")
        if missing:
            missing_vars = ", ".join(f"{provider_name.upper()}__{name.upper()}" for name in missing)
            raise MissingConfigurationError(
                f"Missing required configuration for '{provider_name}'. Set {missing_vars}."
            )

        kwargs = self._resolve_common_kwargs(cfg, overrides)
        return self._registry[provider_name](selected_model, kwargs)

    def _resolve_common_kwargs(self, cfg: CommonModelConfig, overrides: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "temperature": cfg.temperature,
            "timeout": cfg.timeout,
        }
        if cfg.max_tokens is not None:
            kwargs["max_tokens"] = cfg.max_tokens
        kwargs.update({key: value for key, value in overrides.items() if value is not None})
        return kwargs

    def _build_openai(self, model: str, kwargs: dict[str, Any]) -> BaseChatModel:
        cfg = self.settings.get_provider_config(ProviderName.OPENAI.value)
        assert isinstance(cfg, OpenAIConfig)
        build_kwargs = {"model": model, "api_key": cfg.api_key, **kwargs}
        if cfg.base_url:
            build_kwargs["base_url"] = cfg.base_url
        return ChatOpenAI(**build_kwargs)

    def _build_azure(self, model: str, kwargs: dict[str, Any]) -> BaseChatModel:
        cfg = self.settings.get_provider_config(ProviderName.AZURE.value)
        assert isinstance(cfg, AzureConfig)
        return AzureChatOpenAI(
            model=model,
            api_key=cfg.api_key,
            azure_endpoint=cfg.endpoint,
            api_version=cfg.api_version,
            **kwargs,
        )

    def _build_anthropic(self, model: str, kwargs: dict[str, Any]) -> BaseChatModel:
        cfg = self.settings.get_provider_config(ProviderName.ANTHROPIC.value)
        assert isinstance(cfg, AnthropicConfig)
        build_kwargs = {"model": model, "api_key": cfg.api_key, **kwargs}
        if cfg.base_url:
            build_kwargs["base_url"] = cfg.base_url
        return ChatAnthropic(**build_kwargs)

    def _build_openrouter(self, model: str, kwargs: dict[str, Any]) -> BaseChatModel:
        cfg = self.settings.get_provider_config(ProviderName.OPENROUTER.value)
        assert isinstance(cfg, OpenRouterConfig)
        return ChatOpenAI(model=model, api_key=cfg.api_key, base_url=cfg.base_url, **kwargs)

    def _build_lm_studio(self, model: str, kwargs: dict[str, Any]) -> BaseChatModel:
        cfg = self.settings.get_provider_config(ProviderName.LM_STUDIO.value)
        return ChatOpenAI(model=model, api_key=getattr(cfg, "api_key", "lm-studio"), base_url=cfg.base_url, **kwargs)


model_provider = ModelProvider(settings=get_llm_sql_settings())
