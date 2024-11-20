# src/skills/semantic_iterator.py

"""
Enhanced semantic iterator implementation.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any
import structlog
from src.skills.semantic_extract import SemanticExtract
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

class ItemIterator:
    """Iterator over extracted items"""
    def __init__(self, items: List[Any], raw_response: str = ""):
        self._items = items if isinstance(items, list) else []
        self._index = 0
        self._raw_response = raw_response
        
    def has_next(self) -> bool:
        return self._index < len(self._items)
        
    def __next__(self) -> Any:
        if self.has_next():
            item = self._items[self._index]
            self._index += 1
            return item
        raise StopIteration

    def get_raw_response(self) -> str:
        """Get raw LLM response for debugging"""
        return self._raw_response

class SemanticIterator:
    """Iterator using semantic extraction"""
    
    def __init__(self, config: List[Dict[str, Any]]):
        cfg = config[0]
        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=cfg.get('temperature', 0),
            config=cfg.get('config')
        )
        logger.debug("iterator.init", config=cfg)

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items"""
        try:
            logger.debug("iterator.extract.start", 
                        content_type=type(content).__name__)
                    
            result = await self.extractor.extract(
                content=content,
                prompt=config.instruction,
                format_hint=config.format
            )

            # Process into items
            items = []
            if result.success:
                if isinstance(result.value, list):
                    items = result.value
                elif result.value:
                    items = [result.value]
            
            logger.info("iterator.extract.complete", 
                       success=result.success,
                       items_count=len(items))
                    
            return ItemIterator(items, result.raw_response)

        except Exception as e:
            logger.error("iterator.extract.failed", error=str(e))
            return ItemIterator([], str(e))
    
    async def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """
        Extract all items at once.
        """
        iterator = await self.iter_extract(content, config)
        items = []
        while iterator.has_next():
            items.append(next(iterator))
        return items