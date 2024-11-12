# tests/test_solution_design.py

import pytest
import json
import os
from pathlib import Path
import structlog
from src.agents.base import LLMProvider, AgentResponse
from src.agents.solution_designer import SolutionDesigner

logger = structlog.get_logger()

# Sample Java code with printf statements
SAMPLE_JAVA = """
public class UserManager {
    public void createUser(String username, String email) {
        System.out.printf("Creating user with username: %s and email: %s%n", username, email);
        
        if (validateUser(username, email)) {
            System.out.printf("User %s validated successfully%n", username);
            saveUser(username, email);
        } else {
            System.out.printf("Error: Failed to validate user %s%n", username);
        }
    }
    
    private boolean validateUser(String username, String email) {
        System.out.printf("Validating user data for %s%n", username);
        if (username == null || email == null) {
            System.out.printf("Validation failed - null values detected%n");
            return false;
        }
        return true;
    }
    
    private void saveUser(String username, String email) {
        System.out.printf("Saving user %s to database%n", username);
        // Database operations here
        System.out.printf("Successfully saved user %s%n", username);
    }
}
"""

@pytest.fixture
def designer():  # Regular fixture, not async
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    
    return SolutionDesigner(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet-20240229"
    )


@pytest.mark.asyncio
async def test_solution_designer_request_format(designer):
    """Test solution designer formats requests properly"""
    test_input = {
        "intent": {
            "description": "Add logging"
        },
        "discovery_data": {
            "files": {
                "test.py": "print('hello')"
            }
        }
    }

    # Call format_request directly to test formatting
    formatted = designer._format_request(test_input)
    
    # Verify key components present
    assert "INTENT:" in formatted
    assert "Add logging" in formatted
    assert "SOURCE CODE:" in formatted
    assert "print('hello')" in formatted

@pytest.mark.asyncio
async def test_solution_designer_response_passthrough(designer):
    """Test solution designer passes through LLM response"""
    test_input = {
        "intent": {
            "description": "Add error handling"
        },
        "discovery_data": {
            "files": {
                "test.py": "def process(): return True"
            }
        }
    }
    
    response = await designer.process(test_input)
    
    # We mainly verify structure, not content since it's just passing through
    assert response is not None
    assert hasattr(response, 'success')
    assert hasattr(response, 'data')
    assert hasattr(response, 'error')
    
    if response.success:
        assert isinstance(response.data, dict)
    else:
        assert isinstance(response.error, str)

@pytest.mark.asyncio
async def test_solution_designer_logging(designer, caplog):
    """Test solution designer logs appropriate information"""
    caplog.set_level("INFO")
    
    test_input = {
        "intent": {
            "description": "Add logging"
        },
        "discovery_data": {
            "files": {
                "test.py": "print('hello')"
            }
        }
    }
    
    await designer.process(test_input)
    
    # Check key log messages
    logs = [record.message for record in caplog.records if record.name.startswith('src.agents')]
    
    # Verify key events are logged
    assert any("design_request_received" in msg for msg in logs)
    assert any("formatting_request" in msg for msg in logs)
    
    # Verify context is logged
    assert any("intent" in msg for msg in logs)
    assert any("file_count" in msg for msg in logs)

@pytest.mark.asyncio
async def test_solution_designer_error_handling(designer):
    """Test solution designer's error handling"""
    # Test with invalid input
    response = await designer.process(None)
    assert response.success  # Changed from not response.success
    assert 'needs_clarification' in response.data.get('response', {})
    
    # Test with empty input
    response = await designer.process({})
    assert response.success  # Changed from not response.success
    assert 'needs_clarification' in response.data.get('response', {})

    # Test with missing discovery data
    response = await designer.process({"intent": {"description": "test"}})
    assert not response.success  # This should still fail
    assert response.error is not None

@pytest.mark.asyncio
async def test_solution_designer_retries(designer):
    """Test solution designer retry behavior"""
    # We can't easily test the retries directly, but we can verify
    # the retry configuration is present
    assert hasattr(designer, 'max_retries')
    assert designer.max_retries > 0