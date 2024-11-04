# src/agents/base.py

from typing import Dict, Any, Optional
import autogen
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

class AgentConfig(BaseModel):
    """Configuration for AutoGen agent"""
    name: str
    model: str = "gpt-4"
    temperature: float = 0
    system_message: str

class BaseAgent:
    """Base class for all agents in the system"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logger.bind(agent=config.name)
        
        # Initialize AutoGen agent
        self.agent = autogen.AssistantAgent(
            name=config.name,
            llm_config={
                "config_list": [{
                    "model": config.model,
                    "temperature": config.temperature,
                }],
            },
            system_message=config.system_message
        )
    
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process a request - to be implemented by concrete agents"""
        raise NotImplementedError()
