
"""Semantic extraction using LLM.
Path: src/skills/semantic_extract.py
"""
from typing import Dict, Any, Optional
import structlog
import json
from dataclasses import dataclass
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

@dataclass 
class ExtractResult:
    """Result of semantic extraction"""
    success: bool
    value: Any
    raw_response: str
    error: Optional[str] = None

class SemanticExtract(BaseAgent):
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(
            provider=provider,
            model=model, 
            temperature=temperature,
            config=config
        )

    def _get_agent_name(self) -> str:
        return "semantic_extract"

    def _get_system_message(self) -> str:
        return """You are a precise information extractor.
        When given content and instructions:
        1. Extract ONLY the specific information requested
        2. Return the information in exactly the format requested
        3. Do not add explanations or descriptions
        4. Do not validate or verify the content
        5. If content cannot be extracted, return {"error": "reason"}"""

    async def extract(self,
                     content: Any,
                     prompt: str,
                     format_hint: str = "default",
                     **context: Any) -> ExtractResult:
        """Extract information using LLM"""
        try:
            request = {
                "content": content,
                "prompt": prompt,
                "format_hint": format_hint,
                "context": context
            }
            
            response = await self.process(request)
            
            return ExtractResult(
                success=response.success,
                value=response.data.get("response", {}),
                raw_response=str(response.data),
                error=response.error
            )
            
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            return ExtractResult(
                success=False,
                value=None,
                raw_response="",
                error=str(e)
            )