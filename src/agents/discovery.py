# src/agents/discovery.py

from typing import Dict, Any, List
import structlog
from pathlib import Path
from .base import BaseAgent, AgentConfig

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery and initial analysis"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="discovery",
            system_message="""You are a discovery agent that analyzes Python projects.
            When analyzing files for adding logging:
            1. For single line changes, provide: 
               file_path:line_number:old_line -> new_line
            2. For function changes, provide the complete new function with location:
               file_path:function_name
               <complete function code>
            3. For new imports, provide:
               file_path:import:import statement
            Do not explain or apologize - just provide the structured output."""
        ))
        self.logger = structlog.get_logger()

    def format_changes(self, files: Dict[str, str]) -> List[Dict[str, Any]]:
        """Format file changes in a structured way"""
        changes = []
        
        for file_path, content in files.items():
            # Add logging import if needed
            changes.append({
                "file": file_path,
                "type": "import",
                "content": "import logging\nlogger = logging.getLogger(__name__)"
            })
            
            # Parse file and find functions
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Add logging to function
                    changes.append({
                        "file": file_path,
                        "type": "function",
                        "name": node.name,
                        "lineno": node.lineno,
                        "logging_stmt": f'    logger.info(f"Calling {node.name}")\n'
                    })
                    
        return changes

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process discovery request with structured output"""
        project_path = context.get("project_path")
        if not project_path:
            raise ValueError("No project path provided")
            
        try:
            # Run discovery using tartxt
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "--exclude", "*.pyc,__pycache__",
                 "--output", project_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse files and format changes
            python_files = self._extract_python_files(result.stdout)
            file_contents = self._read_files(python_files)
            changes = self.format_changes(file_contents)
            
            return {
                "discovery_output": result.stdout,
                "files": python_files,
                "changes": changes
            }
            
        except Exception as e:
            self.logger.error("discovery.failed", error=str(e))
            raise

    def _extract_python_files(self, tartxt_output: str) -> List[str]:
        """Extract Python file paths from tartxt output"""
        files = []
        for line in tartxt_output.splitlines():
            if line.endswith('.py'):
                files.append(line.strip())
        return files

    def _read_files(self, files: List[str]) -> Dict[str, str]:
        """Read content of Python files"""
        contents = {}
        for file_path in files:
            try:
                with open(file_path, 'r') as f:
                    contents[file_path] = f.read()
            except Exception as e:
                self.logger.error(f"Failed to read {file_path}: {e}")
        return contents