# tests/test_intent_agent_iterations.py

import pytest
import os
from pathlib import Path
import structlog
from typing import Dict, Any

from src.agents.intent_agent import IntentAgent, IntentContext
from src.models.intent import Intent, IntentStatus
from src.agents.base import AgentResponse

logger = structlog.get_logger()

class MockDiscoveryAgent:
    def __init__(self, fail_first: bool = False):
        self.fail_first = fail_first
        self.call_count = 0
        
    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        self.call_count += 1
        if self.fail_first and self.call_count == 1:
            return AgentResponse(
                success=False,
                data={},
                error="Simulated discovery failure"
            )
        return AgentResponse(
            success=True,
            data={
                "files": {
                    "main.py": True,
                    "utils.py": True
                },
                "language": "python",
                "project_structure": {
                    "type": "simple",
                    "has_tests": True
                }
            }
        )

class MockSolutionArchitect:
    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        return AgentResponse(
            success=True,
            data={
                "actions": [
                    {
                        "file": "main.py",
                        "type": "modify",
                        "changes": "Add logging"
                    },
                    {
                        "file": "utils.py",
                        "type": "modify",
                        "changes": "Add error handling"
                    }
                ],
                "validation_requirements": {
                    "tests": ["test_logging.py"],
                    "compile_check": True
                }
            }
        )

class MockCoder:
    def __init__(self, fail_on_file: str = None):
        self.fail_on_file = fail_on_file
        
    async def process(self, action: Dict[str, Any]) -> AgentResponse:
        if self.fail_on_file and action["file"] == self.fail_on_file:
            return AgentResponse(
                success=False,
                data={},
                error=f"Failed to modify {self.fail_on_file}"
            )
        return AgentResponse(
            success=True,
            data={
                "file": action["file"],
                "status": "modified",
                "changes_applied": True
            }
        )

class MockAssurance:
    def __init__(self, pass_after_attempts: int = 1):
        self.call_count = 0
        self.pass_after_attempts = pass_after_attempts
        
    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        self.call_count += 1
        if self.call_count < self.pass_after_attempts:
            return AgentResponse(
                success=False,
                data={
                    "test_results": {
                        "passed": 5,
                        "failed": 1,
                        "errors": ["Test test_logging failed"]
                    }
                },
                error="Validation failed"
            )
        return AgentResponse(
            success=True,
            data={
                "test_results": {
                    "passed": 6,
                    "failed": 0,
                    "errors": []
                }
            }
        )

@pytest.fixture
def test_project(tmp_path):
    """Create test project structure"""
    # Create main file
    main_py = tmp_path / "main.py"
    main_py.write_text("""
def process_data(data):
    result = data * 2
    print(f"Processing result: {result}")
    return result

if __name__ == "__main__":
    process_data(42)
    """)
    
    # Create utils file
    utils_py = tmp_path / "utils.py"
    utils_py.write_text("""
def validate_input(value):
    if not isinstance(value, (int, float)):
        print("Invalid input")
        return False
    return True
    """)
    
    return tmp_path

@pytest.fixture
def intent_agent():
    """Create intent agent with mocked dependencies"""
    agent = IntentAgent(max_iterations=3)
    agent.discovery = MockDiscoveryAgent()
    agent.architect = MockSolutionArchitect()
    agent.coder = MockCoder()
    agent.assurance = MockAssurance(pass_after_attempts=2)
    return agent

@pytest.mark.asyncio
async def test_successful_iteration(intent_agent, test_project):
    """Test successful completion after one validation failure"""
    print("\nTesting successful iteration with one retry...")
    
    intent_desc = {
        "type": "refactor",
        "description": "Add logging and error handling",
        "requirements": ["Add logging", "Add error handling"]
    }
    
    result = await intent_agent.process(test_project, intent_desc)
    
    print("\nProcessing Result:")
    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Changes Made: {len(result.get('changes', []))}")
    print(f"Final Assurance: {result.get('assurance', {})}")
    
    assert result["status"] == "success"
    assert result["iterations"] == 2
    assert len(result["changes"]) > 0
    assert result["assurance"]["test_results"]["failed"] == 0

@pytest.mark.asyncio
async def test_max_iterations_failure(intent_agent, test_project):
    """Test hitting max iterations with continued failures"""
    print("\nTesting max iterations failure...")
    
    # Configure assurance to always fail
    intent_agent.assurance = MockAssurance(pass_after_attempts=5)
    
    intent_desc = {
        "type": "refactor",
        "description": "Add logging and error handling",
        "requirements": ["Add logging", "Add error handling"]
    }
    
    result = await intent_agent.process(test_project, intent_desc)
    
    print("\nProcessing Result:")
    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Error: {result.get('error')}")
    print(f"Last Assurance: {result.get('last_assurance')}")
    
    assert result["status"] == "failed"
    assert result["iterations"] == 3
    assert "Maximum iterations reached" in result["error"]
    assert result["last_assurance"] is not None

@pytest.mark.asyncio
async def test_discovery_failure_recovery(test_project):
    """Test recovery from initial discovery failure"""
    print("\nTesting discovery failure recovery...")
    
    agent = IntentAgent(max_iterations=3)
    agent.discovery = MockDiscoveryAgent(fail_first=True)
    agent.architect = MockSolutionArchitect()
    agent.coder = MockCoder()
    agent.assurance = MockAssurance(pass_after_attempts=1)
    
    intent_desc = {"type": "refactor", "description": "Add logging"}
    
    result = await agent.process(test_project, intent_desc)
    
    print("\nProcessing Result:")
    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Discovery Attempts: {agent.discovery.call_count}")
    
    assert result["status"] == "success"
    assert agent.discovery.call_count == 2  # Failed once, succeeded on retry
    assert result["iterations"] == 2

@pytest.mark.asyncio
async def test_coder_partial_failure(test_project):
    """Test handling of partial implementation failure"""
    print("\nTesting partial implementation failure...")
    
    agent = IntentAgent(max_iterations=3)
    agent.discovery = MockDiscoveryAgent()
    agent.architect = MockSolutionArchitect()
    agent.coder = MockCoder(fail_on_file="utils.py")
    agent.assurance = MockAssurance(pass_after_attempts=2)
    
    intent_desc = {"type": "refactor", "description": "Add logging"}
    
    result = await agent.process(test_project, intent_desc)
    
    print("\nProcessing Result:")
    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Changes: {result.get('changes')}")
    
    assert result["status"] == "success"
    assert any(c["result"]["file"] == "main.py" for c in result["changes"])
    assert result["iterations"] > 1

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])