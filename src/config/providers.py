from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"

class ProviderConfig(BaseModel):
    model: str
    api_key_env: str
    timeout: int = 120
    temperature: float = 0
    additional_params: Dict[str, Any] = {}

DEFAULT_PROVIDER_CONFIGS = {
    LLMProvider.OPENAI: {
        "model": "gpt-4",
        "api_key_env": "OPENAI_API_KEY",
        "timeout": 120,
        "temperature": 0
    },
    LLMProvider.ANTHROPIC: {
        "model": "claude-3-opus-20240229",
        "api_key_env": "ANTHROPIC_API_KEY",
        "timeout": 120,
        "temperature": 0
    },
    LLMProvider.GEMINI: {
        "model": "gemini-pro",
        "api_key_env": "GEMINI_API_KEY",
        "timeout": 120,
        "temperature": 0
    }
}