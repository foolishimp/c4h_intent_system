"""
Comprehensive test suite for semantic extraction and iteration.
Path: tests/test_semantic_iterator.py
"""

import pytest
from typing import List, Dict, Any
import structlog
import json
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

    MALFORMED_RESPONSES = [
        '{"not": "an array"}',
        'Some text [{"id": 1}] more text',
        'Invalid JSON',
        '[]',
        None
    ]

@pytest.fixture(scope="module")
def iterator(test_config):
    """Create reusable iterator instance"""
    return SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])

@pytest.mark.asyncio
async def test_code_block_extraction(iterator):
    """Test extraction of Python classes from markdown"""
    logger.info("test.code_block_extraction.start")
    
    config = ExtractConfig(
        instruction="Extract each Python class as a separate item with name and code",
        format="json"
    )
    
    result = await iterator.iter_extract(TestData.MARKDOWN_WITH_CODE, config)
    classes = []
    while result.has_next():
        classes.append(next(result))
    
    logger.info("test.code_block_extraction.complete", 
                classes_found=len(classes))
    
    assert len(classes) == 2, "Should extract two classes"
    assert "DataProcessor" in classes[0]["code"]
    assert "JsonProcessor" in classes[1]["code"]

@pytest.mark.asyncio
async def test_csv_record_iteration(iterator):
    """Test extraction of structured CSV records"""
    logger.info("test.csv_record_iteration.start")
    
    config = ExtractConfig(
        instruction="Extract each bird record with name and habitat",
        format="json"
    )
    
    result = await iterator.iter_extract(TestData.CSV_DATA, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.csv_record_iteration.complete",
                birds_found=len(birds))
    
    assert len(birds) == 4, "Should extract four bird records"
    assert birds[0]["name"] == "Northern Cardinal"
    assert birds[0]["habitat"] == "Woodland"

@pytest.mark.asyncio
async def test_json_bird_extraction(iterator):
    """Test extraction from nested JSON"""
    logger.info("test.json_bird_extraction.start")
    
    config = ExtractConfig(
        instruction="Extract each bird with name and wingspan",
        format="json"
    )
    
    result = await iterator.iter_extract(TestData.JSON_RECORDS, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.json_bird_extraction.complete",
                birds_found=len(birds))
    
    assert len(birds) == 3, "Should extract three bird records"
    assert birds[0]["name"] == "Eagle"
    assert birds[0]["wingspan"] == "2.3m"

@pytest.mark.asyncio
async def test_natural_text_extraction(iterator):
    """Test extraction from unstructured text"""
    logger.info("test.natural_text_extraction.start")
    
    config = ExtractConfig(
        instruction="Extract each bird species mentioned with its distinctive feature",
        format="json"
    )
    
    result = await iterator.iter_extract(TestData.NATURAL_TEXT, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.natural_text_extraction.complete",
                birds_found=len(birds))
    
    assert len(birds) == 4, "Should extract four bird records"
    assert any(b["name"] == "Ruby-throated Hummingbird" for b in birds)
    assert any(b["feature"].lower().startswith("red breast") for b in birds)

@pytest.mark.asyncio
async def test_malformed_responses(iterator):
    """Test handling of malformed responses"""
    logger.info("test.malformed_responses.start")
    
    config = ExtractConfig(
        instruction="Extract any items",
        format="json"
    )
    
    for response in TestData.MALFORMED_RESPONSES:
        logger.debug("test.malformed_response.checking",
                    response_type=type(response).__name__)
        
        result = await iterator.iter_extract(response, config)
        assert not result.has_next(), f"Should handle malformed response: {response}"
        
        # Verify we can still get raw response
        raw = result.get_raw_response()
        assert raw is not None, "Should always have raw response access"
        
    logger.info("test.malformed_responses.complete")

@pytest.mark.asyncio
async def test_response_parsing():
    """Test different response formats"""
    logger.info("test.response_parsing.start")
    
    test_cases = [
        ("Direct JSON array", '[{"id": 1}, {"id": 2}]'),
        ("JSON with wrapper", '{"items": [{"id": 1}, {"id": 2}]}'),
        ("Markdown wrapped", '```json\n[{"id": 1}]\n```'),
        ("Invalid but extractable", 'Some text [{"id": 1}] more text'),
        ("Completely invalid", "Not JSON at all")
    ]
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': 'claude-3-opus-20240229',
        'temperature': 0,
        'config': {'providers': {'anthropic': {'api_base': 'https://api.anthropic.com'}}}
    }])
    
    for case_name, content in test_cases:
        logger.info(f"test.response_parsing.case", case=case_name)
        
        config = ExtractConfig(
            instruction=f"Extract items from: {content}",
            format="json"
        )
        
        result = await iterator.iter_extract(content, config)
        items = []
        while result.has_next():
            items.append(next(result))
            
        logger.info("test.response_parsing.result",
                   case=case_name,
                   items_found=len(items),
                   raw_response=result.get_raw_response())
        
        if case_name.startswith("Direct") or case_name.startswith("Invalid but"):
            assert len(items) > 0, f"Should extract items from {case_name}"
        else:
            assert len(items) == 0, f"Should handle {case_name} gracefully"

@pytest.mark.asyncio
async def test_iterator_lifecycle():
    """Test complete iterator lifecycle and state"""
    logger.info("test.iterator_lifecycle.start")
    
    test_data = [{"id": 1}, {"id": 2}, {"id": 3}]
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': 'claude-3-opus-20240229',
        'temperature': 0,
        'config': {'providers': {'anthropic': {'api_base': 'https://api.anthropic.com'}}}
    }])
    
    config = ExtractConfig(
        instruction="Return these items unchanged",
        format="json"
    )
    
    result = await iterator.iter_extract(json.dumps(test_data), config)
    
    # Test initial state
    assert len(result) == 3, "Should have correct length"
    assert result.has_next(), "Should have next item"
    
    # Test iteration
    items = []
    item_count = 0
    while result.has_next():
        items.append(next(result))
        item_count += 1
        assert item_count <= 3, "Should not iterate beyond data"
        
    # Test final state    
    assert not result.has_next(), "Should be exhausted"
    assert len(items) == 3, "Should extract all items"
    
    # Verify raw response access still works
    raw = result.get_raw_response()
    assert raw, "Should maintain raw response access"
    
    logger.info("test.iterator_lifecycle.complete",
                items_processed=len(items))

@pytest.mark.asyncio
async def test_concurrent_extraction():
    """Test concurrent extractions"""
    logger.info("test.concurrent_extraction.start")
    
    iterator = SemanticIterator([{
        'provider': 'anthropic',
        'model': 'claude-3-opus-20240229',
        'temperature': 0,
        'config': {'providers': {'anthropic': {'api_base': 'https://api.anthropic.com'}}}
    }])
    
    config = ExtractConfig(
        instruction="Extract items",
        format="json"
    )
    
    # Run multiple extractions concurrently
    import asyncio
    tasks = []
    for data in [TestData.CSV_DATA, TestData.JSON_RECORDS, TestData.NATURAL_TEXT]:
        tasks.append(iterator.extract_all(data, config))
    
    results = await asyncio.gather(*tasks)
    
    logger.info("test.concurrent_extraction.complete",
                extraction_count=len(results),
                total_items=sum(len(r) for r in results))
    
    # Verify all extractions worked
    assert all(isinstance(r, list) for r in results), "All extractions should return lists"
    assert all(len(r) > 0 for r in results), "All extractions should find items"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])