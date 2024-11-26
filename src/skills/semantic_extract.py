"""
Enhanced semantic extraction following agent design principles.
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
                provider: LLMProvider,
                model: str,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None):
        """Initialize with standard agent configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )

    def _get_agent_name(self) -> str:
        return "semantic_extract"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request with proper prompting"""
        content = context.get('content', '')
        prompt = context.get('prompt', '')
        format_hint = context.get('format_hint', 'default')
        
        return f"""Content to analyze:
{content}

Extraction instructions:
{prompt}

Return format: {format_hint}"""

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
                raw_response=response.data.get("raw_content", "")
            )
            
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            return ExtractResult(
                success=False,
                value=None,
                raw_response="",
                error=str(e)
            )