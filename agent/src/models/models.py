"""Model-provider selection from environment.

One build supports three providers. Pick with MODEL_PROVIDER:
- openai:    OpenAI API (default for local testing; key is in the env)
- anthropic: Anthropic API
- vllm:      any OpenAI-compatible /v1 endpoint, e.g. self-hosted vLLM

vLLM reuses Strands' OpenAIModel with a custom base_url and a placeholder key,
since vLLM exposes an OpenAI-compatible API.
"""

from __future__ import annotations

from strands.models.anthropic import AnthropicModel
from strands.models.openai import OpenAIModel

from config.settings import settings


def openai_model() -> OpenAIModel:
    return OpenAIModel(
        client_args={"api_key": settings.openai_api_key},
        model_id=settings.openai_model_id,
        params={"temperature": 0.3},
    )


def anthropic_model() -> AnthropicModel:
    return AnthropicModel(
        client_args={"api_key": settings.anthropic_api_key},
        model_id=settings.anthropic_model_id,
        max_tokens=4096,
        params={"temperature": 0.3},
    )


def vllm_model() -> OpenAIModel:
    return OpenAIModel(
        client_args={
            "api_key": settings.vllm_api_key,
            "base_url": settings.vllm_base_url,
        },
        model_id=settings.vllm_model_id,
        params={"temperature": 0.3},
    )


def build_model():
    """Return the model object for the configured provider."""
    provider = settings.provider
    if provider == "openai":
        return openai_model()
    if provider == "anthropic":
        return anthropic_model()
    if provider == "vllm":
        return vllm_model()
    raise ValueError(
        f"Unknown MODEL_PROVIDER '{provider}'. Use one of: openai, anthropic, vllm."
    )
