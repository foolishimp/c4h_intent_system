# src/skills/semantic_extract.py

from typing import Dict, Any, Optional, Union, List
import structlog
import json
from dataclasses import dataclass
from src.agents.base import BaseAgent, LLMProvider, AgentResponse  # Changed from .base

logger = structlog.get_logger()

@dataclass
class ExtractResult:
    """Result of semantic extraction"""
    success: bool            # Whether extraction found the requested info
    value: Any              # The extracted value or empty result
    raw_response: str       # Original LLM response for debugging
    error: Optional[str] = None  # Error message if any

class SemanticExtract(BaseAgent):
    """Extracts specific information from content using LLMs"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize extractor with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config  # Pass config to parent
        )

    def _get_agent_name(self) -> str:
        return "semantic_extract"
    
    def _get_system_message(self) -> str:
        return """You are a precise information extractor that pulls specific details from content.
        When given content and instructions:
        1. Extract ONLY the specific information requested
        2. For simple values (emails, names, dates, etc), return just the value
        3. For complex data:
           - Return valid JSON object with requested fields
           - For arrays, include them as JSON arrays
           - Preserve numeric types (don't convert to strings)
        4. If the requested information is not found:
           - Return exactly: NOT_FOUND
           - Don't return any other content
        5. If extraction is ambiguous:
           - Return exactly: AMBIGUOUS
           - Don't return any other content
        6. Never add explanations or descriptions"""

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format the extraction request"""
        if not isinstance(context, dict):
            return "Error: Invalid input format"

        content = context.get('content')
        prompt = context.get('prompt')
        format_hint = context.get('format_hint', 'default')

        if not prompt or not isinstance(prompt, str) or prompt.strip() == "":
            return "Error: No prompt provided"
            
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

        format_instruction = "Return the value directly without ANY formatting or explanation."
        if format_hint == "json":
            format_instruction = """Return ONLY a valid JSON object or array containing the extracted information.
            Preserve data types (numbers should be numbers, not strings)."""

        return f"""Extract information from this content according to the instructions:

        INSTRUCTIONS:
        {prompt}

        CONTENT:
        {content_str}

        {format_instruction}

        If the information is not found, respond with exactly: NOT_FOUND
        If the request is ambiguous, respond with exactly: AMBIGUOUS"""

# src/skills/semantic_extract.py

    def _process_response(self, response: AgentResponse, format_hint: str) -> ExtractResult:
        """Process and validate LLM response"""
        if not response.success:
            return ExtractResult(
                success=False,
                value=None,
                raw_response=str(response.data),
                error=response.error
            )

        # Extract the actual response content
        raw_response = response.data.get('response', {})
        if isinstance(raw_response, dict):
            # Handle case where response is wrapped in raw_message
            content = raw_response.get('raw_message', raw_response)
        else:
            content = raw_response

        # Convert content to string for comparison
        content_str = str(content).strip()
        
        # Handle special response markers
        if content_str.upper() == 'NOT_FOUND':
            return ExtractResult(
                success=False,
                value=None if format_hint == "string" else {},
                raw_response=str(raw_response),
                error="Information not found in content"
            )
        
        if content_str.upper() == 'AMBIGUOUS':
            return ExtractResult(
                success=False,
                value=None if format_hint == "string" else {},
                raw_response=str(raw_response),
                error="Ambiguous extraction request"
            )

        # Process based on format
        try:
            if format_hint == "string":
                # For string format, extract single value
                value = content_str
                if isinstance(content, dict):
                    # If we got a dict, try to extract a single value
                    if len(content) == 1:
                        value = str(next(iter(content.values())))
                    else:
                        return ExtractResult(
                            success=False,
                            value="",
                            raw_response=str(raw_response),
                            error="Expected string but got complex object"
                        )
                
                return ExtractResult(
                    success=bool(value) and value.upper() != 'NOT_FOUND',
                    value=value,
                    raw_response=str(raw_response)
                )
            else:
                # Handle JSON format
                try:
                    if isinstance(content, (dict, list)):
                        parsed = content
                    else:
                        # Try to parse string as JSON
                        try:
                            parsed = json.loads(content_str)
                        except json.JSONDecodeError:
                            # If not valid JSON, wrap in dict
                            if isinstance(content, (int, float)):
                                parsed = {"value": content}
                            elif isinstance(content, str) and content.upper() == 'NOT_FOUND':
                                return ExtractResult(
                                    success=False,
                                    value={},
                                    raw_response=str(raw_response),
                                    error="Information not found in content"
                                )
                            else:
                                parsed = {"raw_value": content_str}

                    # Handle array responses
                    if isinstance(parsed, list):
                        parsed = {"values": parsed}

                    return ExtractResult(
                        success=bool(parsed),
                        value=parsed,
                        raw_response=str(raw_response)
                    )
                    
                except Exception as e:
                    return ExtractResult(
                        success=False,
                        value={},
                        raw_response=str(raw_response),
                        error=f"Failed to parse JSON response: {str(e)}"
                    )
                    
        except Exception as e:
            return ExtractResult(
                success=False,
                value=None if format_hint == "string" else {},
                raw_response=str(raw_response),
                error=f"Response processing error: {str(e)}"
            )
        
    async def extract(self,
                     content: Any,
                     prompt: str,
                     format_hint: str = "default",
                     **context: Any) -> ExtractResult:
        """
        Extract specific information from content according to prompt
        
        Args:
            content: The content to extract from (any format convertible to string)
            prompt: Instructions specifying what information to extract
            format_hint: Desired format ("json", "string", or "default")
            **context: Additional context parameters
            
        Returns:
            ExtractResult containing success status and extraction result
        """
        if not prompt or not isinstance(prompt, str) or prompt.strip() == "":
            return ExtractResult(
                success=False,
                value=None,
                raw_response="",
                error="No prompt provided for extraction"
            )

        try:
            request = {
                "content": content,
                "prompt": prompt,
                "format_hint": format_hint,
                "context": context
            }
            
            response = await self.process(request)
            return self._process_response(response, format_hint)
            
        except Exception as e:
            logger.error("extraction.failed", 
                        error=str(e),
                        content_type=type(content).__name__)
            return ExtractResult(
                success=False,
                value=None,
                raw_response="",
                error=f"Extraction failed: {str(e)}"
            )