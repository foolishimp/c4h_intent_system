# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List 
import structlog
import autogen
import os

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution architect that provides concrete code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]

        self.assistant = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a solution architect that creates concrete code changes.
            For each file:
            - Small files (<100 lines): Provide complete new content
            - Large files: Provide unified diff
            Always return a JSON object with an actions array."""
        )
        
        # Create coordinator with specific termination message
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False,
            # Define clear termination 
            is_termination_msg=lambda x: True,  # Terminate after first response
        )

    async def analyze(self, context: Dict[str, Any]) -> str:
        """Generate concrete code changes to fulfill the intent"""
        if not context.get("discovery_output", {}).get("discovery_output"):
            raise ValueError("Missing discovery output")

        # Just get the first message - no continued conversation
        response = await self.coordinator.a_initiate_chat(
            self.assistant,
            message=f"""Based on this intent and code, generate changes needed.

            INTENT:
            {context['intent']}

            CURRENT CODE:
            {context['discovery_output']['discovery_output']}

            Return a JSON object containing an actions array with file changes."""
        )

        # Get the first response from the assistant
        messages = response.chat_messages.get(self.assistant.name, [])
        if not messages:
            raise ValueError("No response received from assistant")
            
        return messages[0]["content"]