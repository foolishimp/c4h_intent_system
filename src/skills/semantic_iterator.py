"""
Enhanced semantic iterator implementation.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
import json
import re
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract
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
    raw_response: str
    error: Optional[str] = None

class ItemIterator:
    """Iterator over extracted items with state tracking"""
    
    def __init__(self, state: ExtractionState):
        self._state = state
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items),
                    position=state.position)
    
    def __iter__(self):
        """Make iterator properly iterable"""
        return self
    
    def __next__(self) -> Any:
        """Get next item in iteration"""
        if self.has_next():
            item = self._state.items[self._state.position]
            self._state.position += 1
            return item
        raise StopIteration()

    def has_next(self) -> bool:
        """Check if more items available"""
        return self._state.position < len(self._state.items)

    def get_state(self) -> ExtractionState:
        """Get current extraction state"""
        return self._state

class SemanticIterator:
    """Extracts and iterates over semantic items with configurable modes"""
    
    LIST_FORMAT_PROMPT = """
    Your response MUST be a valid JSON array of objects, with NO additional text.
    
    Requirements:
    1. Start with '['
    2. End with ']'
    3. Each item must be a complete JSON object
    4. No text before or after the JSON array
    
    Example response format:
    [
        {
            "key1": "value1",
            "key2": "value2"
        },
        {
            "key1": "value3",
            "key2": "value4"
        }
    ]
    """
    
    def __init__(self, 
                 config: List[Dict[str, Any]], 
                 extraction_modes: Optional[List[str]] = None):
        """Initialize iterator with specified modes"""
        if not config:
            raise ValueError("Config required")
            
        cfg = config[0]
        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=0,
            config=cfg.get('config')
        )
        
        # Configure modes with improved validation
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

    """
    Semantic iterator with enhanced logging for fast extraction.
    Path: src/skills/semantic_iterator.py
    """

    async def _extract_fast(self, content: Any) -> Optional[List[Any]]:
        """Direct extraction from structured data"""
        if not content:
            logger.debug("fast_extract.empty_content")
            return None

        # Log incoming content type and structure
        logger.debug("fast_extract.input", 
                    content_type=type(content).__name__,
                    is_dict='content' in content if isinstance(content, dict) else False,
                    length=len(str(content)))

        # Enhanced handling of anthropic-style responses
        if isinstance(content, dict) and 'content' in content:
            logger.debug("fast_extract.checking_anthropic_format")
            for item in content.get('content', []):
                if isinstance(item, dict) and 'text' in item:
                    try:
                        logger.debug("fast_extract.parsing_text", text=item['text'][:100])
                        parsed = json.loads(item['text'])
                        if isinstance(parsed, list):
                            logger.info("fast_extract.found_items", count=len(parsed))
                            return parsed
                    except json.JSONDecodeError as e:
                        logger.debug("fast_extract.json_parse_failed", error=str(e))

        # Try standard JSON parsing if content is a string
        if isinstance(content, str):
            logger.debug("fast_extract.attempting_string_parse", content_preview=content[:100])
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    logger.info("fast_extract.found_list", count=len(parsed))
                    return parsed
                if isinstance(parsed, dict):
                    for key in ['items', 'changes', 'results']:
                        if key in parsed and isinstance(parsed[key], list):
                            logger.info(f"fast_extract.found_{key}", count=len(parsed[key]))
                            return parsed[key]
                    logger.debug("fast_extract.no_list_fields", available_keys=list(parsed.keys()))
            except json.JSONDecodeError as e:
                logger.debug("fast_extract.string_parse_failed", error=str(e))

        logger.debug("fast_extract.no_valid_data")
        return None

    async def _extract_slow(self, content: Any, config: ExtractConfig) -> Optional[List[Any]]:
        """LLM-based semantic extraction"""
        try:
            # Enhance prompt with list format requirements
            enhanced_prompt = f"""
            {config.instruction}
            
            {self.LIST_FORMAT_PROMPT}
            """
            
            result = await self.extractor.extract(
                content=content,
                prompt=enhanced_prompt,
                format_hint="json"
            )
            
            if result.success and result.value:
                # Try parsing the response
                if isinstance(result.value, str):
                    try:
                        # Strip any non-JSON content
                        json_str = result.value.strip()
                        if json_str.startswith('[') and json_str.endswith(']'):
                            items = json.loads(json_str)
                            if isinstance(items, list):
                                logger.info("slow_extract.found_items", count=len(items))
                                return items
                    except json.JSONDecodeError:
                        logger.error("slow_extract.json_parse_failed")
                        
            logger.debug("slow_extract.failed", 
                        success=result.success,
                        value_type=type(result.value).__name__)
                        
        except Exception as e:
            logger.error("slow_extract.error", error=str(e))
                
        return None

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items using configured modes"""
        state = ExtractionState(
            current_mode=self.modes[0],
            attempted_modes=[],
            items=[],
            position=0,
            raw_response=str(content)
        )
        
        try:
            # Try each mode in sequence
            for mode in self.modes:
                try:
                    state.current_mode = mode
                    state.attempted_modes.append(mode)
                    
                    logger.info("extraction.attempt", mode=mode)
                    
                    items = None
                    if mode == ExtractionMode.FAST:
                        items = await self._extract_fast(content)
                    elif mode == ExtractionMode.SLOW:
                        items = await self._extract_slow(content, config)
                    
                    if items:
                        # Validate items
                        if not isinstance(items, list):
                            items = [items]
                            
                        items = [item for item in items if item]
                        
                        if items:
                            state.items = items
                            logger.info("extraction.success", 
                                    mode=mode,
                                    items_found=len(items))
                            break
                            
                except Exception as e:
                    logger.error(f"extraction.{mode}_failed", error=str(e))
                    state.error = str(e)
                    
        except Exception as e:
            logger.error("extraction.failed", error=str(e))
            state.error = str(e)
            
        logger.info("extraction.complete",
                    attempted_modes=state.attempted_modes,
                    items_found=len(state.items))
                    
        return ItemIterator(state)