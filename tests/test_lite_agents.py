# tests/test_lite_agents.py

import pytest
from typing import Dict, Any, Optional
import os
from src.agents.base_lite import LiteAgent, LLMProvider, AgentResponse
import structlog

logger = structlog.get_logger()

class TestLiteAgent(LiteAgent):
    """Test implementation of LiteAgent"""
    
    def _get_agent_name(self) -> str:
        return "test_lite_agent"
    
    def _get_system_message(self) -> str:
        return """You are a test agent. You must respond with valid JSON containing:
        {
            "message": "the processed message",
            "status": "success"
        }"""

@pytest.fixture
def check_env_vars():
    """Check required environment variables"""
    missing = []
    for provider in LLMProvider:
        if not os.getenv(provider.value.upper() + "_API_KEY"):
            missing.append(provider.value.upper() + "_API_KEY")
    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")

@pytest.mark.asyncio
async def test_anthropic_agent(check_env_vars):
    """Test Claude agent"""
    agent = TestLiteAgent(provider=LLMProvider.ANTHROPIC)
    response = await agent.process({"message": "Hello Claude"})
    _validate_response(response, "anthropic")

@pytest.mark.asyncio
async def test_openai_agent(check_env_vars):
    """Test OpenAI agent"""
    agent = TestLiteAgent(provider=LLMProvider.OPENAI)
    response = await agent.process({"message": "Hello GPT"})
    _validate_response(response, "openai")

@pytest.mark.asyncio
async def test_gemini_agent(check_env_vars):
    """Test Gemini agent"""
    agent = TestLiteAgent(provider=LLMProvider.GEMINI)
    response = await agent.process({"message": "Hello Gemini"})
    _validate_response(response, "gemini")

@pytest.mark.asyncio
async def test_fallback_chain(check_env_vars):
    """Test fallback chain functionality"""
    agent = TestLiteAgent(
        provider=LLMProvider.ANTHROPIC,
        fallback_providers=[
            LLMProvider.OPENAI,
            LLMProvider.GEMINI
        ]
    )
    response = await agent.process({"message": "Test fallback"})
    _validate_response(response, "fallback")

@pytest.mark.asyncio
async def test_all_providers(check_env_vars):
    """Test all providers with same input"""
    test_message = {"message": "Hello AI"}
    results = []
    
    for provider in LLMProvider:
        try:
            agent = TestLiteAgent(provider=provider)
            response = await agent.process(test_message)
            
            results.append({
                "provider": provider.value,
                "success": response.success,
                "response": response
            })
            
            print(f"\n{provider.value} response:", response)
            
        except Exception as e:
            results.append({
                "provider": provider.value,
                "success": False,
                "error": str(e)
            })
    
    # Print summary
    print("\n=== Provider Test Results ===")
    for result in results:
        status = "PASSED" if result["success"] else "FAILED"
        print(f"\n{result['provider']}: {status}")
        if not result["success"]:
            print(f"Error: {result.get('error', 'Unknown error')}")

def _validate_response(response: AgentResponse, provider: str):
    """Validate agent response"""
    assert response.success, f"{provider} request failed"
    assert isinstance(response.data, dict), f"{provider} response not dict"
    assert "response" in response.data, f"{provider} missing response field"
    
    content = response.data["response"]
    assert isinstance(content, dict), f"{provider} response not parsed JSON"
    assert "message" in content, f"{provider} response missing message"
    assert "status" in content, f"{provider} response missing status"
    assert content["status"] in ["success", "Processed"], \
        f"{provider} invalid status: {content['status']}"

@pytest.mark.asyncio
async def test_invalid_input():
    """Test handling of invalid input"""
    agent = TestLiteAgent(provider=LLMProvider.ANTHROPIC)
    response = await agent.process(None)
    assert response.success == False
    assert "Invalid input" in response.error

@pytest.mark.asyncio
async def test_missing_api_key():
    """Test handling of missing API key"""
    with pytest.raises(ValueError) as exc:
        TestLiteAgent(provider=LLMProvider.ANTHROPIC, 
                     model="nonexistent-model")
    assert "API key" in str(exc.value)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])