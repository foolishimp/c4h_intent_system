# src/skills/semantic_interpreter.py
from typing import Dict, Any, List, Optional, Union
import autogen
import structlog
import json
from .shared.types import InterpretResult

logger = structlog.get_logger()

class SemanticInterpreter:
    """Uses LLM to extract structured information from text"""
    
    def __init__(self, config_list: List[Dict[str, Any]]):
        self.interpreter = autogen.AssistantAgent(
            name="semantic_interpreter",
            llm_config={"config_list": config_list},
            system_message="""You are a semantic interpreter that extracts structured information from text.
            Given source content and a prompt describing what to find:
            1. Analyze the content according to the prompt
            2. Return the requested information in the specified format
            3. Be precise in following format requests
            4. Return exactly what was asked for without additions"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="interpreter_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _process_llm_response(self, response: str) -> Dict[str, Any]:
        """Process LLM response and attempt to extract structured data"""
        try:
            # Try to parse as JSON first
            return json.loads(response)
        except json.JSONDecodeError:
            # If not JSON, return as unstructured content
            return {"content": response}

    async def interpret(self, 
                       content: Union[str, Dict, List], 
                       prompt: str,
                       context_type: str = "general",
                       **context: Any) -> InterpretResult:
        """Interpret content according to prompt"""
        try:
            # Normalize content to string if needed
            content_str = (json.dumps(content) 
                         if isinstance(content, (dict, list)) 
                         else str(content))
            
            response = await self.coordinator.a_initiate_chat(
                self.interpreter,
                message=f"""Interpret this content according to the instructions:

                INSTRUCTIONS:
                {prompt}

                CONTENT:
                {content_str}
                """,
                max_turns=1
            )
            
            # Get last assistant message
            for message in reversed(response.chat_history):
                if message.get("role") == "assistant":
                    result = self._process_llm_response(message.get("content", ""))
                    
                    return InterpretResult(
                        data=result,
                        raw_response=message.get("content", ""),
                        context={
                            "type": context_type,
                            "original_content": content,
                            "prompt": prompt,
                            **context
                        }
                    )
            
            raise ValueError("No valid response from interpreter")
            
        except Exception as e:
            logger.error("interpretation.failed", error=str(e))
            return InterpretResult(
                data=None,
                raw_response=str(e),
                context={
                    "error": str(e),
                    "type": context_type,
                    "original_content": content,
                    "prompt": prompt,
                    **context
                }
            )