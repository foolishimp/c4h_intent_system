# src/config.py

from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import yaml
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
import os
import structlog

class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"

class SkillConfig(BaseModel):
    """Configuration for a skill"""
    type: str
    path: Path
    config: Dict[str, Any] = Field(default_factory=dict)

    @validator('path')
    def validate_path(cls, v):
        if not v.exists():
            raise ValueError(f"Skill path does not exist: {v}")
        return v

class LLMConfig(BaseModel):
    """Configuration for LLM usage"""
    seed: int = 42
    primary_provider: str
    fallback_providers: List[str] = Field(default_factory=list)
    temperature: float = 0
    request_timeout: int = 120
    functions: Optional[List[Dict[str, Any]]] = None

    @validator('temperature')
    def validate_temperature(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        return v

class AgentConfig(BaseModel):
    """Configuration for an agent"""
    name: str
    type: str
    description: str
    base_prompt: str
    providers: List[str]
    llm_config: LLMConfig

class ProviderConfig(BaseModel):
    """Configuration for an LLM provider"""
    model: str
    api_key_env: str
    timeout: int = 120
    temperature: float = 0
    additional_params: Dict[str, Any] = Field(default_factory=dict)

    @validator('api_key_env')
    def validate_api_key(cls, v):
        if not os.getenv(v):
            raise ValueError(f"Missing environment variable: {v}")
        return v

class IntentConfig(BaseModel):
    """Configuration for an intent type"""
    description_template: str
    resolution: str
    required_skills: List[str] = Field(default_factory=list)
    criteria: Dict[str, bool] = Field(default_factory=dict)
    environment: Dict[str, Any] = Field(default_factory=dict)
    validation_rules: Dict[str, str] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)

class Config(BaseModel):
    """Application configuration"""
    default_llm: str
    providers: Dict[str, ProviderConfig]
    master_prompt_overlay: str
    asset_base_path: Path
    agents: Dict[str, AgentConfig]
    skills: Dict[str, SkillConfig] = Field(default_factory=dict)
    intents: Dict[str, Dict[str, IntentConfig]] = Field(default_factory=dict)

    logger: Any = Field(default_factory=lambda: structlog.get_logger())

    class Config:
        arbitrary_types_allowed = True

    @validator('asset_base_path')
    def validate_asset_path(cls, v):
        v.mkdir(parents=True, exist_ok=True)
        return v

    @classmethod
    def from_yaml(cls, path: Path) -> 'Config':
        """Load config from YAML and environment variables"""
        # Load .env file from project root if it exists
        project_root = path.parent.parent
        env_path = project_root / '.env'
        
        if env_path.exists():
            load_dotenv(env_path)
            structlog.get_logger().info("config.env_loaded", path=str(env_path))
        else:
            structlog.get_logger().info("config.no_env_file")

        # Load and parse YAML config
        try:
            with path.open() as f:
                data = yaml.safe_load(f)
            
            # Convert paths to Path objects
            data['asset_base_path'] = Path(data['asset_base_path'])
            if 'skills' in data:
                for skill in data['skills'].values():
                    skill['path'] = Path(skill['path'])

            # Create config instance
            config = cls(**data)
            
            # Validate all components
            config.validate_components()
            
            return config

        except Exception as e:
            structlog.get_logger().exception("config.load_failed", error=str(e))
            raise

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

    def get_skill_config(self, skill_name: str) -> SkillConfig:
        """Get configuration for a specific skill"""
        if skill_name not in self.skills:
            raise ValueError(f"Skill not configured: {skill_name}")
        return self.skills[skill_name]

    def validate_components(self) -> None:
        """Validate all component configurations"""
        self._validate_providers()
        self._validate_agents()
        self._validate_skills()
        self._validate_intents()

    def _validate_providers(self) -> None:
        """Validate provider configurations"""
        if not self.default_llm in self.providers:
            raise ValueError(f"Default LLM provider {self.default_llm} not configured")
        
        for provider in self.providers.values():
            if not os.getenv(provider.api_key_env):
                raise ValueError(f"Missing API key for provider: {provider.api_key_env}")

    def _validate_agents(self) -> None:
        """Validate agent configurations"""
        for agent in self.agents.values():
            for provider in agent.providers:
                if provider not in self.providers:
                    raise ValueError(f"Agent {agent.name} references unknown provider: {provider}")

    def _validate_skills(self) -> None:
        """Validate skill configurations"""
        for skill_name, skill in self.skills.items():
            if not skill.path.exists():
                raise ValueError(f"Skill path does not exist for {skill_name}: {skill.path}")

    def _validate_intents(self) -> None:
        """Validate intent configurations"""
        if 'initial' not in self.intents:
            raise ValueError("No initial intent configurations found")
            
        for intent_type, intent in self.intents.get('actions', {}).items():
            if 'skill' in intent.dict() and intent.dict()['skill'] not in self.skills:
                raise ValueError(f"Intent {intent_type} references unknown skill: {intent.dict()['skill']}")

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