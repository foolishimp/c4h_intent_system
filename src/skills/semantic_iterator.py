"""
Semantic iterator with configurable extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
from dataclasses import dataclass
from src.agents.base import BaseAgent, LLMProvider, AgentResponse
from src.skills.shared.types import ExtractConfig
from src.skills._semantic_fast import FastExtractor, FastItemIterator
from src.skills._semantic_slow import SlowExtractor, SlowItemIterator

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
        # Create extractors with same settings
        self._fast_extractor = FastExtractor(provider, model, temperature, config)
        self._slow_extractor = SlowExtractor(provider, model, temperature, config)

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