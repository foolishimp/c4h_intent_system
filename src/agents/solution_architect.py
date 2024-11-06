# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import os

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution architect that provides concrete code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with AutoGen config"""
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
            Always return a JSON object with an 'actions' array containing file changes."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate concrete code changes to fulfill the intent"""
        intent = context.get("intent")
        discovery_output = context.get("discovery_output", {}).get("discovery_output")
        
        if not discovery_output:
            raise ValueError("Missing discovery output")

        logger.info("architect.analyzing", intent=intent)
        
        # Get single response from AutoGen
        try:
            response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=f"""Based on this intent and code, generate changes needed.

                INTENT:
                {intent}

                CURRENT CODE:
                {discovery_output}

                Return a JSON object with an 'actions' array containing:
                {{
                    "actions": [
                        {{
                            "file": "path/to/file",
                            "content": "complete file contents"
                        }}
                    ]
                }}""",
                max_turns=1  # Ensure only one response
            )
            
            # Extract the last assistant message
            assistant_msgs = [msg for msg in response.chat_messages if msg["role"] == "assistant"]
            if assistant_msgs:
                return {"actions": assistant_msgs[-1]["content"]}
            return {"actions": []}
            
        except Exception as e:
            logger.error("architect.analysis_failed", error=str(e))
            raise