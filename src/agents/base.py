"""
Base agent implementation with integrated LiteLLM configuration.
Path: src/agents/base.py
"""

from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
from typing import Dict, Any, Optional, List
from functools import wraps
import time
import litellm
from litellm import completion

logger = structlog.get_logger()

class LogDetail(str, Enum):
    MINIMAL = "minimal"
    BASIC = "basic"
    DETAILED = "detailed" 
    DEBUG = "debug"
    
    @classmethod
    def from_str(cls, level: str) -> 'LogDetail':
        try:
            return cls(level.lower())
        except ValueError:
            return cls.BASIC  # Safe default

class LLMProvider(str, Enum):
    """Supported model providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"

@dataclass
class AgentResponse:
    """Standard response format"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

def log_operation(operation_name: str):
    """Operation logging decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            start_time = time.time()
            try:
                result = await func(self, *args, **kwargs)
                self._update_metrics(time.time() - start_time, True)
                return result
            except Exception as e:
                self._update_metrics(time.time() - start_time, False, str(e))
                raise
        return wrapper
    return decorator

class BaseAgent(ABC):
    """Base agent with integrated LiteLLM configuration"""
    
    def __init__(self,
                provider: LLMProvider,
                model: str, 
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None):
        """Initialize with provider configuration"""
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.config = config or {}
        
        # Validate and setup provider config
        self._setup_provider()
        
        # Configure litellm for this agent
        self._setup_litellm()
        
        # Initialize metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0, 
            "failed_requests": 0,
            "total_duration": 0.0,
            "last_error": None
        }
    
        # Set logging level with safe conversion
        log_level = self.config.get("logging", {}).get("agent_level", "basic")
        self.log_level = LogDetail.from_str(log_level)
        
        self.logger = structlog.get_logger().bind(
            agent_type=self._get_agent_name(),
            provider=provider.value,
            model=model
        )

    def _should_log(self, level: LogDetail) -> bool:
        """Check if should log at this level"""
        log_levels = {
            LogDetail.MINIMAL: 0,
            LogDetail.BASIC: 1, 
            LogDetail.DETAILED: 2,
            LogDetail.DEBUG: 3
        }
        return log_levels[level] <= log_levels[self.log_level]

    def _setup_provider(self) -> None:
        """Setup provider configuration"""
        provider_config = self.config.get("providers", {}).get(self.provider.value)
        if not provider_config:
            raise ValueError(f"No configuration for provider: {self.provider}")
            
        # Allow any model if valid_models not specified
        valid_models = provider_config.get("valid_models")
        if valid_models and self.model not in valid_models:
            raise ValueError(f"Invalid model {self.model} for provider {self.provider}")
            
        self.provider_config = provider_config

    def _setup_litellm(self) -> None:
        """Configure litellm for this agent"""
        litellm_config = self.provider_config.get("litellm_params", {})
        
        for key, value in litellm_config.items():
            setattr(litellm, key, value)
            
        # Set model format based on provider
        if self.provider == LLMProvider.OPENAI:
            self.model_str = self.model  # OpenAI doesn't need prefix
        else:
            self.model_str = f"{self.provider.value}/{self.model}"

    def _update_metrics(self, duration: float, success: bool, error: Optional[str] = None) -> None:
        """Update agent metrics"""
        self.metrics["total_requests"] += 1
        self.metrics["total_duration"] += duration
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            self.metrics["last_error"] = error

    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        pass

    def _get_system_message(self) -> str:
        """Get system message from config"""
        return self.config.get("llm_config", {}).get("agents", {}).get(
            self._get_agent_name(), {}).get("prompts", {}).get("system", "")

    def _get_prompt(self, prompt_type: str) -> str:
        """Get prompt template by type"""
        prompts = self.config.get("llm_config", {}).get("agents", {}).get(
            self._get_agent_name(), {}).get("prompts", {})
        if prompt_type not in prompts:
            raise ValueError(f"No prompt template found for type: {prompt_type}")
        return prompts[prompt_type]

    def _ensure_loop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Synchronous process interface"""
        loop = self._ensure_loop()
        return loop.run_until_complete(self._process_async(context))

    async def _process_async(self, context: Dict[str, Any]) -> AgentResponse:
        """Internal async implementation"""
        try:
            messages = [
                {"role": "system", "content": self._get_system_message()},
                {"role": "user", "content": self._format_request(context)}
            ]
            
            response = completion(  # Removed await since completion is sync
                model=self.model_str,
                messages=messages,
                temperature=self.temperature,
                api_base=self.provider_config.get("api_base")
            )

            if response and response.choices:
                content = response.choices[0].message.content
                return AgentResponse(
                    success=True,
                    data=self._process_response(content, response)
                )
                
        except Exception as e:
            logger.error("process.failed", error=str(e))
            return AgentResponse(success=False, data={}, error=str(e))
        
    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request message"""
        return str(context)

    def _process_response(self, content: str, raw_response: Any) -> Dict[str, Any]:
        """Process LLM response"""
        return {
            "response": content,
            "raw_output": raw_response,
            "timestamp": datetime.utcnow().isoformat()
        }