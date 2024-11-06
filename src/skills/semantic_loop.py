# src/skills/semantic_loop.py
from typing import Dict, Any, List, Optional, Callable
import autogen
import structlog
from .shared.types import InterpretResult

logger = structlog.get_logger()

class SemanticLoop:
    """Uses LLM to iteratively improve results"""
    
    def __init__(self, config_list: List[Dict[str, Any]], max_iterations: int = 3):
        self.max_iterations = max_iterations
        self.improver = autogen.AssistantAgent(
            name="semantic_improver",
            llm_config={"config_list": config_list},
            system_message="""You help improve results through iteration.
            When given a result and improvement goal:
            1. Analyze what worked and what didn't
            2. Suggest specific improvements
            3. Maintain successful parts while fixing issues"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="loop_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )
        
        self.context = {}

    async def iterate(self,
                     initial_result: Any,
                     improvement_goal: str,
                     success_check: Optional[Callable[[Any], bool]] = None) -> Dict[str, Any]:
        """Iteratively improve a result"""
        current_result = initial_result
        iteration = 0
        
        while iteration < self.max_iterations:
            if success_check and success_check(current_result):
                break
                
            try:
                response = await self.coordinator.a_initiate_chat(
                    self.improver,
                    message=f"""Improve this result:
                    
                    CURRENT RESULT:
                    {current_result}
                    
                    IMPROVEMENT GOAL:
                    {improvement_goal}
                    
                    ITERATION: {iteration + 1} of {self.max_iterations}
                    """,
                    max_turns=1
                )
                
                # Update result and context
                current_result = self._process_response(response)
                self.context[f"iteration_{iteration}"] = {
                    "result": current_result,
                    "response": response
                }
                
            except Exception as e:
                logger.error("iteration.failed", 
                           iteration=iteration,
                           error=str(e))
                break
                
            iteration += 1
            
        return {
            "final_result": current_result,
            "iterations": iteration,
            "context": self.context
        }
