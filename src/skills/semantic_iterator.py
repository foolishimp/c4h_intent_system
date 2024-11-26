"""
Enhanced semantic iterator with fast and slow extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union, Tuple
import structlog
import json
import asyncio
from dataclasses import dataclass
from enum import Enum
from .shared.types import ExtractConfig, ExtractionState
from .semantic_extract import SemanticExtract
from src.agents.base import BaseAgent, LLMProvider, AgentResponse, LLMConfigError

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
    content: Any = None
    config: Optional[ExtractConfig] = None
    extractor: Optional[SemanticExtract] = None

class ItemIterator:
    """Iterator over extracted items with state access"""
    
    def __init__(self, state: ExtractionState):
        self._state = state
        self._loop = None
        self._peek_cache = None
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items),
                    position=state.position)

    @staticmethod
    def _generate_ordinal(n: int) -> str:
        """Generate ordinal string for a number"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    def _ensure_loop(self):
        """Ensure we have an event loop"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    @property
    def state(self) -> ExtractionState:
        """Access to iterator state"""
        return self._state

    def peek(self) -> Optional[Any]:
        """Look at next item without advancing"""
        if self._state.current_mode == ExtractionMode.FAST:
            if not self._has_next_fast():
                return None
            return self._state.items[self._state.position]
        else:
            if not self._peek_cache:
                try:
                    self._ensure_loop()
                    self._peek_cache = self._loop.run_until_complete(self._get_next_slow())
                except StopAsyncIteration:
                    return None
            return self._peek_cache

    def back(self) -> Optional[Any]:
        """Move back one item if possible"""
        if self._state.position > 0:
            self._state.position -= 1
            if self._state.current_mode == ExtractionMode.FAST:
                return self._state.items[self._state.position]
            # For slow mode, we'd need to re-extract
            return None
        return None

    def reset(self) -> None:
        """Reset iterator to beginning"""
        self._state.position = 0
        self._peek_cache = None

    def skip(self, count: int) -> None:
        """Skip forward by count items"""
        if self._state.current_mode == ExtractionMode.FAST:
            self._state.position = min(
                self._state.position + count,
                len(self._state.items)
            )
        else:
            # For slow mode, we need to advance carefully
            for _ in range(count):
                try:
                    next(self)
                except StopIteration:
                    break

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        """Unified sync interface for both fast and slow modes"""
        try:
            if self._state.current_mode == ExtractionMode.FAST:
                if not self._has_next_fast():
                    logger.info("fast_extract.completed",
                              total_items=len(self._state.items))
                    raise StopIteration()
                    
                item = self._state.items[self._state.position]
                self._state.position += 1
                return item
            else:
                self._ensure_loop()
                try:
                    return self._loop.run_until_complete(self._get_next_slow())
                except StopAsyncIteration as e:
                    logger.info("slow_extract.completed",
                              position=self._state.position)
                    raise StopIteration()
                
        except Exception as e:
            logger.error("iterator.error",
                        error=str(e),
                        mode=self._state.current_mode,
                        position=self._state.position)
            raise StopIteration()

    def _has_next_fast(self) -> bool:
        """Check for next item in fast mode"""
        return (bool(self._state.items) and 
                self._state.position >= 0 and 
                self._state.position < len(self._state.items))

    async def _get_next_slow(self) -> Any:
        """Get next item in slow mode"""
        try:
            ordinal = self._generate_ordinal(self._state.position + 1)
            
            # Get slow extraction prompt from config
            prompt = self._state.extractor._get_prompt('slow_extract').format(
                ordinal=ordinal,
                instruction=self._state.config.instruction,
                format=self._state.config.format,
                content=self._state.content
            )
            
            logger.info("slow_extract.requesting_item", 
                       position=self._state.position + 1,
                       ordinal=ordinal)
            
            result = await self._state.extractor.extract(
                content=self._state.content,
                prompt=prompt,
                format_hint=self._state.config.format
            )
            
            if not result.success:
                logger.error("slow_extract.failed", error=result.error)
                raise StopAsyncIteration
                
            self._state.raw_response = result.raw_response
            
            response_text = str(result.value).upper().replace(" ", "")
            if "NO_MORE_ITEMS" in response_text:
                logger.info("slow_extract.completed", 
                          position=self._state.position)
                raise StopAsyncIteration
                
            # Validate extracted item
            validate_prompt = self._state.extractor._get_prompt('slow_validate').format(
                format=self._state.config.format
            )
            
            validation = await self._state.extractor.extract(
                content=result.value,
                prompt=validate_prompt,
                format_hint=self._state.config.format
            )
            
            if not validation.success:
                logger.error("slow_extract.validation_failed",
                           error=validation.error)
                raise StopAsyncIteration
            
            # Parse and return validated item
            try:
                if isinstance(validation.value, dict):
                    item = validation.value
                else:
                    item = json.loads(validation.value)
                
                self._state.position += 1
                
                # Periodically summarize progress
                if self._state.position % 5 == 0:
                    await self._summarize_progress()
                    
                return item
                
            except json.JSONDecodeError as e:
                logger.error("slow_extract.parse_error", 
                           error=str(e))
                raise StopAsyncIteration
                
        except Exception as e:
            logger.error("slow_extract.error", error=str(e))
            raise StopAsyncIteration

    async def _summarize_progress(self):
        """Summarize extraction progress"""
        try:
            prompt = self._state.extractor._get_prompt('slow_summarize').format(
                count=self._state.position,
                position=self._state.position
            )
            
            result = await self._state.extractor.extract(
                content=self._state.content,
                prompt=prompt,
                format_hint="text"
            )
            
            if result.success:
                logger.info("extraction.progress", 
                          summary=result.value)
                          
        except Exception as e:
            logger.error("summarize.failed", error=str(e))

class SemanticIterator(BaseAgent):
    """Iterator factory for semantic extraction"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: str,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None,
                 extraction_modes: Optional[List[str]] = None,
                 allow_fallback: bool = True):
        """Initialize iterator with provider configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.extractor = SemanticExtract(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.modes = [ExtractionMode(m) for m in (extraction_modes or ["fast", "slow"])]
        self.allow_fallback = allow_fallback

    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    async def _extract_fast(self, content: Any, config: ExtractConfig) -> Tuple[Optional[List[Any]], str]:
        """Fast extraction attempting direct JSON parsing then single LLM call."""
        try:
            prompt = self._get_prompt('fast_extract').format(
                instruction=config.instruction,
                format=config.format,
                content=content
            )

            result = await self.extractor.extract(
                content=content,
                prompt=prompt,
                format_hint="json"
            )
            
            if result.success and result.value:
                try:
                    if isinstance(result.value, list):
                        return result.value, result.raw_response
                    parsed = json.loads(result.value)
                    if isinstance(parsed, list):
                        return parsed, result.raw_response
                except json.JSONDecodeError:
                    pass

            return None, result.raw_response if result else ""
            
        except Exception as e:
            logger.error("fast_extract.failed", error=str(e))
            return None, ""

    def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Create iterator for extracting items"""
        try:
            self._ensure_loop()
            
            state = ExtractionState(
                current_mode=self.modes[0],
                attempted_modes=[],
                items=[],
                position=0,
                content=content,
                config=config,
                extractor=self.extractor
            )
            
            if ExtractionMode.FAST in self.modes:
                logger.info("extraction.attempt", mode="fast")
                state.attempted_modes.append(ExtractionMode.FAST)
                
                items, raw_response = self._loop.run_until_complete(
                    self._extract_fast(content, config)
                )
                
                state.raw_response = raw_response
                
                if items:
                    state.items = items
                    logger.info("extraction.fast_success",
                              items_found=len(items))
                    return ItemIterator(state)
                    
                if self.allow_fallback and ExtractionMode.SLOW in self.modes:
                    logger.info("extraction.fallback_to_slow")
                    state.current_mode = ExtractionMode.SLOW
                    state.attempted_modes.append(ExtractionMode.SLOW)
                    return ItemIterator(state)
                    
            elif ExtractionMode.SLOW in self.modes:
                logger.info("extraction.using_slow_mode")
                state.current_mode = ExtractionMode.SLOW
                state.attempted_modes.append(ExtractionMode.SLOW)
                return ItemIterator(state)

            return ItemIterator(state)
            
        except Exception as e:
            logger.error("iterator.creation_failed", error=str(e))
            return ItemIterator(ExtractionState(
                current_mode=ExtractionMode.FAST,
                attempted_modes=[],
                items=[],
                position=0
            ))
        
    def get_progress(self) -> Dict[str, Any]:
        """Get current extraction progress"""
        return {
            "position": self._state.position,
            "mode": self._state.current_mode.value,
            "attempted_modes": [m.value for m in self._state.attempted_modes],
            "has_error": bool(self._state.error),
            "error": self._state.error
        }

    def get_state(self) -> ExtractionState:
        """Access current state"""
        return self._state

    def set_mode(self, mode: Union[str, ExtractionMode]) -> None:
        """Explicitly set extraction mode"""
        if isinstance(mode, str):
            mode = ExtractionMode(mode)
        self._state.current_mode = mode
        if mode not in self._state.attempted_modes:
            self._state.attempted_modes.append(mode)