"""
Semantic iterator with configurable extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
from dataclasses import dataclass
import json
from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.shared.types import ExtractConfig
from skills._semantic_fast import FastExtractor, FastItemIterator
from skills._semantic_slow import SlowExtractor, SlowItemIterator

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes"""
    FAST = "fast"      # Direct extraction from structured data
    SLOW = "slow"      # Sequential item-by-item extraction

@dataclass
class ExtractorConfig:
    """Configuration for extraction behavior"""
    initial_mode: ExtractionMode = ExtractionMode.FAST
    allow_fallback: bool = True
    fallback_modes: List[ExtractionMode] = None
    
    def __post_init__(self):
        if self.fallback_modes is None:
            self.fallback_modes = [ExtractionMode.SLOW] if self.initial_mode == ExtractionMode.FAST else []

class SemanticIterator(BaseAgent):
    """LLM-based iterator for semantic extraction with configurable modes"""

    def __init__(self,
                provider: LLMProvider,
                model: str,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None,
                extractor_config: Optional[ExtractorConfig] = None):
        """Initialize iterator with specified configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        self.extractor_config = extractor_config or ExtractorConfig()
        
        # Debug logging
        logger.debug("semantic_iterator.init_extractors",
                    provider=str(provider),
                    model=model,
                    config_type=type(config).__name__,
                    config_keys=list(config.keys()) if isinstance(config, dict) else None)
        
        # Create extractors with SAME configuration as parent
        self._fast_extractor = FastExtractor(
            provider=provider,
            model=model,   
            temperature=temperature,
            config=config  # Pass through the same config
        )
        self._slow_extractor = SlowExtractor(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config  # Pass through the same config
        )

    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    def _get_extractor(self, mode: ExtractionMode):
        """Get mode-specific extractor"""
        return self._fast_extractor if mode == ExtractionMode.FAST else self._slow_extractor

    async def iter_extract(self, content: Any, config: ExtractConfig):
        """Create an iterator for extracted items"""
        try:
            current_mode = self.extractor_config.initial_mode
            extractor = self._get_extractor(current_mode)
            
            if current_mode == ExtractionMode.FAST:
                iterator = await extractor.create_iterator(content, config)
            else:
                iterator = SlowItemIterator(extractor, content, config)
            
            # Handle fallback if needed and configured
            if (self.extractor_config.allow_fallback and 
                not iterator.has_items() and 
                self.extractor_config.fallback_modes):
                
                for fallback_mode in self.extractor_config.fallback_modes:
                    logger.info("extraction.fallback", 
                              from_mode=current_mode.value,
                              to_mode=fallback_mode.value)
                    
                    current_mode = fallback_mode
                    extractor = self._get_extractor(current_mode)
                    
                    if current_mode == ExtractionMode.FAST:
                        iterator = await extractor.create_iterator(content, config)
                    else:
                        iterator = SlowItemIterator(extractor, content, config)
                    
                    if iterator.has_items():
                        break

            return iterator

        except Exception as e:
            logger.error("iterator.creation_failed", error=str(e))
            return FastItemIterator([])  # Return empty iterator

    def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract all items at once using configured mode"""
        try:
            if self.extractor_config.initial_mode == ExtractionMode.FAST:
                result = self._fast_extractor.process({
                    'content': content,
                    'config': config
                })
                if not result.success:
                    if self.extractor_config.allow_fallback:
                        return self._extract_slow(content, config)
                    return []

                try:
                    items = json.loads(result.data.get('response', '[]'))
                    if isinstance(items, dict):
                        items = [items]
                    return items if isinstance(items, list) else []
                except json.JSONDecodeError:
                    if self.extractor_config.allow_fallback:
                        return self._extract_slow(content, config)
                    return []
            else:
                return self._extract_slow(content, config)

        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            return []

    def _extract_slow(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract items using slow mode"""
        items = []
        position = 0
        
        while True:
            result = self._slow_extractor.process({
                'content': content,
                'config': config,
                'position': position
            })

            if not result.success:
                break

            response = result.data.get('response', '')
            if 'NO_MORE_ITEMS' in str(response):
                break

            try:
                item = json.loads(response) if isinstance(response, str) else response
                items.append(item)
                position += 1
            except json.JSONDecodeError:
                continue

        return items