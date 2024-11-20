# tests/test_semantic_iterator.py

"""
Test suite for semantic extraction and iteration.
Path: tests/test_semantic_iterator.py
"""

import pytest
import structlog
from textwrap import dedent
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

# Test data
MARKDOWN_WITH_CODE = dedent('''
    # Data Processing Example
    Here's the base class:
    ```python
    class DataProcessor:
        def process(self, data: Dict) -> Dict:
            raise NotImplementedError()
    ```
    And implementation:
    ```python
    class JsonProcessor(DataProcessor):
        def process(self, data: Dict) -> Dict:
            return {"processed": data}
    ```
''')

@pytest.fixture
def iterator_config(test_config):
    """Create standardized iterator config."""
    return [{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }]

@pytest.mark.asyncio
async def test_iteration_basics(iterator_config):
    """Test basic iteration functionality."""
    iterator = SemanticIterator(iterator_config)
    
    instruction = """Extract Python class definitions with name and code. Return as JSON array with fields:
    - name: The class name
    - code: The complete class definition
    """
    
    config = ExtractConfig(
        instruction=instruction,
        format="json"
    )
    
    result = await iterator.iter_extract(MARKDOWN_WITH_CODE, config)
    
    # Test raw response access
    raw_response = result.get_raw_response()
    assert isinstance(raw_response, str)
    
    # Test iteration
    items = []
    while result.has_next():
        item = next(result)
        items.append(item)
        
        # Verify item structure
        assert isinstance(item, dict)
        assert 'name' in item
        assert 'code' in item
    
    assert len(items) > 0, "Should extract at least one class"

@pytest.mark.asyncio
async def test_bulk_extraction(iterator_config):
    """Test bulk extraction functionality."""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract Python class definitions with name and code",
        format="json"
    )
    
    items = await iterator.extract_all(MARKDOWN_WITH_CODE, config)
    
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert isinstance(item, dict)
        assert 'name' in item
        assert 'code' in item

@pytest.mark.asyncio
async def test_empty_content(iterator_config):
    """Test handling of empty content."""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract items",
        format="json"
    )
    
    result = await iterator.iter_extract("", config)
    assert isinstance(result.get_raw_response(), str)
    
    items = []
    while result.has_next():
        items.append(next(result))
    
    assert isinstance(items, list)
    assert len(items) == 0

@pytest.mark.asyncio
async def test_error_recovery(iterator_config):
    """Test recovery from extraction errors."""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract items",
        format="json"
    )
    
    # Test with None content
    result = await iterator.iter_extract(None, config)
    assert isinstance(result.get_raw_response(), str)
    assert not result.has_next()
    
    # Test with invalid content
    result = await iterator.iter_extract(object(), config)
    assert isinstance(result.get_raw_response(), str)
    assert not result.has_next()

@pytest.mark.asyncio
async def test_iterator_config_validation():
    """Test iterator configuration validation."""
    with pytest.raises(ValueError):
        SemanticIterator([])  # Empty config
        
    with pytest.raises(ValueError):
        SemanticIterator(None)  # None config