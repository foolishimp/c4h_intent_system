# tests/test_intent_agent_basic.py

import pytest
import os
from pathlib import Path
import structlog
import sys

# Add src to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.intent_agent import IntentAgent, IntentContext
from src.models.intent import Intent, IntentStatus

logger = structlog.get_logger()

# Test setup
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
def intent_agent():  # Changed from async fixture to regular fixture
    """Create intent agent"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    
    logger.info("Creating intent agent")
    return IntentAgent(max_iterations=2)  # Return the agent directly

@pytest.mark.asyncio
async def test_basic_refactoring(intent_agent, test_project):
    """Test basic refactoring workflow"""
    logger.info("Starting basic refactoring test")
    
    intent_desc = {
        "description": "Add logging instead of print statements",
        "merge_strategy": "smart"
    }
    
    try:
        result = await intent_agent.process(test_project, intent_desc)
        
        logger.info("Refactoring completed", 
                   status=result['status'],
                   error=result.get('error'))
        
        assert result['status'] == 'success', f"Refactoring failed: {result.get('error')}"
        
        # Check the modified file
        modified_file = test_project / "math_utils.py"
        assert modified_file.exists(), "Modified file should exist"
        
        content = modified_file.read_text()
        logger.info("Modified file content length", length=len(content))
        
        assert "import logging" in content, "Should add logging import"
        assert "logging.info" in content, "Should use logging.info"
        
    except Exception as e:
        logger.error("Test failed", error=str(e))
        raise

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])