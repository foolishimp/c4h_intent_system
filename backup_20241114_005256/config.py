# src/config.py

from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import yaml
from pydantic import BaseModel, Field
from pydantic.functional_validators import field_validator
from dotenv import load_dotenv
import os
import structlog

class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"

class SkillConfig(BaseModel):
    """Configuration for a skill"""
    type: str
    path: Path
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: Path) -> Path:
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

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        return v

class ProviderConfig(BaseModel):
    """Configuration for an LLM provider"""
    model: str
    api_key_env: str
    timeout: int = 120
    temperature: float = 0
    additional_params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('api_key_env')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not os.getenv(v):
            raise ValueError(f"Missing environment variable: {v}")
        return v

class AgentConfig(BaseModel):
    """Configuration for an agent"""
    name: str
    type: str
    description: str
    base_prompt: str
    providers: List[str]
    llm_config: LLMConfig

class IntentConfig(BaseModel):
    """Configuration for an intent type"""
    description_template: str
    resolution: str
    skill: Optional[str] = None
    criteria: Dict[str, bool] = Field(default_factory=dict)
    environment: Dict[str, Any] = Field(default_factory=dict)
    validation_rules: Dict[str, str] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)

class ValidationRuleConfig(BaseModel):
    """Configuration for a validation rule"""
    type: str
    validator: str
    additional_params: Dict[str, Any] = Field(default_factory=dict)

class ValidationConfig(BaseModel):
    """Configuration for validation rules"""
    rules: Dict[str, ValidationRuleConfig]

class Config(BaseModel):
    """Application configuration"""
    default_llm: str
    providers: Dict[str, ProviderConfig]
    master_prompt_overlay: str
    asset_base_path: Path
    agents: Dict[str, AgentConfig]
    skills: Dict[str, SkillConfig]
    intents: Dict[str, Dict[str, IntentConfig]]
    validation: ValidationConfig

    logger: Any = Field(default_factory=lambda: structlog.get_logger())

    class Config:
        """Pydantic model configuration"""
        arbitrary_types_allowed = True

    @field_validator('asset_base_path')
    @classmethod
    def validate_asset_path(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    def get_skill_config(self, skill_name: str) -> SkillConfig:
        """Get configuration for a specific skill"""
        if skill_name not in self.skills:
            raise ValueError(f"No configuration found for skill: {skill_name}")
        return self.skills[skill_name]

    def get_skill_path(self, skill_name: str) -> Path:
        """Get the path for a specific skill"""
        skill_config = self.get_skill_config(skill_name)
        return skill_config.path

    @field_validator('skills')
    @classmethod
    def validate_skills(cls, v: Dict[str, SkillConfig]) -> Dict[str, SkillConfig]:
        """Validate that all referenced skills exist"""
        for skill_name, skill_config in v.items():
            if not skill_config.path.exists():
                raise ValueError(f"Skill path does not exist: {skill_config.path}")
        return v

    def validate_references(self) -> None:
        """Validate all cross-references in configuration"""
        self._validate_intent_skills()
        self._validate_agent_providers()

    def _validate_intent_skills(self) -> None:
        """Ensure all skills referenced by intents exist"""
        for intent_type in self.intents.values():
            for intent in intent_type.values():
                if intent.skill and intent.skill not in self.skills:
                    raise ValueError(f"Intent references unknown skill: {intent.skill}")

    def _validate_agent_providers(self) -> None:
        """Ensure all providers referenced by agents exist"""
        for agent in self.agents.values():
            for provider in agent.providers:
                if provider not in self.providers:
                    raise ValueError(f"Agent {agent.name} references unknown provider: {provider}")

    @classmethod
    def from_yaml(cls, path: Path) -> 'Config':
        """Load config from YAML and environment variables"""
        # Check for .env file in project root
        project_root = path.parent.parent
        env_path = project_root / '.env'
        logger = structlog.get_logger()
        
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("config.env_loaded", path=str(env_path))
        else:
            logger.info("config.no_env_file")

        try:
            # Load and parse YAML
            with path.open() as f:
                data = yaml.safe_load(f)
            
            # Convert paths to Path objects
            data['asset_base_path'] = Path(data['asset_base_path'])
            if 'skills' in data:
                for skill in data['skills'].values():
                    if 'path' in skill:
                        skill['path'] = Path(skill['path'])

            # Create and validate config
            config = cls(**data)
            config.validate_references()
            
            return config

        except Exception as e:
            logger.exception("config.load_failed", error=str(e))
            raise

def load_config(path: Path) -> Config:
    """Load and validate configuration
    
    Args:
        path: Path to the config file
        
    Returns:
        Validated Config instance
    
    Raises:
        Exception: If config loading or validation fails
    """
    logger = structlog.get_logger()
    
    try:
        logger.info("config.loading", path=str(path))
        config = Config.from_yaml(path)
        logger.info("config.loaded")
        return config
        
    except Exception as e:
        logger.exception("config.load_failed", error=str(e))
        raise