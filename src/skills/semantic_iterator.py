"""
Semantic extraction and iteration implementation.
Path: src/skills/semantic_iterator.py

This module provides a flexible iterator pattern for extracting and processing
sequences of items from LLM responses. It handles various response formats and
wrapping patterns while maintaining a simple, focused interface.

Key patterns supported:
- Direct JSON arrays
- Wrapped responses (raw_output, response, items)
- Single-item responses
- Markdown-formatted content
- Structured API responses
"""

from typing import List, Dict, Any, Optional, Iterator, Union
import structlog
import json
import re
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

class ItemIterator:
    """Iterator over extracted items with stateful tracking.
    
    Provides a consistent interface for iterating over extracted items,
    regardless of their source format. Maintains iteration state and
    provides access to the original raw response.
    
    Attributes:
        _items: List of extracted items
        _index: Current iteration position
        _raw_response: Original response string
    """
    
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

    def __iter__(self) -> Iterator[Any]:
        """Make iterator compatible with for loops."""
        return self

    def peek(self) -> Optional[Any]:
        """Look at next item without advancing iterator."""
        if self.has_next():
            return self._items[self._index]
        return None

    def reset(self) -> None:
        """Reset iterator to beginning."""
        self._index = 0
        logger.debug("item_iterator.reset")

    def get_raw_response(self) -> str:
        """Get original raw response from LLM."""
        return self._raw_response

    def get_remaining(self) -> List[Any]:
        """Get remaining unprocessed items."""
        return self._items[self._index:]

    def __len__(self) -> int:
        """Get total number of items."""
        return len(self._items)

