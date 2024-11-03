# src/config.py

from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"

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

class Config(BaseModel):
    """Application configuration"""
    default_llm: str
    providers: Dict[str, ProviderConfig]
    master_prompt_overlay: str
    asset_base_path: Path
    agents: Dict[str, AgentConfig]

    @classmethod
    def from_yaml(cls, path: Path) -> 'Config':
        """Load config from YAML and environment variables"""
        # Load .env file from project root
        project_root = path.parent.parent
        env_path = project_root / '.env'
        
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from {env_path}")
        else:
            print("No .env file found, using existing environment variables")
            
        # Load and parse YAML config
        with path.open() as f:
            data = yaml.safe_load(f)
            data['asset_base_path'] = Path(data['asset_base_path'])
            
        # Create config instance
        config = cls(**data)
        
        # Validate required environment variables
        missing_vars = []
        for provider in config.providers.values():
            if not os.getenv(provider.api_key_env):
                missing_vars.append(provider.api_key_env)
                
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
            
        return config

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

def load_config(path: Path) -> Config:
    """Load and validate configuration"""
    return Config.from_yaml(path)