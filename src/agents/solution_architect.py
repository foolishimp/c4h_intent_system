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

    async def _get_solution_proposal(self, intent: str, discovery_output: str) -> str:
        """Get initial solution proposal from LLM"""
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
        
        return response.last_message()

    async def _interpret_solution(self, solution: str) -> Dict[str, Any]:
        """Extract structured actions from solution using semantic interpretation"""
        interpretation = await self.interpreter.interpret(
            content=solution,
            prompt="""Extract the concrete code changes described in this solution.
            
            For each change identify:
            1. The target file path
            2. The specific changes needed
            3. Any validation requirements
            4. Potential risks or concerns
            
            Structure your understanding to capture:
            - Which files are being modified
            - What modifications are needed
            - How to verify the changes work
            """
        )
        
        return interpretation.data

    async def _validate_solution(self, solution: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the solution meets the intent using semantic analysis"""
        validation = await self.interpreter.interpret(
            content={
                "solution": solution,
                "context": context
            },
            prompt="""Analyze if this solution fulfills the original intent.
            
            Consider:
            1. Does it address all aspects of the intent?
            2. Are the proposed changes complete?
            3. Are there any missing pieces?
            4. What validations would confirm success?
            
            Provide your analysis of the solution's completeness.
            """
        )
        
        return validation.data

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze intent and produce refactoring actions with semantic validation"""
        try:
            intent = context.get("intent")
            discovery_output = context.get("discovery_output", {}).get("discovery_output")
            
            if not discovery_output:
                raise ValueError("Missing discovery output")

            logger.info("architect.analyzing", intent=intent)
            
            # Get initial solution proposal
            solution_proposal = await self._get_solution_proposal(intent, discovery_output)
            
            # Extract structured understanding
            interpreted_solution = await self._interpret_solution(solution_proposal)
            
            # Validate solution completeness
            validation_result = await self._validate_solution(interpreted_solution, context)
            
            return {
                "solution": interpreted_solution,
                "validation": validation_result,
                "context": {
                    "raw_proposal": solution_proposal,
                    "interpretation_context": {
                        "original_intent": intent,
                        "discovery_output": discovery_output
                    }
                }
            }

        except Exception as e:
            logger.error("architect.failed", error=str(e))
            raise