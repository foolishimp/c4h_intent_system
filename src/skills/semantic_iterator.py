"""
Enhanced semantic iterator with configurable extraction modes.
Path: src/skills/semantic_iterator.py
"""

import os
from typing import List, Dict, Any, Optional, Iterator, Union
from enum import Enum
import structlog
import json
import re
from dataclasses import dataclass
from dotenv import load_dotenv  # Add this import
from src.skills.semantic_extract import SemanticExtract
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

# Load environment variables at module level
load_dotenv()  # This will load .env file

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes from fastest to slowest"""
    FAST = "fast"      # Direct extraction only
    MEDIUM = "medium"  # Pattern matching and heuristics
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
                 extraction_modes: Optional[List[str]] = None):
        """Initialize iterator with specified modes
        
        Args:
            config: LLM configuration
            extraction_modes: List of modes to try in sequence
                            Defaults to ["fast", "medium", "slow"]
        """
        if not config:
            raise ValueError("Config required")
            
        # Ensure environment variables are loaded
        if 'ANTHROPIC_API_KEY' not in os.environ:
            logger.warning("Environment check", 
                         env_vars=list(os.environ.keys()),
                         anthropic_key_present='ANTHROPIC_API_KEY' in os.environ)
            
        # Setup extractor
        cfg = config[0]
        # Ensure provider config is complete
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
        
        # Configure modes
        self.modes = [ExtractionMode(m) for m in (extraction_modes or ["fast", "medium", "slow"])]
        logger.info("iterator.configured", modes=self.modes)

    async def _extract_fast(self, content: Any) -> Optional[List[Any]]:
        """Direct extraction from clean data structures"""
        if content is None:
            return None
            
        # Handle lists
        if isinstance(content, list):
            return content
            
        # Handle dict
        if isinstance(content, dict):
            # Look for direct list values
            for value in content.values():
                if isinstance(value, list):
                    return value
                    
            # Look through nested structures
            for value in content.values():
                if isinstance(value, dict):
                    for nested_value in value.values():
                        if isinstance(nested_value, list):
                            return nested_value
                            
            # Single item case
            return [content]
        
        return None

    async def _extract_medium(self, content: Any) -> Optional[List[Any]]:
        """Pattern matching and heuristic extraction"""
        if not isinstance(content, str):
            content = str(content)
            
        items = []
        
        # Class extraction
        class_matches = re.finditer(r'class\s+(\w+)(?:\([^)]*\))?\s*:([^class]*?)(?=\s*class|\s*$)', 
                                  content, re.DOTALL)
        for match in class_matches:
            name, body = match.groups()
            items.append({
                "name": name,
                "code": f"class {name}:{body.rstrip()}"
            })
        
        # JSON pattern matching
        json_matches = re.findall(r'(?:\{[^}]+\}|\[[^\]]+\])', content)
        for match in json_matches:
            try:
                parsed = json.loads(match)
                if isinstance(parsed, list):
                    items.extend(parsed)
                elif isinstance(parsed, dict):
                    items.append(parsed)
            except json.JSONDecodeError:
                continue
                
        # CSV parsing
        if ',' in content and '\n' in content:
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            if len(lines) > 1:  # Has header
                header = [h.strip() for h in lines[0].split(',')]
                for line in lines[1:]:
                    values = [v.strip() for v in line.split(',')]
                    if len(values) == len(header):
                        items.append(dict(zip(header, values)))
        
        # Code block extraction
        code_blocks = re.finditer(r'```(?:\w+)?\s*(.*?)\s*```', content, re.DOTALL)
        for block in code_blocks:
            block_content = block.group(1)
            try:
                # Try parsing as JSON first
                items.append(json.loads(block_content))
            except json.JSONDecodeError:
                # If not JSON, treat as code content
                items.append({"content": block_content})
        
        return items if items else None

    async def _extract_slow(self, content: Any, config: ExtractConfig) -> Optional[List[Any]]:
        """LLM-based semantic extraction"""
        prompt = f"""Extract items from the following content. Return each item as a complete JSON object.
        
        Extraction guidelines:
        1. If content contains Python classes:
           - Extract each class with name and full code
           - Preserve indentation and formatting
        
        2. If content contains records (like CSV):
           - Create an object for each record
           - Include all fields with proper names
        
        3. If content contains natural text:
           - Identify distinct items
           - Create structured objects with relevant fields
        
        Format the output as a JSON array: 
        [
            {{"type": "item_type", "name": "item_name", "details": "..."}},
            ...
        ]
        
        Original instruction: {config.instruction}
        Content to analyze: {content}
        """
        
        try:
            result = await self.extractor.extract(
                content=content,
                prompt=prompt,
                format_hint="json"
            )
            
            if result.success:
                # Handle both array and single object responses
                if isinstance(result.value, list):
                    return result.value
                elif isinstance(result.value, dict):
                    if "items" in result.value:
                        return result.value["items"]
                    return [result.value]
                    
        except Exception as e:
            logger.error("slow_extraction.error", error=str(e))
                
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
        
        for mode in self.modes:
            try:
                state.current_mode = mode
                state.attempted_modes.append(mode)
                
                logger.info("extraction.attempt", mode=mode)
                
                items = None
                if mode == ExtractionMode.FAST:
                    items = await self._extract_fast(content)
                elif mode == ExtractionMode.MEDIUM:
                    items = await self._extract_medium(content)
                elif mode == ExtractionMode.SLOW:
                    items = await self._extract_slow(content, config)
                    
                if items:
                    state.items = items
                    logger.info("extraction.success", 
                              mode=mode,
                              items_found=len(items))
                    break
                    
            except Exception as e:
                logger.error("extraction.failed",
                           mode=mode,
                           error=str(e))
                state.error = str(e)
        
        return ItemIterator(state)

    async def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract all items at once using configured modes"""
        iterator = await self.iter_extract(content, config)
        items = []
        while iterator.has_next():
            items.append(next(iterator))
        return items