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
    mode: ExtractionMode = ExtractionMode.FAST
    allow_fallback: bool = True
    fallback_modes: List[ExtractionMode] = None
    
    def __post_init__(self):
        if self.fallback_modes is None:
            self.fallback_modes = [ExtractionMode.SLOW] if self.mode == ExtractionMode.FAST else []

class SemanticIterator(BaseAgent):
    """LLM-based iterator for semantic extraction with configurable modes"""

    def __init__(self,
                provider: LLMProvider,
                model: Optional[str] = None,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None,
                extractor_config: Optional[ExtractorConfig] = None):
        """Initialize iterator with proper configuration"""
        super().__init__(provider=provider, model=model, temperature=temperature, config=config)
        
        self.extractor_config = extractor_config or ExtractorConfig()
        
        # Create extractors using the resolved model and config from BaseAgent
        self._fast_extractor = FastExtractor(
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
            config=self.config
        )
        self._slow_extractor = SlowExtractor(
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
            config=self.config
        )
        
        self._current_items = None
        self._position = 0
        self._content = None
        self._extract_config = None
        self._current_mode = None
        
        logger.debug("semantic_iterator.initialized",
                    provider=str(self.provider),
                    model=self.model,
                    mode=self.extractor_config.mode)

    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    def configure(self, content: Any, config: ExtractConfig) -> 'SemanticIterator':
        """Configure iterator for use"""
        self._content = content
        self._extract_config = config
        self._position = 0
        self._current_items = None
        self._current_mode = self.extractor_config.mode
        logger.info("iterator.configured", mode=self._current_mode)
        return self

    def _get_extractor(self, mode: ExtractionMode):
        """Get mode-specific extractor"""
        return self._fast_extractor if mode == ExtractionMode.FAST else self._slow_extractor

    def __iter__(self):
        """Initialize iteration based on configured mode"""
        logger.debug("iterator.starting", mode=self._current_mode)
        
        if self._current_mode == ExtractionMode.FAST:
            self._current_items = self._fast_extractor.create_iterator(
                self._content, 
                self._extract_config
            )
            if not self._current_items.has_items() and self.extractor_config.allow_fallback:
                for mode in self.extractor_config.fallback_modes:
                    logger.info("extraction.fallback", 
                             from_mode=self._current_mode, 
                             to_mode=mode)
                    self._current_mode = mode
                    break
        
        self._position = 0
        return self

    def __next__(self):
        """Get next item based on current mode"""
        try:
            if self._current_mode == ExtractionMode.FAST:
                return self._next_fast()
            else:
                return self._next_slow()
        except StopIteration:
            logger.info("iterator.complete", 
                      mode=self._current_mode,
                      items_processed=self._position)
            raise

    def _next_fast(self):
        """Handle fast mode iteration"""
        if not self._current_items:
            response = self._fast_extractor.process({
                'content': self._content,
                'config': self._extract_config
            })
            if response.success:
                self._current_items = json.loads(response.data.get('response', '[]'))
            else:
                self._current_items = []
                if self.extractor_config.allow_fallback:
                    self._current_mode = ExtractionMode.SLOW
                    return self.__next__()

        if self._position < len(self._current_items):
            item = self._current_items[self._position]
            self._position += 1
            return item
        raise StopIteration

    def _next_slow(self):
        """Handle slow mode iteration"""
        response = self._slow_extractor.process({
            'content': self._content,
            'config': self._extract_config,
            'position': self._position
        })
        
        if not response.success or 'NO_MORE_ITEMS' in str(response.data.get('response', '')):
            raise StopIteration
            
        self._position += 1
        return response.data.get('response', '')
