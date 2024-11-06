# src/agents/base.py

from typing import Dict, Any, Optional, List, Union
from abc import ABC, abstractmethod
import structlog
import autogen
from dataclasses import dataclass

logger = structlog.get_logger()

@dataclass
class AgentResponse:
    """Standard response format for all agents"""
    success: bool
    data: Dict[str, Any]  # Always required, even if empty
    error: Optional[str] = None

class SingleShotAgent(ABC):
    """Base class for single-shot agents using Autogen"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with Autogen agents"""
        if not config_list:
            raise ValueError("Config list is required")

        # Initialize Autogen agents
        self.assistant = autogen.AssistantAgent(
            name=self._get_agent_name(),
            llm_config={"config_list": config_list},
            system_message=self._get_system_message()
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="coordinator",
            human_input_mode="NEVER",
            code_execution_config=False,
            max_consecutive_auto_reply=0
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
        """Format the request message for the agent"""
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return str(intent)

    def _extract_last_message(self, chat_response: Any) -> Optional[str]:
        """Safely extract last assistant message"""
        try:
            if not chat_response:
                logger.warning(f"{self._get_agent_name()}.no_chat_response")
                return None

            # Get messages from Autogen response
            messages = getattr(chat_response, 'messages', [])
            if messages:
                logger.debug(f"{self._get_agent_name()}.messages_found", 
                           count=len(messages))
                for msg in reversed(messages):
                    if 'content' in msg and msg.get('role', '') == 'assistant':
                        return msg['content']

            # Try last_message
            last_message = getattr(chat_response, 'last_message', None)
            if last_message and isinstance(last_message, dict):
                logger.debug(f"{self._get_agent_name()}.using_last_message")
                return last_message.get('content')

            # Try reply
            reply = getattr(chat_response, 'reply', None)
            if reply:
                logger.debug(f"{self._get_agent_name()}.using_reply")
                return str(reply)

            # If we have the chat_response as string
            if hasattr(chat_response, '__str__'):
                return str(chat_response)

            logger.warning(f"{self._get_agent_name()}.no_message_found")
            return None
            
        except Exception as e:
            logger.error(f"{self._get_agent_name()}.message_extraction_failed", 
                        error=str(e))
            return None

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process an intent with single-shot Autogen interaction"""
        try:
            # Validate input
            if not isinstance(intent, dict):
                return AgentResponse(
                    success=False,
                    data={},
                    error="Invalid input: intent must be a dictionary"
                )

            # Format request message
            message = self._format_request(intent)
            logger.debug(f"{self._get_agent_name()}.sending_message", 
                        message=message)
            
            # Single Autogen interaction with explicit reply handling
            chat_response = await self.coordinator.a_initiate_chat(
                recipient=self.assistant,
                message=message,
                max_turns=1
            )

            # Try to get response content
            response_content = self._extract_last_message(chat_response)
            
            # If we have any kind of response, consider it a success
            if response_content:
                logger.debug(f"{self._get_agent_name()}.response_received", 
                           content_length=len(response_content))
                return AgentResponse(
                    success=True,
                    data={"response": response_content}
                )
            
            logger.error(f"{self._get_agent_name()}.no_response")
            return AgentResponse(
                success=False,
                data={},
                error="No response received from assistant"
            )
                
        except Exception as e:
            logger.error(f"{self._get_agent_name()}.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )