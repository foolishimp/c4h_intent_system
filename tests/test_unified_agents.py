# tests/test_unified_agents.py

import pytest
from typing import Dict, Any, Optional, List
import os
import json
from datetime import datetime

from src.agents.base import SingleShotAgent
from src.agents.base_langchain import SingleShotLangChainAgent
from src.agents.base_direct import SingleShotDirectAgent
from src.agents.base_lite import LiteAgent, LLMProvider

# Test implementations of each agent type
class AutogenTestAgent(SingleShotAgent):
    def _get_agent_name(self) -> str:
        return "autogen_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent for the Autogen implementation.
        When given input, respond with valid JSON in this format:
        {
            "timestamp": "ISO timestamp",
            "processed_input": "the input you received",
            "agent_type": "autogen",
            "status": "success"
        }"""

class LangChainTestAgent(SingleShotLangChainAgent):
    def _get_agent_name(self) -> str:
        return "langchain_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent for the LangChain implementation.
        When given input, respond with valid JSON in this format:
        {
            "timestamp": "ISO timestamp",
            "processed_input": "the input you received",
            "agent_type": "langchain",
            "status": "success"
        }"""

class DirectTestAgent(SingleShotDirectAgent):
    def _get_agent_name(self) -> str:
        return "direct_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent for the Direct OpenAI implementation.
        When given input, respond with valid JSON in this format:
        {
            "timestamp": "ISO timestamp",
            "processed_input": "the input you received",
            "agent_type": "direct",
            "status": "success"
        }"""

class LiteTestAgent(LiteAgent):
    def _get_agent_name(self) -> str:
        return "lite_test"
    
    def _get_system_message(self) -> str:
        return """You are a test agent for the LiteLLM implementation.
        When given input, respond with valid JSON in this format:
        {
            "timestamp": "ISO timestamp",
            "processed_input": "the input you received",
            "agent_type": "lite",
            "status": "success"
        }"""

@pytest.fixture
def config_list():
    """OpenAI config fixture"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set")
    return [{
        "model": "gpt-4",
        "api_key": api_key,
        "temperature": 0,
        "request_timeout": 120
    }]

@pytest.fixture
def all_agents(config_list):
    """Initialize all agent types"""
    return {
        "autogen": AutogenTestAgent(config_list),
        "langchain": LangChainTestAgent(config_list),
        "direct": DirectTestAgent(config_list),
        "lite": LiteTestAgent(
            provider=LLMProvider.OPENAI,
            fallback_providers=[
                LLMProvider.ANTHROPIC,
                LLMProvider.GEMINI
            ]
        )
    }

class TestResult:
    """Structured test result"""
    def __init__(self, agent_type: str, success: bool, error: Optional[str] = None,
                 response: Optional[Dict] = None, latency: Optional[float] = None):
        self.agent_type = agent_type
        self.success = success
        self.error = error
        self.response = response
        self.latency = latency
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "agent_type": self.agent_type,
            "success": self.success,
            "error": self.error,
            "response": self.response,
            "latency_ms": round(self.latency * 1000) if self.latency else None,
            "timestamp": self.timestamp
        }

class TestScenario:
    """Test scenario definition"""
    def __init__(self, name: str, input_data: Dict[str, Any],
                 validation_rules: List[callable]):
        self.name = name
        self.input_data = input_data
        self.validation_rules = validation_rules

    def run(self, agent: Any) -> TestResult:
        """Run scenario against an agent"""
        start_time = datetime.utcnow().timestamp()
        try:
            # Process the input
            response = agent.process(self.input_data)
            latency = datetime.utcnow().timestamp() - start_time
            
            # Validate response
            success = True
            error = None
            
            for rule in self.validation_rules:
                if not rule(response):
                    success = False
                    error = f"Failed validation rule: {rule.__name__}"
                    break
                    
            return TestResult(
                agent_type=agent._get_agent_name(),
                success=success,
                error=error,
                response=response.data if hasattr(response, 'data') else response,
                latency=latency
            )
            
        except Exception as e:
            latency = datetime.utcnow().timestamp() - start_time
            return TestResult(
                agent_type=agent._get_agent_name(),
                success=False,
                error=str(e),
                latency=latency
            )

# Validation rules
def validate_response_format(response):
    """Check response has expected structure"""
    if not hasattr(response, 'success'):
        return False
    if not hasattr(response, 'data'):
        return False
    return True

def validate_json_response(response):
    """Validate JSON response content"""
    try:
        if not hasattr(response, 'data') or 'response' not in response.data:
            return False
        content = response.data['response']
        if isinstance(content, str):
            content = json.loads(content)
        required_fields = ['timestamp', 'processed_input', 'agent_type', 'status']
        return all(field in content for field in required_fields)
    except:
        return False

def validate_error_response(response):
    """Validate error response"""
    if not hasattr(response, 'success'):
        return False
    if not response.success:
        return response.error is not None
    return True

# Test scenarios
basic_scenarios = [
    TestScenario(
        name="Basic message processing",
        input_data={"message": "Hello, agent!"},
        validation_rules=[validate_response_format, validate_json_response]
    ),
    TestScenario(
        name="Empty message",
        input_data={"message": ""},
        validation_rules=[validate_response_format, validate_json_response]
    )
]

error_scenarios = [
    TestScenario(
        name="Invalid input type",
        input_data=None,
        validation_rules=[validate_error_response]
    )
]

def test_all_agents_basic(all_agents):
    """Test basic functionality across all agent types"""
    results = []
    
    for scenario in basic_scenarios:
        print(f"\n=== Running Scenario: {scenario.name} ===")
        
        for agent_type, agent in all_agents.items():
            print(f"\nTesting {agent_type} agent...")
            result = scenario.run(agent)
            results.append(result)
            
            # Print result summary
            status = "PASSED" if result.success else "FAILED"
            print(f"{agent_type} agent: {status}")
            if not result.success:
                print(f"Error: {result.error}")
            if result.latency:
                print(f"Latency: {round(result.latency * 1000)}ms")
    
    # Verify all tests passed
    failed = [r for r in results if not r.success]
    if failed:
        failure_details = "\n".join([
            f"{r.agent_type}: {r.error}" for r in failed
        ])
        pytest.fail(f"Some agents failed basic tests:\n{failure_details}")

def test_all_agents_errors(all_agents):
    """Test error handling across all agent types"""
    results = []
    
    for scenario in error_scenarios:
        print(f"\n=== Running Error Scenario: {scenario.name} ===")
        
        for agent_type, agent in all_agents.items():
            print(f"\nTesting {agent_type} agent...")
            result = scenario.run(agent)
            results.append(result)
            
            # Print result summary
            status = "PASSED" if result.success else "FAILED"
            print(f"{agent_type} agent: {status}")
            if result.error:
                print(f"Error: {result.error}")
            if result.latency:
                print(f"Latency: {round(result.latency * 1000)}ms")
    
    # For error scenarios, we expect failures
    unexpected_success = [r for r in results if r.success]
    if unexpected_success:
        details = "\n".join([
            f"{r.agent_type}: Expected failure but succeeded"
            for r in unexpected_success
        ])
        pytest.fail(f"Some agents didn't handle errors correctly:\n{details}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])