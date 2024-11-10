# src/agents/base.py

from typing import Dict, Any, Optional, List, Union
from abc import ABC, abstractmethod
import structlog
from dataclasses import dataclass
import json
import os
from datetime import datetime
from autogen import AssistantAgent, UserProxyAgent

logger = structlog.get_logger()

@dataclass
class AgentResponse:
    """Standard response format for all agents"""
    success: bool
    data: Dict[str, Any]  # Always required, even if empty
    error: Optional[str] = None
    metadata: Dict[str, Any] = None  # Optional metadata for tracking

class BaseAgent(ABC):
    """Abstract base agent class"""
    
    @abstractmethod
    def _get_agent_name(self) -> str:
        """Get name for this agent type"""
        raise NotImplementedError()
    
    @abstractmethod
    def _get_system_message(self) -> str:
        """Get system message for this agent type"""
        raise NotImplementedError()

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format the request message for the agent
        
        Args:
            intent: Intent dictionary to format
        
        Returns:
            Formatted message string
        """
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return str(intent)

class SingleShotAgent(BaseAgent):
    """Base class for single-shot agents using Autogen 0.3.1"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with Autogen agents
        
        Args:
            config_list: List containing OpenAI configuration dict
        """
        if not config_list:
            raise ValueError("Config list is required")

        # Initialize Autogen agents
        self.assistant = AssistantAgent(
            name=self._get_agent_name(),
            llm_config={
                "config_list": config_list,
                "temperature": 0,
                "request_timeout": 120,
            },
            system_message=self._get_system_message()
        )
        
        # Use non-interactive proxy without code execution
        self.coordinator = UserProxyAgent(
            name="coordinator",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": None,  # Disable code execution
                "use_docker": False
            },
            max_consecutive_auto_reply=0
        )

        # Initialize logger with bound context
        self.logger = structlog.get_logger().bind(agent=self._get_agent_name())

    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from text that might contain markdown or other content
        
        Args:
            text: Text that might contain JSON
            
        Returns:
            Parsed JSON dict or None if no valid JSON found
        """
        try:
            # Clean up text
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
                
            return json.loads(text)
            
        except json.JSONDecodeError:
            # Try to extract JSON between curly braces
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
            return None

    def _extract_response(self, last_message: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extract and parse agent response
        
        Args:
            last_message: The last message from the conversation
            
        Returns:
            Parsed response data or None if invalid
        """
        try:
            if not last_message:
                self.logger.warning(f"{self._get_agent_name()}.no_message")
                return None

            content = last_message.get('content', '')
            if not content:
                self.logger.warning(f"{self._get_agent_name()}.empty_content")
                return None

            # Extract JSON if present
            json_data = self._extract_json_from_text(content)
            if json_data:
                return json_data
                
            # Return raw content if no JSON found
            return {"response": content}
            
        except Exception as e:
            self.logger.error(f"{self._get_agent_name()}.extraction_failed", 
                            error=str(e))
            return None

    async def process(self, intent: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process an intent with single-shot Autogen interaction
        
        Args:
            intent: Intent dictionary to process
            
        Returns:
            AgentResponse containing processing results
        """
        try:
            # Validate input
            if not isinstance(intent, dict):
                return AgentResponse(
                    success=False,
                    data={},
                    error="Invalid input: intent must be a dictionary",
                    metadata={"timestamp": datetime.utcnow().isoformat()}
                )

            # Format request message
            message = self._format_request(intent)
            self.logger.debug(f"{self._get_agent_name()}.sending_message", 
                            message=message)
            
            # Initialize chat
            chat_response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=message,
                clear_history=True
            )

            # Get the last message
            last_message = self.coordinator.last_message()
            
            # Extract and validate response
            response_data = self._extract_response(last_message)
            
            if response_data:
                self.logger.debug(f"{self._get_agent_name()}.response_received", 
                           content=str(response_data))
                return AgentResponse(
                    success=True,
                    data={"response": response_data},
                    metadata={
                        "timestamp": datetime.utcnow().isoformat(),
                        "chat_messages": len(chat_response.chat_messages) if chat_response else 0
                    }
                )
            
            self.logger.error(f"{self._get_agent_name()}.no_valid_response")
            return AgentResponse(
                success=False,
                data={},
                error="No valid response received from assistant",
                metadata={"timestamp": datetime.utcnow().isoformat()}
            )
                
        except Exception as e:
            self.logger.error(f"{self._get_agent_name()}.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e),
                metadata={"timestamp": datetime.utcnow().isoformat()}
            )