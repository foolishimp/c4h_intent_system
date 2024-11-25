"""
Enhanced semantic iterator with proper state access.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union, Tuple
from enum import Enum
import structlog
import json
import asyncio
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
    content: Any = None
    config: Optional[ExtractConfig] = None
    extractor: Optional[SemanticExtract] = None

class ItemIterator:
    """Iterator over extracted items with state access"""
    
    def __init__(self, state: ExtractionState):
        self._state = state
        self._loop = None
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

    @property
    def state(self) -> ExtractionState:
        """Access to iterator state"""
        return self._state

    def get_state(self) -> ExtractionState:
        """Get current extraction state"""
        return self._state

    def _ensure_loop(self):
        """Ensure we have an event loop, create if needed"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

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
                    if str(e) == "Completed normal iteration":
                        logger.info("iteration.completed",
                                  mode=self._state.current_mode,
                                  total_items=self._state.position)
                    else:
                        logger.warning("iteration.stopped",
                                     reason=str(e),
                                     mode=self._state.current_mode,
                                     items_processed=self._state.position)
                    raise StopIteration()
                
        except Exception as e:
            if isinstance(e, StopIteration):
                # Clean completion, just re-raise
                raise
            logger.error("iterator.error",
                        error=str(e),
                        error_type=type(e).__name__,
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
            
            nth_prompt = f"""Extract the {ordinal} item from the content.

Original instruction for reference:
{self._state.config.instruction}

Important:
1. Return ONLY the {ordinal} item that matches the format
2. Use EXACTLY the same JSON structure as shown in the original instruction
3. If no {ordinal} item exists, return exactly "NO_MORE_ITEMS"
4. Do not include any explanations or additional text

Content to analyze:
{self._state.content}"""
            
            logger.info("slow_extract.requesting_item", 
                    position=self._state.position + 1,
                    ordinal=ordinal)
            
            result = await self._state.extractor.extract(
                content=self._state.content,
                prompt=nth_prompt,
                format_hint=self._state.config.format
            )
            
            if not result.success:
                logger.error("slow_extract.failed", error=result.error)
                raise StopAsyncIteration
                
            self._state.raw_response = result.raw_response
            
            response_text = str(result.value).upper().replace(" ", "")
            if "NO_MORE_ITEMS" in response_text or "NOMOREITEM" in response_text:
                logger.info("slow_extract.completed", 
                    position=self._state.position,
                    total_items_processed=self._state.position)
                # Use a specific exception for iteration completion
                raise StopAsyncIteration("Completed normal iteration")
                
            try:
                if isinstance(result.value, dict):
                    parsed_item = result.value
                else:
                    response_str = str(result.value).strip()
                    if response_str.startswith('[') and response_str.endswith(']'):
                        parsed_item = json.loads(response_str)[0]
                    else:
                        parsed_item = json.loads(response_str)
                
                self._state.position += 1
                return parsed_item
                
            except json.JSONDecodeError as e:
                logger.error("slow_extract.json_parse_error", 
                            error=str(e),
                            content=result.value if 'result' in locals() else None)
                raise StopAsyncIteration(f"JSON parse error: {str(e)}")
                
        except Exception as e:
            if isinstance(e, StopAsyncIteration):
                # Re-raise completion signal with context
                raise
            logger.error("slow_extract.unexpected_error", 
                        error=str(e),
                        error_type=type(e).__name__)
            raise StopAsyncIteration(f"Extraction error: {str(e)}")
        
class SemanticIterator:
    """Iterator factory for semantic extraction"""
    
    def __init__(self, 
                 config: List[Dict[str, Any]], 
                 extraction_modes: Optional[List[str]] = None,
                 allow_fallback: bool = False):
        """Initialize iterator with configuration and modes."""
        if not config:
            raise ValueError("Config required")
            
        cfg = config[0]
        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=cfg.get('temperature', 0),
            config=cfg.get('config')
        )
        
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
        """Fast extraction attempting direct JSON parsing then single LLM call."""
        if not content:
            logger.debug("fast_extract.empty_content")
            return None, ""

        try:
            fast_prompt = f"""Extract ALL items at once as a complete list.

Original instruction:
{self.extract_config.instruction}

Important:
1. Return items in a single JSON array
2. Use exactly the same structure for each item
3. Include ALL matching items
4. Do not include any explanations or text before/after the JSON array

Content to analyze:
{content}"""

            result = await self.extractor.extract(
                content=content,
                prompt=fast_prompt,
                format_hint="json"
            )
            
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

    def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Create iterator for extracting items.
        
        Args:
            content: Content to extract from
            config: Extraction configuration
            
        Returns:
            ItemIterator instance
        """
        self.extract_config = config
        
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
            if ExtractionMode.FAST in self.modes:
                logger.info("extraction.attempt", mode="fast")
                state.attempted_modes.append(ExtractionMode.FAST)
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    items, raw_response = loop.run_until_complete(
                        self._extract_fast(content)
                    )
                finally:
                    loop.close()
                
                state.raw_response = raw_response
                
                if items:
                    state.items = items
                    logger.info("extraction.fast_success",
                              items_found=len(items))
                    return ItemIterator(state)
                    
                if (self.allow_fallback and 
                    ExtractionMode.SLOW in self.modes):
                    logger.info("extraction.fallback_to_slow")
                    state.current_mode = ExtractionMode.SLOW
                    state.attempted_modes.append(ExtractionMode.SLOW)
                    return ItemIterator(state)
                    
            elif ExtractionMode.SLOW in self.modes:
                logger.info("extraction.using_slow_mode")
                state.current_mode = ExtractionMode.SLOW
                state.attempted_modes.append(ExtractionMode.SLOW)
                return ItemIterator(state)

            logger.info("extraction.complete",
                       mode=state.current_mode.value,
                       attempted_modes=[m.value for m in state.attempted_modes],
                       items_found=len(state.items))
                    
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            state.error = str(e)
            
        return ItemIterator(state)