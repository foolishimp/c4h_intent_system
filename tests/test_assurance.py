# tests/test_assurance.py

import pytest
import os
from pathlib import Path
import structlog
from src.agents.base import LLMProvider
from src.agents.assurance import AssuranceAgent

logger = structlog.get_logger()

# Test data with proper Python indentation
SAMPLE_TEST_CASE = """import pytest

def test_file_changes():
    assert True  # Basic test that should pass
"""

SAMPLE_VALIDATION_SCRIPT = """#!/usr/bin/env python3
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
        
    temp_workspace = Path("test_workspace")
    temp_workspace.mkdir(exist_ok=True)
    
    return AssuranceAgent(
        provider=LLMProvider.ANTHROPIC,
        workspace_root=temp_workspace
    )

@pytest.fixture(autouse=True)
async def cleanup_workspace():
    """Clean up test workspace after each test"""
    yield
    workspace = Path("test_workspace")
    if workspace.exists():
        for file in workspace.iterdir():
            try:
                if file.is_file():
                    file.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up {file}: {e}")

@pytest.mark.asyncio
async def test_validation_type_detection(assurance_agent):
    """Test detection of validation type"""
    print("\nTesting validation type detection...")
    
    # Test pytest detection
    test_type = await assurance_agent._extract_validation_type(SAMPLE_TEST_CASE)
    print(f"Detected type for test case: {test_type}")
    assert test_type == "test"
    
    # Test script detection
    script_type = await assurance_agent._extract_validation_type(SAMPLE_VALIDATION_SCRIPT)
    print(f"Detected type for script: {script_type}")
    assert script_type == "script"

@pytest.mark.asyncio
async def test_instruction_extraction(assurance_agent):
    """Test extraction of validation instructions"""
    print("\nTesting instruction extraction...")
    
    # Test pytest instructions
    test_instructions = await assurance_agent._extract_instructions(SAMPLE_TEST_CASE)
    print(f"\nTest instructions: {test_instructions}")
    assert "command" in test_instructions
    assert test_instructions["type"] == "pytest"
    
    # Test script instructions  
    script_instructions = await assurance_agent._extract_instructions(SAMPLE_VALIDATION_SCRIPT)
    print(f"\nScript instructions: {script_instructions}")
    assert "command" in script_instructions
    assert script_instructions["type"] == "script"
    assert "success_patterns" in script_instructions

@pytest.mark.asyncio
async def test_validation_execution(assurance_agent):
    """Test execution of validation"""
    print("\nTesting validation execution...")
    
    # Create test file
    test_path = assurance_agent.workspace_root / "test_changes.py"
    test_path.write_text(SAMPLE_TEST_CASE)
    print(f"\nCreated test file at: {test_path}")
    
    result = await assurance_agent.validate(SAMPLE_TEST_CASE)
    print(f"\nValidation result: {result}")
    assert result["success"] == True, "Basic test should pass"
    assert "output" in result, "Should include test output"

@pytest.mark.asyncio
async def test_script_execution(assurance_agent):
    """Test execution of validation script"""
    print("\nTesting script execution...")
    
    # Create validation script
    script_path = assurance_agent.workspace_root / "validate.py"
    script_path.write_text(SAMPLE_VALIDATION_SCRIPT)
    script_path.chmod(0o755)  # Make executable
    print(f"\nCreated script at: {script_path}")
    
    result = await assurance_agent.validate(SAMPLE_VALIDATION_SCRIPT)
    print(f"\nScript execution result: {result}")
    assert result["success"] == True, "Validation script should succeed"
    assert "output" in result, "Should include execution output"
    assert "Validation successful" in result["output"], "Should show success message"

@pytest.mark.asyncio
async def test_failed_validation(assurance_agent):
    """Test handling of validation failures"""
    print("\nTesting validation failure handling...")
    
    # Create failing test with proper indentation
    failing_test = """import pytest

def test_should_fail():
    assert False, "This test should fail"
"""
    
    result = await assurance_agent.validate(failing_test)
    print(f"\nFailed validation result: {result}")
    
    assert result["success"] == False, "Should detect test failure"
    assert "error" in result, "Should include error message"
    assert "output" in result, "Should include test output"
    # Note: We're looking for test failure in output, not syntax error
    assert "failed" in result["output"].lower() or "assertion" in result["output"].lower(), "Should indicate test failure in output"

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])