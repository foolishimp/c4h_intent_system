# src/agents/base.py

from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
import autogen_core
import autogen_agentchat
from autogen_agentchat.agent import AssistantAgent, UserProxyAgent

@dataclass
class AgentResponse:
    """Standard response format for all agents"""
    success: bool
    content: str  # Raw LLM response
    error: Optional[str] = None

class SingleShotAgent(ABC):
    """Base class for single-shot agents using AutoGen 0.4"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize the agent with AutoGen configuration"""
        if not config_list:
            raise ValueError("Config list is required")

        # Basic LLM configuration
        self.config = {
            "cache_seed": None,  # Disable caching
            "temperature": 0,
            "config_list": config_list,
            "timeout": 120,
        }
        
        # Initialize agents with AutoGen 0.4 syntax
        self.assistant = AssistantAgent(
            name=self._get_agent_name(),
            system_message=self._get_system_message(),
            llm_config=self.config
        )
        
        self.coordinator = UserProxyAgent(
            name="coordinator",
            human_input_mode="NEVER",
            code_execution_config={"use_docker": False},
            llm_config=None,  # Changed from False to None for 0.4
            default_auto_reply=None  # Changed from empty string to None
        )

        self.logger = structlog.get_logger().bind(agent=self._get_agent_name())
        
    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get the name for this agent type"""
        raise NotImplementedError()
    
    @abstractmethod
    def _get_system_message(self) -> str:
        """Get the system message for this agent type"""
        raise NotImplementedError()

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format the request message"""
        if not isinstance(intent, dict):
            return "Error: Invalid input - intent must be a dictionary"
        return str(intent)

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process an intent and return raw response"""
        try:
            if not isinstance(intent, dict):
                return AgentResponse(
                    success=False,
                    content="",
                    error="Invalid input: intent must be a dictionary"
                )

            message = self._format_request(intent)
            self.logger.debug("sending_request", message=message)
            
            # Reset history before new chat
            self.assistant.reset()
            self.coordinator.reset()
            
            # Single interaction
            chat_response = await self.coordinator.a_initiate_chat(
                recipient=self.assistant,
                message=message,
                silent=True  # Added for 0.4
            )
            
            # Get raw response using AutoGen 0.4 message access
            last_message = chat_response.last_message if chat_response else None
            
            if not last_message:
                return AgentResponse(
                    success=False,
                    content="",
                    error="No response received"
                )

            if isinstance(last_message, dict):
                content = last_message.get('content', '')
            else:
                content = str(last_message)

            return AgentResponse(
                success=True,
                content=content
            )
                
        except Exception as e:
            self.logger.error("processing_failed", error=str(e))
            return AgentResponse(
                success=False,
                content="",
                error=f"Processing failed: {str(e)}"
            )

    def __del__(self):
        """Cleanup when agent is destroyed"""
        try:
            self.assistant.reset()
            self.coordinator.reset()
        except:
            pass