# tests/test_base_agent.py

import pytest
from typing import Dict, Any, Optional
import os
import json
from datetime import datetime
import structlog
from unittest.mock import Mock, patch

from src.agents.base import AgentResponse, SingleShotAgent, BaseAgent

# Test implementation without using __init__
class TestAgent(SingleShotAgent):
    """Test implementation of SingleShotAgent"""
    
    def _get_agent_name(self) -> str:
        return "test_agent"
    
    def _get_system_message(self) -> str:
        return """You are a test agent.
        When given input, respond with valid JSON containing:
        {
            "test": "value"
        }"""

# Test implementation for base agent
class TestBaseOnlyAgent(BaseAgent):
    """Test implementation of base agent only"""
    
    def _get_agent_name(self) -> str:
        return "base_test_agent"
        
    def _get_system_message(self) -> str:
        return "Test system message"

# Fixtures
@pytest.fixture
def api_key(mock_openai_env):
    """Get API key from environment"""
    return mock_openai_env["OPENAI_API_KEY"]

@pytest.fixture
def test_agent(api_key):
    """Create test agent instance"""
    config = [{
        "model": "gpt-4",
        "api_key": api_key,
        "temperature": 0
    }]
    return TestAgent(config)

@pytest.fixture
def base_agent():
    """Create base agent instance"""
    return TestBaseOnlyAgent()

@pytest.mark.asyncio
class TestBaseAgent:
    """Test cases for base agent functionality"""
    
    async def test_agent_initialization(self, api_key):
        """Test basic agent initialization"""
        config = [{
            "model": "gpt-4",
            "api_key": api_key,
            "temperature": 0
        }]
        agent = TestAgent(config)
        assert agent.assistant is not None
        assert agent.coordinator is not None
        assert isinstance(agent.logger, structlog.stdlib.BoundLogger)
        assert agent._get_agent_name() == "test_agent"

    async def test_agent_no_config(self):
        """Test agent initialization without config"""
        with pytest.raises(ValueError) as exc:
            TestAgent(None)
        assert "Config list is required" in str(exc.value)

    async def test_basic_process(self, test_agent):
        """Test basic message processing"""
        with patch.object(test_agent.coordinator, 'a_initiate_chat') as mock_chat:
            with patch.object(test_agent.coordinator, 'last_message') as mock_last:
                mock_last.return_value = {
                    'content': '{"test": "value"}',
                    'role': 'assistant'
                }
                response = await test_agent.process({"test": "message"})
                assert isinstance(response, AgentResponse)
                assert response.success is True
                assert response.data["response"]["test"] == "value"
                assert "timestamp" in response.metadata

    async def test_invalid_input(self, test_agent):
        """Test handling of invalid input"""
        response = await test_agent.process(None)
        assert response.success is False
        assert "Invalid input" in response.error
        assert "timestamp" in response.metadata

    async def test_format_request(self, test_agent):
        """Test request formatting"""
        test_input = {"message": "test"}
        formatted = test_agent._format_request(test_input)
        assert isinstance(formatted, str)
        assert "test" in formatted

    async def test_system_message(self, test_agent):
        """Test system message format"""
        message = test_agent._get_system_message()
        assert isinstance(message, str)
        assert "test agent" in message.lower()

    async def test_coordinator_error(self, test_agent):
        """Test handling of coordinator errors"""
        with patch.object(test_agent.coordinator, 'a_initiate_chat', 
                         side_effect=Exception("Test error")):
            response = await test_agent.process({"test": "message"})
            assert response.success is False
            assert "error" in response.error.lower()
            assert "timestamp" in response.metadata

    async def test_full_conversation_flow(self, test_agent):
        """Test a complete conversation flow"""
        test_input = {
            "message": "test",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with patch.object(test_agent.coordinator, 'a_initiate_chat') as mock_chat:
            with patch.object(test_agent.coordinator, 'last_message') as mock_last:
                mock_last.return_value = {
                    'content': json.dumps({
                        "test": "value",
                        "received": "test"
                    }),
                    'role': 'assistant'
                }
                response = await test_agent.process(test_input)
                assert response.success is True
                assert isinstance(response.data, dict)
                assert "response" in response.data
                assert "timestamp" in response.metadata
                assert "chat_messages" in response.metadata

    def test_base_agent_methods(self, base_agent):
        """Test base agent implementation"""
        assert base_agent._get_agent_name() == "base_test_agent"
        assert base_agent._get_system_message() == "Test system message"
        assert "Error: Invalid input" in base_agent._format_request(None)
        assert isinstance(base_agent._format_request({"test": "value"}), str)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--log-cli-level=DEBUG"])