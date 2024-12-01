"""
Semantic iterator with configurable extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
from dataclasses import dataclass
import json
import asyncio
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
        super().__init__(provider=provider, model=model, temperature=temperature, config=config)
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

        # Iterator state
        self._current_items = None
        self._position = 0
        self._content = None
        self._config = None
        self._current_mode = None
        self._loop = None

    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    def _get_extractor(self, mode: ExtractionMode):
        """Get mode-specific extractor"""
        return self._fast_extractor if mode == ExtractionMode.FAST else self._slow_extractor

    def _ensure_event_loop(self):
        """Ensure we have an event loop for async calls"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def __iter__(self):
        """Initialize iteration - synchronous interface"""
        if self._current_mode == ExtractionMode.FAST:
            self._current_items = self._fast_extractor.create_iterator(
                self._content, 
                self._config
            )
            if not self._current_items.has_items() and self.extractor_config.allow_fallback:
                for mode in self.extractor_config.fallback_modes:
                    logger.info("extraction.fallback", 
                              from_mode=self._current_mode.value,
                              to_mode=mode.value)
                    self._current_mode = mode
                    if mode == ExtractionMode.SLOW:
                        break
        
        self._position = 0
        return self

    def __next__(self):
            """Get next item using current mode - synchronous interface"""
            if self._current_mode == ExtractionMode.FAST:
                if not self._current_items:
                    response = self._fast_extractor.process({
                        'content': self._content,
                        'config': self._config
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

            else:  # SLOW mode
                response = self._slow_extractor.process({
                    'content': self._content,
                    'config': self._config,
                    'position': self._position
                })
                
                if not response.success:
                    raise StopIteration
                    
                content = response.data.get('response', '')
                if 'NO_MORE_ITEMS' in str(content):
                    raise StopIteration
                    
                self._position += 1
                return content

    def configure(self, content: Any, config: ExtractConfig):
        """Configure iterator for use - synchronous interface"""
        self._content = content
        self._config = config
        self._position = 0
        self._current_items = None
        self._current_mode = self.extractor_config.initial_mode
        return self