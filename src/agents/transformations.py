# src/agents/transformations.py

from typing import List, Dict, Any
from pathlib import Path
from libcst.codemod import CodemodContext, VisitorBasedCodemodCommand
from libcst import MetadataWrapper, parse_module
import libcst as cst
import subprocess
import semgrep
import autogen
import os

def format_code(file_path: Path) -> None:
    """Format code using ruff CLI"""
    try:
        # First fix with ruff
        subprocess.run(['ruff', 'check', '--fix', str(file_path)], check=True)
        # Then format with ruff format
        subprocess.run(['ruff', 'format', str(file_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error formatting {file_path}: {e}")

def run_semgrep_check(files: List[Path], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Run semgrep checks on files"""
    try:
        findings = semgrep.scan_files(
            [str(f) for f in files],
            config=rules
        )
        return findings
    except Exception as e:
        print(f"Error running semgrep: {e}")
        return {}

class BaseTransformation:
    """Base class for code transformations using libcst"""
    
    def __init__(self, context: CodemodContext, transform_args: Dict[str, Any]):
        self.context = context
        self.transform_args = transform_args
        
    def visit_Module(self, node: cst.Module) -> None:
        """Override to implement module-level transforms"""
        pass
        
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Override to implement function-level transforms"""
        pass

class LoggingTransform(VisitorBasedCodemodCommand):
    """Add logging to functions using libcst"""
    
    def visit_Module(self, node: cst.Module) -> cst.Module:
        # Add logging import if needed
        has_logging = any(
            isinstance(i, cst.Import) and "logging" in i.names
            for i in node.body
        )
        
        if not has_logging:
            return node.with_changes(
                body=[
                    cst.Import(names=[cst.ImportAlias(name=cst.Name("logging"))]),
                    *node.body
                ]
            )
        return node
        
    def visit_FunctionDef(self, node: cst.FunctionDef) -> cst.FunctionDef:
        # Add logging statement at start of function
        log_stmt = cst.SimpleStatementLine(
            body=[
                cst.Expr(
                    value=cst.Call(
                        func=cst.Attribute(
                            value=cst.Name("logging"),
                            attr=cst.Name("info")
                        ),
                        args=[
                            cst.Arg(
                                value=cst.SimpleString(
                                    f'f"Calling {node.name.value}"'
                                )
                            )
                        ]
                    )
                )
            ]
        )
        
        return node.with_changes(
            body=cst.IndentedBlock(
                body=[log_stmt, *node.body.body]
            )
        )

class LLMTransformation:
    """Add logging to functions using LLM"""
    
    def __init__(self):
        # Initialize LLM agent
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": api_key,
            }
        ]
        
        self.llm_agent = autogen.AssistantAgent(
            name="llm_transformer",
            llm_config={"config_list": self.config_list},
            system_message="""You are a Python code transformation expert.
            When given Python code:
            1. Add logging import if needed
            2. Add logging.info calls at the start of each function
            3. Preserve all existing functionality
            4. Return only the modified code
            5. Use proper indentation"""
        )
        
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def transform_code(self, source_code: str) -> str:
        """Transform code using LLM"""
        try:
            chat_response = await self.manager.a_initiate_chat(
                self.llm_agent,
                message=f"""Add logging to all functions in this Python code:

                {source_code}
                
                Return only the complete modified code."""
            )
            
            # Get the last assistant message
            assistant_messages = [
                msg['content'] for msg in chat_response.chat_messages
                if msg.get('role') == 'assistant'
            ]
            
            if not assistant_messages:
                return source_code
                
            # Extract code from the last message
            code = self._extract_code(assistant_messages[-1])
            return code if code else source_code
            
        except Exception:
            return source_code

    def _extract_code(self, message: str) -> str:
        """Extract code from message"""
        if "```python" in message:
            return message.split("```python")[1].split("```")[0].strip()
        elif "```" in message:
            return message.split("```")[1].strip()
        return message.strip()

def get_transformer(strategy: str = "codemod") -> BaseTransformation | LLMTransformation:
    """Factory function to get the right transformation implementation"""
    if strategy == "llm":
        return LLMTransformation()
    return LoggingTransform  # Default to codemod