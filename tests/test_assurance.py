# tests/test_assurance.py

import pytest
from pathlib import Path
import structlog
from src.agents.base import LLMProvider
from src.agents.assurance import AssuranceAgent

logger = structlog.get_logger()

# Test data
SAMPLE_TEST_CASE = """
import pytest

def test_file_changes():
    assert True  # Replace with actual test
"""

SAMPLE_VALIDATION_SCRIPT = """
#!/usr/bin/env python3
import sys
from pathlib import Path

def validate_changes():
    # Add actual validation logic
    return True

if __name__ == "__main__":
    if validate_changes():
        print("Validation successful")
        sys.exit(0)
    else:
        print("Validation failed")
        sys.exit(1)
"""

@pytest.fixture
async def assurance_agent():
    """Create assurance agent for testing"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
        
    return AssuranceAgent(
        provider=LLMProvider.ANTHROPIC,
        workspace_root=Path("test_workspace")
    )

@pytest.mark.asyncio
async def test_validation_type_detection(assurance_agent):
    """Test detection of validation type"""
    
    # Test pytest detection
    test_type = await assurance_agent._extract_validation_type(SAMPLE_TEST_CASE)
    assert test_type == "test"
    
    # Test script detection
    script_type = await assurance_agent._extract_validation_type(SAMPLE_VALIDATION_SCRIPT)
    assert script_type == "script"

@pytest.mark.asyncio
async def test_instruction_extraction(assurance_agent):
    """Test extraction of validation instructions"""
    
    # Test pytest instructions
    test_instructions = await assurance_agent._extract_instructions(SAMPLE_TEST_CASE)
    assert "command" in test_instructions
    assert test_instructions["type"] == "pytest"
    
    # Test script instructions  
    script_instructions = await assurance_agent._extract_instructions(SAMPLE_VALIDATION_SCRIPT)
    assert "command" in script_instructions
    assert script_instructions["type"] == "script"
    assert "success_patterns" in script_instructions

@pytest.mark.asyncio
async def test_validation_execution(assurance_agent):
    """Test execution of validation"""
    
    # Create test file
    test_path = assurance_agent.workspace_root / "test_changes.py"
    test_path.write_text(SAMPLE_TEST_CASE)
    
    result = await assurance_agent.validate(SAMPLE_TEST_CASE)
    assert result["success"] == True
    assert "output" in result
    assert result["validation_type"] == "test"

@pytest.mark.asyncio
async def test_script_execution(assurance_agent):
    """Test execution of validation script"""
    
    # Create validation script
    script_path = assurance_agent.workspace_root / "validate.py"
    script_path.write_text(SAMPLE_VALIDATION_SCRIPT)
    script_path.chmod(0o755)  # Make executable
    
    result = await assurance_agent.validate(SAMPLE_VALIDATION_SCRIPT)
    assert result["success"] == True
    assert "output" in result
    assert result["validation_type"] == "script"

@pytest.mark.asyncio
async def test_failed_validation(assurance_agent):
    """Test handling of validation failures"""
    
    # Create failing test
    failing_test = """
    import pytest
    def test_should_fail():
        assert False
    """
    
    result = await assurance_agent.validate(failing_test)
    assert result["success"] == False
    assert "error" in result
    assert "analysis" in result

if __name__ == "__main__":
    pytest.main(["-v", __file__])