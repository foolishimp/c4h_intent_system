"""
System configuration handling.
Path: src/config.py
"""

from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field
from enum import Enum
import structlog
from .agents.base import LLMProvider

logger = structlog.get_logger()

class AgentLLMConfig(BaseModel):
    """LLM configuration for an agent"""
    provider: str = Field(default="anthropic")
    model: str = Field(default="claude-3-opus-20240229")
    temperature: float = Field(default=0)
    
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

class ProviderConfig(BaseModel):
    """Provider-specific configuration"""
    api_base: str
    context_length: int
    env_var: str

class SystemConfig(BaseModel):
    """System-wide configuration"""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    llm_config: Dict[str, Any] = Field(default_factory=dict)
    backup: Dict[str, Any] = Field(default_factory=dict)
    logging: Dict[str, Any] = Field(default_factory=dict)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    
    def get_agent_config(self, agent_name: str) -> AgentLLMConfig:
        """Get LLM configuration for specific agent"""
        default_config = {
            "provider": self.llm_config.get("default_provider", "anthropic"),
            "model": self.llm_config.get("default_model"),
            "temperature": 0
        }
        
        agent_config = self.llm_config.get("agents", {}).get(agent_name, {})
        return AgentLLMConfig(**{**default_config, **agent_config})

    @classmethod
    def load(cls, config_path: Path) -> 'SystemConfig':
        """Load configuration from YAML file"""
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return cls(**data)
        except Exception as e:
            logger.error("config.load_failed", error=str(e))
            raise