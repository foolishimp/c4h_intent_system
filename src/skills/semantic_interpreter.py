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
            2. Return the requested information as a JSON object
            3. Be precise in following format requests
            4. Return exactly what was asked for without additions"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="interpreter_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _extract_last_message(self, chat_history: List[Dict[str, Any]]) -> Optional[str]:
        """Extract the last assistant message from chat history"""
        for message in reversed(chat_history):
            if isinstance(message, dict) and message.get("role") == "assistant":
                return message.get("content", "")
        return None

    def _process_llm_response(self, response: str) -> Dict[str, Any]:
        """Process LLM response and attempt to extract structured data"""
        if not response:
            return {"error": "No response received"}
            
        try:
            # Try to find JSON in the response
            try:
                # First try direct JSON parsing
                return json.loads(response)
            except json.JSONDecodeError:
                # Look for JSON-like structure in text
                start_idx = response.find('{')
                end_idx = response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = response[start_idx:end_idx + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                
                # If no JSON found, return as unstructured content
                return {
                    "content": response,
                    "format": "unstructured"
                }
        except Exception as e:
            logger.error("response_processing.failed", error=str(e))
            return {
                "error": str(e),
                "raw_content": response
            }

    async def interpret(self, 
                       content: Union[str, Dict, List], 
                       prompt: str,
                       context_type: str = "general",
                       **context: Any) -> InterpretResult:
        """Interpret content according to prompt"""
        try:
            # Normalize content to string if needed
            content_str = (json.dumps(content, indent=2) 
                         if isinstance(content, (dict, list)) 
                         else str(content))
            
            # Get interpretation from LLM
            chat_response = await self.coordinator.a_initiate_chat(
                self.interpreter,
                message=f"""Interpret this content according to the instructions:

                INSTRUCTIONS:
                {prompt}

                CONTENT:
                {content_str}

                Return your interpretation as a JSON object with appropriate structure.
                """,
                max_turns=1
            )
            
            # Extract last message
            last_message = self._extract_last_message(chat_response.chat_messages)
            if not last_message:
                raise ValueError("No response received from interpreter")
            
            # Process the response
            interpreted_data = self._process_llm_response(last_message)
            
            return InterpretResult(
                data=interpreted_data,
                raw_response=last_message,
                context={
                    "type": context_type,
                    "original_content": content,
                    "prompt": prompt,
                    **context
                }
            )
            
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