# tests/test_agent_comparison.py

import pytest
from typing import Dict, Any, Optional
import os
from src.agents.base import SingleShotAgent
from src.agents.base_langchain import SingleShotLangChainAgent
from src.agents.base_direct import SingleShotDirectAgent
import json

# Test implementations for each base class
class AutogenTestAgent(SingleShotAgent):
    def _get_agent_name(self) -> str:
        return "autogen_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent. You must respond with valid JSON containing:
        {
            "message": "the processed message",
            "status": "success"
        }"""
    
    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return f"Process this message: {intent.get('message', 'no message')}"

class LangChainTestAgent(SingleShotLangChainAgent):
    def _get_agent_name(self) -> str:
        return "langchain_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent. You must respond with valid JSON containing:
        {
            "message": "the processed message",
            "status": "success"
        }"""
    
    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        if not isinstance(intent, dict):
            return "Error: Invalid input"
        return f"Process this message: {intent.get('message', 'no message')}"

class DirectTestAgent(SingleShotDirectAgent):
    def _get_agent_name(self) -> str:
        return "direct_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent. You must respond with valid JSON containing:
        {
            "message": "the processed message",
            "status": "success"
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
def autogen_agent(config_list):
    return AutogenTestAgent(config_list)

@pytest.fixture
def langchain_agent(config_list):
    return LangChainTestAgent(config_list)

@pytest.fixture
def direct_agent(config_list):
    return DirectTestAgent(config_list)

@pytest.mark.asyncio
async def test_all_agents_basic(autogen_agent, langchain_agent, direct_agent):
    """Test that all agents can process a basic message"""
    
    test_message = {"message": "Hello world"}
    results = []
    
    # Test each agent independently
    agents = {
        "autogen": autogen_agent,
        "langchain": langchain_agent,
        "direct": direct_agent
    }
    
    print("\n=== Testing Basic Message Processing ===")
    for name, agent in agents.items():
        try:
            print(f"\nTesting {name} agent...")
            response = await agent.process(test_message)
            print(f"{name} agent response:", response)
            
            # Collect test results
            test_passed = True
            error_msg = None
            try:
                assert response.success == True, "Agent failed"
                assert isinstance(response.data, dict), "Data not dict"
                assert "response" in response.data, "Missing response field"
                
                actual_response = response.data["response"]
                assert "message" in actual_response, "Missing message field"
                assert "status" in actual_response, "Missing status field"
                assert actual_response["status"] in ["success", "Processed"], "Invalid status"
                
            except AssertionError as e:
                test_passed = False
                error_msg = str(e)
            
            results.append({
                "agent": name,
                "passed": test_passed,
                "error": error_msg,
                "response": response
            })
            
        except Exception as e:
            results.append({
                "agent": name,
                "passed": False,
                "error": str(e),
                "response": None
            })
    
    # Print summary
    print("\n=== Test Results Summary ===")
    for result in results:
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"\n{result['agent']} agent: {status}")
        if not result["passed"]:
            print(f"Error: {result['error']}")
        if result["response"]:
            print(f"Response: {result['response']}")
    
    # If any test failed, raise assertion error with details
    failed_tests = [r for r in results if not r["passed"]]
    if failed_tests:
        error_msg = "\n".join([
            f"{r['agent']}: {r['error']}" 
            for r in failed_tests
        ])
        pytest.fail(f"Some agents failed:\n{error_msg}")

@pytest.mark.asyncio
async def test_all_agents_error(autogen_agent, langchain_agent, direct_agent):
    """Test that all agents handle errors gracefully"""
    
    results = []
    agents = {
        "autogen": autogen_agent,
        "langchain": langchain_agent,
        "direct": direct_agent
    }
    
    print("\n=== Testing Error Handling ===")
    for name, agent in agents.items():
        try:
            print(f"\nTesting {name} agent error handling...")
            response = await agent.process(None)
            print(f"{name} agent response:", response)
            
            test_passed = True
            error_msg = None
            try:
                assert response.success == False, "Agent should fail"
                assert isinstance(response.data, dict), "Data not dict"
                assert response.error is not None, "Missing error message"
            except AssertionError as e:
                test_passed = False
                error_msg = str(e)
                
            results.append({
                "agent": name,
                "passed": test_passed,
                "error": error_msg,
                "response": response
            })
            
        except Exception as e:
            results.append({
                "agent": name,
                "passed": False,
                "error": str(e),
                "response": None
            })
    
    # Print summary
    print("\n=== Error Handling Test Results ===")
    for result in results:
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"\n{result['agent']} agent: {status}")
        if not result["passed"]:
            print(f"Error: {result['error']}")
        if result["response"]:
            print(f"Response: {result['response']}")
            
    # If any test failed, raise assertion error with details
    failed_tests = [r for r in results if not r["passed"]]
    if failed_tests:
        error_msg = "\n".join([
            f"{r['agent']}: {r['error']}" 
            for r in failed_tests
        ])
        pytest.fail(f"Some agents failed:\n{error_msg}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])