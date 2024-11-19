"""
Test suite for semantic extraction and iteration across different data formats.
Path: tests/test_semantic_iterator.py
"""

import pytest
from typing import List, Dict, Any
import structlog
from dataclasses import dataclass
from textwrap import dedent
from src.agents.base import LLMProvider
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

@dataclass
class TestData:
    """Test data container for different formats"""
    
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
    
    CSV_DATA = dedent('''
        name,category,habitat
        Northern Cardinal,Songbird,Woodland
        Blue Jay,Corvid,Forest
        American Robin,Thrush,Urban
        House Sparrow,Sparrow,Urban
    ''')
    
    JSON_RECORDS = {
        "birds": [
            {"name": "Eagle", "type": "Raptor", "wingspan": "2.3m"},
            {"name": "Owl", "type": "Nocturnal", "wingspan": "1.4m"},
            {"name": "Hummingbird", "type": "Small", "wingspan": "0.12m"}
        ]
    }
    
    NATURAL_TEXT = dedent('''
        Common birds in North America include the American Robin, 
        which has a red breast and yellow beak. The Blue Jay is 
        known for its bright blue feathers and loud calls. 
        Northern Cardinals are striking red birds often seen at feeders.
        The tiny Ruby-throated Hummingbird can hover and fly backwards.
    ''')

@pytest.mark.asyncio
async def test_code_block_extraction(test_config):
    """Test extraction of Python classes from markdown"""
    config = ExtractConfig(
        pattern="Extract each Python class as a separate item with name and code",
        format="json"
    )
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])
    
    result = await iterator.iter_extract(TestData.MARKDOWN_WITH_CODE, config)
    classes = [block for block in iter(lambda: next(result) if result.has_next() else None, None)]
    
    assert len(classes) == 2
    assert "DataProcessor" in classes[0]["code"]
    assert "JsonProcessor" in classes[1]["code"]

@pytest.mark.asyncio
async def test_csv_record_iteration(test_config):
    """Test extraction of structured CSV records"""
    config = ExtractConfig(
        pattern="Extract each bird record with name and habitat",
        format="json"
    )
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])
    
    result = await iterator.iter_extract(TestData.CSV_DATA, config)
    birds = [bird for bird in iter(lambda: next(result) if result.has_next() else None, None)]
    
    assert len(birds) == 4
    assert birds[0]["name"] == "Northern Cardinal"
    assert birds[0]["habitat"] == "Woodland"

@pytest.mark.asyncio
async def test_json_bird_extraction(test_config):
    """Test extraction from nested JSON"""
    config = ExtractConfig(
        pattern="Extract each bird with name and wingspan",
        format="json"
    )
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])
    
    result = await iterator.iter_extract(TestData.JSON_RECORDS, config)
    birds = [bird for bird in iter(lambda: next(result) if result.has_next() else None, None)]
    
    assert len(birds) == 3
    assert birds[0]["name"] == "Eagle"
    assert birds[0]["wingspan"] == "2.3m"

@pytest.mark.asyncio
async def test_natural_text_extraction(test_config):
    """Test extraction from unstructured text"""
    config = ExtractConfig(
        pattern="Extract each bird species mentioned with its distinctive feature",
        format="json"
    )
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])
    
    result = await iterator.iter_extract(TestData.NATURAL_TEXT, config)
    birds = [bird for bird in iter(lambda: next(result) if result.has_next() else None, None)]
    
    assert len(birds) == 4
    assert any(b["name"] == "Ruby-throated Hummingbird" for b in birds)
    assert any(b["feature"].lower().startswith("red breast") for b in birds)

@pytest.mark.asyncio
async def test_error_handling(test_config):
    """Test iterator error handling"""
    config = ExtractConfig(pattern="Extract birds", format="json")
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])
    
    for invalid in ["invalid { json", "", None]:
        result = await iterator.iter_extract(invalid, config)
        assert not result.has_next()

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO"])