"""
Fast extraction mode implementation.
Path: src/skills/_semantic_fast.py
"""

from typing import Dict, Any, Optional, List
import structlog
from dataclasses import dataclass
from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.shared.types import ExtractConfig
import json

logger = structlog.get_logger()

class FastItemIterator:
    """Iterator for fast extraction results with indexing support"""
    def __init__(self, items: List[Any]):
        self._items = items if items else []
        self._position = 0
        logger.debug("fast_iterator.initialized", items_count=len(self._items))

    def __iter__(self):
        return self

    def __next__(self):
        if self._position >= len(self._items):
            raise StopIteration
        item = self._items[self._position]
        self._position += 1
        return item

    def __len__(self):
        """Support length checking"""
        return len(self._items)

    def __getitem__(self, idx):
        """Support array-style access"""
        return self._items[idx]

    def has_items(self) -> bool:
        return bool(self._items)

class FastExtractor(BaseAgent):
    """Implements fast extraction mode using direct LLM parsing"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize with parent agent configuration"""
        super().__init__(config=config)
        
        # Get provider settings from config
        provider_cfg = config.get('llm_config', {}).get('agents', {}).get('semantic_fast_extractor', {})
        self.provider = LLMProvider(provider_cfg.get('provider', 'anthropic'))
        self.model = provider_cfg.get('model', 'claude-3-opus-20240229')
        self.temperature = provider_cfg.get('temperature', 0)
        
        # Build model string based on provider
        self.model_str = f"{self.provider.value}/{self.model}"
        if self.provider == LLMProvider.OPENAI:
            self.model_str = self.model  # OpenAI doesn't need prefix
            
        logger.info("fast_extractor.initialized",
                   provider=str(self.provider),
                   model=self.model,
                   temperature=self.temperature)

    def _get_agent_name(self) -> str:
        return "semantic_fast_extractor"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for fast mode using config template"""
        if not context.get('config'):
            logger.error("fast_extractor.missing_config")
            raise ValueError("Extract config required")

        extract_template = self._get_prompt('extract')
        return extract_template.format(
            content=context.get('content', ''),
            instruction=context['config'].instruction,
            format=context['config'].format
        )

    def create_iterator(self, content: Any, config: ExtractConfig) -> FastItemIterator:
        """Create iterator for fast extraction - synchronous interface"""
        try:
            logger.debug("fast_extractor.creating_iterator",
                        content_type=type(content).__name__)
                        
            # Use synchronous process instead of async
            result = self.process({
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
            except json.JSONDecodeError as e:
                logger.error("fast_extraction.parse_error", error=str(e))
                items = []

            logger.info("fast_extraction.complete", items_found=len(items))
            return FastItemIterator(items)

        except Exception as e:
            logger.error("fast_extraction.failed", error=str(e))
            return FastItemIterator([])