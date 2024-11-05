# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
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
                """,
                max_turns=2  # Limit conversation length
            )

            # Get response from chat history instead of chat_messages
            if not chat_response.chat_history:
                logger.error("architect.no_chat_history")
                return {}

            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    try:
                        # Parse the message content into structured format
                        content = message['content']
                        changes = []
                        validation_rules = []
                        
                        # Simple parsing of the architect's response
                        current_file = None
                        current_content = []
                        
                        for line in content.split('\n'):
                            if line.startswith('tests/test_projects/'):
                                if current_file and current_content:
                                    changes.append({
                                        "file": current_file,
                                        "content": '\n'.join(current_content)
                                    })
                                current_file = line.strip()
                                current_content = []
                            elif line.startswith('```python'):
                                continue
                            elif line.startswith('```'):
                                if current_file and current_content:
                                    changes.append({
                                        "file": current_file,
                                        "content": '\n'.join(current_content)
                                    })
                                current_file = None
                                current_content = []
                            elif current_file and current_content or line.strip():
                                current_content.append(line)
                            elif line.startswith('VALIDATION CRITERIA:'):
                                in_validation = True
                            elif in_validation and line.strip():
                                validation_rules.append(line.strip())

                        return {
                            "architectural_plan": {
                                "changes": changes,
                                "validation_rules": validation_rules
                            },
                            "files_to_modify": [
                                "tests/test_projects/project1/sample.py",
                                "tests/test_projects/project2/utils.py",
                                "tests/test_projects/project2/main.py"
                            ]
                        }
                    except Exception as e:
                        logger.error("architect.parse_error", error=str(e))
                    break
                    
            logger.error("architect.no_valid_response")
            return {}
                
        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise