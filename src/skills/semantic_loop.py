# src/skills/semantic_loop.py
from typing import Dict, Any, List, Optional, Callable
import autogen
import structlog
import json
from .shared.types import InterpretResult
from .semantic_interpreter import SemanticInterpreter

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
        
        self.interpreter = SemanticInterpreter(config_list)
        self.context = {}

    def _process_response(self, response: autogen.ConversableAgent) -> Dict[str, Any]:
        """Process the LLM response into structured data"""
        for message in reversed(response.chat_history):
            if message.get("role") == "assistant":
                content = message.get("content", "")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"content": content}
        return {}

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
                chat_response = await self.coordinator.a_initiate_chat(
                    self.improver,
                    message=f"""Improve this result:
                    
                    CURRENT RESULT:
                    {json.dumps(current_result, indent=2)}
                    
                    IMPROVEMENT GOAL:
                    {improvement_goal}
                    
                    ITERATION: {iteration + 1} of {self.max_iterations}
                    
                    Analyze the current result and suggest improvements.
                    Focus on:
                    1. What worked well
                    2. What failed or needs improvement
                    3. Specific changes to try next
                    """,
                    max_turns=1
                )
                
                # Interpret the improvement suggestions
                interpretation = await self.interpreter.interpret(
                    content=chat_response.last_message(),
                    prompt="""Extract the concrete improvements suggested.
                    What specific changes should be made to the current result?""",
                    context_type="improvement_analysis",
                    iteration=iteration
                )
                
                # Update result based on interpretation
                current_result = interpretation.data
                
                # Store iteration context
                self.context[f"iteration_{iteration}"] = {
                    "original_result": current_result,
                    "improvement_suggestion": chat_response.last_message(),
                    "interpretation": interpretation.raw_response
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
            "success": success_check(current_result) if success_check else True,
            "context": self.context
        }