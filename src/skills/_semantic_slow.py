"""
Slow extraction mode with lazy LLM calls.
Path: src/skills/_semantic_slow.py
"""
# src/skills/_semantic_slow.py

from typing import Dict, Any, Optional
import structlog
import asyncio
from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.shared.types import ExtractConfig
import json

logger = structlog.get_logger()

class SlowItemIterator:
    """Iterator for slow extraction results with lazy LLM calls"""
    def __init__(self, extractor: 'SlowExtractor', content: Any, config: ExtractConfig):
        self._extractor = extractor
        self._content = content
        self._config = config
        self._position = 0
        self._exhausted = False
        self._has_items = False
        self._current_item = None
        self._max_attempts = 10  # Safety limit
        self._ensure_event_loop()

    def _ensure_event_loop(self):
        """Ensure we have an event loop for async operations"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def __iter__(self):
        return self

    def __next__(self):
        """Synchronous next implementation wrapping async calls"""
        if self._exhausted or self._position >= self._max_attempts:
            raise StopIteration

        try:
            # Run async extraction synchronously
            result = self._extractor.process({
                'content': self._content,
                'config': self._config,
                'position': self._position
            })

            if not result.success:
                self._exhausted = True
                raise StopIteration

            response = result.data.get('response', '')
            
            # Check for completion marker
            if 'NO_MORE_ITEMS' in str(response):
                self._exhausted = True
                raise StopIteration

            # Parse response
            try:
                if isinstance(response, str):
                    item = json.loads(response)
                else:
                    item = response
            except json.JSONDecodeError:
                logger.error("slow_extraction.parse_error", position=self._position)
                self._exhausted = True
                raise StopIteration

            self._position += 1
            self._has_items = True
            return item

        except Exception as e:
            logger.error("slow_iteration.failed", error=str(e), position=self._position)
            self._exhausted = True
            raise StopIteration

    def has_items(self) -> bool:
        return self._has_items

class SlowExtractor(BaseAgent):
    """Implements slow extraction mode using iterative LLM queries"""

    def _get_agent_name(self) -> str:
        return "semantic_slow_extractor"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for slow mode using config template"""
        if not context.get('config'):
            raise ValueError("Extract config required")

        extract_template = self._get_prompt('extract')
        position = context.get('position', 0)
        
        # Add explicit completion marker to prompt
        return extract_template.format(
            ordinal=self._get_ordinal(position + 1),
            content=context.get('content', ''),
            instruction=f"{context['config'].instruction}\nIf no more items exist, respond exactly with 'NO_MORE_ITEMS'",
            format=context['config'].format
        )

    @staticmethod
    def _get_ordinal(n: int) -> str:
        """Generate ordinal string for a number"""
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10 if n % 100 not in [11, 12, 13] else 0, 'th')
        return f"{n}{suffix}"

    def create_iterator(self, content: Any, config: ExtractConfig) -> SlowItemIterator:
        """Create iterator for slow extraction - synchronous interface"""
        return SlowItemIterator(self, content, config)