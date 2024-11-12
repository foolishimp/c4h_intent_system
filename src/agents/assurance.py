# src/agents/assurance.py

from typing import Dict, Any, Optional, List
import structlog
from pathlib import Path
import subprocess
import sys
import pytest
from dataclasses import dataclass
import json

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
        self.workspace_root = workspace_root or Path.cwd() / "validation_workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
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

    async def _analyze_output(self, output: str, validation_type: str) -> Dict[str, Any]:
        """Analyze validation output"""
        result = await self.extractor.extract(
            content=output,
            prompt=f"""Analyze this {validation_type} output and return JSON with:
            - success: boolean indicating overall success
            - error: any error message if failed
            - details: List of specific failure details""",
            format_hint="json"
        )
        return result.value if result.success else {"success": False, "error": "Failed to analyze output"}

    async def _run_validation(self, instructions: Dict[str, Any]) -> ValidationResult:
        """Execute validation command and capture results"""
        try:
            if instructions.get("type") == "pytest":
                # Run pytest programmatically
                test_output = []
                class OutputCapture:
                    def pytest_runtest_logreport(self, report):
                        test_output.append(report)

                pytest.main(
                    ["-v", instructions["command"]],
                    plugins=[OutputCapture()]
                )
                output = "\n".join(str(r) for r in test_output)
                success = all(r.passed for r in test_output if hasattr(r, 'passed'))
                
            else:
                # Run shell command
                result = subprocess.run(
                    instructions["command"],
                    shell=True,
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True
                )
                output = result.stdout + result.stderr
                success = result.returncode == 0 and \
                         any(p in output for p in instructions.get("success_patterns", []))
            
            return ValidationResult(
                success=success,
                output=output,
                validation_type=instructions.get("type", "script")
            )
            
        except Exception as e:
            logger.error("validation.execution_failed", error=str(e))
            return ValidationResult(
                success=False,
                output="",
                error=str(e),
                validation_type=instructions.get("type", "script")
            )

    async def validate(self, validation_content: str) -> Dict[str, Any]:
        """Execute validation and analyze results"""
        try:
            # Determine validation type
            validation_type = await self._extract_validation_type(validation_content)
            
            # Extract execution instructions
            instructions = await self._extract_instructions(validation_content)
            if not instructions:
                raise ValueError("Failed to extract validation instructions")
            
            # Execute validation
            result = await self._run_validation(instructions)
            
            # Analyze output
            analysis = await self._analyze_output(result.output, validation_type)
            
            return {
                "success": result.success and analysis.get("success", False),
                "validation_type": validation_type,
                "output": result.output,
                "analysis": analysis,
                "error": result.error or analysis.get("error")
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