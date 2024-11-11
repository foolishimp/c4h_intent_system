# tests/test_solution_architect.py

import pytest
import json
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

@pytest.mark.asyncio
async def test_solution_architect_printf_to_logging():
    """Test solution architect's ability to plan printf to logging transformation"""
    
    architect = SolutionArchitect(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet-20240229"
    )
    
    test_input = {
        "intent": "Convert all System.out.printf statements to use Java logging (java.util.logging.Logger)",
        "discovery_output": {
            "code": SAMPLE_JAVA,
            "language": "java",
            "file_path": "UserManager.java"
        }
    }
    
    print("\nTEST INPUT:")
    print(json.dumps(test_input, indent=2))
    
    response = await architect.process(test_input)
    
    print("\nRAW RESPONSE:")
    print(json.dumps(response.data, indent=2))
    
    assert response.success