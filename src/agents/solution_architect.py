# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import json
import os
import re

logger = structlog.get_logger()

class SolutionArchitect:
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]

        self.assistant = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a solution architect that creates refactoring plans.
            When proposing code changes:
            1. Format your response with a ```json block containing an actions array
            2. For each action, include:
                - file_path: The path to the file
                - changes: The complete new file content (not diffs)
            3. After the JSON, provide your analysis and concerns
            
            Example format:
            ```json
            {
                "actions": [
                    {
                        "file_path": "path/to/file.py",
                        "changes": "# Complete new file content here..."
                    }
                ]
            }
            ```
            """
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _extract_json_from_markdown(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from markdown content, handling both code blocks and bare JSON"""
        # First try to find JSON in code blocks
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        matches = re.finditer(code_block_pattern, content)
        
        for match in matches:
            try:
                json_str = match.group(1).strip()
                if json_str.startswith('{'):
                    return json.loads(json_str)
            except json.JSONDecodeError:
                continue
                
        # If no valid JSON in code blocks, try finding bare JSON
        try:
            # Find outermost matching braces
            brace_count = 0
            start_idx = -1
            potential_json = ""
            
            for i, char in enumerate(content):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        potential_json = content[start_idx:i+1]
                        try:
                            return json.loads(potential_json)
                        except json.JSONDecodeError:
                            start_idx = -1  # Reset and keep looking
                            
        except Exception as e:
            logger.error("architect.json_extraction_failed", error=str(e))
            
        return None

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce refactoring actions with context"""
        try:
            intent = context.get("intent")
            discovery_output = context.get("discovery_output", {}).get("discovery_output")
            
            logger.info("architect.analyzing", intent=intent)
            
            if not discovery_output:
                raise ValueError("Missing discovery output")

            chat_response = await self.coordinator.a_initiate_chat(
                self.assistant,
                message=f"""Analyze this code and provide complete file changes:

                Intent: {intent}
                
                Codebase: {discovery_output}
                
                Please provide:
                1. ```json block with actions array containing:
                   - file_path: Path to the file
                   - changes: Complete new file content with your changes
                2. Analysis of the changes
                3. Implementation concerns
                
                Do not use diffs - provide the complete new file content for each file.""",
                max_turns=1
            )

            # Process each assistant message
            for message in reversed(chat_response.chat_history):
                if message.get('role') == 'assistant':
                    content = message.get('content', '')
                    actions = self._extract_json_from_markdown(content)
                    
                    if actions:
                        # Split content around the JSON to get observations
                        json_str = json.dumps(actions)
                        parts = content.split(json_str)
                        
                        return {
                            **actions,  # The parsed actions
                            "context": {
                                "full_response": content,
                                "observations": "\n".join(part.strip() for part in parts if part.strip())
                            }
                        }

            raise ValueError("No valid actions found in response")

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise