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
from typing import Dict, Any, Optional, List, Literal
from functools import wraps
import time
import litellm
from litellm import completion
from config import locate_config

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

@dataclass
class AgentConfig:
    """Configuration requirements for base agent"""
    provider: Literal['anthropic', 'openai', 'gemini']
    model: str
    temperature: float = 0
    api_base: Optional[str] = None
    context_length: Optional[int] = None

class BaseAgent:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize agent with raw config dictionary."""
        self.config = config or {}
        
        # Extract and validate config for this agent
        agent_config = self._get_agent_config()
        
        # Set provider and model
        self.provider = LLMProvider(agent_config.get('provider', 'anthropic'))
        self.model = agent_config.get('model', 'claude-3-opus-20240229')
        self.temperature = agent_config.get('temperature', 0)
        
        # Initialize metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration": 0.0,
            "last_error": None,
            "start_time": datetime.utcnow().isoformat()
        }

        # Set logging detail level from config
        log_level = self.config.get('logging', {}).get('agent_level', 'basic')
        self.log_level = LogDetail.from_str(log_level)
        
        # Build model string and setup LiteLLM
        self.model_str = self._get_model_str()
        self._setup_litellm(self._get_provider_config(self.provider))
        
        # Initialize logger with context
        self.logger = structlog.get_logger().bind(
            agent=self._get_agent_name(),
            provider=str(self.provider),
            model=self.model,
            log_level=str(self.log_level)
        )
        
        logger.info(f"{self._get_agent_name()}.initialized",
                   provider=str(self.provider),
                   model=self.model,
                   log_level=str(self.log_level))

    def _resolve_model(self, explicit_model: Optional[str], provider_config: Dict[str, Any]) -> str:
        """Resolve model using fallback chain"""
        # 1. Use explicitly passed model if provided
        if explicit_model:
            return explicit_model
            
        # 2. Check agent-specific config
        agent_config = self.config.get("llm_config", {}).get("agents", {}).get(self._get_agent_name(), {})
        if "model" in agent_config:
            return agent_config["model"]
            
        # 3. Use provider's default model
        if "default_model" in provider_config:
            return provider_config["default_model"]
            
        # 4. Use system-wide default model
        system_default = self.config.get("llm_config", {}).get("default_model")
        if system_default:
            return system_default
        
        raise ValueError(f"No model specified for provider {self.provider} and no defaults found")

    def _get_model_str(self) -> str:
        """Get the appropriate model string for the provider"""
        if self.provider == LLMProvider.OPENAI:
            # OpenAI models don't need provider prefix
            return self.model
        elif self.provider == LLMProvider.ANTHROPIC:
            # Anthropic models need anthropic/ prefix
            return f"anthropic/{self.model}"
        elif self.provider == LLMProvider.GEMINI:
            # Gemini models need google/ prefix
            return f"google/{self.model}"
        else:
            # Safe fallback
            return f"{self.provider.value}/{self.model}"

    def _get_agent_config(self) -> Dict[str, Any]:
        """Extract relevant config for this agent."""
        try:
            # Use locate_config to find agent's settings
            agent_config = locate_config(self.config or {}, self._get_agent_name())
            
            # Get provider name - prefer agent specific over default
            provider_name = agent_config.get('provider', 
                                        self.config.get('llm_config', {}).get('default_provider'))
            
            # Get provider level config
            provider_config = self.config.get('providers', {}).get(provider_name, {})
            
            # Resolve model using proper chain
            model = self._resolve_model(agent_config.get('model'), provider_config)
            
            # Build complete config with correct override order
            config = {
                'provider': provider_name,
                'model': model,  # Using resolved model
                'temperature': 0,
                'api_base': provider_config.get('api_base'),
                'context_length': provider_config.get('context_length')
            }
            
            # Override with agent specific settings (most specific wins)
            config.update({
                k: v for k, v in agent_config.items() 
                if k in ['provider', 'temperature', 'api_base']  # Note: model handled separately
            })
            
            logger.debug("agent.config_loaded",
                        agent=self._get_agent_name(),
                        config=config)
                        
            return config

        except Exception as e:
            logger.error("agent.config_failed",
                        agent=self._get_agent_name(),
                        error=str(e))
            return {}

    def _get_provider_config(self, provider: LLMProvider) -> Dict[str, Any]:
        """Get provider configuration from system config"""
        return self.config.get("providers", {}).get(provider.value, {})

    def _should_log(self, level: LogDetail) -> bool:
        """Check if should log at this level"""
        log_levels = {
            LogDetail.MINIMAL: 0,
            LogDetail.BASIC: 1, 
            LogDetail.DETAILED: 2,
            LogDetail.DEBUG: 3
        }
        return log_levels[level] <= log_levels[self.log_level]

    def _setup_litellm(self, provider_config: Dict[str, Any]) -> None:
        """Configure litellm with provider settings"""
        litellm_config = provider_config.get("litellm_params", {})
        
        for key, value in litellm_config.items():
            setattr(litellm, key, value)
            
        if self._should_log(LogDetail.DEBUG):
            logger.debug("litellm.configured", 
                        provider=str(self.provider),
                        config=litellm_config)

    def _update_metrics(self, duration: float, success: bool, error: Optional[str] = None) -> None:
        """Update agent metrics"""
        self.metrics["total_requests"] += 1
        self.metrics["total_duration"] += duration
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            self.metrics["last_error"] = error

        if self._should_log(LogDetail.DETAILED):
            logger.info("agent.metrics_updated",
                       metrics=self.metrics,
                       duration=duration,
                       success=success)

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

    @log_operation("process")
    async def _process_async(self, context: Dict[str, Any]) -> AgentResponse:
        """Internal async implementation"""
        try:
            if self._should_log(LogDetail.DETAILED):
                logger.info("agent.processing",
                          context_keys=list(context.keys()) if context else None)

            messages = [
                {"role": "system", "content": self._get_system_message()},
                {"role": "user", "content": self._format_request(context)}
            ]
            
            response = completion(
                model=self.model_str,
                messages=messages,
                temperature=self.temperature,
                api_base=self._get_provider_config(self.provider).get("api_base")
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
        if self._should_log(LogDetail.DEBUG):
            logger.debug("agent.processing_response",
                        content_length=len(content) if content else 0,
                        response_type=type(raw_response).__name__)

        return {
            "response": content,
            "raw_output": raw_response,
            "timestamp": datetime.utcnow().isoformat()
        }