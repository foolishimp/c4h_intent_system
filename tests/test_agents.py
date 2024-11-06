# tests/test_agents.py

import pytest
from typing import Dict, Any, Optional
from src.agents.base import SingleShotAgent
from src.agents.solution_architect import SolutionArchitect
import os

class TestAgent(SingleShotAgent):
    """Simple test agent implementation"""
    
    def _get_agent_name(self) -> str:
        return "test_agent"
    
    def _get_system_message(self) -> str:
        return """You are a test agent.
        When given any input, respond with a JSON object containing:
        {
            "message": "the input message",
            "status": "ok"
        }"""
    
    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return f"Process this message: {intent.get('message', 'no message')}"

@pytest.fixture
def config_list():
    """Test fixture for OpenAI config"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")
    return [{"model": "gpt-4", "api_key": api_key}]

@pytest.fixture
def test_agent(config_list):
    return TestAgent(config_list)

@pytest.fixture
def solution_architect(config_list):
    return SolutionArchitect(config_list)

@pytest.mark.asyncio
async def test_base_agent_single_shot(test_agent):
    """Test that the base agent can process a simple message"""
    response = await test_agent.process({
        "message": "Hello world"
    })
    
    assert response.success == True
    assert isinstance(response.data, dict)
    assert "response" in response.data

@pytest.mark.asyncio
async def test_agent_error_handling(test_agent):
    """Test that the agent handles errors gracefully"""
    response = await test_agent.process(None)
    
    assert response.success == False
    assert isinstance(response.data, dict)
    assert response.error is not None

@pytest.mark.asyncio
async def test_solution_architect_basic(solution_architect):
    """Test that the solution architect can process a basic request"""
    response = await solution_architect.process({
        "intent": "Add logging",
        "discovery_output": {
            "discovery_output": "def test(): pass"
        }
    })
    
    assert response.success == True
    assert isinstance(response.data, dict)
    assert "response" in response.data

if __name__ == "__main__":
    pytest.main([__file__, "-v"])