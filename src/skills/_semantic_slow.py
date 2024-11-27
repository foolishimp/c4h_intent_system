"""
Slow extraction mode implementation.
Path: src/skills/_semantic_slow.py
"""

from typing import Dict, Any, Optional
import structlog
from src.agents.base import BaseAgent, LLMProvider, AgentResponse
from src.skills.shared.types import ExtractConfig
import json

logger = structlog.get_logger()

class SlowItemIterator:
    """Iterator for slow extraction results"""
    def __init__(self, extractor: 'SlowExtractor', content: Any, config: ExtractConfig):
        self._extractor = extractor
        self._content = content
        self._config = config
        self._position = 0
        self._exhausted = False
        self._has_items = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._exhausted:
            raise StopAsyncIteration

        try:
            result = await self._extractor.extract_next(
                self._content,
                self._config,
                self._position
            )

            if result.get('completed', False):
                self._exhausted = True
                raise StopAsyncIteration

            self._position += 1
            self._has_items = True
            return result.get('item')

        except Exception as e:
            logger.error("slow_iteration.failed", error=str(e))
            self._exhausted = True
            raise StopAsyncIteration

    def has_items(self) -> bool:
        return self._has_items

class SlowExtractor(BaseAgent):
    """Implements slow extraction mode using iterative LLM queries"""

    def _get_agent_name(self) -> str:
        return "semantic_slow_extractor"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for slow mode"""
        position = context.get('position', 0)
        return f"""Extract the {self._get_ordinal(position + 1)} item matching these requirements:

Content to analyze:
{context.get('content', '')}

Extraction instructions:
{context.get('config').instruction}

Return format:
{context.get('config').format}

If no more items exist, respond with exactly: NO_MORE_ITEMS"""

    @staticmethod
    def _get_ordinal(n: int) -> str:
        """Generate ordinal string for a number"""
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10 if n % 100 not in [11, 12, 13] else 0, 'th')
        return f"{n}{suffix}"

    async def extract_next(self, content: Any, config: ExtractConfig, position: int) -> Dict[str, Any]:
        """Extract next item using slow extraction"""
        try:
            result = await self.process({
                'content': content,
                'config': config,
                'position': position
            })

            if not result.success:
                return {'completed': True}

            response_content = result.data.get('response', '')
            if 'NO_MORE_ITEMS' in str(response_content):
                return {'completed': True}

            try:
                if isinstance(response_content, str):
                    item = json.loads(response_content)
                else:
                    item = response_content
            except json.JSONDecodeError:
                item = response_content

            return {
                'completed': False,
                'item': item
            }

        except Exception as e:
            logger.error("slow_extraction.failed", error=str(e))
            return {'completed': True}