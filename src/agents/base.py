# src/agents/base.py
"""
Base Agent Implementation for Intent-Based Architecture
Follows Microsoft AutoGen patterns for agent interactions

Key features:
- Async intent processing
- Structured logging
- Error handling with lineage preservation
- Configuration validation
- Resource lifecycle management
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from enum import Enum
import structlog
import asyncio
from datetime import datetime

from src.models.intent import Intent, IntentStatus, ResolutionState
from src.config import Config

class AgentState(str, Enum):
    """Agent lifecycle states"""
    INITIALIZED = "initialized"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"
    SHUTDOWN = "shutdown"

@dataclass
class AgentContext:
    """Shared context for agent operations"""
    agent_id: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    processed_intents: List[str] = field(default_factory=list)
    state: AgentState = AgentState.INITIALIZED
    metrics: Dict[str, Any] = field(default_factory=dict)

class BaseAgent(ABC):
    """Base class for all agents in the intent system
    
    Implements core agent functionality following Microsoft AutoGen patterns:
    - Async intent processing
    - Resource lifecycle management
    - Error handling with recovery
    - Metrics tracking
    - Configuration validation
    """
    
    def __init__(self, config: Config):
        """Initialize the agent with configuration"""
        self.config = config
        self.logger = structlog.get_logger()
        self.context = AgentContext(agent_id=self.__class__.__name__)
        self._validate_config()

    @asynccontextmanager
    async def lifecycle(self):
        """Manage agent lifecycle with proper resource cleanup"""
        try:
            await self.initialize()
            self.context.state = AgentState.READY
            yield self
        finally:
            await self.cleanup()
            self.context.state = AgentState.SHUTDOWN

    async def initialize(self) -> None:
        """Initialize agent resources and validate configuration"""
        self.logger.info("agent.initializing", 
                        agent_id=self.context.agent_id,
                        config=self.config.dict())
        await self._setup_resources()
        self.context.state = AgentState.INITIALIZED
        self.logger.info("agent.initialized")

    async def cleanup(self) -> None:
        """Cleanup agent resources"""
        self.logger.info("agent.cleanup", 
                        agent_id=self.context.agent_id,
                        metrics=self.context.metrics)

    @abstractmethod
    async def process_intent(self, intent: Intent) -> Intent:
        """Process an intent and return transformed result
        
        Must be implemented by concrete agent classes.
        """
        pass

    async def handle_error(self, error: Exception, intent: Intent) -> Intent:
        """Create error intent for debugging and recovery
        
        Maintains complete lineage for debugging and recovery flows.
        """
        self.context.state = AgentState.ERROR
        self.logger.exception("agent.error",
                            agent_id=self.context.agent_id,
                            intent_id=str(intent.id),
                            error=str(error))

        # Create debug intent while maintaining lineage
        debug_intent = intent.transformTo("debug")
        debug_intent.description = f"Error in {self.context.agent_id}: {str(error)}"
        debug_intent.context.update({
            "original_intent": intent.dict(),
            "error": str(error),
            "error_type": type(error).__name__,
            "agent_context": self.context.__dict__
        })
        debug_intent.criteria = {"resolve_error": True}
        debug_intent.status = IntentStatus.ERROR
        debug_intent.resolution_state = ResolutionState.SKILL_FAILURE

        # Track error in metrics
        self._update_metrics("errors", error)

        return debug_intent

    def _validate_config(self) -> None:
        """Validate agent configuration requirements"""
        if not self.config:
            raise ValueError(f"{self.context.agent_id} requires configuration")
        
        required_fields = ["agents", "providers", "master_prompt_overlay"]
        missing = [field for field in required_fields if not hasattr(self.config, field)]
        if missing:
            raise ValueError(f"Missing required config fields: {missing}")

    async def _setup_resources(self) -> None:
        """Setup agent resources and connections"""
        # Implement resource setup (e.g., LLM clients, caches, etc.)
        pass

    def _update_metrics(self, metric_name: str, value: Any) -> None:
        """Update agent metrics"""
        if metric_name not in self.context.metrics:
            self.context.metrics[metric_name] = []
        self.context.metrics[metric_name].append({
            "timestamp": datetime.utcnow().isoformat(),
            "value": str(value)
        })
