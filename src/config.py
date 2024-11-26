"""
System configuration handling.
Path: src/config.py
"""

from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field, validator
from enum import Enum
import structlog
from .agents.base import LLMProvider
import os

logger = structlog.get_logger()

class ConfigValidationError(Exception):
    """Custom exception for configuration validation failures"""
    pass

class AgentLLMConfig(BaseModel):
    """LLM configuration for an agent"""
    provider: str = Field(..., description="LLM provider name (required)")
    model: str = Field(..., description="Model name for this agent (required)")
    temperature: float = Field(default=0)
    
    @validator('provider')
    def valid_provider(cls, v):
        try:
            LLMProvider(v)
            return v
        except ValueError:
            raise ConfigValidationError(f"Invalid provider '{v}'. Must be one of: {[p.value for p in LLMProvider]}")

    @validator('model')
    def model_not_empty(cls, v):
        if not v.strip():
            raise ConfigValidationError("Model name cannot be empty")
        return v
    
    @property
    def provider_enum(self) -> LLMProvider:
        return LLMProvider(self.provider)
    
    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        """Override dict to ensure all fields are included"""
        base_dict = super().dict(*args, **kwargs)
        if 'temperature' not in base_dict:
            base_dict['temperature'] = 0
        return base_dict

class ProjectConfig(BaseModel):
    """Project configuration settings"""
    default_path: Optional[str] = None
    default_intent: Optional[str] = None
    workspace_root: str = Field(default="workspaces")
    max_file_size: int = Field(default=1024 * 1024)  # 1MB default

    @validator('workspace_root')
    def validate_workspace_root(cls, v):
        if not v:
            raise ConfigValidationError("workspace_root cannot be empty")
        return v

class ProviderConfig(BaseModel):
    """Provider-specific configuration"""
    api_base: str = Field(..., description="API base URL (required)")
    context_length: int = Field(..., description="Maximum context length (required)")
    env_var: str = Field(..., description="Environment variable name for API key (required)")

    @validator('api_base')
    def validate_api_base(cls, v):
        if not v:
            raise ConfigValidationError("API base URL cannot be empty")
        return v

    @validator('context_length')
    def validate_context_length(cls, v):
        if v <= 0:
            raise ConfigValidationError("Context length must be positive")
        return v

    @validator('env_var')
    def env_var_exists(cls, v):
        if not v:
            raise ConfigValidationError("Environment variable name cannot be empty")
        if not os.getenv(v):
            raise ConfigValidationError(f"Environment variable '{v}' not set")
        return v

class SystemConfig(BaseModel):
    """System-wide configuration"""
    providers: Dict[str, ProviderConfig] = Field(..., description="Provider configurations (required)")
    llm_config: Dict[str, Any] = Field(..., description="LLM configurations (required)")
    backup: Dict[str, Any] = Field(default_factory=dict)
    logging: Dict[str, Any] = Field(default_factory=dict)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    
    @validator('providers')
    def validate_providers(cls, v):
        if not v:
            raise ConfigValidationError("At least one provider must be configured")
        
        # Validate all required providers are present
        required_providers = {p.value for p in LLMProvider}
        missing_providers = required_providers - set(v.keys())
        if missing_providers:
            raise ConfigValidationError(f"Missing configurations for providers: {missing_providers}")
        return v

    @validator('llm_config')
    def validate_llm_config(cls, v):
        required = ['default_provider', 'default_model', 'agents']
        missing = [f for f in required if f not in v]
        if missing:
            raise ConfigValidationError(f"Missing required LLM config fields: {missing}")
        
        # Validate default provider exists
        default_provider = v.get('default_provider')
        if default_provider not in [p.value for p in LLMProvider]:
            raise ConfigValidationError(f"Invalid default_provider: {default_provider}")
        
        # Validate agents configuration
        agents = v.get('agents', {})
        if not isinstance(agents, dict):
            raise ConfigValidationError("agents config must be a dictionary")
            
        required_agents = {'discovery', 'solution_designer', 'coder', 'assurance'}
        missing_agents = required_agents - set(agents.keys())
        if missing_agents:
            raise ConfigValidationError(f"Missing configurations for agents: {missing_agents}")
        
        return v

    def get_agent_config(self, agent_name: str) -> AgentLLMConfig:
        """Get LLM configuration for specific agent with validation"""
        if not agent_name:
            raise ConfigValidationError("Agent name is required")

        agent_configs = self.llm_config.get("agents", {})
        if agent_name not in agent_configs:
            raise ConfigValidationError(
                f"No configuration found for agent '{agent_name}'. "
                f"Available agents: {list(agent_configs.keys())}"
            )
        
        config = agent_configs[agent_name]
        try:
            return AgentLLMConfig(**config)
        except Exception as e:
            raise ConfigValidationError(f"Invalid configuration for agent '{agent_name}': {str(e)}")

    @classmethod
    def load(cls, config_path: Path) -> 'SystemConfig':
        """Load configuration from YAML file"""
        try:
            if not config_path.exists():
                raise ConfigValidationError(f"Configuration file not found: {config_path}")
                
            with open(config_path) as f:
                data = yaml.safe_load(f)
                
            if not data:
                raise ConfigValidationError("Empty configuration file")
                
            return cls(**data)
        except Exception as e:
            logger.error("config.load_failed", error=str(e))
            raise ConfigValidationError(f"Failed to load configuration: {str(e)}")