"""
Base agent implementation supporting multiple LLM providers.
Path: src/agents/base.py
"""

from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from litellm import completion
import json
from typing import Dict, Any, Optional, List
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
    
class BaseAgent(ABC):
    def __init__(self, 
                 provider: LLMProvider,
                 model: str,  # Now required
                 temperature: float = 0,
                 max_retries: int = 3,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize agent with provider configuration"""
        self.provider = provider
        self.model = model  # No default model logic here
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Only validate provider config exists
        if not config or 'providers' not in config:
            raise ValueError("Provider configuration required")
            
        provider_config = config.get('providers', {}).get(provider.value)
        if not provider_config:
            raise ValueError(f"Configuration missing for provider: {provider.value}")
        
        self.config = config

    def _get_provider_model(self, model: Optional[str] = None) -> str:
        """Get appropriate model name from config or provided model"""
        if model:
            return model
            
        # Get from config
        llm_config = self.config.get('llm_config', {})
        
        # First check if there's a specific agent model configured
        agent_name = self._get_agent_name()
        agent_config = llm_config.get('agents', {}).get(agent_name, {})
        if agent_config.get('model'):
            return agent_config['model']
        
        # Fall back to default model for the provider
        if self.provider.value == llm_config.get('default_provider'):
            return llm_config.get('default_model')
        
        # If no specific model found, raise error
        raise ValueError(
            f"No model specified for provider {self.provider.value} "
            f"and agent {agent_name}. Please specify in config."
        )

    def _format_messages(self, user_content: str) -> List[Dict[str, str]]:
        """Format messages based on provider requirements"""
        system_msg = self._get_system_message()
        
        if self.provider == LLMProvider.GEMINI:
            # Gemini doesn't support system messages directly
            combined = f"{system_msg}\n\nUser request: {user_content}"
            return [{"role": "user", "content": combined}]
        else:
            return [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content}
            ]

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
        timestamp = datetime.utcnow().isoformat()
        
        # Log the complete response data
        logger.debug("agent.response_data",
                    success=success,
                    data_keys=list(data.keys()) if data else None,
                    error=error,
                    timestamp=timestamp)
                    
        return AgentResponse(
            success=success,
            data={
                **data,  # Preserve all original data
                "timestamp": timestamp,
                "status": "completed" if success else "failed"
            },
            error=error
        )

    def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process context with LLM"""
        if not isinstance(context, dict):
            return self._create_standard_response(
                False,
                {},
                "Invalid input: context must be a dictionary"
            )

        provider_config = self.config['providers'][self.provider.value]
        api_key = os.getenv(provider_config["env_var"])
        if not api_key:
            return self._create_standard_response(
                False, 
                {},
                f"API key not found in environment: {provider_config['env_var']}"
            )
        
        # Log the request
        logger.debug("agent.request",
                    context_keys=list(context.keys()),
                    provider=self.provider.value,
                    model=self.model)

        for attempt in range(self.max_retries):
            try:
                self.logger.info("request.sending", 
                               provider=self.provider.value,
                               model=self.model,
                               attempt=attempt + 1)
                
                # Format request for logging
                formatted_request = self._format_request(context)
                logger.debug("agent.request_content",
                           system_message=self._get_system_message(),
                           user_message=formatted_request)
                
                response = completion(
                    model=self._get_provider_model(self.model),
                    messages=self._format_messages(formatted_request),
                    temperature=self.temperature,
                    api_base=provider_config["api_base"],
                    api_key=api_key
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    self.logger.info("request.success",
                                   provider=self.provider.value,
                                   content_length=len(content))
                                   
                    # Log full response for debugging
                    logger.debug("agent.llm_response",
                               content_preview=content[:200],
                               content_type=type(content).__name__)
                    
                    # Preserve both raw response and processed content
                    return self._create_standard_response(
                        True,
                        {
                            "response": content,  # The actual LLM response content
                            "raw_output": response,  # Complete litellm response object
                            "raw_content": content  # Duplicate for backwards compatibility
                        }
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