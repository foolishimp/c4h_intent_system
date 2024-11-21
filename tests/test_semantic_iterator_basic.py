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

# Simple test data
TEST_DATA = {
    "changes": [
        {
            "file_path": "src/example/test.py",
            "type": "modify",
            "description": "Add logging",
            "content": """
                def test():
                    print("hello")
            """
        },
        {
            "file_path": "src/example/other.py", 
            "type": "modify",
            "description": "Add type hints",
            "content": """
                def other():
                    return None
            """
        }
    ]
}

@pytest.fixture
def iterator(test_config):
    """Create iterator with test configuration"""
    return SemanticIterator([{
        'provider': 'anthropic',
        'model': test_config['llm_config']['default_model'],
        'temperature': 0,
        'config': test_config
    }])

def print_response(response: str):
    """Print response for debugging"""
    print("\nRaw Response:")
    print("-" * 40)
    print(response)
    print("-" * 40)

@pytest.mark.asyncio
async def test_basic_extraction(iterator):
    """Test basic extraction of well-formed changes"""
    logger.info("test.basic_extraction.start")
    
    config = ExtractConfig(
        instruction="""Extract code changes from the input and return them as a JSON array. 
            Each change should be a JSON object with these exact fields:
            - file_path (string)  
            - type (string)
            - description (string)
            - content (string)

            Return ONLY the JSON array with no other text.
            
            Example response format:
            [
                {
                    "file_path": "path/to/file.py",
                    "type": "modify", 
                    "description": "Added logging",
                    "content": "def example()..."
                }
            ]""",
        format="json"
    )

    result = await iterator.iter_extract(TEST_DATA, config)
    
    # Print raw response for debugging
    print_response(result.get_raw_response())
    
    # Collect changes
    changes = []
    while result.has_next():
        change = next(result)
        logger.info("change.extracted",
                   file=change.get('file_path'),
                   type=change.get('type'))
        changes.append(change)

    # Print extracted changes
    print("\nExtracted Changes:")
    for i, change in enumerate(changes, 1):
        print(f"\nChange {i}:")
        print(f"File: {change.get('file_path')}")
        print(f"Type: {change.get('type')}")
        print(f"Description: {change.get('description')}")
        if 'content' in change:
            print("Content Preview:", change['content'].split('\n')[0])

    # Verify extraction
    assert len(changes) == 2, "Should extract exactly two changes"
    assert all(isinstance(c, dict) for c in changes), "All changes should be dictionaries"
    
    required_fields = ['file_path', 'type', 'description', 'content']
    for change in changes:
        for field in required_fields:
            assert field in change, f"Change missing required field: {field}"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", "-k", "test_basic_extraction"])