"""
Basic semantic iterator test focused on change extraction.
Path: tests/test_semantic_iterator_basic.py
"""

import pytest
import json 
import structlog
from typing import Dict, Any, List
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

# Define expected code changes
EXPECTED_CHANGES = [
    {
        "file_path": "src/example/test.py",
        "type": "modify",
        "description": "Add logging",
        "content": """import logging

def test():
    logging.info("hello")"""
    },
    {
        "file_path": "src/example/other.py",
        "type": "modify", 
        "description": "Add type hints",
        "content": """def other() -> None:
    return None"""
    }
]

@pytest.fixture
def mock_llm_response():
    """Override the default bird-related mock with code changes"""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "text",
            "text": json.dumps(EXPECTED_CHANGES)
        }]
    }

@pytest.mark.asyncio
async def test_basic_extraction(test_iterator, mock_llm_response):
    """Test semantic extraction of code changes"""
    logger.info("test.basic_extraction.start")
    
    # Configure extraction
    config = ExtractConfig(
        instruction="""Extract code changes from the input and return them as a JSON array. 
            Each change should be a JSON object with these exact fields:
            - file_path (string): The target file path  
            - type (string): The type of change [create|modify|delete]
            - description (string): Brief description of the change
            - content (string): The complete code content

            Return ONLY the JSON array with these exact fields.""",
        format="json"
    )

    # Test input describing changes
    input_text = """
    Please modify these files:
    1. src/example/test.py: Add logging instead of print statements
    2. src/example/other.py: Add proper return type hints
    """

    # Execute extraction
    result = await test_iterator.iter_extract(input_text, config)
    
    # Log state for debugging
    state = result.get_state()
    logger.info("test.extraction_state",
                mode=state.current_mode,
                attempted_modes=state.attempted_modes,
                has_llm_response=bool(state.raw_response))

    # Collect all changes
    changes = []
    while result.has_next():
        change = next(result)
        logger.info("change.extracted",
                   file=change.get('file_path'),
                   type=change.get('type'),
                   description=change.get('description'))
        changes.append(change)

    # Print actual vs expected for debugging
    print("\n=== Extracted Changes ===")
    print(json.dumps(changes, indent=2))
    print("\n=== Expected Changes ===")
    print(json.dumps(EXPECTED_CHANGES, indent=2))

    # Verify we got the right number of changes
    assert len(changes) == len(EXPECTED_CHANGES), \
        f"Expected {len(EXPECTED_CHANGES)} changes, got {len(changes)}"

    # Verify each change matches expected format
    for i, (actual, expected) in enumerate(zip(changes, EXPECTED_CHANGES)):
        print(f"\nValidating change {i+1}:")
        
        # Check all required fields exist
        for field in ['file_path', 'type', 'description', 'content']:
            assert field in actual, f"Missing field '{field}' in change {i+1}"
            
        # Verify essential fields match
        assert actual['file_path'] == expected['file_path'], \
            f"Change {i+1} file_path mismatch"
        assert actual['type'] == expected['type'], \
            f"Change {i+1} type mismatch"
        
        # Compare code content (normalized)
        actual_code = actual['content'].strip()
        expected_code = expected['content'].strip()
        assert actual_code == expected_code, \
            f"Change {i+1} code content mismatch"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", "-k", "test_basic_extraction"])