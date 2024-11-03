# src/agents/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from autogen import AssistantAgent, UserProxyAgent
from ..models.intent import Intent
from ..config.providers import LLMProvider, ProviderConfig
import os

class BaseAgent(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config["name"]
        self.providers = self._setup_providers()
        self._initialize_agent()

    def _setup_providers(self) -> Dict[LLMProvider, ProviderConfig]:
        """Setup all configured LLM providers"""
        providers = {}
        llm_config = self.config["llm_config"]
        
        # Setup primary provider
        primary = llm_config["primary_provider"]
        providers[primary] = self._get_provider_config(primary)
        
        # Setup fallback providers
        for provider in llm_config.get("fallback_providers", []):
            providers[provider] = self._get_provider_config(provider)
            
        return providers

    def _get_provider_config(self, provider: str) -> ProviderConfig:
        """Get configuration for specific provider"""
        provider_config = self.config.get("providers", {}).get(provider, {})
        
        # Ensure API key is available
        api_key_env = provider_config.get("api_key_env")
        if not api_key_env or not os.getenv(api_key_env):
            raise ValueError(f"API key not found for provider {provider}")
            
        return ProviderConfig(**provider_config)

    def _initialize_agent(self):
        """Initialize the AutoGen agent with primary provider"""
        primary_provider = self.config["llm_config"]["primary_provider"]
        provider_config = self.providers[primary_provider]
        
        self.agent = AssistantAgent(
            name=self.name,
            system_message=self.config["base_prompt"],
            llm_config={
                "config_list": [{
                    "model": provider_config.model,
                    "api_key": os.getenv(provider_config.api_key_env)
                }],
                "temperature": provider_config.temperature,
                "request_timeout": provider_config.timeout,
                **provider_config.additional_params
            }
        )
        
        # Initialize fallback agents
        self.fallback_agents = {}
        for provider in self.config["llm_config"].get("fallback_providers", []):
            provider_config = self.providers[provider]
            self.fallback_agents[provider] = AssistantAgent(
                name=f"{self.name}_{provider}",
                system_message=self.config["base_prompt"],
                llm_config={
                    "config_list": [{
                        "model": provider_config.model,
                        "api_key": os.getenv(provider_config.api_key_env)
                    }],
                    "temperature": provider_config.temperature,
                    "request_timeout": provider_config.timeout,
                    **provider_config.additional_params
                }
            )

    async def try_with_fallbacks(self, func, *args, **kwargs):
        """Try operation with primary agent, fall back to others if needed"""
        try:
            return await func(self.agent, *args, **kwargs)
        except Exception as e:
            for provider, fallback_agent in self.fallback_agents.items():
                try:
                    return await func(fallback_agent, *args, **kwargs)
                except Exception as fallback_e:
                    continue
            raise Exception("All providers failed")

    @abstractmethod
    async def process_intent(self, intent: Intent) -> Intent:
        pass

    @abstractmethod
    async def handle_error(self, error: Exception, intent: Intent) -> Intent:
        pass