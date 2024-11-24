"""
Base agent implementation with improved authentication handling.
Path: src/agents/base.py
"""

from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from litellm import acompletion
import json
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import os

logger = structlog.get_logger()

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

class BaseAgent(ABC):
    """Base agent using LiteLLM"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: Optional[str] = None,
                 temperature: float = 0,
                 max_retries: int = 3,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize agent with provider configuration"""
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Validate config
        if not config:
            raise ValueError("Provider configuration required - config is None")
        if 'providers' not in config:
            raise ValueError("Provider configuration required - no providers section")
            
        self.config = config
        provider_config = config.get('providers', {}).get(provider.value)
        if not provider_config:
            raise ValueError(f"Configuration missing for provider: {provider.value}")
        
        # Get API key from environment
        env_var = provider_config.get('env_var')
        if not env_var:
            raise ValueError(f"Missing env_var in provider config: {provider.value}")
            
        api_key = os.getenv(env_var)
        if not api_key:
            # In test environment, use a default test key
            if os.getenv('PYTEST_CURRENT_TEST'):
                api_key = f"sk-{provider.value}-test-key"
                os.environ[env_var] = api_key
                logger.info("test.using_mock_key", provider=provider.value)
            else:
                raise ValueError(f"Missing API key environment variable: {env_var}")
        
        # Initialize logger
        self.logger = structlog.get_logger(
            agent=self._get_agent_name(),
            provider=provider.value
        )

    @abstractmethod
    def _get_system_message(self) -> str:
        """Get system message for this agent type"""
        raise NotImplementedError()
        
    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get name for this agent type"""
        raise NotImplementedError()

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format request message"""
        if not isinstance(context, dict):
            return "Error: Invalid input"
        return str(context)

    def _create_standard_response(self, success: bool, data: Dict[str, Any], error: Optional[str] = None) -> AgentResponse:
        """Create standardized response format"""
        return AgentResponse(
            success=success,
            data={
                "raw_output": data,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed" if success else "failed"
            },
            error=error
        )

    async def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process context with LLM"""
        if not isinstance(context, dict):
            return self._create_standard_response(
                False,
                {},
                "Invalid input: context must be a dictionary"
            )

        provider_config = self.config['providers'][self.provider.value]

        for attempt in range(self.max_retries):
            try:
                self.logger.info("request.sending", 
                               provider=self.provider.value,
                               model=self.model,
                               attempt=attempt + 1)
                
                response = await acompletion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_message()},
                        {"role": "user", "content": self._format_request(context)}
                    ],
                    temperature=self.temperature,
                    api_base=provider_config["api_base"],
                    api_key=os.getenv(provider_config["env_var"])
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    self.logger.info("request.success",
                                   provider=self.provider.value,
                                   content_length=len(content))
                    
                    return self._create_standard_response(
                        True,
                        {"response": content, "raw_output": response}
                    )
                    
            except Exception as e:
                error_msg = str(e)
                self.logger.error("request.failed",
                                provider=self.provider.value,
                                error=error_msg,
                                attempt=attempt + 1)
                
                if attempt == self.max_retries - 1:
                    return self._create_standard_response(
                        False,
                        {},
                        error_msg
                    )

        return self._create_standard_response(
            False,
            {},
            "Maximum retries exceeded"
        )