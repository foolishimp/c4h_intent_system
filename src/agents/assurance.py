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
import os

from .base import BaseAgent, LLMProvider, AgentResponse
from src.skills.semantic_extract import SemanticExtract, ExtractResult

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
                 workspace_root: Optional[Path] = None,
                 **kwargs):  # Added **kwargs to handle extra config params
        """Initialize assurance agent with semantic tools.
        
        Args:
            provider: LLM provider to use
            model: Specific model to use
            workspace_root: Optional workspace directory
            **kwargs: Additional configuration parameters including temperature
        """
        super().__init__(
            provider=provider,
            model=model,
            temperature=kwargs.get('temperature', 0)  # Get temperature from kwargs with default
        )
        
        # Optional workspace for persistent storage
        if workspace_root:
            self.workspace_root = workspace_root
        else:
            self.workspace_root = Path(tempfile.mkdtemp(prefix="validation_")).resolve()
            
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        logger.info("workspace.created", path=str(self.workspace_root))
        
    def _get_agent_name(self) -> str:
        """Get agent name - required by BaseAgent"""
        return "assurance_agent"
    
    def _get_system_message(self) -> str:
        """Get system message - required by BaseAgent"""
        return """You are a validation expert that analyzes test results.
        When given test output:
        1. Extract key success/failure indicators
        2. Identify specific test failures
        3. Extract relevant error messages
        4. Determine overall validation status
        5. Provide clear validation summary
        """
    
    def __del__(self):
        """Cleanup workspace on destruction"""
        try:
            if hasattr(self, 'workspace_root') and self.workspace_root.exists():
                shutil.rmtree(self.workspace_root)
                logger.info("workspace.cleaned", path=str(self.workspace_root))
        except Exception as e:
            logger.error("workspace.cleanup_failed", error=str(e))

    async def _run_pytest(self, test_content: str) -> ValidationResult:
        """Run pytest validation"""
        try:
            # Create test file with proper indentation
            test_content = "\n".join(line.strip() for line in test_content.splitlines() if line.strip())
            test_file = self.workspace_root / "test_validation.py"
            test_file.write_text(test_content)
            
            logger.info("pytest.file_created", path=str(test_file))
            
            # Capture test output
            import io
            import contextlib
            output = io.StringIO()
            
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exitcode = pytest.main(["-v", "--no-header", str(test_file)])
            
            output_text = output.getvalue()
            success = exitcode == pytest.ExitCode.OK
            
            # Log test result
            if success:
                logger.info("pytest.passed", exitcode=exitcode)
            else:
                logger.warning("pytest.failed", 
                            exitcode=exitcode,
                            output=output_text)
            
            if "failed" in output_text.lower() or "error" in output_text.lower():
                success = False
                
            return ValidationResult(
                success=success,
                output=output_text,
                validation_type="test",
                error=None if success else "Test failed"
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error("pytest.execution_failed", error=error_msg)
            return ValidationResult(
                success=False,
                output="",
                error=error_msg,
                validation_type="test"
            )

    async def _run_script(self, script_content: str) -> ValidationResult:
        """Run validation script"""
        try:
            # Write script to file
            script_file = (self.workspace_root / "validate.py").resolve()
            script_file.write_text(script_content)
            script_file.chmod(0o755)
            
            logger.info("script.created", path=str(script_file))
            
            # Execute script with full path
            env = os.environ.copy()
            env["PYTHONPATH"] = str(script_file.parent)
            
            result = subprocess.run(
                [sys.executable, str(script_file)],
                capture_output=True,
                text=True,
                cwd=str(script_file.parent),
                env=env
            )
            
            # Check for success
            success = (result.returncode == 0 and 
                      "Validation successful" in result.stdout)
            
            if not success:
                logger.warning("script.failed", 
                             returncode=result.returncode,
                             stdout=result.stdout,
                             stderr=result.stderr)
            
            return ValidationResult(
                success=success,
                output=result.stdout + result.stderr,
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
            logger.info("validation.type_determined", type=validation_type)
            
            # Get execution instructions
            instructions = await self._extract_instructions(validation_content)
            
            # Run validation
            if validation_type == "test":
                result = await self._run_pytest(validation_content)
            else:
                result = await self._run_script(validation_content)
            
            return {
                "success": result.success,
                "validation_type": result.validation_type,
                "output": result.output,
                "analysis": {
                    "success": result.success,
                    "error": result.error if not result.success else None,
                    "details": [result.output] if result.output else []
                },
                "error": result.error
            }
            
        except Exception as e:
            logger.error("validation.failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

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