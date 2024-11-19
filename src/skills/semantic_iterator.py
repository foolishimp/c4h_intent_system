"""Semantic iterator for structured extraction.
Path: src/skills/semantic_iterator.py"""

from typing import Dict, Any, Optional, TypeVar, Generic, List, AsyncIterator, Sequence
from dataclasses import dataclass
import structlog
from src.skills.semantic_extract import SemanticExtract
from src.agents.base import LLMProvider

logger = structlog.get_logger()

T = TypeVar('T')

@dataclass
class SemanticPrompt:
    """Configuration for extraction prompt"""
    instruction: str  # Pattern to match
    format: str = "json"  # Expected response format

class SemanticList(Generic[T]):
    """Container for extracted items"""
    def __init__(self, items: Sequence[T]):
        self._items = list(items)
        
    def __len__(self) -> int:
        return len(self._items)
    
    def __getitem__(self, index: int) -> T:
        return self._items[index]
    
    def __iter__(self):
        return iter(self._items)

class ItemIterator:
    """Iterator over extracted items"""
    def __init__(self, items: List[Any]):
        self._items = items
        self._index = 0
        
    def has_next(self) -> bool:
        return self._index < len(self._items)
        
    def __next__(self) -> Any:
        if self.has_next():
            item = self._items[self._index]
            self._index += 1
            return item
        raise StopIteration

class SemanticIterator:
    """Iterator using semantic extraction"""
    
    def __init__(self, config: List[Dict[str, Any]]):
        if not config or not isinstance(config[0], dict):
            raise ValueError("Invalid config format")
            
        cfg = config[0]
        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=cfg.get('temperature', 0),
            config=cfg.get('config')
        )
        
    async def iter_extract(self, content: Any, config: SemanticPrompt) -> ItemIterator:
        """Extract and iterate over items"""
        try:
            result = await self.extractor.extract(
                content=content,
                prompt=config.instruction,
                format_hint=config.format
            )

            if not result.success:
                logger.error("extraction.failed", error=result.error)
                return ItemIterator([])

            # Handle direct response or nested items
            response = result.value
            if isinstance(response, dict):
                if 'raw_output' in response:
                    response = response['raw_output']
                if isinstance(response, dict) and 'error' not in response:
                    response = [{"key": k, "value": v} for k,v in response.items()]
            
            items = response if isinstance(response, list) else [response]
            return ItemIterator(items)

        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            return ItemIterator([])