# src/agents/simple_base.py

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from autogen_core import oai
from autogen_agentchat import AssistantAgent, UserProxyAgent

@dataclass
class SimpleResponse:
    """Minimal response wrapper"""
    success: bool
    message: str
    error: Optional[str] = None

class SimpleAgent:
    """Minimal single-shot agent using AutoGen 0.4.0.dev4"""
    
    def __init__(self):
        """Initialize with basic configuration"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
            
        config_list = [{
            "model": "gpt-4-turbo-preview",
            "api_key": api_key,
            "base_url": "https://api.openai.com/v1"
        }]

        llm_config = {
            "config_list": config_list,
            "cache_seed": None,  # Disable caching
            "temperature": 0
        }
        
        # Initialize agents for 0.4.0.dev4
        self.assistant = AssistantAgent(
            name="simple_assistant",
            system_message="You are a simple test agent. Respond briefly to any message.",
            llm_config=llm_config
        )
        
        self.user = UserProxyAgent(
            name="simple_user",
            human_input_mode="NEVER",
            llm_config=None,
            code_execution_config={"use_docker": False}
        )
    
    async def simple_chat(self, message: str) -> SimpleResponse:
        """Make a single agent exchange"""
        try:
            # Reset states
            self.assistant.reset()
            self.user.reset()
            
            # Single message exchange with 0.4.0.dev4 syntax
            response = await self.user.a_initiate_chat(
                recipient=self.assistant,
                message=message,
                silent=True
            )
            
            # Extract last message with 0.4.0.dev4 format
            if not response or not hasattr(response, 'last_message'):
                return SimpleResponse(
                    success=False,
                    message="",
                    error="No response received"
                )
                
            content = response.last_message.get('content') if isinstance(response.last_message, dict) else str(response.last_message)
                
            return SimpleResponse(
                success=True,
                message=content
            )
            
        except Exception as e:
            return SimpleResponse(
                success=False,
                message="",
                error=f"Error: {str(e)}"
            )

    def __del__(self):
        """Cleanup when agent is destroyed"""
        try:
            self.assistant.reset()
            self.user.reset()
        except:
            pass