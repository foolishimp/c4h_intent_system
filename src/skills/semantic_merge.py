# src/skills/semantic_merge.py
from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog
import re
import asyncio
from src.agents.base import BaseAgent, LLMProvider  # Changed from .base

logger = structlog.get_logger()
@dataclass
class MergeResult:
    """Result of semantic merge operation"""
    success: bool
    content: str
    error: Optional[str] = None

class SemanticMerge(BaseAgent):
    """Merges code changes using semantic understanding"""
    
    def __init__(self, provider: LLMProvider, model: str, 
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
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

    def merge(self, original: str, instructions: str) -> MergeResult:
        """Merge changes into original content"""
        try:
            request = {
                "original_code": original,
                "instructions": instructions,
                "format": "Return only the complete modified code"
            }
            
            # Create event loop and run process synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(self.process(request))
            finally:
                loop.close()
            
            if not response.success:
                return MergeResult(
                    success=False,
                    content="",
                    error=response.error
                )
                
            merged_content = self._extract_code_content(response.data)
            
            if not merged_content or merged_content.isspace():
                return MergeResult(
                    success=False,
                    content="",
                    error="Empty or invalid merge result"
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