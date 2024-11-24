"""
Test suite for semantic extraction and iteration across different data formats.
Path: tests/test_semantic_iterator.py
"""

import pytest
from typing import List, Dict, Any
import structlog
from dataclasses import dataclass
from textwrap import dedent
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
async def test_code_block_extraction(test_iterator):
    """Test extraction of Python classes from markdown"""
    config = ExtractConfig(
        instruction="""Analyze the markdown text and extract all Python class definitions.

        For each class found, return a JSON object with these exact fields:
        - name: The class name (string)
        - code: The complete class definition including docstrings and methods (string)
        - parent: The parent class name if inherited, otherwise null (string|null)

        Return as a JSON array of objects in this exact format:
        [
            {
                "name": "ExampleClass",
                "code": "class ExampleClass:\n    def method(self):\n        pass",
                "parent": null
            },
            {
                "name": "ChildClass",
                "code": "class ChildClass(ParentClass):\n    pass",
                "parent": "ParentClass"
            }
        ]

        Important:
        - Preserve all indentation in the code field
        - Include the complete class definition from 'class' keyword to the last method
        - Extract ALL classes found in the markdown code blocks
        - Do not include any explanatory text, only the JSON array
        """,
        format="json"
    )

    result = await test_iterator.iter_extract(TestData.MARKDOWN_WITH_CODE, config)

@pytest.mark.asyncio
async def test_csv_record_iteration(test_iterator):
    """Test extraction of structured CSV records"""
    logger.info("test.csv_record_iteration.start")
    
    config = ExtractConfig(
        instruction="Extract each bird record with name and habitat",
        format="json"
    )
    
    result = await test_iterator.iter_extract(TestData.CSV_DATA, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.csv_record_iteration.complete",
                birds_found=len(birds))
    
    assert len(birds) == 4, "Should extract four bird records"
    assert birds[0]["name"] == "Northern Cardinal"
    assert birds[0]["habitat"] == "Woodland"

@pytest.mark.asyncio
async def test_json_bird_extraction(test_iterator):
    """Test extraction from nested JSON"""
    logger.info("test.json_bird_extraction.start")
    
    config = ExtractConfig(
        instruction="Extract each bird with name and wingspan",
        format="json"
    )
    
    result = await test_iterator.iter_extract(TestData.JSON_RECORDS, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.json_bird_extraction.complete",
                birds_found=len(birds))
    
    assert len(birds) == 3, "Should extract three bird records"
    assert birds[0]["name"] == "Eagle"
    assert birds[0]["wingspan"] == "2.3m"

@pytest.mark.asyncio
async def test_natural_text_extraction(test_iterator):
    """Test extraction from unstructured text"""
    logger.info("test.natural_text_extraction.start")
    
    config = ExtractConfig(
        instruction="Extract each bird species mentioned with its distinctive feature",
        format="json"
    )
    
    result = await test_iterator.iter_extract(TestData.NATURAL_TEXT, config)
    birds = []
    while result.has_next():
        birds.append(next(result))
    
    logger.info("test.natural_text_extraction.complete",
                birds_found=len(birds))
    
    assert len(birds) == 4, "Should extract four bird records"
    assert any(b.get("feature", "").startswith("can hover") for b in birds)

@pytest.mark.asyncio
async def test_malformed_responses(test_iterator):
    """Test handling of malformed responses"""
    config = ExtractConfig(
        instruction="Extract any items",
        format="json"
    )
    
    test_inputs = [
        '{"not": "an array"}',
        'Some text [{"id": 1}] more text',
        'Invalid JSON',
        '[]',
        None
    ]
    
    for response in test_inputs:
        logger.debug("test.malformed_response.checking",
                    response_type=type(response).__name__)
        
        result = await test_iterator.iter_extract(response, config)
        # Should handle gracefully and not raise exceptions
        assert not result.has_next()

@pytest.mark.asyncio
async def test_response_parsing(test_iterator, test_config):
    """Test different response formats"""
    logger.info("test.response_parsing.start")
    
    test_cases = [
        ("Direct JSON array", '[{"id": 1}, {"id": 2}]'),
        ("JSON with wrapper", '{"items": [{"id": 1}, {"id": 2}]}'),
        ("Markdown wrapped", '```json\n[{"id": 1}]\n```'),
        ("Invalid but extractable", 'Some text [{"id": 1}] more text'),
        ("Completely invalid", "Not JSON at all")
    ]
    
    config = ExtractConfig(
        instruction="Extract items with ids",
        format="json"
    )
    
    for case_name, content in test_cases:
        logger.info(f"test.response_parsing.case", case=case_name)
        
        result = await test_iterator.iter_extract(content, config)
        items = []
        while result.has_next():
            items.append(next(result))
            
        logger.info("test.response_parsing.result",
                   case=case_name,
                   items_found=len(items))
        
        if case_name.startswith("Completely invalid"):
            assert not items, f"Should not extract items from {case_name}"
        else:
            assert items, f"Should extract items from {case_name}"