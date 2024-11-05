# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import json
import os

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
            3. Return a single, definitive response with:
               - Files to modify
               - Exact changes to make
               - Validation criteria
            Do not engage in back-and-forth discussion."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator", 
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,  # Prevent loops
            code_execution_config=False
        )

    def _extract_code_blocks(self, content: str) -> Dict[str, str]:
        """Extract code blocks and their associated file paths from the architect's response"""
        files = {}
        current_file = None
        in_code_block = False
        current_content = []
        
        for line in content.split('\n'):
            # Strip any trailing colons from file paths
            if line.startswith('tests/test_projects/'):
                current_file = line.strip().rstrip(':')
            elif line.strip() == '```python':
                in_code_block = True
                current_content = []
            elif line.strip() == '```':
                if current_file and current_content:
                    files[current_file] = '\n'.join(current_content)
                in_code_block = False
            elif in_code_block:
                current_content.append(line)
                
        return files

    def _extract_validation_rules(self, content: str) -> List[str]:
        """Extract validation rules from the architect's response"""
        rules = []
        in_validation = False
        
        for line in content.split('\n'):
            if line.startswith('VALIDATION CRITERIA:'):
                in_validation = True
            elif in_validation and line.strip():
                rules.append(line.strip())
                
        return rules

    def _write_changes(self, files: Dict[str, str]) -> None:
        """Write changes to the filesystem"""
        for file_path, content in files.items():
            try:
                # Ensure clean file path without colons
                clean_path = file_path.rstrip(':')
                # Create directories if they don't exist
                Path(clean_path).parent.mkdir(parents=True, exist_ok=True)
                
                # Write the content
                with open(clean_path, 'w') as f:
                    f.write(content)
                    
                logger.info(f"Updated file: {clean_path}")
            except Exception as e:
                logger.error(f"Failed to write file {clean_path}: {str(e)}")
                raise

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce concrete code changes"""
        try:
            intent = context.get("intent_description")
            discovery_output = context.get("discovery_output")
            
            if not intent or not discovery_output:
                raise ValueError("Missing required architect context")
            
            # Force single response with terminate_after
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
                max_turns=2  # Limit conversation length
            )

            # Get response from chat history 
            if not chat_response.chat_history:
                logger.error("architect.no_chat_history")
                return {}

            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    try:
                        content = message['content']
                        
                        # Extract code blocks and validation rules
                        files = self._extract_code_blocks(content)
                        validation_rules = self._extract_validation_rules(content)
                        
                        if not files:
                            logger.error("architect.no_file_changes")
                            return {}
                            
                        # Write changes to files
                        self._write_changes(files)

                        # Ensure clean file paths in the response
                        clean_files = {k.rstrip(':'): v for k, v in files.items()}
                        clean_file_paths = [k.rstrip(':') for k in files.keys()]

                        return {
                            "architectural_plan": {
                                "changes": [
                                    {"file": file, "content": content}
                                    for file, content in clean_files.items()
                                ],
                                "validation_rules": validation_rules
                            },
                            "files_to_modify": clean_file_paths
                        }
                    except Exception as e:
                        logger.error("architect.parse_error", error=str(e))
                        raise
                    
            logger.error("architect.no_valid_response")
            return {}
                
        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise