# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import os
from skills.semantic_interpreter import SemanticInterpreter
from skills.semantic_loop import SemanticLoop

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution architect using semantic interpretation for flexible analysis"""
    
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
            system_message="""You are a solution architect that creates refactoring plans.
            When analyzing code and proposing changes:
            1. Describe each change clearly in natural language
            2. Specify which files need modification
            3. Explain the rationale for each change
            4. Note any potential risks or concerns
            5. Suggest any necessary validations
            """
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

        # Initialize semantic skills
        self.interpreter = SemanticInterpreter(config_list)
        self.semantic_loop = SemanticLoop(config_list)

    def _extract_last_message(self, response: autogen.ConversableAgent) -> Optional[str]:
        """Extract the last assistant message from chat response"""
        try:
            # Get the last message from chat history
            if hasattr(response, 'chat_history'):
                history = response.chat_history
            else:
                history = response.messages if hasattr(response, 'messages') else []

            # Find last assistant message
            for message in reversed(history):
                if isinstance(message, dict) and message.get("role") == "assistant":
                    return message.get("content", "")
            return None
        except Exception as e:
            logger.error("message_extraction.failed", error=str(e))
            return None

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce refactoring actions with semantic validation"""
        try:
            intent = context.get("intent")
            discovery_output = context.get("discovery_output", {}).get("discovery_output")
            
            if not discovery_output:
                raise ValueError("Missing discovery output")

            logger.info("architect.analyzing", intent=intent)
            
            # Get solution from LLM
            response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=f"""Analyze this code and propose changes:

                INTENT:
                {intent}

                CODEBASE:
                {discovery_output}

                Provide a detailed description of:
                1. Which files need to change
                2. What changes are needed in each file
                3. How the changes fulfill the intent
                4. Any potential risks or special considerations
                """,
                max_turns=1
            )
            
            # Extract last message
            last_message = self._extract_last_message(response)
            if not last_message:
                raise ValueError("No response received from solution architect")
            
            # Use semantic interpreter to structure the solution
            interpretation = await self.interpreter.interpret(
                content=last_message,
                prompt="""Convert this solution into a structured format with:
                {
                    "files": [
                        {
                            "path": "file path",
                            "changes": [
                                {
                                    "type": "change type (e.g., add_import, add_logging)",
                                    "content": "actual change content"
                                }
                            ]
                        }
                    ],
                    "validation": [
                        {
                            "type": "validation type",
                            "description": "what to validate"
                        }
                    ],
                    "risks": [
                        {
                            "type": "risk type",
                            "description": "risk description",
                            "mitigation": "how to mitigate"
                        }
                    ]
                }""",
                context_type="solution_analysis"
            )
            
            return {
                "solution": interpretation.data,
                "context": {
                    "raw_solution": last_message,
                    "interpretation": interpretation.raw_response,
                    "original_intent": intent,
                }
            }

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise