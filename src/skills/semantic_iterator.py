"""
Enhanced semantic iterator with simplified modes.
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

    def peek(self) -> Optional[Any]:
        """Look at next item without advancing"""
        if self.has_next():
            return self._state.items[self._state.position]
        return None

    def get_raw_response(self) -> str:
        """Get original response content"""
        return self._state.raw_response

    def get_state(self) -> ExtractionState:
        """Get current extraction state"""
        return self._state

class SemanticIterator:
    """Extracts and iterates over semantic items with configurable modes"""
    
    def __init__(self, 
                 config: List[Dict[str, Any]], 
                 extraction_modes: Optional[List[str]] = None,
                 default_mode: str = "fast"):
        """Initialize iterator with specified modes"""
        if not config:
            raise ValueError("Config required")
            
        # Ensure provider config is complete
        cfg = config[0]
        if 'providers' not in cfg.get('config', {}):
            cfg['config'] = {
                'providers': {
                    'anthropic': {
                        'api_base': 'https://api.anthropic.com',
                        'env_var': 'ANTHROPIC_API_KEY',
                        'context_length': 100000
                    }
                }
            }
            
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
            
        if not self.modes:  # Use default if no valid modes specified
            default = ExtractionMode(default_mode)
            self.modes = [default if default in allowed_modes else ExtractionMode.FAST]
            
        logger.info("iterator.configured", 
                   modes=self.modes,
                   default_mode=default_mode)

    async def _extract_fast(self, content: Any) -> Optional[List[Any]]:
        """Direct extraction from clean data structures"""
        if content is None:
            return None
        
        # Handle coroutines
        if hasattr(content, '__await__'):
            try:
                content = await content
            except Exception as e:
                logger.error("coroutine.extraction_failed", error=str(e))
                return None
            
        # Handle lists
        if isinstance(content, list):
            return content
            
        # Handle dict with improved nested search
        if isinstance(content, dict):
            # Look for list values at any level
            def find_lists(d: Dict) -> Optional[List]:
                if not isinstance(d, dict):
                    return None
                    
                # Priority keys to check first
                priority_keys = ['items', 'changes', 'results', 'data']
                for key in priority_keys:
                    if key in d and isinstance(d[key], list):
                        return d[key]
                
                # General search
                for v in d.values():
                    if isinstance(v, list):
                        return v
                    elif isinstance(v, dict):
                        nested = find_lists(v)
                        if nested:
                            return nested
                return None

            # Try to find lists
            if items := find_lists(content):
                return items

            # Handle single item case
            if any(k in content for k in ['type', 'name', 'content', 'value']):
                return [content]

        # Handle string content with improved parsing
        if isinstance(content, str):
            # Handle markdown code blocks
            if '```' in content:
                parts = content.split('```')
                for part in parts:
                    if part.startswith('json'):
                        content = part[4:].strip()
                        break
            
            try:
                parsed = json.loads(content)
                # Recursively try to extract from parsed content
                return self._extract_fast(parsed)
            except json.JSONDecodeError:
                # Try to find JSON-like structures in text
                json_pattern = r'\[[\s\S]*\]|\{[\s\S]*\}'
                matches = re.findall(json_pattern, content)
                for match in matches:
                    try:
                        parsed = json.loads(match)
                        return self._extract_fast(parsed)
                    except json.JSONDecodeError:
                        continue
                        
        return None

    async def _extract_slow(self, content: Any, config: ExtractConfig) -> Optional[List[Any]]:
        """LLM-based semantic extraction"""
        prompt = f"""Extract items from the following content. Return a JSON array of objects.
        
        Guidelines:
        1. Each object should have appropriate fields based on the content type
        2. Return ONLY the JSON array
        3. Include all relevant information in each object
        4. Use consistent field names across objects
        
        Instructions: {config.instruction}
        Content: {content}
        """
        
        try:
            result = await self.extractor.extract(
                content=content,
                prompt=prompt,
                format_hint="json"
            )
            
            if result.success:
                response = result.value
                
                # Handle various response formats
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                    except json.JSONDecodeError:
                        pass
                        
                if isinstance(response, dict):
                    # Check common wrapper keys
                    for key in ['items', 'results', 'data', 'changes']:
                        if key in response and isinstance(response[key], list):
                            return response[key]
                    return [response]
                elif isinstance(response, list):
                    return response
                    
        except Exception as e:
            logger.error("slow_extraction.error", error=str(e))
                
        return None

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items using configured modes."""
        # Initialize extraction state
        state = ExtractionState(
            current_mode=self.modes[0],
            attempted_modes=[],
            items=[],
            position=0,
            raw_response=str(content)
        )
        
        try:
            # Handle coroutines
            if hasattr(content, '__await__'):
                try:
                    content = await content
                except Exception as e:
                    logger.error("content.await_failed", error=str(e))
                    content = str(content)
            
            # Try each mode in sequence
            for mode in self.modes:
                try:
                    state.current_mode = mode
                    state.attempted_modes.append(mode)
                    
                    logger.info("extraction.attempt", mode=mode)
                    
                    items = None
                    if mode == ExtractionMode.FAST:
                        try:
                            items = await self._extract_fast(content)
                        except Exception as e:
                            logger.error("fast_extraction.failed", error=str(e))
                            continue
                            
                    elif mode == ExtractionMode.SLOW:
                        try:
                            items = await self._extract_slow(content, config)
                        except Exception as e:
                            logger.error("slow_extraction.failed", error=str(e))
                            continue
                    
                    # Process extracted items if found
                    if items:
                        # Ensure list type
                        if not isinstance(items, list):
                            items = [items]
                            
                        # Remove None and empty items
                        items = [item for item in items 
                                if item is not None and item != {}]
                                
                        if items:
                            state.items = items
                            logger.info("extraction.success", 
                                    mode=mode,
                                    items_found=len(items))
                            break
                        
                    logger.debug("extraction.no_items", 
                            mode=mode,
                            content_preview=str(content)[:100])
                        
                except Exception as e:
                    logger.error("extraction.failed",
                            mode=mode,
                            error=str(e))
                    state.error = str(e)
                    
                    if "coroutine" in str(e).lower():
                        break
                        
        except Exception as e:
            logger.error("extraction.process_failed", error=str(e))
            state.error = str(e)
            
        finally:
            logger.debug("extraction.complete",
                        attempted_modes=state.attempted_modes,
                        items_found=len(state.items) if state.items else 0,
                        has_error=bool(state.error))
        
        return ItemIterator(state)

    async def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract all items at once using configured modes"""
        iterator = await self.iter_extract(content, config)
        return [item for item in iterator]