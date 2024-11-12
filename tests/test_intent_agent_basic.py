# tests/test_intent_agent_basic.py

import pytest
import os
from pathlib import Path
import structlog

from src.agents.intent_agent import IntentAgent
from src.models.intent import Intent, IntentStatus

logger = structlog.get_logger()

@pytest.fixture
def test_project(tmp_path):
    """Create a simple test project"""
    # Create main file
    test_file = tmp_path / "math_utils.py"
    test_file.write_text("""
def calculate_sum(numbers):
    result = sum(numbers)
    print(f"The sum is: {result}")
    return result

def multiply_list(numbers):
    result = 1
    for num in numbers:
        result *= num
    print(f"The product is: {result}")
    return result

if __name__ == "__main__":
    test_numbers = [1, 2, 3, 4, 5]
    calculate_sum(test_numbers)
    multiply_list(test_numbers)
""")
    return tmp_path

@pytest.fixture
async def intent_agent():
    """Create intent agent"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return IntentAgent(max_iterations=2)

@pytest.mark.asyncio
async def test_basic_refactoring(intent_agent, test_project):
    """Test basic refactoring workflow"""
    print("\nTesting basic refactoring workflow...")
    
    intent_desc = {
        "description": "Add logging instead of print statements",
        "merge_strategy": "smart"
    }
    
    result = await intent_agent.process(test_project, intent_desc)
    
    print(f"\nRefactoring Result:")
    print(f"Status: {result['status']}")
    if result.get('error'):
        print(f"Error: {result['error']}")
    
    assert result['status'] == 'success', f"Refactoring failed: {result.get('error')}"
    
    # Check the modified file
    modified_file = test_project / "math_utils.py"
    assert modified_file.exists(), "Modified file should exist"
    
    content = modified_file.read_text()
    print("\nModified File Content:")
    print(content)
    
    assert "import logging" in content, "Should add logging import"
    assert "logging.info" in content, "Should use logging.info"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])