# src/skills/semantic_extract.py

"""
Semantic extraction using LLM. Focused purely on extraction, structure determined by caller.
Path: src/skills/semantic_extract.py
"""

from typing import Dict, Any, Optional
import structlog
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
    """Base extractor that follows given instructions without imposing structure"""
    
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
        1. Follow the instructions exactly as given
        2. Extract ONLY the specific information requested
        3. Return in exactly the format specified
        4. Do not add explanations or extra content
        5. Do not modify or enhance the instructions"""

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
            
            if not response.success:
                return ExtractResult(
                    success=False,
                    value=None,
                    raw_response=str(response.data),
                    error=response.error
                )
            
            return ExtractResult(
                success=True,
                value=response.data.get("response"),
                raw_response=str(response.data)
            )
            
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            return ExtractResult(
                success=False,
                value=None,
                raw_response="",
                error=str(e)
            )