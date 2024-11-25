"""
Enhanced semantic iterator implementation with proper response handling.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
import json
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract, ExtractResult
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes from fastest to slowest"""
    FAST = "fast"      # Direct extraction from structured data
    SLOW = "slow"      # LLM-based semantic extraction

@dataclass
class ExtractionState:
    """Tracks extraction state across attempts"""
    current_mode: ExtractionMode
    attempted_modes: List[ExtractionMode]
    items: List[Any]
    position: int
    raw_response: str = ""  # Initialize empty, will be set with actual LLM response
    error: Optional[str] = None

class ItemIterator:
    """Iterator over extracted items with state tracking"""
    
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
        if self.has_next():
            item = self._state.items[self._state.position]
            self._state.position += 1
            return item
        raise StopIteration()

    def has_next(self) -> bool:
        return self._state.position < len(self._state.items)

    def get_state(self) -> ExtractionState:
        return self._state

class SemanticIterator:
    """Extracts and iterates over semantic items with configurable modes"""
    
    def __init__(self, 
                 config: List[Dict[str, Any]], 
                 extraction_modes: Optional[List[str]] = None):
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
        allowed_modes = [ExtractionMode.FAST, ExtractionMode.SLOW]
        self.modes = []
        
        if extraction_modes:
            validated_modes = []
            for mode in extraction_modes:
                try:
                    validated_modes.append(ExtractionMode(mode))
                except ValueError:
                    logger.warning(f"Invalid extraction mode: {mode}")
                    continue
            self.modes = [m for m in validated_modes if m in allowed_modes]
            
        if not self.modes:
            self.modes = [ExtractionMode.FAST, ExtractionMode.SLOW]
            
        logger.info("iterator.configured", modes=self.modes)

    async def _extract_fast(self, content: Any) -> Optional[List[Any]]:
        """Direct extraction from structured data"""
        if not content:
            logger.debug("fast_extract.empty_content")
            return None

        # Log incoming content for debugging
        logger.debug("fast_extract.input", 
                    content_type=type(content).__name__,
                    content_preview=str(content)[:100] if content else None)

        try:
            # Try to parse as JSON if it's a string
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        logger.info("fast_extract.direct_json_success", count=len(parsed))
                        return parsed
                except json.JSONDecodeError:
                    pass

            # Handle structured response
            if isinstance(content, dict):
                for key in ['response', 'raw_output', 'choices']:
                    value = content.get(key)
                    if isinstance(value, str):
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, list):
                                logger.info(f"fast_extract.{key}_success", count=len(parsed))
                                return parsed
                        except json.JSONDecodeError:
                            continue

            logger.debug("fast_extract.no_json_found")
            return None

        except Exception as e:
            logger.error("fast_extract.failed", error=str(e))
            return None

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items using configured modes"""
        state = ExtractionState(
            current_mode=self.modes[0],
            attempted_modes=[],
            items=[],
            position=0,
            raw_response=""
        )
        
        try:
            # Fast extraction attempt
            if ExtractionMode.FAST in self.modes:
                state.current_mode = ExtractionMode.FAST
                state.attempted_modes.append(ExtractionMode.FAST)
                
                logger.info("extraction.fast_attempt")
                if items := await self._extract_fast(content):
                    state.items = items
                    logger.info("extraction.fast_success", items_found=len(items))
                    return ItemIterator(state)

            # Key change: ALWAYS make LLM call if fast mode didn't return items
            logger.info("extraction.trying_llm")
            state.current_mode = ExtractionMode.SLOW
            state.attempted_modes.append(ExtractionMode.SLOW)
            
            result = await self.extractor.extract(
                content=content,
                prompt=config.instruction
            )

            # Store raw response regardless of parsing success
            state.raw_response = result.raw_response
            
            if result.success:
                logger.info("extraction.llm_success")
                if isinstance(result.value, list):
                    state.items = result.value
                elif isinstance(result.value, str):
                    try:
                        parsed = json.loads(result.value)
                        if isinstance(parsed, list):
                            state.items = parsed
                    except json.JSONDecodeError as e:
                        logger.error("json_parse_failed", error=str(e))
                        state.error = str(e)
            else:
                logger.error("extraction.llm_failed", error=result.error)
                state.error = result.error
                
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            state.error = str(e)
            
        return ItemIterator(state)
