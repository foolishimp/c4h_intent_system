"""
Enhanced semantic iterator implementation with robust fast and slow modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union, Tuple
from enum import Enum
import structlog
import json
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract, ExtractResult
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes"""
    FAST = "fast"      # Direct extraction from structured data
    SLOW = "slow"      # Sequential item-by-item extraction

@dataclass
class ExtractionState:
    """Tracks extraction state across attempts"""
    current_mode: ExtractionMode
    attempted_modes: List[ExtractionMode]
    items: List[Any]
    position: int
    raw_response: str = ""
    error: Optional[str] = None
    # Additional fields for slow mode
    content: Any = None
    config: Optional[ExtractConfig] = None
    extractor: Optional[SemanticExtract] = None

class ItemIterator:
    """Iterator over extracted items"""
    
    def __init__(self, state: ExtractionState):
        self._state = state
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items),
                    position=state.position,
                    has_response=bool(state.raw_response))
    
    def __iter__(self):
        return self
    
    def __next__(self) -> Any:
        """Standard iteration for fast mode"""
        if not self.has_next():
            raise StopIteration()
            
        if self._state.current_mode == ExtractionMode.FAST:
            item = self._state.items[self._state.position]
            self._state.position += 1
            return item
        else:
            raise RuntimeError("Slow mode requires async iteration")

    async def __anext__(self) -> Any:
        """Async iteration for slow mode"""
        if not await self.has_next():
            raise StopAsyncIteration
            
        if self._state.current_mode == ExtractionMode.FAST:
            return self.__next__()
            
        # Slow mode: extract next item
        try:
            nth_prompt = f"""From the following content, return ONLY the {self._state.position}th instance of the requested item.
            If no {self._state.position}th item exists, return exactly "NO_MORE_ITEMS".
            
            {self._state.config.instruction}"""
            
            logger.info("slow_extract.requesting_item", position=self._state.position)
            
            result = await self._state.extractor.extract(
                content=self._state.content,
                prompt=nth_prompt
            )
            
            if not result.success:
                logger.error("slow_extract.failed", error=result.error)
                raise StopAsyncIteration
                
            self._state.raw_response = result.raw_response
            
            if not result.value or "NO_MORE_ITEMS" in str(result.value):
                logger.info("slow_extract.no_more_items", position=self._state.position)
                raise StopAsyncIteration
                
            self._state.position += 1
            return result.value
            
        except Exception as e:
            logger.error("slow_extract.error", error=str(e))
            raise StopAsyncIteration

    async def has_next(self) -> bool:
        """Check for next item availability"""
        if self._state.current_mode == ExtractionMode.FAST:
            return self._state.position < len(self._state.items)
        return True  # Slow mode checks in __anext__

    def get_state(self) -> ExtractionState:
        """Get current iterator state"""
        return self._state

class SemanticIterator:
    """Extracts and iterates over semantic items"""
    
    def __init__(self, 
                 config: List[Dict[str, Any]], 
                 extraction_modes: Optional[List[str]] = None,
                 allow_fallback: bool = False):
        """Initialize iterator with configuration and modes.
        
        Args:
            config: LLM configuration dictionary
            extraction_modes: List of modes to use in order (default: ['fast'])
            allow_fallback: Whether to allow fallback from fast to slow mode
        """
        if not config:
            raise ValueError("Config required")
            
        cfg = config[0]
        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=cfg.get('temperature', 0),
            config=cfg.get('config')
        )
        
        # Configure modes
        self.modes = []
        self.allow_fallback = allow_fallback
        
        if extraction_modes:
            for mode in extraction_modes:
                try:
                    self.modes.append(ExtractionMode(mode))
                except ValueError:
                    logger.warning(f"Invalid extraction mode: {mode}")
                    continue
                    
        if not self.modes:
            self.modes = [ExtractionMode.FAST]
            
        logger.info("iterator.configured",
                   modes=[m.value for m in self.modes],
                   allow_fallback=allow_fallback)

    async def _extract_fast(self, content: Any) -> Tuple[Optional[List[Any]], str]:
        """Fast extraction attempting direct JSON parsing then single LLM call.
        Returns tuple of (items, raw_response)
        """
        if not content:
            logger.debug("fast_extract.empty_content")
            return None, ""
            
        logger.debug("fast_extract.input",
                    content_type=type(content).__name__,
                    content_preview=str(content)[:100] if content else None)
                    
        try:
            # Step 1: Try direct JSON parse
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        logger.info("fast_extract.direct_json_success",
                                  count=len(parsed))
                        return parsed, content
                except json.JSONDecodeError:
                    pass

            # Step 2: Check response structure
            if isinstance(content, dict):
                for key in ['response', 'raw_output', 'choices']:
                    value = content.get(key)
                    if isinstance(value, str):
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, list):
                                logger.info(f"fast_extract.{key}_success",
                                          count=len(parsed))
                                return parsed, value
                        except json.JSONDecodeError:
                            continue

            # Step 3: Make LLM call
            result = await self.extractor.extract(
                content=content,
                prompt="Extract items as JSON array")
                
            if result.success and result.value:
                try:
                    if isinstance(result.value, list):
                        return result.value, result.raw_response
                    parsed = json.loads(result.value)
                    if isinstance(parsed, list):
                        return parsed, result.raw_response
                except (json.JSONDecodeError, TypeError):
                    pass

            logger.debug("fast_extract.no_items_found")
            return None, result.raw_response if result else ""
            
        except Exception as e:
            logger.error("fast_extract.failed", error=str(e))
            return None, ""

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items using configured mode.
        
        Args:
            content: Content to extract from
            config: Extraction configuration
            
        Returns:
            ItemIterator instance
        """
        state = ExtractionState(
            current_mode=self.modes[0],
            attempted_modes=[],
            items=[],
            position=0,
            raw_response="",
            content=content,
            config=config,
            extractor=self.extractor
        )
        
        try:
            # Try fast extraction first if enabled
            if ExtractionMode.FAST in self.modes:
                logger.info("extraction.attempt", mode="fast")
                state.attempted_modes.append(ExtractionMode.FAST)
                
                items, raw_response = await self._extract_fast(content)
                state.raw_response = raw_response
                
                if items:
                    state.items = items
                    logger.info("extraction.fast_success",
                              items_found=len(items))
                    return ItemIterator(state)
                    
                # Handle fallback to slow mode if enabled and configured
                if (self.allow_fallback and 
                    ExtractionMode.SLOW in self.modes):
                    logger.info("extraction.fallback_to_slow")
                    state.current_mode = ExtractionMode.SLOW
                    state.attempted_modes.append(ExtractionMode.SLOW)
                    state.position = 1  # Start with first item
                    return ItemIterator(state)
                    
            # Initialize slow mode if it's the primary mode
            elif ExtractionMode.SLOW in self.modes:
                logger.info("extraction.using_slow_mode")
                state.current_mode = ExtractionMode.SLOW
                state.attempted_modes.append(ExtractionMode.SLOW)
                state.position = 1  # Start with first item
                return ItemIterator(state)

            logger.info("extraction.complete",
                       mode=state.current_mode.value,
                       attempted_modes=[m.value for m in state.attempted_modes],
                       items_found=len(state.items))
                    
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            state.error = str(e)
            
        return ItemIterator(state)