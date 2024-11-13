# src/skills/semantic_iterator.py

from typing import Dict, Any, List, Optional, Iterator, Iterable, TypeVar, Generic, Callable
from collections.abc import Sequence
import structlog
from .semantic_extract import SemanticExtract
from .shared.types import ExtractConfig, InterpretResult
from src.agents.base import LLMProvider, AgentResponse

logger = structlog.get_logger()

T = TypeVar('T')

class ItemIterator(Generic[T]):
    """Iterator for semantically extracted content"""
    
    def __init__(self, items: Sequence[T], config: ExtractConfig):
        self._items = items
        self._config = config
        self._index = 0
        self._history: List[int] = []
        
    def __iter__(self) -> 'ItemIterator[T]':
        return self
        
    def __next__(self) -> T:
        if self._index >= len(self._items):
            raise StopIteration
        item = self._items[self._index]
        self._history.append(self._index)
        self._index += 1
        return item

    def has_next(self) -> bool:
        """Check if there are more items"""
        return self._index < len(self._items)
        
    def peek(self) -> Optional[T]:
        """Look at the next item without advancing"""
        if not self.has_next():
            return None
        return self._items[self._index]
    
    def back(self) -> Optional[T]:
        """Go back one item in history"""
        if not self._history:
            return None
        self._index = self._history.pop()
        return self._items[self._index]
        
    def reset(self) -> None:
        """Reset iterator to the beginning"""
        self._index = 0
        self._history.clear()
        
    def skip(self, count: int = 1) -> None:
        """Skip ahead n items"""
        self._index = min(self._index + count, len(self._items))
        
    def position(self) -> int:
        """Get the current position"""
        return self._index
        
    def remaining(self) -> int:
        """Get the count of remaining items"""
        return len(self._items) - self._index
    
    def to_list(self) -> List[T]:
        """Convert remaining items to a list"""
        return list(self._items[self._index:])

class SemanticIterator:
    """Creates iterable semantic extractions from content"""
    
    def __init__(self, config_list: List[Dict[str, Any]]):
        """Initialize with LLM configuration
        
        Args:
            config_list: List of provider configurations
        """
        if not config_list or not isinstance(config_list, list):
            raise ValueError("Config list must be a non-empty list of configurations")
        
        provider = LLMProvider.ANTHROPIC  # Default to Anthropic
        model = None
        
        if config_list[0].get('model'):
            model = config_list[0]['model']
            if 'gpt' in model.lower():
                provider = LLMProvider.OPENAI
            elif 'claude' in model.lower():
                provider = LLMProvider.ANTHROPIC
            elif 'gemini' in model.lower():
                provider = LLMProvider.GEMINI

        self.extractor = SemanticExtract(
            provider=provider,
            model=model,
            temperature=0
        )
        
        self.logger = structlog.get_logger(component="semantic_iterator")

    async def iter_extract(self, 
                           content: Any,
                           config: ExtractConfig) -> ItemIterator:
        """Extract iterable content based on configuration
        
        Args:
            content: Source content to extract from
            config: Extraction configuration including:
                - pattern: What to extract (e.g., "each CSV record")
                - format: Expected format of each item
                - filters: Optional filters to apply
                - sort_key: Optional key to sort by
                
        Returns:
            ItemIterator over extracted items
        """
        try:
            # Use semantic extract to get initial items
            extract_result = await self.extractor.extract(
                content=content,
                prompt=config.pattern,
                format_hint="json",
                context={"extraction_config": config}
            )
            
            if not extract_result.success:
                self.logger.error("extraction.failed", 
                                  error=extract_result.error)
                return ItemIterator([], config)

            # Handle the response data structure correctly
            response_data = self._extract_items(extract_result.value)

            # Apply filters
            if config.filters:
                response_data = [
                    item for item in response_data 
                    if all(f(item) for f in config.filters)
                ]

            # Apply sorting
            if config.sort_key and response_data:
                response_data.sort(key=lambda x: x.get(config.sort_key))

            self.logger.info("iterator.created", item_count=len(response_data))
            
            return ItemIterator(response_data, config)
            
        except Exception as e:
            self.logger.error("iterator.failed", error=str(e))
            return ItemIterator([], config)

    def _extract_items(self, data: Any) -> List[Any]:
        """Extract items from response data based on common container keys"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ['items', 'values', 'records', 'results']:
                if key in data:
                    return data[key]
            return list(data.values())
        return [data] if data is not None else []
