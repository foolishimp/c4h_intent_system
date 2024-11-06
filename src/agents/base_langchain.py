# src/agents/base_langchain.py

from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

logger = structlog.get_logger()

@dataclass
class AgentResponse:
    """Standard response format for all agents"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

class SingleShotLangChainAgent(ABC):
    """Base class for single-shot agents using LangChain"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with LangChain chat model"""
        if not config_list:
            raise ValueError("Config list is required")
            
        self.api_key = config_list[0].get('api_key')
        self.model = config_list[0].get('model', 'gpt-4')
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found in config")
            
        self.chat = ChatOpenAI(
            model_name=self.model,
            openai_api_key=self.api_key,
            temperature=0
        )
        
        self.logger = structlog.get_logger(agent=self._get_agent_name())

    @abstractmethod
    def _get_system_message(self) -> str:
        """Get system message for this agent type"""
        raise NotImplementedError()
        
    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get name for this agent type"""
        raise NotImplementedError()

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format the request message for the agent"""
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return str(intent)

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process an intent with single LangChain interaction"""
        try:
            if not isinstance(intent, dict):
                return AgentResponse(
                    success=False,
                    data={},
                    error="Invalid input: intent must be a dictionary"
                )

            # Format messages
            messages = [
                SystemMessage(content=self._get_system_message()),
                HumanMessage(content=self._format_request(intent))
            ]
            
            # Get response
            self.logger.debug(f"{self._get_agent_name()}.sending_request")
            response = await self.chat.agenerate([messages])
            
            if response.generations:
                content = response.generations[0][0].text
                self.logger.debug(f"{self._get_agent_name()}.response_received",
                               content_length=len(content))
                return AgentResponse(
                    success=True,
                    data={"response": content}
                )
            
            return AgentResponse(
                success=False,
                data={},
                error="No response received"
            )
                
        except Exception as e:
            self.logger.error(f"{self._get_agent_name()}.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )