# tests/test_refactoring.py

import pytest
import asyncio
from pathlib import Path
from src.models.intent import Intent
from src.main import process_intent

@pytest.fixture
def project1_path():
    return Path(__file__).parent / "test_projects" / "project1"

@pytest.fixture
def project2_path():
    return Path(__file__).parent / "test_projects" / "project2"

@pytest.mark.asyncio
async def test_add_logging(project1_path):
    """Test adding logging to functions"""
    intent = Intent(
        description="Add logging to all functions",
        project_path=str(project1_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project1_path / "sample.py") as f:
        content = f.read()
        assert "import logging" in content
        assert "logging.info" in content

@pytest.mark.asyncio
async def test_add_type_hints(project2_path):
    """Test adding type hints to functions"""
    intent = Intent(
        description="Add type hints to all functions",
        project_path=str(project2_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project2_path / "utils.py") as f:
        content = f.read()
        assert "def format_name(name: str) ->" in content
        assert "def validate_age(age: int) ->" in content

@pytest.mark.asyncio
async def test_error_handling(project2_path):
    """Test adding error handling to functions"""
    intent = Intent(
        description="Add try-except blocks to all functions",
        project_path=str(project2_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project2_path / "main.py") as f:
        content = f.read()
        assert "try:" in content
        assert "except" in content
