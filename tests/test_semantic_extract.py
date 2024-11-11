# tests/test_semantic_extract.py

import pytest
from typing import Dict, Any
import os
import json
import structlog
from datetime import datetime
from skills.semantic_extract import SemanticExtract
from src.agents.base import LLMProvider, AgentResponse

logger = structlog.get_logger()

# Test data
SAMPLE_JSON = {
    "user": {
        "name": "Alice Smith",
        "age": 28,
        "contact": {
            "email": "alice@example.com",
            "phone": "123-456-7890"
        },
        "preferences": {
            "theme": "dark",
            "notifications": True
        }
    },
    "settings": {
        "language": "en",
        "timezone": "UTC-5"
    }
}

SAMPLE_TEXT = """
Title: Project Status Report
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
async def interpreter():
    """Create interpreter instance with environment check"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
    
    return SemanticInterpreter(
        provider=LLMProvider.ANTHROPIC,
        temperature=0  # Ensure consistent results
    )

@pytest.mark.asyncio
async def test_json_extraction(interpreter):
    """Test extracting specific fields from JSON"""
    print("\nTesting JSON field extraction...")
    
    # Test extracting nested field
    response = await interpreter.interpret(
        content=SAMPLE_JSON,
        prompt="Extract the user's email address"
    )
    
    print(f"\nResponse success: {response.success}")
    print(f"Response data: {response.data}")
    
    assert response.success, f"JSON extraction failed: {response.error}"
    result = response.data.get("response")
    assert "alice@example.com" in str(result).lower(), "Failed to extract email"

@pytest.mark.asyncio
async def test_text_analysis(interpreter):
    """Test extracting information from text"""
    print("\nTesting text analysis...")
    
    response = await interpreter.interpret(
        content=SAMPLE_TEXT,
        prompt="Extract all numeric metrics (users, revenue, projects) as JSON"
    )
    
    print(f"\nResponse success: {response.success}")
    print(f"Response data: {response.data}")
    
    assert response.success, f"Text analysis failed: {response.error}"
    result = response.data.get("response")
    
    # Parse result if it's a string
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pytest.fail("Response is not valid JSON")
    
    # Verify metrics were extracted
    assert isinstance(result, dict), "Result should be a dictionary"
    assert any(str(1250) in str(v) for v in result.values()), "Users count not found"
    assert any(str(45000) in str(v) for v in result.values()), "Revenue not found"
    assert any(str(12) in str(v) for v in result.values()), "Project count not found"

@pytest.mark.asyncio
async def test_error_handling(interpreter):
    """Test handling of invalid inputs"""
    print("\nTesting error handling...")
    
    # Test cases for different error conditions
    test_cases = [
        {
            "name": "None content",
            "content": None,
            "prompt": "This should fail gracefully",
            "expected_error": "No content provided"
        },
        {
            "name": "Empty prompt",
            "content": "Some content",
            "prompt": "",
            "expected_error": "No prompt provided"
        },
        {
            "name": "Invalid content type",
            "content": type('BadType', (), {})(),  # Create a weird type
            "prompt": "Try to handle this",
            "expected_error": "Failed to process content"
        }
    ]
    
    for case in test_cases:
        print(f"\nTesting {case['name']}...")
        response = await interpreter.interpret(
            content=case["content"],
            prompt=case["prompt"]
        )
        
        print(f"Response: {response}")
        
        # Verify failure
        assert response.success == False, f"{case['name']} should fail"
        assert response.error is not None, f"{case['name']} should have error message"
        assert case["expected_error"] in response.error, f"{case['name']} should have expected error"
        assert response.data == {}, f"{case['name']} should have empty data"

@pytest.mark.asyncio
async def test_complex_interpretation(interpreter):
    """Test more complex interpretation tasks"""
    print("\nTesting complex interpretation...")
    
    # Mix of text and structured data
    complex_content = {
        "text": SAMPLE_TEXT,
        "metadata": {
            "author": "John Doe",
            "department": "Engineering"
        }
    }
    
    response = await interpreter.interpret(
        content=complex_content,
        prompt="""Extract the following as JSON:
        1. All dates mentioned in the text
        2. Author name from metadata
        3. Total number of action items"""
    )
    
    print(f"\nComplex interpretation response: {response.data}")
    
    assert response.success, f"Complex interpretation failed: {response.error}"
    result = response.data.get("response")
    
    # Parse result if it's a string
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pytest.fail("Response is not valid JSON")
    
    # Verify complex extraction
    assert isinstance(result, dict), "Result should be a dictionary"
    assert "John Doe" in str(result), "Author not found"
    assert "March" in str(result), "Dates not found"
    assert "3" in str(result), "Action item count not found"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])