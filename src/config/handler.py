# src/config/handler.py

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
import yaml

class LLMConfig(BaseModel):
    seed: int = 42
    primary_provider: str
    fallback_providers: List[str] = []
    temperature: float = 0
    request_timeout: int = 120
    functions: Optional[List[Dict[str, Any]]] = None

class AgentConfig(BaseModel):
    name: str
    type: str
    description: str
    base_prompt: str
    providers: List[str]
    llm_config: LLMConfig

class ProviderConfig(BaseModel):
    model: str
    api_key_env: str
    timeout: int = 120
    temperature: float = 0
    additional_params: Dict[str, Any] = Field(default_factory=dict)

class SystemConfig(BaseModel):
    default_llm: str
    providers: Dict[str, ProviderConfig]
    master_prompt_overlay: str
    asset_base_path: Path
    agents: Dict[str, AgentConfig]

    @classmethod
    def from_yaml(cls, path: str) -> 'SystemConfig':
        with open(path, 'r') as f:
            config_dict = yaml.safe_load(f)
            # Convert string path to Path object
            config_dict['asset_base_path'] = Path(config_dict['asset_base_path'])
            return cls(**config_dict)

    def get_agent_config(self, agent_type: str) -> AgentConfig:
        """Get configuration for a specific agent type"""
        for agent in self.agents.values():
            if agent.type == agent_type:
                return agent
        raise ValueError(f"No configuration found for agent type: {agent_type}")

    def get_provider_config(self, provider: str) -> ProviderConfig:
        """Get configuration for a specific provider"""
        if provider not in self.providers:
            raise ValueError(f"Provider not configured: {provider}")
        return self.providers[provider]