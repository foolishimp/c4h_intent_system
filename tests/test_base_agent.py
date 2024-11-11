# tests/test_base_agent.py

import pytest
from typing import Dict, Any, Optional
import os
from datetime import datetime
import time
import structlog
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class TestAgent(BaseAgent):
    """Test agent implementation"""
    
    def _get_agent_name(self) -> str:
        return "test_agent"
    
    def _get_system_message(self) -> str:
        return """You are a test agent. You must respond with valid JSON containing:
        {
            "timestamp": "ISO timestamp",
            "message": "the processed message",
            "agent_type": "test",
            "status": "success"
        }"""

class TestMetrics:
    """Test metrics container"""
    def __init__(self, provider: str, start_time: float):
        self.provider = provider
        self.start_time = start_time
        self.end_time: Optional[float] = None
        self.latency_ms: Optional[float] = None
        self.success: bool = False
        self.error: Optional[str] = None
        
    def complete(self, success: bool, error: Optional[str] = None):
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error = error
        
    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        latency = f"{self.latency_ms:.0f}ms" if self.latency_ms else "N/A"
        error = f"\n  Error: {self.error}" if self.error else ""
        return f"{self.provider}: {status} ({latency}){error}"

def validate_response(response: AgentResponse, provider_name: str):
    """Validate response format across providers"""
    assert response.success, f"{provider_name} request failed"
    assert isinstance(response.data, dict), f"{provider_name} response not dict"
    assert "response" in response.data, f"{provider_name} missing response field"
    
    parsed = response.data["response"]
    assert isinstance(parsed, dict), f"{provider_name} response not parsed JSON"
    assert "message" in parsed, f"{provider_name} missing message field"
    assert "timestamp" in parsed, f"{provider_name} missing timestamp field"
    assert "status" in parsed, f"{provider_name} missing status field"

# Fixtures
@pytest.fixture
async def anthropic_agent():
    """Create Anthropic agent for testing"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    agent = TestAgent(provider=LLMProvider.ANTHROPIC)
    yield agent

@pytest.fixture
async def openai_agent():
    """Create OpenAI agent for testing"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    agent = TestAgent(provider=LLMProvider.OPENAI)
    yield agent

@pytest.mark.asyncio
async def test_basic_completion(anthropic_agent, openai_agent):
    """Test basic completion across available providers"""
    print("\n=== Testing Basic Completion ===")
    successes = []
    failures = []
    skipped = []
    
    # Test each available provider
    for name, agent in {
        "anthropic": anthropic_agent,
        "openai": openai_agent
    }.items():
        if agent is None:
            skipped.append(name)
            logger.info(f"skipping_provider", provider=name, reason="no api key")
            print(f"\nSkipping {name} - no API key")
            continue
            
        print(f"\nTesting {name}...")
        test_metrics = TestMetrics(name, time.time())
        
        try:
            response = await agent.process({"message": "Hello AI"})
            validate_response(response, name)
            test_metrics.complete(True)
            
            # Log response info
            parsed = response.data["response"]
            print(f"└─ Response status: {parsed['status']}")
            print(f"└─ Message: {parsed['message'][:50]}...")
            successes.append(name)
            
        except Exception as e:
            test_metrics.complete(False, str(e))
            logger.error("provider_failed", provider=name, error=str(e))
            print(f"└─ Error: {e}")
            failures.append(name)
        
        # Print details
        print(test_metrics)
    
    # Print summary
    print("\n=== Test Summary ===")
    if successes:
        print(f"Successes: {', '.join(successes)}")
    if failures:
        print(f"Failures: {', '.join(failures)}")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")
        
    # Only fail if both providers fail
    if len(failures) == 2:
        pytest.fail("All providers failed")

@pytest.mark.asyncio
async def test_error_handling(anthropic_agent):
    """Test error handling"""
    print("\n=== Testing Error Handling ===")
    
    # Test cases
    test_cases = [
        ("None input", None, False, "Invalid input"),
        ("Empty dict", {}, True, None),
        ("Malformed input", {"broken": None}, True, None)
    ]
    
    failures = []
    for name, input_data, should_succeed, expected_error in test_cases:
        print(f"\nTest: {name}")
        start_time = time.time()
        
        try:
            response = await anthropic_agent.process(input_data)
            success = (response.success == should_succeed)
            error_matches = True
            
            if expected_error and success:
                error_matches = expected_error in (response.error or "")
                
            if not success or not error_matches:
                failures.append(name)
                print("✗ Test failed")
                
            latency = (time.time() - start_time) * 1000
            status = "✓" if success and error_matches else "✗"
            print(f"{status} ({latency:.0f}ms)")
            
        except Exception as e:
            failures.append(name)
            print(f"✗ Test error: {e}")
    
    if failures:
        pytest.fail(f"Failed test cases: {', '.join(failures)}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])