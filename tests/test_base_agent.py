# tests/test_base_agent.py

import pytest
import structlog
import os
from typing import Dict, Any, Optional, List
from src.agents.base import SingleShotAgent, AgentResponse

logger = structlog.get_logger()

class TestAgent(SingleShotAgent):
    """Simple test agent implementation"""
    
    def _get_agent_name(self) -> str:
        return "test_agent"
    
    def _get_system_message(self) -> str:
        return "You are a test agent. Respond to any input with valid JSON content."

@pytest.fixture(scope="module")
def config_list():
    """Test fixture for OpenAI config"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")
    return [{
        "model": "gpt-4-turbo-preview",
        "api_key": api_key,
        "temperature": 0,
        "request_timeout": 30
    }]

@pytest.fixture
async def test_agent(config_list):
    """Create and cleanup test agent"""
    agent = TestAgent(config_list=config_list)
    yield agent
    # Cleanup using AutoGen 0.4 methods
    if hasattr(agent.assistant, "reset"):
        agent.assistant.reset()
    if hasattr(agent.coordinator, "reset"):
        agent.coordinator.reset()

@pytest.mark.asyncio
async def test_basic_interaction(test_agent):
    """Test basic request-response interaction"""
    logger.info("test_basic_interaction.starting")
    response = await test_agent.process({"message": "test"})
    
    assert response.success is True, f"Failed with error: {response.error}"
    assert isinstance(response.content, str)
    assert response.content, "Response should have content"
    assert response.error is None
    logger.info("test_basic_interaction.completed", success=response.success)

@pytest.mark.asyncio
async def test_invalid_input(test_agent):
    """Test handling of invalid input"""
    logger.info("test_invalid_input.starting")
    response = await test_agent.process(None)
    
    assert response.success is False
    assert response.error is not None
    assert "Invalid input" in response.error
    assert response.content == ""
    logger.info("test_invalid_input.completed", error=response.error)

@pytest.mark.asyncio
async def test_conversation_independence(test_agent):
    """Test that each request is independent"""
    logger.info("test_conversation_independence.starting")
    first = await test_agent.process({"message": "first"})
    second = await test_agent.process({"message": "second"})
    
    assert first.success and second.success
    assert first.content != second.content
    logger.info("test_conversation_independence.completed",
               first_success=first.success,
               second_success=second.success)

@pytest.mark.asyncio
async def test_timeout_handling(test_agent):
    """Test timeout handling"""
    logger.info("test_timeout_handling.starting")
    original_timeout = test_agent.config["timeout"]
    test_agent.config["timeout"] = 1
    
    try:
        response = await test_agent.process({"message": "x" * 10000})
        assert isinstance(response, AgentResponse)
        logger.info("test_timeout_handling.response_received",
                   success=response.success,
                   error=response.error)
    finally:
        test_agent.config["timeout"] = original_timeout

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--log-cli-level=INFO"])