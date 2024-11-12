# tests/test_coder.py

import pytest
import json
from pathlib import Path
import structlog
from typing import Any
from src.agents.base import LLMProvider
from src.agents.coder import Coder, MergeMethod

logger = structlog.get_logger()

# Sample Python class for testing
SAMPLE_CLASS = """
class UserService:
    def __init__(self, database):
        self.db = database

    def create_user(self, username: str, email: str) -> bool:
        user = {
            "username": username,
            "email": email
        }
        
        if self.validate_user(user):
            self.db.insert("users", user)
            return True
        return False
        
    def validate_user(self, user: dict) -> bool:
        if not user["username"] or not user["email"]:
            return False
        if "@" not in user["email"]:
            return False
        return True
        
    def get_user(self, username: str) -> dict:
        return self.db.find_one("users", {"username": username})
"""

def print_section(title: str, content: Any) -> None:
    """Print section with clear formatting"""
    print(f"\n{'-' * 20} {title} {'-' * 20}")
    if isinstance(content, (dict, list)):
        print(json.dumps(content, indent=2))
    else:
        print(content)

@pytest.fixture
def test_file(tmp_path):
    """Create temporary test file"""
    file_path = tmp_path / "test_user_service.py"
    file_path.write_text(SAMPLE_CLASS)
    return file_path

@pytest.mark.asyncio
async def test_coder_add_logging(test_file):
    """Test coder's ability to add logging to a Python class"""
    logger.info("Starting add logging test")
    
    # Initialize Coder
    coder = Coder(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet-20240229"
    )

    try:
        # Prepare change request
        change_request = {
            "file_path": str(test_file),
            "change_type": "modify",
            "instructions": """
            Add comprehensive logging to this class using Python's logging module:
            1. Add logging import at the top
            2. Add logger initialization using __name__
            3. Add info level logging for:
               - Service initialization
               - User creation success/failure
               - User retrieval results
            4. Add debug level logging for:
               - Validation steps
               - Database operations
            5. Add warning level logging for:
               - Validation failures
            6. Maintain all existing functionality and type hints
            7. Preserve code style and indentation
            """
        }
        
        print_section("ORIGINAL FILE", test_file.read_text())
        print_section("CHANGE REQUEST", change_request)
        
        # Execute transformation
        result = await coder.transform(change_request)
        print_section("TRANSFORM RESULT", result)
        
        if result["status"] == "success":
            # Show both backup and modified files
            backup_path = Path(result["backup_path"])
            modified_path = Path(result["file_path"])
            
            print_section("BACKUP FILE", backup_path.read_text())
            print_section("MODIFIED FILE", modified_path.read_text())
            
            # Also save to a known location
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            
            # Save both versions
            out_original = output_dir / "original_userservice.py"
            out_modified = output_dir / "modified_userservice.py"
            
            out_original.write_text(backup_path.read_text())
            out_modified.write_text(modified_path.read_text())
            
            print(f"\nOutput files saved to:")
            print(f"Original: {out_original}")
            print(f"Modified: {out_modified}")
        
        # Run validations
        assert result["status"] == "success", f"Transform failed: {result.get('error')}"
        
        modified_content = Path(result["file_path"]).read_text()
        
        # Verify basic changes
        assert "import logging" in modified_content
        assert "logger = logging.getLogger" in modified_content
        assert "logger.info" in modified_content
        assert "logger.debug" in modified_content
        assert "logger.warning" in modified_content
        
        # Verify type hints preserved
        assert "def create_user(self, username: str, email: str) -> bool:" in modified_content
        assert "def validate_user(self, user: dict) -> bool:" in modified_content
        assert "def get_user(self, username: str) -> dict:" in modified_content
        
        logger.info("Add logging test completed successfully")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_coder_invalid_requests():
    """Test coder's handling of invalid requests"""
    logger.info("Starting invalid requests test")
    
    coder = Coder(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet-20240229"
    )
    
    test_cases = [
        {
            "name": "Missing file path",
            "request": {
                "change_type": "modify",
                "instructions": "Add logging"
            }
        },
        {
            "name": "Invalid change type",
            "request": {
                "file_path": "test.py",
                "change_type": "invalid",
                "instructions": "Add logging"
            }
        },
        {
            "name": "Empty instructions",
            "request": {
                "file_path": "test.py",
                "change_type": "modify",
                "instructions": ""
            }
        }
    ]
    
    for case in test_cases:
        print_section(f"TESTING {case['name']}", case['request'])
        
        result = await coder.transform(case['request'])
        print_section("RESULT", result)
        
        assert result["status"] == "failed", f"{case['name']} should fail"
        assert "error" in result, f"{case['name']} missing error message"
        logger.info(f"Invalid request test {case['name']} completed")

if __name__ == "__main__":
    pytest.main(["-v", "--log-cli-level=INFO", __file__])