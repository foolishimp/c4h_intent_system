# src/agents/base_lite.py

from typing import Dict, Any, Optional, List, Literal
from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from litellm import acompletion  # Changed to async completion
import json
from enum import Enum
import os
from datetime import datetime 

logger = structlog.get_logger()

class LLMProvider(str, Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"

class ModelConfig:
    """Model configuration and defaults"""
    MODELS = {
        LLMProvider.ANTHROPIC: "claude-3-sonnet-20240229",
        LLMProvider.OPENAI: "gpt-4-turbo-preview",
        LLMProvider.GEMINI: "gemini-pro"
    }
    
    ENV_VARS = {
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.OPENAI: "OPENAI_API_KEY",
        LLMProvider.GEMINI: "GEMINI_API_KEY"
    }

    PROVIDER_CONFIG = {
        LLMProvider.ANTHROPIC: {
            "api_base": "https://api.anthropic.com", # Remove /v1 as litellm adds it
            "api_version": "v1",
            "context_length": 100000
        },
        LLMProvider.OPENAI: {
            "api_base": "https://api.openai.com/v1",
            "context_length": 128000
        },
        LLMProvider.GEMINI: {
            "api_base": "https://generativelanguage.googleapis.com",
            "context_length": 32000
        }
    }

@dataclass
class AgentResponse:
    """Standard response format"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

class LiteAgent(ABC):
    """Base agent using LiteLLM"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: Optional[str] = None,
                 fallback_providers: Optional[List[LLMProvider]] = None,
                 temperature: float = 0,
                 max_retries: int = 3):
        """Initialize agent with provider configuration"""
        self.provider = provider
        self.model = model or ModelConfig.MODELS[provider]
        self.temperature = temperature
        self.fallback_providers = fallback_providers or []
        self.max_retries = max_retries
        
        # Verify API key availability
        self._verify_api_keys([provider] + (fallback_providers or []))
        
        # Get provider configuration
        self.provider_config = ModelConfig.PROVIDER_CONFIG[provider]
        
        # Initialize logger
        self.logger = structlog.get_logger(
            agent=self._get_agent_name(),
            provider=provider.value
        )

    def _verify_api_keys(self, providers: List[LLMProvider]) -> None:
        """Verify required API keys are available"""
        missing_keys = []
        for provider in providers:
            env_var = ModelConfig.ENV_VARS[provider]
            if not os.getenv(env_var):
                missing_keys.append(env_var)
        if missing_keys:
            raise ValueError(f"Missing required API keys: {', '.join(missing_keys)}")

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

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse and validate JSON response"""
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
            self.logger.error("json_parse_failed", error=str(e))
            return {"raw_message": content}

    def _prepare_messages(self, intent: Dict[str, Any]) -> List[Dict[str, str]]:
        """Prepare messages for LLM request"""
        return [
            {"role": "system", "content": self._get_system_message()},
            {"role": "user", "content": self._format_request(intent)}
        ]

    async def _try_provider(self, 
                          provider: LLMProvider, 
                          messages: List[Dict[str, str]]) -> Optional[AgentResponse]:
        """Try a single provider with retries"""
        for attempt in range(self.max_retries):
            try:
                self.logger.info("request.sending", 
                               provider=provider.value,
                               model=self.model,
                               attempt=attempt + 1)
                
                # Use async completion
                response = await acompletion(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    api_base=self.provider_config["api_base"]
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    parsed = self._parse_json_response(content)
                    
                    self.logger.info("request.success",
                                   provider=provider.value,
                                   content_length=len(content))
                    
                    return AgentResponse(
                        success=True,
                        data={"response": parsed}
                    )
                    
            except Exception as e:
                error_msg = str(e)
                self.logger.error("request.failed",
                                provider=provider.value,
                                error=error_msg,
                                attempt=attempt + 1)
                
                if attempt == self.max_retries - 1:
                    return AgentResponse(
                        success=False,
                        data={},
                        error=error_msg
                    )
                    
        return None

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process intent with fallback support"""
        if not isinstance(intent, dict):
            return AgentResponse(
                success=False,
                data={},
                error="Invalid input: intent must be a dictionary"
            )

        # Try providers in sequence
        providers = [self.provider] + self.fallback_providers
        last_error = None
        
        for provider in providers:
            config = ModelConfig.PROVIDER_CONFIG[provider]
            try:
                self.logger.info("request.sending", 
                               provider=provider.value,
                               model=self.model)
                
                response = await acompletion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_message()},
                        {"role": "user", "content": self._format_request(intent)}
                    ],
                    temperature=self.temperature,
                    api_base=config["api_base"]
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    parsed = self._parse_json_response(content)
                    
                    self.logger.info("request.success",
                                   provider=provider.value,
                                   content_length=len(content))
                    
                    return AgentResponse(
                        success=True,
                        data={"response": parsed}
                    )
                    
            except Exception as e:
                error_msg = str(e)
                self.logger.error("request.failed",
                                provider=provider.value,
                                error=error_msg)
                last_error = error_msg
                continue

        return AgentResponse(
            success=False,
            data={},
            error=f"All providers failed. Last error: {last_error}"
        )