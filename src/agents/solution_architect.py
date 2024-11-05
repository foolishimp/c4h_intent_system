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
        
        self.assistant = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a solution architect that creates refactoring plans.
            Analyze the code and intent, then produce a series of merge actions.
            Each merge action must specify:
            - file_path: Path to the target file
            - changes: Unified diff of the changes
            Return ONLY a JSON object with an 'actions' array.
            Do not include any explanatory text or markdown formatting."""
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

            prompt = f"""
            REFACTORING REQUEST:
            {intent}
            
            CODEBASE:
            {discovery_output}
            
            Analyze the code and provide merge actions in this format:
            {{
                "actions": [
                    {{
                        "file_path": "path/to/file.py",
                        "changes": "unified diff format changes"
                    }}
                ]
            }}
            
            Return ONLY the JSON object, no additional text.
            """

            chat_response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=prompt,
                max_turns=1
            )

            # Extract and validate response
            for message in reversed(chat_response.chat_history):
                if message.get('role') == 'assistant':
                    content = message['content'].strip()
                    
                    try:
                        # Try parsing as direct JSON first
                        result = json.loads(content)
                        if "actions" in result:
                            return result
                    except json.JSONDecodeError:
                        # If not valid JSON, try extracting from potential markdown
                        if "```json" in content:
                            json_str = content.split("```json")[1].split("```")[0].strip()
                            result = json.loads(json_str)
                            if "actions" in result:
                                return result
                        
                        # Last resort - try to find JSON-like content
                        json_start = content.find('{')
                        json_end = content.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            result = json.loads(content[json_start:json_end])
                            if "actions" in result:
                                return result
                                
                    raise ValueError("Could not extract valid actions from response")

            raise ValueError("No valid response from architect")

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise