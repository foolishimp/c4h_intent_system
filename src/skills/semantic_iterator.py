"""
Path: src/skills/shared/types.py
"""
from dataclasses import dataclass, field
from typing import List, Callable, Any, Optional, Dict

@dataclass
class ExtractConfig:
    """Configuration for semantic extraction"""
    instruction: str  # Pattern/prompt for extraction
    format: str = "json"  # Expected output format 

"""
Path: src/skills/semantic_iterator.py
"""
from typing import Dict, Any, List
import structlog
from src.skills.semantic_extract import SemanticExtract
from src.agents.base import LLMProvider
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

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
        logger.debug("iterator.extract.start", 
                    content_type=type(content).__name__,
                    instruction=config.instruction)
                    
        result = await self.extractor.extract(
            content=content,
            prompt=config.instruction,
            format_hint=config.format
        )
        
        items = result.value if result.success else []
        logger.debug("iterator.extract.complete", 
                    success=result.success,
                    items_count=len(items))
                    
        return ItemIterator(items)

# Package exports
__all__ = ['SemanticIterator', 'ItemIterator', 'ExtractConfig']