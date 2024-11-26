"""
Base agent implementation supporting multiple LLM providers.
Path: src/agents/base.py
"""

from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from litellm import completion
import json
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from enum import Enum
import os

logger = structlog.get_logger()

class LLMProviderError(Exception):
    """Custom exception for LLM provider configuration and runtime errors"""
    pass

class LLMConfigError(Exception):
    """Custom exception for LLM configuration errors"""
    pass

class LLMProvider(str, Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"

@dataclass
class AgentResponse:
    """Standard response format"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    raw_response: Optional[str] = None

class BaseAgent(ABC):
    """Base agent with centralized LLM handling"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: str,
                 temperature: float = 0,
                 max_retries: int = 3,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize agent with provider configuration"""
        self._validate_init_params(provider, model, config)
        
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.config = config
        
        # Load agent-specific configuration
        self.agent_config = self._load_agent_config()
        
        self.logger = structlog.get_logger().bind(
            agent=self._get_agent_name(),
            provider=provider.value,
            model=model
        )
        
        self.logger.info("agent.initialized",
                        temperature=temperature,
                        max_retries=max_retries)

    def _load_agent_config(self) -> Dict[str, Any]:
        """Load agent-specific configuration including prompts"""
        agent_name = self._get_agent_name()
        agent_config = self.config.get('llm_config', {}).get('agents', {}).get(agent_name)
        
        if not agent_config:
            raise LLMConfigError(f"No configuration found for agent: {agent_name}")
            
        if 'prompts' not in agent_config:
            raise LLMConfigError(f"No prompts configured for agent: {agent_name}")
            
        if 'system' not in agent_config['prompts']:
            raise LLMConfigError(f"No system prompt configured for agent: {agent_name}")
            
        return agent_config

    def _validate_init_params(self, provider: LLMProvider, model: str, config: Dict[str, Any]) -> None:
        """Centralized parameter validation"""
        if not isinstance(provider, LLMProvider):
            raise LLMProviderError(f"Invalid provider type. Must be LLMProvider enum, got {type(provider)}")
        
        if not model:
            raise LLMProviderError(f"Model must be specified for agent {self._get_agent_name()}")
            
        if not config or not isinstance(config, dict):
            raise LLMProviderError("Valid configuration dictionary is required")
            
        if 'providers' not in config:
            raise LLMProviderError("Provider configurations missing from config")
            
        provider_config = config.get('providers', {}).get(provider.value)
        if not provider_config:
            available = list(config.get('providers', {}).keys())
            raise LLMProviderError(
                f"Configuration missing for provider: {provider.value}. "
                f"Available providers: {available}"
            )
            
        required_fields = ['api_base', 'env_var']
        missing = [f for f in required_fields if f not in provider_config]
        if missing:
            raise LLMProviderError(f"Missing provider configuration fields: {missing}")

        env_var = provider_config['env_var']
        if not os.getenv(env_var):
            raise LLMProviderError(f"Environment variable {env_var} not set")

    def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Main synchronous processing with retries and error handling"""
        if not isinstance(context, dict):
            return AgentResponse(
                success=False,
                data={},
                error="Context must be a dictionary"
            )

        for attempt in range(self.max_retries):
            try:
                self.logger.info("request.attempt", attempt=attempt + 1)
                return self._handle_llm_request(context)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    self.logger.error("request.failed", error=str(e))
                    return AgentResponse(
                        success=False,
                        data={},
                        error=f"Failed after {self.max_retries} attempts: {str(e)}"
                    )

    def _handle_llm_request(self, request: Dict[str, Any]) -> AgentResponse:
        """Centralized synchronous LLM request handling"""
        try:
            provider_config = self.config['providers'][self.provider.value]
            api_key = os.getenv(provider_config["env_var"])
            
            formatted_request = self._format_request(request)
            messages = self._format_messages(formatted_request)
            
            self.logger.debug("agent.request_content",
                          system_message=self._get_system_message(),
                          request_preview=str(formatted_request)[:200])
            
            response = completion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                api_base=provider_config["api_base"],
                api_key=api_key
            )
            
            if response and response.choices:
                content = response.choices[0].message.content
                return AgentResponse(
                    success=True,
                    data=self._process_llm_response(content, response),
                    raw_response=content
                )
                
            return AgentResponse(
                success=False,
                data={},
                error="Empty response from LLM"
            )
            
        except Exception as e:
            self.logger.error("llm_request.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def _process_llm_response(self, content: str, raw_response: Any) -> Dict[str, Any]:
        """Process LLM response into standard format"""
        return {
            "response": content,
            "raw_output": raw_response,
            "raw_content": content,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _format_messages(self, user_content: str) -> List[Dict[str, str]]:
        """Format messages based on provider"""
        system_msg = self._get_system_message()
        
        if self.provider == LLMProvider.GEMINI:
            combined = f"{system_msg}\n\nUser request: {user_content}"
            return [{"role": "user", "content": combined}]
        
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content}
        ]

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request message"""
        return str(context)

    def _get_prompt(self, prompt_type: str) -> str:
        """Get prompt by type from configuration"""
        prompts = self.agent_config.get('prompts', {})
        if prompt_type not in prompts:
            raise LLMConfigError(f"Prompt type '{prompt_type}' not found for agent: {self._get_agent_name()}")
        return prompts[prompt_type]

    def _get_system_message(self) -> str:
        """Get system message from configuration"""
        return self._get_prompt('system')

    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get name for this agent type"""
        raise NotImplementedError()