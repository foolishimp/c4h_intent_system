# src/agents/transformations.py

from typing import List, Dict, Any
from pathlib import Path
from libcst.codemod import CodemodContext, VisitorBasedCodemodCommand
from libcst import MetadataWrapper, parse_module
import libcst as cst
import subprocess
import semgrep

class BaseTransformation(VisitorBasedCodemodCommand):
    """Base class for code transformations using libcst"""
    
    def __init__(self, context: CodemodContext, transform_args: Dict[str, Any]):
        super().__init__(context)
        self.transform_args = transform_args
        
    def visit_Module(self, node: cst.Module) -> None:
        """Override to implement module-level transforms"""
        pass
        
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Override to implement function-level transforms"""
        pass

class LoggingTransform(BaseTransformation):
    """Add logging to functions"""
    
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

def format_code(file_path: Path) -> None:
    """Format code using ruff CLI"""
    try:
        # Use ruff CLI instead of API
        subprocess.run(['ruff', 'check', '--fix', str(file_path)], check=True)
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

def get_transformation(transform_type: str) -> BaseTransformation:
    """Factory function to get the right transformation"""
    transforms = {
        "add_logging": LoggingTransform,
    }
    return transforms[transform_type]