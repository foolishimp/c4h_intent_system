# tests/test_solution_architect.py

import pytest
from pathlib import Path
import os
from src.agents.base import LLMProvider
from src.agents.solution_architect import SolutionArchitect

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
def sample_discovery_output():
    """Simulate discovery agent output"""
    return {
        "files": {
            "UserManager.java": SAMPLE_JAVA
        },
        "analysis": {
            "language": "Java",
            "patterns": ["System.out.printf usage", "Basic logging needs"],
            "complexity": "low"
        }
    }

@pytest.mark.asyncio
async def test_solution_architect_printf_to_logging():
    """Test solution architect's ability to plan printf to logging transformation"""
    
    # Initialize agent with Claude
    architect = SolutionArchitect(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet-20240229"
    )
    
    # Prepare test input
    test_input = {
        "intent": "Convert all System.out.printf statements to use Java logging (java.util.logging.Logger)",
        "discovery_output": {
            "code": SAMPLE_JAVA,
            "language": "java",
            "file_path": "UserManager.java"
        }
    }
    
    print("\nTesting Solution Architect's printf to logging transformation plan...")
    
    # Get transformation plan
    response = await architect.process(test_input)
    
    print(f"\nResponse success: {response.success}")
    if response.success:
        actions = response.data["response"]["actions"]
        print("\nProposed changes:")
        for action in actions:
            print(f"\nFile: {action['file_path']}")
            print("New content:")
            print(action['content'])
    else:
        print(f"Error: {response.error}")
    
    # Validate response
    assert response.success, "Solution architect should return successful response"
    assert "response" in response.data, "Response should contain response data"
    
    actions = response.data["response"]["actions"]
    assert len(actions) > 0, "Should provide at least one action"
    
    # Validate first action
    action = actions[0]
    assert action["file_path"].endswith(".java"), "Should target Java file"
    assert "content" in action, "Should provide new content"
    
    new_content = action["content"]
    assert "import java.util.logging" in new_content, "Should add logging import"
    assert "Logger" in new_content, "Should use Logger class"
    assert "System.out.printf" not in new_content, "Should remove printf statements"
    
    print("\nValidation checks passed!")
    return response

if __name__ == "__main__":
    pytest.main(["-v", __file__])