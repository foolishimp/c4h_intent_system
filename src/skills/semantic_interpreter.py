# src/skills/semantic_interpreter.py

from typing import Dict, Any, List, Optional, Union
import autogen
import structlog
import json
from dataclasses import dataclass
from openai import AsyncOpenAI

logger = structlog.get_logger()

@dataclass
class InterpretResult:
    """Result from semantic interpretation"""
    data: Optional[Dict[str, Any]]  # Parsed JSON data
    raw_response: str               # Raw LLM response
    success: bool                   # Whether interpretation succeeded
    error: Optional[str] = None     # Error message if failed

class SemanticInterpreter:
    """Single-shot semantic interpreter using Autogen"""
    
    def __init__(self, config_list: List[Dict[str, Any]]):
        """Initialize interpreter with OpenAI config
        
        Args:
            config_list: List containing OpenAI configuration dict
        """
        if not config_list:
            raise ValueError("Config list cannot be empty")
            
        # Extract OpenAI config
        self.api_key = config_list[0].get('api_key')
        self.model = config_list[0].get('model', 'gpt-4')
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found in config")
            
        # Initialize OpenAI client
        self.client = AsyncOpenAI(api_key=self.api_key)
        
        # Initialize Autogen agents
        self.interpreter = autogen.AssistantAgent(
            name="semantic_interpreter",
            llm_config={"config_list": config_list},
            system_message="""You are a semantic interpreter that extracts structured information from text.
            Given source content and a prompt describing what to find:
            1. Analyze the content according to the prompt
            2. Return ONLY a JSON object containing the requested information
            3. Be precise and include exactly what was asked for
            4. Do not include any other text or explanation
            5. Ensure the JSON is valid and properly formatted"""
        )
        
        # Use non-interactive user proxy
        self.coordinator = autogen.UserProxyAgent(
            name="interpreter_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False,
            max_consecutive_auto_reply=0  # Prevent auto-replies
        )

    async def interpret(self, 
                       content: Union[str, Dict, List], 
                       prompt: str,
                       context_type: str = "general",
                       **context: Any) -> InterpretResult:
        """Interpret content according to prompt in single-shot mode
        
        Args:
            content: Content to interpret (string, dict or list)
            prompt: Instructions for interpretation
            context_type: Type of interpretation being performed
            **context: Additional context parameters
            
        Returns:
            InterpretResult containing parsed data and metadata
        """
        try:
            # Convert content to string if needed
            content_str = (json.dumps(content, indent=2) 
                         if isinstance(content, (dict, list)) 
                         else str(content))
            
            # Make single request using OpenAI client directly
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.interpreter.system_message},
                    {"role": "user", "content": f"""Interpret this content according to the instructions:

                    INSTRUCTIONS:
                    {prompt}

                    CONTENT:
                    {content_str}

                    Return your interpretation as a JSON object."""}
                ],
                temperature=0,
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            # Extract response content
            result = response.choices[0].message.content
            
            try:
                # Parse JSON response
                parsed_data = json.loads(result)
                return InterpretResult(
                    data=parsed_data,
                    raw_response=result,
                    success=True
                )
                
            except json.JSONDecodeError as e:
                logger.error("interpretation.json_parse_failed", 
                           error=str(e), 
                           response=result)
                return InterpretResult(
                    data=None,
                    raw_response=result,
                    success=False,
                    error=f"Failed to parse JSON response: {str(e)}"
                )
                
        except Exception as e:
            logger.error("interpretation.failed", error=str(e))
            return InterpretResult(
                data=None,
                raw_response="",
                success=False,
                error=str(e)
            )