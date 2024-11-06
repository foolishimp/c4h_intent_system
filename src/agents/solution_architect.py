# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import os
from skills.semantic_interpreter import SemanticInterpreter

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution architect that provides concrete code changes using diffs for efficiency"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with LLM config and semantic skills"""
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]

        # Initialize main solution architect LLM
        self.assistant = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a solution architect that creates concrete code changes.
            For small files, provide complete content.
            For large files (>100 lines), provide unified diff format changes.
            Always maintain existing functionality unless explicitly part of the changes.
            All responses must be JSON formatted."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

        self.interpreter = SemanticInterpreter(config_list)

    def _extract_last_message(self, chat_result: Any) -> Optional[str]:
        """Extract the last assistant message from chat response"""
        try:
            # Handle different AutoGen response formats
            if hasattr(chat_result, 'last_message'):
                return chat_result.last_message.get('content', '')
            
            messages = (getattr(chat_result, 'messages', None) or 
                       getattr(chat_result, 'chat_messages', []))
            
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "")
            return None
            
        except Exception as e:
            logger.error("message_extraction.failed", error=str(e))
            return None

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate concrete code changes to fulfill the intent"""
        try:
            intent = context.get("intent")
            discovery_output = context.get("discovery_output", {}).get("discovery_output")
            
            if not discovery_output:
                raise ValueError("Missing discovery output")

            logger.info("architect.analyzing", intent=intent)
            
            # Get solution with concrete code changes
            response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=f"""Based on this intent and code, generate a JSON object containing an actions array.
                For small files provide complete content, for large files provide unified diffs.

                INTENT:
                {intent}

                CURRENT CODE:
                {discovery_output}

                Example response format:
                {{
                    "actions": [
                        {{
                            "file_path": "path/to/small/file.ext",
                            "type": "content",
                            "content": "complete file content here"
                        }},
                        {{
                            "file_path": "path/to/large/file.ext",
                            "type": "diff",
                            "diff": "@@ -1,5 +1,7 @@\\n line1\\n+new line\\n line2"
                        }}
                    ]
                }}""",
                max_turns=1
            )
            
            last_message = self._extract_last_message(response)
            if not last_message:
                logger.warning("architect.no_response")
                return {"actions": [], "context": {"error": "No response received"}}
            
            # Extract actions array
            interpretation = await self.interpreter.interpret(
                content=last_message,
                prompt="Return the actions array from the response. If no valid actions exist, return {'actions': []}",
                context_type="code_changes"
            )
            
            actions = interpretation.data.get("actions", [])
            if not actions:
                logger.info("architect.no_changes_needed")
            
            return {
                "actions": actions,
                "context": {
                    "raw_solution": last_message,
                    "interpretation": interpretation.raw_response
                }
            }

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise