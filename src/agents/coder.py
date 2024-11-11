# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import os
from enum import Enum
import ast
import py_compile
from skills.semantic_extract import SemanticInterpreter

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    """Available merge methods"""
    LLM = "llm"      # Use LLM to interpret and apply changes
    CODEMOD = "codemod"  # Use AST-based transformations

class Coder:
    """Coder agent using semantic interpretation for validation"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize with LLM config and semantic skills"""
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        # Initialize code verification LLM
        self.assistant = autogen.AssistantAgent(
            name="code_verifier",
            llm_config={"config_list": config_list},
            system_message="""You are an expert code verifier.
            When analyzing code changes:
            1. Verify syntax correctness
            2. Check for potential runtime errors
            3. Suggest improvements if issues found
            4. Consider edge cases and error conditions
            """
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="verifier_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

        # Initialize semantic interpreter
        self.interpreter = SemanticInterpreter(config_list)

    async def _verify_syntax(self, file_path: str, content: str) -> Dict[str, Any]:
        """Verify code syntax through compilation attempt"""
        try:
            # Try to parse as AST
            ast.parse(content)
            
            # Write to temporary file for compilation test
            temp_path = Path(file_path + '.temp')
            temp_path.write_text(content)
            
            try:
                py_compile.compile(str(temp_path), doraise=True)
                success = True
                error = None
            except Exception as e:
                success = False
                error = str(e)
            finally:
                temp_path.unlink(missing_ok=True)
            
            return {
                "valid": success,
                "error": error
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Syntax error: {str(e)}"
            }

    async def _analyze_changes(self, file_path: str, content: str, 
                             syntax_result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze code changes using semantic interpretation"""
        analysis = await self.interpreter.interpret(
            content={
                "file": file_path,
                "code": content,
                "syntax_check": syntax_result
            },
            prompt="""Analyze these code changes for potential issues.
            
            Consider:
            1. Syntax correctness
            2. Runtime safety
            3. Error handling
            4. Edge cases
            5. Potential improvements
            
            Provide detailed analysis of any issues found.
            """
        )
        
        return analysis.data

    async def _test_changes(self, file_path: str, content: str) -> Dict[str, Any]:
        """Test code changes through execution analysis"""
        try:
            # Basic syntax and compilation check
            syntax_result = await self._verify_syntax(file_path, content)
            
            # Semantic analysis of changes
            analysis_result = await self._analyze_changes(file_path, content, syntax_result)
            
            return {
                "success": syntax_result["valid"] and not analysis_result.get("critical_issues"),
                "syntax": syntax_result,
                "analysis": analysis_result,
                "safe_to_write": syntax_result["valid"]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "safe_to_write": False
            }

    def _write_file(self, file_path: str, content: str) -> bool:
        """Write content to file with backup"""
        try:
            path = Path(file_path)
            backup_path = path.with_suffix(path.suffix + '.bak')
            
            # Create backup if file exists
            if path.exists():
                path.rename(backup_path)
            
            # Write new content
            path.write_text(content)
            logger.info("coder.file_written", file=str(path))
            return True
            
        except Exception as e:
            logger.error("coder.write_failed", file=file_path, error=str(e))
            # Try to restore backup
            if backup_path.exists():
                backup_path.rename(path)
            return False

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Apply code changes with semantic validation"""
        try:
            # Extract changes using semantic interpretation
            changes_result = await self.interpreter.interpret(
                content=context,
                prompt="""Extract the concrete code changes to be made.
                For each change, identify:
                1. The target file path
                2. The new file content
                3. Any special handling needed
                """
            )
            
            if not changes_result.data:
                return {
                    "status": "failed",
                    "error": "No valid changes extracted from context"
                }

            modified_files = []
            failures = []
            
            # Process each change
            for change in changes_result.data:
                file_path = change.get("file_path")
                new_content = change.get("content")
                
                if not file_path or not new_content:
                    continue
                
                # Test changes before applying
                test_result = await self._test_changes(file_path, new_content)
                
                if test_result["safe_to_write"]:
                    if self._write_file(file_path, new_content):
                        modified_files.append(file_path)
                    else:
                        failures.append({
                            "file": file_path,
                            "reason": "Failed to write changes",
                            "context": test_result
                        })
                else:
                    failures.append({
                        "file": file_path,
                        "reason": "Changes failed validation",
                        "context": test_result
                    })

            return {
                "status": "failed" if failures else "success",
                "modified_files": modified_files,
                "failures": failures,
                "validation_context": {
                    "interpretation": changes_result.raw_response,
                    "changes_data": changes_result.data
                }
            }
            
        except Exception as e:
            logger.error("coder.transform_failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }