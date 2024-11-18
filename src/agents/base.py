"""
Base agent implementation.
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
        
        # Verify API key availability
        env_var = provider_config.get('env_var')
        if not env_var or not os.getenv(env_var):
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

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format request message"""
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return str(intent)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse and validate response content"""
        try:
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
                
            # Try to parse as JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract JSON from markdown
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                else:
                    return {"raw_message": content}
                    
        except Exception as e:
            self.logger.error("response_parse_failed", error=str(e))
            return {"raw_message": content}

    def _create_standard_response(self, success: bool, data: Dict[str, Any], error: Optional[str] = None) -> AgentResponse:
        """Create standardized response format"""
        return AgentResponse(
            success=success,
            data={
                "raw_output": data,  # Store full LLM response
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed" if success else "failed",
                **data  # Allow agents to add their specific data
            },
            error=error
        )

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process intent with LLM"""
        if not isinstance(intent, dict):
            return self._create_standard_response(
                success=False,
                data={},
                error="Invalid input: intent must be a dictionary"
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
                        {"role": "user", "content": self._format_request(intent)}
                    ],
                    temperature=self.temperature,
                    api_base=provider_config["api_base"]
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    parsed = self._parse_response(content)
                    
                    self.logger.info("request.success",
                                   provider=self.provider.value,
                                   content_length=len(content))
                    
                    return self._create_standard_response(
                        success=True,
                        data={"response": parsed}
                    )
                    
            except Exception as e:
                error_msg = str(e)
                self.logger.error("request.failed",
                                provider=self.provider.value,
                                error=error_msg,
                                attempt=attempt + 1)
                
                if attempt == self.max_retries - 1:
                    return self._create_standard_response(
                        success=False,
                        data={},
                        error=error_msg
                    )

        return self._create_standard_response(
            success=False,
            data={},
            error="Maximum retries exceeded"
        )
