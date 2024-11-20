"""
Test suite for semantic iteration functionality.
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
    """Create standardized iterator config"""
    return [{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }]

@pytest.mark.asyncio
async def test_iteration_basics(iterator_config):
    """Test basic iteration functionality"""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract Python class definitions with name and code",
        format="json"
    )
    
    # Test async iteration
    items = []
    async for item in iterator.iter_extract(MARKDOWN_WITH_CODE, config):
        items.append(item)
        logger.info("received_item", item=item)
    
    assert items, "Should receive items from iterator"

@pytest.mark.asyncio
async def test_bulk_extraction(iterator_config):
    """Test bulk extraction functionality"""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract Python class definitions with name and code",
        format="json"
    )
    
    items = await iterator.extract_all(MARKDOWN_WITH_CODE, config)
    assert items, "Should receive items from bulk extraction"

@pytest.mark.asyncio
async def test_empty_content(iterator_config):
    """Test handling of empty content"""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract items",
        format="json"
    )
    
    items = await iterator.extract_all("", config)
    assert not items, "Should handle empty content gracefully"

@pytest.mark.asyncio
async def test_error_recovery(iterator_config):
    """Test recovery from extraction errors"""
    iterator = SemanticIterator(iterator_config)
    
    config = ExtractConfig(
        instruction="Extract items",
        format="json"
    )
    
    # Test with None content
    items = await iterator.extract_all(None, config)
    assert not items, "Should handle None content gracefully"

    # Test with invalid content
    items = await iterator.extract_all(object(), config)
    assert not items, "Should handle invalid content gracefully"