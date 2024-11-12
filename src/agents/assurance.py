# src/agents/assurance.py

from typing import Dict, Any, Optional, List
import structlog
from pathlib import Path
import subprocess
import sys
import pytest
from dataclasses import dataclass
import tempfile
import shutil

from .base import BaseAgent, LLMProvider, AgentResponse
from ..skills.semantic_extract import SemanticExtract, ExtractResult

logger = structlog.get_logger()

@dataclass
class ValidationResult:
    """Result of a validation run"""
    success: bool
    output: str
    error: Optional[str] = None
    validation_type: str = "test"  # "test" or "script"

class AssuranceAgent(BaseAgent):
    """Agent responsible for executing and validating test cases and validation scripts"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 workspace_root: Optional[Path] = None):
        """Initialize assurance agent with semantic tools"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )
        
        self.extractor = SemanticExtract(provider=provider, model=model)
        self.workspace_root = workspace_root or Path(tempfile.mkdtemp(prefix="validation_"))
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
    def __del__(self):
        """Cleanup workspace on destruction"""
        if hasattr(self, 'workspace_root') and self.workspace_root.exists():
            try:
                shutil.rmtree(self.workspace_root)
            except:
                pass
        
    def _get_agent_name(self) -> str:
        return "assurance_agent"
    
    def _get_system_message(self) -> str:
        return """You are a validation expert that analyzes test results.
        When given test output:
        1. Extract key success/failure indicators
        2. Identify specific test failures
        3. Extract relevant error messages
        4. Determine overall validation status
        5. Provide clear validation summary
        """

    async def _extract_validation_type(self, content: str) -> str:
        """Determine if content describes a test case or script"""
        result = await self.extractor.extract(
            content=content,
            prompt="""Determine if this is a test case or script.
            Look for:
            - pytest/unittest patterns for test cases
            - shell commands or python scripts for scripts
            Return exactly "test" or "script"\n""",
            format_hint="string"
        )
        return result.value if result.success else "test"

    async def _extract_instructions(self, content: str) -> Dict[str, Any]:
        """Extract execution instructions from content"""
        result = await self.extractor.extract(
            content=content,
            prompt="""Extract validation instructions as JSON with:
            - command: The command to run
            - type: "pytest" or "script"
            - success_patterns: List of strings indicating success
            - failure_patterns: List of strings indicating failure""",
            format_hint="json"
        )
        return result.value if result.success else {}

    async def _run_pytest(self, test_content: str) -> ValidationResult:
        """Run pytest validation"""
        try:
            # Clean up test content (remove leading whitespace)
            test_content = "\n".join(line.strip() for line in test_content.splitlines())
            
            # Write test content to file
            test_file = self.workspace_root / "test_validation.py"
            test_file.write_text(test_content)
            
            # Run pytest programmatically
            import pytest
            exitcode = pytest.main(["-v", str(test_file)])
            
            # Interpret result
            success = exitcode == 0 or exitcode == pytest.ExitCode.OK
            
            # Include more detailed output
            test_output = "Test passed successfully" if success else f"Test failed with exit code {exitcode}"
            
            return ValidationResult(
                success=success,
                output=test_output,
                validation_type="test"
            )
            
        except Exception as e:
            logger.error("pytest.execution_failed", error=str(e))
            return ValidationResult(
                success=False,
                output="",
                error=str(e),
                validation_type="test"
            )

    async def _run_script(self, script_content: str) -> ValidationResult:
        """Run validation script"""
        try:
            # Write script to file
            script_file = self.workspace_root / "validate.py"
            script_file.write_text(script_content)
            script_file.chmod(0o755)
            
            # Execute script
            result = subprocess.run(
                [sys.executable, str(script_file)],
                capture_output=True,
                text=True,
                cwd=str(self.workspace_root)  # Convert Path to string
            )
            
            success = result.returncode == 0
            output = result.stdout + result.stderr
            
            return ValidationResult(
                success=success,
                output=output,
                validation_type="script"
            )
            
        except Exception as e:
            logger.error("script.execution_failed", error=str(e))
            return ValidationResult(
                success=False,
                output="",
                error=str(e),
                validation_type="script"
            )

    async def validate(self, validation_content: str) -> Dict[str, Any]:
        """Execute validation and analyze results"""
        try:
            # Determine validation type
            validation_type = await self._extract_validation_type(validation_content)
            
            # Get execution instructions
            instructions = await self._extract_instructions(validation_content)
            
            # Run validation
            if validation_type == "test":
                result = await self._run_pytest(validation_content)
            else:
                result = await self._run_script(validation_content)
            
            # Return results
            return {
                "success": result.success,
                "validation_type": result.validation_type,
                "output": result.output,
                "analysis": {
                    "success": result.success,
                    "error": result.error if not result.success else None,
                    "details": []
                },
                "error": result.error
            }
            
        except Exception as e:
            logger.error("validation.failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process validation request"""
        try:
            validation_content = context.get("validation_content")
            if not validation_content:
                return AgentResponse(
                    success=False,
                    data={},
                    error="No validation content provided"
                )
            
            result = await self.validate(validation_content)
            return AgentResponse(
                success=result.get("success", False),
                data=result,
                error=result.get("error")
            )
            
        except Exception as e:
            logger.error("assurance.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )