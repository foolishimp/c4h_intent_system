# tests/test_semantic_extract.py

import pytest
from typing import Dict, Any
import os
import json
import structlog
from datetime import datetime
from src.skills.semantic_extract import SemanticExtract, ExtractResult
from src.agents.base import LLMProvider

logger = structlog.get_logger()

# Test data
SAMPLE_JSON = {
    "user": {
        "name": "Alice Smith",
        "age": 28,
        "contact": {
            "email": "alice@example.com",
            "phone": "123-456-7890"
        }
    },
    "settings": {
        "language": "en",
        "timezone": "UTC-5"
    }
}

SAMPLE_TEXT = """
Project Status Report
Date: 2024-03-15

Key Metrics:
- Users: 1,250 (+15%)
- Revenue: $45,000 (+8%)
- Active Projects: 12

Action Items:
1. Launch new feature by March 20
2. Schedule team review for March 25
3. Update documentation by March 30
"""

@pytest.fixture
async def extractor():
    """Create extractor instance with environment check"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
    
    return SemanticExtract(
        provider=LLMProvider.ANTHROPIC,
        temperature=0
    )

@pytest.mark.asyncio
async def test_json_extraction(extractor):
    """Test extracting specific fields from JSON"""
    print("\nTesting JSON field extraction...")
    
    # Test successful extraction
    result = await extractor.extract(
        content=SAMPLE_JSON,
        prompt="Extract the user's email address",
        format_hint="string"
    )
    
    print(f"\nExtraction result:")
    print(f"Success: {result.success}")
    print(f"Value: {result.value}")
    print(f"Raw response: {result.raw_response}")
    print(f"Error: {result.error}")
    
    assert result.success, f"Extraction failed: {result.error}"
    assert result.value == "alice@example.com", \
        f"Expected 'alice@example.com', got '{result.value}'"
    assert result.error is None, "Should not have error"

    # Test extraction of non-existent field
    result = await extractor.extract(
        content=SAMPLE_JSON,
        prompt="Extract the user's twitter handle",
        format_hint="string"
    )
    
    assert not result.success, "Should fail for non-existent field"
    assert result.value in (None, "", {}), "Should return empty value for not found"

@pytest.mark.asyncio
async def test_text_extraction(extractor):
    """Test extracting information from text"""
    print("\nTesting text extraction...")
    
    result = await extractor.extract(
        content=SAMPLE_TEXT,
        prompt="Extract all numeric metrics (users, revenue, projects) as JSON",
        format_hint="json"
    )
    
    print(f"\nResult: {result}")
    
    assert result.success, f"Text extraction failed: {result.error}"
    assert isinstance(result.value, dict), "Result should be a dictionary"
    
    # Verify extracted values
    assert result.value.get('users') == 1250, "Users count not extracted correctly"
    assert result.value.get('revenue') == 45000, "Revenue not extracted correctly"
    assert any(v == 12 for v in result.value.values()), "Projects count not extracted correctly"

@pytest.mark.asyncio
async def test_error_handling(extractor):
    """Test handling of invalid inputs"""
    print("\nTesting error handling...")
    
    test_cases = [
        {
            "name": "Empty prompt",
            "content": "Some content",
            "prompt": "",
            "should_fail": True,
            "expected_error": "No prompt provided"
        },
        {
            "name": "None prompt",
            "content": "Some content",
            "prompt": None,
            "should_fail": True,
            "expected_error": "No prompt provided"
        },
        {
            "name": "Complex object",
            "content": {"nested": {"data": [1, 2, {"key": "value"}]}},
            "prompt": "Extract all numeric values",
            "format_hint": "json",
            "should_fail": False
        }
    ]
    
    for case in test_cases:
        print(f"\nTesting {case['name']}...")
        result = await extractor.extract(
            content=case["content"],
            prompt=case.get("prompt"),
            format_hint=case.get("format_hint", "default")
        )
        
        print(f"Result: {result}")
        
        if case["should_fail"]:
            assert not result.success, f"{case['name']} should fail"
            assert result.error is not None, f"{case['name']} should have error message"
            assert case["expected_error"] in result.error, \
                f"{case['name']} should have expected error"
            assert result.value in (None, "", {}), "Failed extraction should have empty value"
        else:
            assert result.success, f"{case['name']} should succeed"
            assert result.error is None, f"{case['name']} should not have error"
            assert result.value is not None, "Should have extracted value"

@pytest.mark.asyncio
async def test_mixed_content(extractor):
    """Test extracting from mixed content types"""
    print("\nTesting mixed content extraction...")
    
    mixed_content = {
        "text": SAMPLE_TEXT,
        "metadata": {
            "author": "John Doe",
            "department": "Engineering"
        }
    }
    
    result = await extractor.extract(
        content=mixed_content,
        prompt="""Extract the following as JSON:
        1. All dates from the text
        2. Author name
        3. Total number of action items""",
        format_hint="json"
    )
    
    print(f"\nResult: {result}")
    
    assert result.success, f"Mixed content extraction failed: {result.error}"
    assert isinstance(result.value, dict), "Result should be a dictionary"
    
    # Verify specific fields
    assert 'dates' in result.value, "Should contain dates field"
    assert isinstance(result.value['dates'], list), "Dates should be a list"
    assert '2024-03-15' in str(result.value['dates']), "Should find exact date"
    assert 'author' in result.value, "Should contain author field"
    assert result.value['author'] == "John Doe", "Should extract correct author"
    assert any(str(3) in str(v) for v in result.value.values()), "Should count 3 action items"

@pytest.mark.asyncio
async def test_format_handling(extractor):
    """Test different format hints"""
    print("\nTesting format handling...")
    
    # Test string format
    string_result = await extractor.extract(
        content=SAMPLE_JSON,
        prompt="Extract the user's name",
        format_hint="string"
    )
    
    assert string_result.success, "String extraction failed"
    assert isinstance(string_result.value, str), "String format should return string"
    assert string_result.value == "Alice Smith", "Should extract correct name"
    
    # Test JSON format
    json_result = await extractor.extract(
        content=SAMPLE_JSON,
        prompt="Extract the user's name and age",
        format_hint="json"
    )
    
    assert json_result.success, "JSON extraction failed"
    assert isinstance(json_result.value, dict), "JSON format should return dict"
    assert json_result.value.get('name') == "Alice Smith", "Should include name"
    assert json_result.value.get('age') == 28, "Should include age"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])