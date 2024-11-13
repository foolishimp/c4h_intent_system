# src/skills/semantic_merge.py

from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog
import re
from src.agents.base import BaseAgent, LLMProvider

logger = structlog.get_logger()

@dataclass
class MergeResult:
    """Result of semantic merge operation"""
    success: bool
    content: str
    error: Optional[str] = None

class SemanticMerge(BaseAgent):
    """Merges code changes using semantic understanding"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        """Initialize merger with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )
        
    def _get_agent_name(self) -> str:
        return "semantic_merge"
        
    def _get_system_message(self) -> str:
        return """You are a precise code merger. Given original code and change instructions,
        your task is to apply the changes and return the modified code.
        
        Important rules:
        1. Return ONLY the modified code - no explanations or other text
        2. Do not wrap the code in markdown code blocks or quotes
        3. Return the complete file content, not just the changes
        4. Preserve all existing functionality unless explicitly told to change it
        5. Maintain code style, indentation, and formatting
        
        Example output format:
        import logging
        
        class Example:
            def method(self):
                pass
        
        No additional text or formatting - just the code."""

    def _extract_code_content(self, response: Dict[str, Any]) -> str:
        """Extract code content from LLM response"""
        if not response:
            return ""

        # Get raw response content
        content = ""
        if isinstance(response, dict):
            if "response" in response:
                content = str(response["response"])
            elif "raw_message" in response:
                content = str(response["raw_message"])
            else:
                content = str(response)
        else:
            content = str(response)

        # Strip markdown code blocks if present
        content = re.sub(r'^```\w*\n', '', content)
        content = re.sub(r'\n```$', '', content)
        
        # Remove any leading/trailing whitespace
        content = content.strip()
        
        return content

    async def merge(self, original: str, instructions: str) -> MergeResult:
        """Merge changes into original content"""
        try:
            # Format request to emphasize code-only response
            request = {
                "original_code": original,
                "instructions": instructions,
                "format": "Return only the complete modified code without any additional text or formatting."
            }
            
            # Get response from LLM
            response = await self.process(request)
            
            if not response.success:
                return MergeResult(
                    success=False,
                    content="",
                    error=response.error
                )
                
            # Extract the code content
            merged_content = self._extract_code_content(response.data)
            
            # Basic validation
            if not merged_content or merged_content.isspace():
                logger.error("semantic_merge.empty_content", 
                           raw_response=str(response.data))
                return MergeResult(
                    success=False,
                    content="",
                    error="Empty or invalid merge result"
                )

            # Verify it looks like Python code
            if not any(keyword in merged_content 
                      for keyword in ['class', 'def', 'import']):
                logger.error("semantic_merge.invalid_python",
                           content=merged_content[:100])
                return MergeResult(
                    success=False,
                    content="",
                    error="Response does not appear to be valid Python code"
                )
                
            return MergeResult(
                success=True,
                content=merged_content
            )
                
        except Exception as e:
            logger.error("semantic_merge.failed", error=str(e))
            return MergeResult(
                success=False,
                content="",
                error=str(e)
            )