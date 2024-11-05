# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import structlog
import autogen

logger = structlog.get_logger()

@dataclass
class RefactorAction:
    """Represents a single code refactoring action"""
    file_path: str
    changes: str  # Unified diff format with context
    description: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None

class SolutionArchitect:
    """Solution Architect agent that analyzes requirements and produces refactoring actions"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4o", "api_key": api_key}]
            
        self.architect = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a Solution Architect specializing in code transformations.
            For each refactoring request:
            1. Analyze the requirements and codebase
            2. For each file needing changes, provide:
               - File path
               - Location of changes (line numbers)
               - Changes in unified diff format with 3 lines of context
               - Clear description of the change
            3. Provide validation criteria for the changes

            Format your response with:
            FILES TO MODIFY:
            - path/to/file1
            - path/to/file2

            CHANGES:
            === FILE path/to/file1 (lines 10-20) ===
            Description: Brief description of the change
            ```diff
            @@ -10,6 +10,7 @@ [function_name or context]
             unchanged line
             unchanged line
             unchanged line
            -removed line
            +added line
            +added line
             unchanged line
             unchanged line
             unchanged line
            ```

            VALIDATION CRITERIA:
            1. Criterion 1
            2. Criterion 2
            """
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator", 
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config=False
        )

    def _parse_refactor_actions(self, content: str) -> List[RefactorAction]:
        """Parse the architect's response into refactoring actions"""
        actions = []
        current_file = None
        current_lines = None
        current_desc = None
        in_diff = False
        diff_lines = []
        
        for line in content.split('\n'):
            if line.startswith('=== FILE'):
                # Save previous diff if exists
                if current_file and diff_lines:
                    actions.append(RefactorAction(
                        file_path=current_file,
                        changes='\n'.join(diff_lines),
                        description=current_desc or "",
                        line_start=current_lines[0] if current_lines else None,
                        line_end=current_lines[1] if current_lines else None
                    ))
                    diff_lines = []
                
                # Parse new file info
                parts = line.split(' ')
                current_file = parts[2]
                if '(lines' in line:
                    lines_part = line.split('(lines ')[1].split(')')[0]
                    start, end = map(int, lines_part.split('-'))
                    current_lines = (start, end)
                    
            elif line.startswith('Description:'):
                current_desc = line.replace('Description:', '').strip()
            elif line.strip() == '```diff':
                in_diff = True
            elif line.strip() == '```':
                in_diff = False
            elif in_diff:
                diff_lines.append(line)
        
        # Don't forget the last diff
        if current_file and diff_lines:
            actions.append(RefactorAction(
                file_path=current_file,
                changes='\n'.join(diff_lines),
                description=current_desc or "",
                line_start=current_lines[0] if current_lines else None,
                line_end=current_lines[1] if current_lines else None
            ))
            
        return actions

    def _parse_validation_rules(self, content: str) -> List[str]:
        """Extract validation rules from the response"""
        rules = []
        in_validation = False
        
        for line in content.split('\n'):
            if line.startswith('VALIDATION CRITERIA:'):
                in_validation = True
            elif in_validation and line.strip():
                if line.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                    rules.append(line.strip())
        
        return rules

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce refactoring actions"""
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
                
                Provide targeted changes for each file in unified diff format with context.
                Include clear descriptions and line numbers for changes.
                """,
                max_turns=2
            )

            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    content = message['content']
                    
                    # Extract refactor actions and validation rules
                    actions = self._parse_refactor_actions(content)
                    validation_rules = self._parse_validation_rules(content)
                    
                    if not actions:
                        logger.error("architect.no_refactor_actions")
                        continue

                    logger.info("architect.plan_created", 
                              action_count=len(actions),
                              rules_count=len(validation_rules))
                        
                    return {
                        "refactor_actions": [
                            {
                                "file_path": action.file_path,
                                "changes": action.changes,
                                "description": action.description,
                                "line_range": (action.line_start, action.line_end)
                                if action.line_start and action.line_end else None
                            }
                            for action in actions
                        ],
                        "validation_rules": validation_rules,
                        "files_to_modify": [a.file_path for a in actions]
                    }

            logger.error("architect.no_valid_response")
            return {}

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise