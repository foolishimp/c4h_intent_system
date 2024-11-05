# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import json
import os

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution Architect agent that produces refactoring actions using LLM"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize the solution architect with LLM config"""
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        # Add debug configuration for visibility
        llm_config = {
            "config_list": config_list,
            "log_level": "debug",  # Show prompts
            "logging_func": logger.debug,  # Use structlog
            "timeout": 120
        }
        
        self.assistant = autogen.AssistantAgent(
            name="solution_architect",
            llm_config=llm_config,
            system_message="""You are a solution architect that creates refactoring plans.
            Analyze the code and intent, then produce a series of merge actions.
            Each merge action must specify:
            - file_path: Path to the target file
            - changes: Unified diff of the changes
            Return ONLY a raw JSON object with an 'actions' array.
            Do not include markdown formatting or code blocks."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce refactoring actions"""
        try:
            intent = context.get("intent")
            discovery_output = context.get("discovery_output", {}).get("discovery_output")
            
            logger.info("architect.analyzing", intent=intent)
            
            if not discovery_output:
                raise ValueError("Missing discovery output")

            # Improved prompt formatting to avoid JSON parsing issues
            prompt = f"""
            REFACTORING REQUEST:
            {intent}
            
            CODEBASE:
            {discovery_output}
            
            Analyze the code and provide merge actions in this exact format:
            
            {{
                "actions": [
                    {{
                        "file_path": "path/to/file.py",
                        "changes": "unified diff format changes"
                    }}
                ]
            }}
            
            Important:
            1. Return ONLY the raw JSON
            2. No markdown, no code blocks
            3. No explanation text
            4. The response must start with {{
            """

            # Log the prompt for debugging
            logger.debug("architect.prompt", prompt=prompt)

            chat_response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=prompt,
                max_turns=1
            )

            # Log raw response for debugging
            for message in reversed(chat_response.chat_history):
                if message.get('role') == 'assistant':
                    response = message['content']
                    logger.debug("architect.raw_response", response=response)
                    try:
                        return json.loads(response.strip())
                    except json.JSONDecodeError as e:
                        logger.error("architect.json_parse_failed", 
                                   error=str(e),
                                   response=response,
                                   char_position=e.pos)
                        raise

            raise ValueError("No response from architect")

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise