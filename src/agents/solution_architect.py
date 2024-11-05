# src/agents/solution_architect.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import json
import os

logger = structlog.get_logger()

class SolutionArchitect:
    """Solution Architect agent that analyzes intent and determines required actions"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
            
        self.architect = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={"config_list": config_list},
            system_message="""You are a Solution Architect specializing in code analysis and planning.
            Given a refactoring intent and codebase:
            1. Analyze the requirements
            2. Determine necessary actions
            3. Specify changes needed at module and function level
            4. Return a specific action plan for transformations to implement"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="architect_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and determine required actions"""
        try:
            intent = context.get("intent_description")
            discovered_files = context.get("discovery_output")
            
            if not intent or not discovered_files:
                raise ValueError("Missing required architect context")
            
            chat_response = await self.coordinator.a_initiate_chat(
                self.architect,
                message=f"""
                REFACTORING REQUEST:
                Intent: {intent}
                
                CODEBASE SCOPE:
                {discovered_files}
                
                As the Solution Architect, analyze this request and provide:
                1. Assessment of the changes needed
                2. Module-level requirements (imports, setup, etc)
                3. Function-level requirements
                4. Any architectural considerations
                5. Action plan for transformations
                
                Format your response as JSON with this structure:
                {{
                    "analysis": {{
                        "intent_type": "string",
                        "scope": ["list of files"],
                        "requirements": {{
                            "module_level": [
                                {{
                                    "type": "string",
                                    "reason": "string",
                                    "details": "string"
                                }}
                            ],
                            "function_level": [
                                {{
                                    "type": "string",
                                    "reason": "string",
                                    "details": "string"
                                }}
                            ]
                        }},
                        "considerations": [
                            "list of important points"
                        ],
                        "action_plan": {{
                            "steps": [
                                {{
                                    "step": 1,
                                    "description": "string",
                                    "type": "string",
                                    "target": "string"
                                }}
                            ]
                        }}
                    }}
                }}

                Focus on architectural analysis and planning. The Coder agent will handle implementation details.
                """
            )

            assistant_messages = [
                msg['content'] for msg in chat_response.chat_messages
                if msg.get('role') == 'assistant'
            ]
            plan = assistant_messages[-1] if assistant_messages else ""
            
            try:
                action_plan = json.loads(plan)
                logger.info("architect.plan_created")
                return {"architectural_analysis": action_plan}
            except json.JSONDecodeError as e:
                logger.error("architect.invalid_plan", error=str(e))
                return {"architectural_analysis": {}}
                
        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise