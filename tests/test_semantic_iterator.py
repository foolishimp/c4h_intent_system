# tests/test_semantic_iterator.py

import pytest
from typing import List, Dict, Any
import os
import json
import structlog
from src.agents.base import LLMProvider
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

# Test Data Sets

# 1. Markdown with Python code
MARKDOWN_CODE = """
Here's how we can refactor the solution architect:

First, let's update the base class:

```python
# src/agents/base_architect.py
from typing import Dict, Any

class BaseArchitect:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    async def analyze(self) -> Dict[str, Any]:
        raise NotImplementedError()
```

Then we'll create the main implementation:

```python
# src/agents/solution_architect.py
from typing import Dict, Any
from .base_architect import BaseArchitect

class SolutionArchitect(BaseArchitect):
    async def analyze(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "changes": []
        }
```
"""

# 2. JSON Records
JSON_RECORDS = """
{
    "users": [
        {
            "id": 1,
            "name": "Alice Smith",
            "email": "alice@example.com",
            "age": 28,
            "active": true
        },
        {
            "id": 2,
            "name": "Bob Jones",
            "email": "bob@example.com",
            "age": 35,
            "active": false
        },
        {
            "id": 3,
            "name": "Charlie Brown",
            "email": "charlie@example.com",
            "age": 42,
            "active": true
        }
    ]
}
"""

# 3. Text Paragraph
TEXT_PARAGRAPH = """
The quick brown fox jumps over the lazy dog. This is a simple test paragraph that we'll use to demonstrate sentence extraction. Each sentence should be captured individually! The sentences have different punctuation marks? Some sentences might be questions. And some might be exclamations! But all should be properly extracted.
"""

@pytest.fixture
async def semantic_iterator():
    """Create semantic iterator instance"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
        
    config_list = [{
        "model": "claude-3-sonnet-20240229",
        "api_key": api_key,
        "max_tokens": 4000,
        "temperature": 0
    }]
    
    try:
        iterator = SemanticIterator(config_list)
        return iterator
    except Exception as e:
        pytest.fail(f"Failed to create iterator: {str(e)}")

@pytest.mark.asyncio
async def test_code_block_iteration(semantic_iterator):
    """Test extracting Python code blocks from markdown"""
    print("\nTesting Python code block extraction...")
    
    config = ExtractConfig(
        pattern="""Extract all Python code blocks from the markdown.
        For each block, capture:
        - The complete code content
        - Any filename from comments
        - The order it appears in the document""",
        format="json"
    )
    
    iterator = await semantic_iterator.iter_extract(MARKDOWN_CODE, config)
    
    blocks = []
    while iterator.has_next():
        block = next(iterator)
        blocks.append(block)
        print(f"\nCode Block {iterator.position()}:")
        print(f"Filename: {block.get('filename', 'unknown')}")
        
    assert len(blocks) == 2, "Should find 2 code blocks"
    assert any("base_architect.py" in str(block) for block in blocks)
    assert any("solution_architect.py" in str(block) for block in blocks)

@pytest.mark.asyncio
async def test_json_record_iteration(semantic_iterator):
    """Test iterating over JSON records"""
    print("\nTesting JSON record iteration...")
    
    config = ExtractConfig(
        pattern="Extract each user record as a separate item",
        format="json",
        filters=[
            lambda x: x.get('active', False)  # Only active users
        ]
    )
    
    iterator = await semantic_iterator.iter_extract(JSON_RECORDS, config)
    
    active_users = []
    while iterator.has_next():
        user = next(iterator)
        active_users.append(user)
        print(f"\nActive User: {user.get('name')}")
    
    assert len(active_users) == 2, "Should find 2 active users"
    assert all(user['active'] for user in active_users)

@pytest.mark.asyncio
async def test_sentence_iteration(semantic_iterator):
    """Test iterating over sentences in text"""
    print("\nTesting sentence iteration...")
    
    config = ExtractConfig(
        pattern="""Extract each sentence as a separate item.
        For each sentence capture:
        - The text content
        - The ending punctuation
        - Whether it's a question""",
        format="json"
    )
    
    iterator = await semantic_iterator.iter_extract(TEXT_PARAGRAPH, config)
    
    sentences = []
    while iterator.has_next():
        sentence = next(iterator)
        sentences.append(sentence)
        print(f"\nSentence {iterator.position()}: {sentence.get('text', '')}")
    
    assert len(sentences) > 5, "Should find multiple sentences"
    assert any(s.get('is_question', False) for s in sentences), "Should identify questions"

@pytest.mark.asyncio
async def test_iterator_features(semantic_iterator):
    """Test advanced iterator features with different content types"""
    print("\nTesting iterator features...")
    
    # Test with JSON records
    config = ExtractConfig(
        pattern="Extract user records",
        format="json",
        sort_key="age"  # Sort by age
    )
    
    iterator = await semantic_iterator.iter_extract(JSON_RECORDS, config)
    
    # Test sorting
    first = next(iterator)
    second = next(iterator)
    assert first['age'] < second['age'], "Records should be sorted by age"
    
    # Test backtracking
    previous = iterator.back()
    assert previous['age'] == second['age'], "Should go back to previous record"
    
    # Test reset and skip
    iterator.reset()
    iterator.skip(2)
    assert iterator.position() == 2, "Should skip to position 2"
    
    # Test to_list
    remaining = iterator.to_list()
    assert len(remaining) == 1, "Should have one record remaining"

@pytest.mark.asyncio
async def test_error_handling(semantic_iterator):
    """Test error handling with different content types"""
    print("\nTesting error handling...")
    
    # Test with invalid JSON
    config = ExtractConfig(pattern="Extract records")
    invalid_json = "{invalid json"
    
    iterator = await semantic_iterator.iter_extract(invalid_json, config)
    assert not iterator.has_next(), "Invalid JSON should yield no items"
    
    # Test with empty content
    iterator = await semantic_iterator.iter_extract("", config)
    assert not iterator.has_next(), "Empty content should yield no items"
    
    # Test with None content
    iterator = await semantic_iterator.iter_extract(None, config)
    assert not iterator.has_next(), "None content should yield no items"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])