class SemanticIterator:
    """Extracts and iterates over semantic items from LLM responses.
    
    Provides a flexible way to extract sequences of items from various
    response formats. Uses semantic extraction via LLM to identify and
    structure items, then provides iteration over the results.
    """
    
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

    def _extract_items(self, response: Any) -> List[Any]:
        """Extract list of items from various response formats.
        
        Handles multiple response patterns in priority order:
        1. Direct list of items
        2. Wrapped lists (raw_output, changes, etc)
        3. JSON string containing items
        4. Single item responses
        
        Args:
            response: Response data in any supported format
            
        Returns:
            List of extracted items, empty list if no items found
            
        The extraction follows a careful hierarchy to avoid losing data
        while maintaining type safety and logging visibility.
        """
        if response is None:
            logger.debug("extract.input_none")
            return []

        # Log input characteristics
        logger.debug("extract.input",
                    type=type(response).__name__,
                    is_dict=isinstance(response, dict),
                    is_list=isinstance(response, list),
                    is_str=isinstance(response, str),
                    len=len(str(response)) if response else 0)

        # Handle dictionary responses (most common case)
        if isinstance(response, dict):
            # Log available keys for debugging
            keys = list(response.keys())
            logger.debug("extract.dict_keys", keys=keys)

            # 1. Check for known wrapper patterns in priority order
            wrapper_keys = ['changes', 'raw_output', 'response', 'items', 'data']
            for key in wrapper_keys:
                if key in response:
                    value = response[key]
                    logger.debug(f"extract.found_{key}",
                            value_type=type(value).__name__)
                    
                    if isinstance(value, list):
                        # Validate list items have required fields
                        if self._validate_items(value):
                            logger.debug(f"extract.valid_list_from_{key}",
                                    count=len(value))
                            return value
                        logger.debug(f"extract.invalid_items_from_{key}")
                    
                    # Recursively try to extract from non-list value
                    items = self._extract_items(value)
                    if items:
                        return items

            # 2. Check if dict itself is a valid item
            if self._is_valid_item(response):
                logger.debug("extract.single_item_dict")
                return [response]

        # Handle direct lists
        if isinstance(response, list):
            if not response:
                logger.debug("extract.empty_list")
                return []
                
            # Validate list items
            if self._validate_items(response):
                logger.debug("extract.direct_list", count=len(response))
                return response
                
            # Try extracting from list elements
            logger.debug("extract.processing_list_elements", count=len(response))
            extracted = []
            for item in response:
                if isinstance(item, (dict, str)):
                    items = self._extract_items(item)
                    if items:
                        extracted.extend(items)
            if extracted:
                logger.debug("extract.list_element_extraction", count=len(extracted))
                return extracted

        # Handle string responses
        if isinstance(response, str):
            # Clean string of common formatting
            cleaned = response.strip()
            if cleaned.startswith('```') and cleaned.endswith('```'):
                cleaned = '\n'.join(cleaned.split('\n')[1:-1])
            
            try:
                parsed = json.loads(cleaned)
                logger.debug("extract.string_json_parsed",
                            parsed_type=type(parsed).__name__)
                return self._extract_items(parsed)
            except json.JSONDecodeError as e:
                logger.debug("extract.json_parse_failed",
                            error=str(e),
                            preview=cleaned[:100])

                # Try finding JSON array in string
                matches = re.findall(r'\[[\s\S]*?\]', cleaned)
                for match in matches:
                    try:
                        parsed = json.loads(match)
                        if isinstance(parsed, list):
                            items = self._extract_items(parsed)
                            if items:
                                logger.debug("extract.found_json_in_string",
                                        count=len(items))
                                return items
                    except json.JSONDecodeError:
                        continue

        logger.debug("extract.no_items_found",
                    response_type=type(response).__name__)
        return []

    def _validate_items(self, items: List[Any]) -> bool:
        """Validate list items have required fields.
        
        Args:
            items: List of items to validate
            
        Returns:
            True if all items are valid, False otherwise
        """
        if not isinstance(items, list):
            return False
            
        required_fields = {'file_path', 'type', 'description'}
        for item in items:
            if not isinstance(item, dict):
                return False
            if not required_fields.issubset(item.keys()):
                return False
        return True

    def _is_valid_item(self, item: Dict[str, Any]) -> bool:
        """Check if dictionary is a valid item.
        
        Args:
            item: Dictionary to validate
            
        Returns:
            True if item has required fields, False otherwise
        """
        required_fields = {'file_path', 'type', 'description'}
        return isinstance(item, dict) and required_fields.issubset(item.keys())

    async def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Extract and iterate over items from content."""
        try:
            logger.info("semantic_iterator.extract.start", 
                    content_type=type(content).__name__,
                    format=config.format)

            # Try direct extraction first
            direct_items = self._extract_items(content)
            if direct_items:
                logger.debug("extract.direct_success", items_count=len(direct_items))
                return ItemIterator(direct_items, str(content))  # Direct creation instead of helper

            # Enhance prompt for LLM extraction
            enhanced_prompt = f"""Extract and return items as a JSON array.
            Format requirements:
            - Return ONLY a JSON array, no other text
            - Each object must have ALL required fields
            - Use proper JSON syntax with double quotes
            - No explanations or markdown, just the array

            Example format:
            [
                {{
                    "field1": "value1",
                    "field2": "value2"
                }}
            ]

            Original instruction:
            {config.instruction}"""

            # Get LLM extraction result
            result = await self.extractor.extract(
                content=content,
                prompt=enhanced_prompt,
                format_hint="json"
            )

            if not result.success:
                logger.warning("semantic_iterator.extract.failed",
                            error=result.error)
                return ItemIterator([], str(result.error))

            # Try multiple extraction paths
            items = None
            for source in [result.value, result.raw_response]:
                if source:
                    items = self._extract_items(source)
                    if items:
                        logger.debug("extract.source_success",
                                source_type=type(source).__name__,
                                items_count=len(items))
                        break

            if not items:
                logger.warning("semantic_iterator.extract.no_items")
                return ItemIterator([], result.raw_response)

            # Return iterator with processed items
            logger.info("semantic_iterator.extract.success",
                    items_count=len(items))
            return ItemIterator(items, result.raw_response)

        except Exception as e:
            logger.error("semantic_iterator.extract.error", 
                        error=str(e),
                        error_type=type(e).__name__)
            return ItemIterator([], str(e))

    async def extract_all(self, content: Any, config: ExtractConfig) -> List[Any]:
        """Extract all items at once.
        
        Convenience method to get all items as a list instead of iterating.
        
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