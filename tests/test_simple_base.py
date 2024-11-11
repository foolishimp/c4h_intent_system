# tests/test_simple_base.py

import pytest
import os
from src.agents.simple_base import SimpleAgent

@pytest.mark.asyncio
async def test_simple_chat():
    """Basic chat test"""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
        
    agent = SimpleAgent()
    response = await agent.simple_chat("Hello, are you working?")
    
    print(f"\nResponse success: {response.success}")
    print(f"Response message: {response.message}")
    print(f"Response error: {response.error}")
    
    assert response.success, f"Chat failed: {response.error}"
    assert len(response.message) > 0, "Empty response received"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])