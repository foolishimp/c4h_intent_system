"""
Fast extraction mode implementation.
Path: src/skills/_semantic_fast.py
"""

from typing import Dict, Any, Optional, List
import structlog
from src.agents.base import BaseAgent, LLMProvider, AgentResponse
from src.skills.shared.types import ExtractConfig
import json

logger = structlog.get_logger()

class FastItemIterator:
    """Iterator for fast extraction results"""
    def __init__(self, items: List[Any]):
        self._items = items
        self._position = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._position >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._position]
        self._position += 1
        return item

    def has_items(self) -> bool:
        return bool(self._items)

class FastExtractor(BaseAgent):
    """Implements fast extraction mode using direct LLM parsing"""

    def _get_agent_name(self) -> str:
        return "semantic_fast_extractor"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for fast mode"""
        return f"""Extract ALL items at once matching these requirements:

Content to analyze:
{context.get('content', '')}

Extraction instructions:
{context.get('config').instruction}

Return format:
{context.get('config').format}"""

    async def create_iterator(self, content: Any, config: ExtractConfig) -> FastItemIterator:
        """Create iterator for fast extraction results"""
        try:
            result = await self.process({
                'content': content,
                'config': config
            })

            if not result.success:
                logger.warning("fast_extraction.failed", error=result.error)
                return FastItemIterator([])

            # Extract items from response
            try:
                content = result.data.get('response', '{}')
                if isinstance(content, str):
                    items = json.loads(content)
                else:
                    items = content
                if isinstance(items, dict):
                    items = [items]
                elif not isinstance(items, list):
                    items = []
            except json.JSONDecodeError:
                items = []

            logger.info("fast_extraction.complete", items_found=len(items))
            return FastItemIterator(items)

        except Exception as e:
            logger.error("fast_extraction.failed", error=str(e))
            return FastItemIterator([])