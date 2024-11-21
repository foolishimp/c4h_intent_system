"""
Semantic extraction and iteration implementation.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional
import structlog
import json
import re
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

@dataclass
class ParseResult:
    """Container for parse results"""
    success: bool
    items: List[Any]
    error: Optional[str] = None
    raw_response: str = ""

class ItemIterator:
    """Iterator over extracted items with preserved raw response"""
    
    def __init__(self, items: List[Any], raw_response: str = ""):
        """Initialize iterator with items and raw response.
        
        Args:
            items: List of items to iterate over
            raw_response: Original raw response from LLM
        """
        self._items = items if isinstance(items, list) else []
        self._index = 0
        self._raw_response = raw_response
        
        logger.debug("item_iterator.init",
                    items_count=len(self._items),
                    has_items=bool(self._items))
        
    def has_next(self) -> bool:
        """Check if there are more items."""
        return self._index < len(self._items)
        
    def __next__(self) -> Any:
        """Get next item in iteration."""
        if self.has_next():
            item = self._items[self._index]
            self._index += 1
            logger.debug("item_iterator.next", 
                        index=self._index-1,
                        total=len(self._items))
            return item
        logger.debug("item_iterator.complete")
        raise StopIteration

    def get_raw_response(self) -> str:
        """Get original raw response from LLM."""
        return self._raw_response

    def __len__(self) -> int:
        """Get total number of items."""
        return len(self._items)

class SemanticIterator:
    """Extracts and iterates over semantic items from LLM responses."""
    
    def __init__(self, config: List[Dict[str, Any]]):
        """Initialize iterator with configuration.
        
        Args:
            config: List of configuration dictionaries containing provider settings
        
        Raises:
            ValueError: If config is empty or missing required fields
        """
        if not config:
            logger.error("semantic_iterator.init.failed", error="Empty configuration")
            raise ValueError("Config must be a non-empty list")
            
        cfg = config[0]
        required_fields = ['provider', 'model', 'config']
        missing = [f for f in required_fields if f not in cfg]
        if missing:
            logger.error("semantic_iterator.init.failed", 
                        error=f"Missing required fields: {missing}")
            raise ValueError(f"Missing required fields: {missing}")

        self.extractor = SemanticExtract(
            provider=LLMProvider(cfg['provider']),
            model=cfg['model'],
            temperature=0,  # Always use 0 for deterministic extraction
            config=cfg.get('config')
        )
        
        logger.info("semantic_iterator.initialized", 
                   provider=cfg['provider'],
                   model=cfg['model'])

    """
    JSON array extraction implementation.
    Path: src/skills/semantic_iterator.py
    """

    def _extract_json_array(self, response: Any) -> ParseResult:
        """Extract JSON array from response.
        
        Args:
            response: Response that may contain a JSON array
                
        Returns:
            ParseResult containing extracted items or error
        """
        if not response:
            return ParseResult(False, [], "Empty response", str(response))
            
        # Handle dictionary response
        if isinstance(response, dict):
            # Check common keys that might contain arrays
            for key in ['raw_output', 'response', 'items', 'changes']:
                if key in response:
                    value = response[key]
                    if isinstance(value, list):
                        logger.debug("json_array.dict_extract.success",
                                key=key,
                                items_count=len(value))
                        return ParseResult(True, value, None, str(response))
            return ParseResult(False, [], "No array found in dictionary", str(response))

        # If response is string, try to parse JSON array
        if isinstance(response, str):
            # Try direct parse if looks like JSON array
            text = response.strip()
            if text.startswith('[') and text.endswith(']'):
                try:
                    items = json.loads(text)
                    if isinstance(items, list):
                        logger.debug("json_array.direct_parse.success",
                                items_count=len(items))
                        return ParseResult(True, items, None, text)
                except json.JSONDecodeError as e:
                    logger.debug("json_array.direct_parse.failed",
                            error=str(e))

            # Try to find array pattern
            array_match = re.search(r'\[[\s\S]*?\]', text)
            if array_match:
                try:
                    items = json.loads(array_match.group(0))
                    if isinstance(items, list):
                        logger.debug("json_array.pattern_match.success",
                                items_count=len(items))
                        return ParseResult(True, items, None, text)
                except json.JSONDecodeError as e:
                    logger.debug("json_array.pattern_match.failed",
                            error=str(e))

            # Try to parse as JSON object that might contain array
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    for key in ['raw_output', 'response', 'items', 'changes']:
                        if key in obj and isinstance(obj[key], list):
                            logger.debug("json_array.object_extract.success",
                                    key=key,
                                    items_count=len(obj[key]))
                            return ParseResult(True, obj[key], None, text)
            except json.JSONDecodeError:
                pass

        return ParseResult(False, [], "No valid JSON array found", str(response))

    def _enhance_prompt(self, instruction: str) -> str:
        """Add formatting requirements to instruction.
        
        Args:
            instruction: Original instruction to enhance
            
        Returns:
            Enhanced prompt with formatting requirements
        """
        return f"""You are a precise JSON array generator.
        
Your response must include a valid JSON array with the requested items.
You may include explanatory text, but the array must use proper JSON syntax.

INSTRUCTION:
{instruction}

RESPONSE REQUIREMENTS:
- Must include a JSON array with all requested fields
- Use proper JSON syntax with double quotes for strings
- Array can be empty if no items found: []
- Array can be preceded or followed by explanatory text

Example valid array:
[
    {{
        "field1": "value1",
        "field2": "value2"
    }}
]

Reminder: Always include a properly formatted JSON array in your response."""

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items from content.
        
        Args:
            content: Content to extract items from
            config: Extraction configuration and instructions
            
        Returns:
            ItemIterator for extracted items
        """
        try:
            logger.info("semantic_iterator.extract.start", 
                       content_type=type(content).__name__,
                       format=config.format)

            enhanced_prompt = self._enhance_prompt(config.instruction)
            
            logger.debug("semantic_iterator.prompt.enhanced",
                        original_length=len(config.instruction),
                        enhanced_length=len(enhanced_prompt))
                    
            result = await self.extractor.extract(
                content=content,
                prompt=enhanced_prompt,
                format_hint="json"
            )

            if result.success:
                parse_result = self._extract_json_array(result.raw_response)
                if parse_result.success:
                    logger.info("semantic_iterator.extract.complete",
                              items_count=len(parse_result.items))
                    return ItemIterator(parse_result.items, result.raw_response)
                else:
                    logger.warning("semantic_iterator.extract.no_array",
                                 error=parse_result.error)
            else:
                logger.warning("semantic_iterator.extract.failed",
                             error=result.error)
            
            return ItemIterator([], result.raw_response)

        except Exception as e:
            logger.error("semantic_iterator.extract.error", error=str(e))
            return ItemIterator([], str(e))

    async def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract all items at once.
        
        Args:
            content: Content to extract from
            config: Extraction configuration
            
        Returns:
            List of all extracted items
        """
        iterator = await self.iter_extract(content, config)
        items = []
        while iterator.has_next():
            items.append(next(iterator))
        logger.info("semantic_iterator.extract_all.complete",
                   items_count=len(items))
        return items