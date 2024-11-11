# src/skills/semantic_extract.py

from typing import Dict, Any, Optional, Union, List
import structlog
import json
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SemanticExtract(BaseAgent):
    """Extracts specific information from content using LLMs"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,  # Default to Claude for semantic tasks
                 model: Optional[str] = None,
                 temperature: float = 0):  # Use 0 temperature for consistent extraction
        """Initialize extractor with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature
        )

    def _get_agent_name(self) -> str:
        return "semantic_extract"
    
    def _get_system_message(self) -> str:
        return """You are a precise information extractor that pulls specific details from content.
        When given content and instructions:
        1. Analyze the content carefully
        2. Extract ONLY the specific information requested
        3. Return the extracted information in the exact format requested
        4. If asked for JSON, return valid JSON only
        5. Be precise - include only what was asked for
        6. If requested information isn't found, return an empty result ({} for JSON)
        7. Never include explanations or descriptions in the response"""

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format the extraction request"""
        if not isinstance(context, dict):
            return "Error: Invalid input format"

        content = context.get('content')
        prompt = context.get('prompt')

        if not prompt or not isinstance(prompt, str) or prompt.strip() == "":
            return "Error: No prompt provided"
            
        # Handle content conversion
        try:
            if content is None:
                content_str = "None"
            elif isinstance(content, (dict, list)):
                content_str = json.dumps(content, indent=2)
            else:
                content_str = str(content)
        except Exception as e:
            logger.error("content_conversion.failed", error=str(e))
            return f"Error: Failed to convert content to string: {str(e)}"

        return f"""Extract information from this content according to the instructions:

        INSTRUCTIONS:
        {prompt}

        CONTENT:
        {content_str}

        Extract and return ONLY the requested information.
        If the information cannot be found, return an empty result ({{}}).
        Do not include any explanations or descriptions."""

    async def extract(self,
                     content: Any,
                     prompt: str,
                     **context: Any) -> AgentResponse:
        """
        Extract specific information from content according to prompt
        
        Args:
            content: The content to extract from (any format convertible to string)
            prompt: Instructions specifying what information to extract
            **context: Additional context parameters
            
        Returns:
            AgentResponse containing the extracted information
        """
        # Validate prompt
        if not prompt or not isinstance(prompt, str) or prompt.strip() == "":
            logger.error("extraction.failed", error="No prompt provided")
            return AgentResponse(
                success=False,
                data={},
                error="No prompt provided for extraction"
            )

        try:
            # Package the request
            request = {
                "content": content,
                "prompt": prompt,
                "context": context
            }
            
            # Use base agent processing
            response = await self.process(request)
            
            # Convert explanation responses to empty results
            if response.success and isinstance(response.data.get('response'), dict):
                if ('raw_message' in response.data['response'] or 
                    'explanation' in response.data['response'] or
                    'error' in response.data['response']):
                    return AgentResponse(
                        success=True,
                        data={'response': {}}
                    )
            
            return response
            
        except Exception as e:
            logger.error("extraction.failed", 
                        error=str(e),
                        content_type=type(content).__name__)
            return AgentResponse(
                success=False,
                data={},
                error=f"Extraction failed: {str(e)}"
            )