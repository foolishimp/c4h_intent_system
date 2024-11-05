# src/agents/solution_architect.py

import os
import structlog
from typing import Dict, Any, Optional, List
from pathlib import Path
import autogen
import json

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution Architect agent that produces concrete code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
            
        self.architect = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a Solution Architect specializing in code transformations.
            When given a refactoring intent and codebase:
            1. Analyze the requirements and codebase
            2. Produce concrete, actionable changes
            3. Return a detailed response with:
               - List of files to modify under 'FILES TO MODIFY:'
               - Code blocks for each file under file path markers
               - Validation criteria under 'VALIDATION CRITERIA:'
            Use exact file paths and proper code blocks."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator", 
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config=False
        )

    def _extract_file_changes(self, content: str) -> Dict[str, str]:
        """Extract code blocks and their associated file paths"""
        files = {}
        current_file = None
        lines = content.split('\n')
        in_code_block = False
        current_content = []

        for i, line in enumerate(lines):
            # Look for file paths in the FILES TO MODIFY section
            if line.startswith('tests/test_projects/'):
                current_file = line.strip()
                if current_file.endswith(':'):  # Remove trailing colon if present
                    current_file = current_file[:-1]
            # Handle code blocks
            elif line.strip() == '```python':
                in_code_block = True
                current_content = []
            elif line.strip() == '```':
                if in_code_block and current_file:
                    files[current_file] = '\n'.join(current_content)
                in_code_block = False
            elif in_code_block:
                current_content.append(line)

        return files

    def _extract_validation_criteria(self, content: str) -> List[str]:
        """Extract validation criteria from the response"""
        validation_rules = []
        in_validation = False
        
        for line in content.split('\n'):
            if line.startswith('VALIDATION CRITERIA:'):
                in_validation = True
            elif in_validation and line.strip() and not line.startswith('```'):
                validation_rules.append(line.strip())
                
        return validation_rules

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce concrete code changes"""
        try:
            intent = context.get("intent_description")
            discovery_output = context.get("discovery_output")
            
            if not intent or not discovery_output:
                raise ValueError("Missing required architect context")

            chat_response = await self.coordinator.a_initiate_chat(
                self.architect,
                message=f"""
                REFACTORING REQUEST:
                Intent: {intent}
                
                CODEBASE:
                {discovery_output}
                
                Analyze and return ONE definitive response with concrete changes.
                Ensure file paths do not end with colons.
                """,
                max_turns=2
            )

            # Extract the architect's response
            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    content = message['content']
                    
                    # Extract file changes and validation rules
                    files = self._extract_file_changes(content)
                    validation_rules = self._extract_validation_criteria(content)
                    
                    if not files:
                        logger.error("architect.no_file_changes")
                        return {}

                    logger.info("architect.plan_created", 
                              files=list(files.keys()),
                              rules_count=len(validation_rules))
                        
                    return {
                        "architectural_plan": {
                            "changes": files,
                            "validation_rules": validation_rules
                        },
                        "files_to_modify": list(files.keys())
                    }

            logger.error("architect.no_valid_response")
            return {}
                
        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise