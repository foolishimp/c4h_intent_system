# src/agents/base.py

from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from litellm import acompletion
import json
from typing import Dict, Any, Optional
from enum import Enum
import structlog
import os

logger = structlog.get_logger()

class LLMProvider(str, Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"

class ModelConfig:
    """Model configuration and defaults"""
    MODELS = {
        LLMProvider.ANTHROPIC: "claude-3-opus-20240229",  # Most capable model
        # Alternative Claude models:
        # "claude-3-sonnet-20240229" - Good balance of intelligence and speed
        # "claude-3-haiku-20240307" - Fastest response times
        LLMProvider.OPENAI: "gpt-4-turbo-preview",
        LLMProvider.GEMINI: "gemini-1.5-pro"  # Updated to pro version
    }
    
    # You can specify a specific model by setting alternate defaults:
    CLAUDE_MODELS = {
        "opus": "claude-3-opus-20240229",     # Most intelligent, best for complex tasks
        "sonnet": "claude-3.5-sonnet-20241022", # Balanced performance
        "haiku": "claude-3-haiku-20240307"    # Fastest, good for simple tasks
    }
    
    ENV_VARS = {
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.OPENAI: "OPENAI_API_KEY",
        LLMProvider.GEMINI: "GEMINI_API_KEY"
    }

    PROVIDER_CONFIG = {
        LLMProvider.ANTHROPIC: {
            "api_base": "https://api.anthropic.com",
            "context_length": 200000  # Updated context length for Claude 3
        },
        LLMProvider.OPENAI: {
            "api_base": "https://api.openai.com/v1",
            "context_length": 128000
        },
        LLMProvider.GEMINI: {
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "context_length": 32000
        }
    }

    @classmethod
    def get_claude_model(cls, type: str = "opus") -> str:
        """Get specific Claude model by type"""
        return cls.CLAUDE_MODELS.get(type, cls.CLAUDE_MODELS["opus"])

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
                 max_retries: int = 3):
        """Initialize agent with provider configuration"""
        self.provider = provider
        self.model = model or ModelConfig.MODELS[provider]
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Verify API key availability
        self._verify_api_key(provider)
        
        # Get provider configuration
        self.provider_config = ModelConfig.PROVIDER_CONFIG[provider]
        
        # Initialize logger
        self.logger = structlog.get_logger(
            agent=self._get_agent_name(),
            provider=provider.value
        )

    def _verify_api_key(self, provider: LLMProvider) -> None:
        """Verify required API key is available"""
        env_var = ModelConfig.ENV_VARS[provider]
        if not os.getenv(env_var):
            raise ValueError(f"Missing required API key: {env_var}")

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

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process intent with LLM"""
        if not isinstance(intent, dict):
            return AgentResponse(
                success=False,
                data={},
                error="Invalid input: intent must be a dictionary"
            )

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
                    api_base=self.provider_config["api_base"]
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    parsed = self._parse_response(content)
                    
                    self.logger.info("request.success",
                                   provider=self.provider.value,
                                   content_length=len(content))
                    
                    return AgentResponse(
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
                    return AgentResponse(
                        success=False,
                        data={},
                        error=error_msg
                    )

        return AgentResponse(
            success=False,
            data={},
            error="Maximum retries exceeded"
        )