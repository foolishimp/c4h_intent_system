# tests/test_discovery.py

import pytest
from pathlib import Path
import os
import structlog
from src.agents.base import LLMProvider
from src.agents.discovery import DiscoveryAgent

logger = structlog.get_logger()

@pytest.fixture
def test_project(tmp_path):
    """Create a test project structure"""
    # Create some test files
    (tmp_path / "main.py").write_text("print('Hello World')")
    (tmp_path / "utils.py").write_text("def add(a, b): return a + b")
    (tmp_path / "README.md").write_text("# Test Project")
    
    # Create a subdirectory with files
    sub_dir = tmp_path / "src"
    sub_dir.mkdir()
    (sub_dir / "core.py").write_text("class Core: pass")
    
    return tmp_path

@pytest.fixture
async def discovery_agent():
    """Create discovery agent instance"""
    return DiscoveryAgent(
        provider=LLMProvider.ANTHROPIC
    )

@pytest.mark.asyncio
async def test_manifest_parsing(discovery_agent):
    """Test parsing of tartxt manifest output"""
    sample_output = """== Manifest ==
main.py
src/core.py
utils.py
README.md
== Content ==
# Rest of content..."""

    files = discovery_agent._parse_manifest(sample_output)
    
    assert len(files) == 4
    assert "main.py" in files
    assert "src/core.py" in files
    assert "utils.py" in files
    assert "README.md" in files

@pytest.mark.asyncio
async def test_project_discovery(discovery_agent, test_project):
    """Test full project discovery process"""
    result = await discovery_agent.process({
        "project_path": str(test_project)
    })
    
    print("\nDiscovery Result:")
    print(f"Success: {result.success}")
    print(f"Files Found: {len(result.data.get('files', {}))}")
    print(f"Error: {result.error}")
    
    assert result.success, f"Discovery failed: {result.error}"
    assert "files" in result.data
    assert len(result.data["files"]) >= 4  # At least our test files
    assert "discovery_output" in result.data
    assert result.data["project_path"] == str(test_project)

@pytest.mark.asyncio
async def test_invalid_project_path(discovery_agent):
    """Test handling of invalid project path"""
    result = await discovery_agent.process({
        "project_path": "/path/does/not/exist"
    })
    
    assert not result.success
    assert "exist" in result.error.lower()

@pytest.mark.asyncio
async def test_missing_project_path(discovery_agent):
    """Test handling of missing project path"""
    result = await discovery_agent.process({})
    
    assert not result.success
    assert "no project path" in result.error.lower()

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])