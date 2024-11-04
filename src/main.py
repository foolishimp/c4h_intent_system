# src/main.py

import asyncio
import sys
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
import autogen
from datetime import datetime
import shutil

logger = structlog.get_logger()

class RefactoringStrategy(str, Enum):
    """Available refactoring strategies"""
    CODEMOD = "codemod"  # Uses libcst
    LLM = "llm"          # Direct LLM code generation

class WorkspaceManager:
    """Manages workspaces for refactoring attempts"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.workspace_root = base_path / "workspaces"
        
    def create_workspace(self, intent_id: str, strategy: RefactoringStrategy) -> Path:
        """Create a new workspace for a refactoring attempt"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace_path = self.workspace_root / f"{intent_id}_{strategy}_{timestamp}"
        workspace_path.mkdir(parents=True, exist_ok=True)
        return workspace_path
        
    def copy_to_workspace(self, source_path: Path, workspace: Path) -> None:
        """Copy project files to workspace"""
        if source_path.is_file():
            shutil.copy2(source_path, workspace)
        else:
            shutil.copytree(source_path, workspace / source_path.name, dirs_exist_ok=True)
            
    def get_workspace_files(self, workspace: Path, pattern: str = "*.py") -> List[Path]:
        """Get all matching files in workspace"""
        return list(workspace.rglob(pattern))
        
    def compare_workspaces(self, workspace1: Path, workspace2: Path) -> Dict[str, Any]:
        """Compare results between two workspaces"""
        import difflib
        
        diffs = {}
        files1 = set(self.get_workspace_files(workspace1))
        files2 = set(self.get_workspace_files(workspace2))
        
        for file1 in files1:
            rel_path = file1.relative_to(workspace1)
            file2 = workspace2 / rel_path
            
            if file2.exists():
                with open(file1) as f1, open(file2) as f2:
                    diff = list(difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile=str(file1),
                        tofile=str(file2)
                    ))
                    if diff:
                        diffs[str(rel_path)] = diff
                        
        return diffs

class RefactoringManager:
    """Manages code refactoring with multiple strategies"""
    
    def __init__(self, strategy: RefactoringStrategy = RefactoringStrategy.CODEMOD):
        self.strategy = strategy
        self.workspace_manager = WorkspaceManager(Path.cwd())
        
        # Initialize agents
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        ]
        
        self.llm_agent = autogen.AssistantAgent(
            name="llm_refactor",
            llm_config={"config_list": self.config_list},
            system_message="""You are a Python code refactoring expert.
            When given a Python file and refactoring intent, you:
            1. Analyze the code structure
            2. Make minimal required changes
            3. Return the complete modified file
            4. Preserve all functionality
            5. Follow Python best practices"""
        )
        
        self.codemod_agent = autogen.AssistantAgent(
            name="codemod_refactor",
            llm_config={"config_list": self.config_list},
            system_message="""You generate libcst transformations for Python code.
            You analyze code and create specific codemod classes to modify it."""
        )
        
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False,
            }
        )

    async def refactor_file_llm(self, file_path: Path, intent: str) -> str:
        """Refactor a file using direct LLM approach"""
        with open(file_path) as f:
            content = f.read()
            
        message = f"""Refactor this Python file to {intent}
        
        Original file ({file_path.name}):
        ```python
        {content}
        ```
        
        Return only the refactored code without any explanations."""
        
        response = await self.manager.a_initiate_chat(
            self.llm_agent,
            message=message
        )
        
        # Extract code from response
        code = self._extract_code(response.last_message())
        return code

    async def refactor_file_codemod(self, file_path: Path, intent: str) -> str:
        """Refactor a file using codemod approach"""
        from libcst.codemod import CodemodContext
        from agents.transformations import LoggingTransform
        
        with open(file_path) as f:
            content = f.read()
            
        context = CodemodContext(filename=str(file_path))
        transform = LoggingTransform(context, {})
        modified_content = transform.transform_module(content)
        
        return modified_content

    async def process_intent(self, intent_id: str, project_path: Path, intent_desc: str) -> Dict[str, Any]:
        """Process a refactoring intent"""
        # Create workspace
        workspace = self.workspace_manager.create_workspace(intent_id, self.strategy)
        self.workspace_manager.copy_to_workspace(project_path, workspace)
        
        results = {}
        for file_path in self.workspace_manager.get_workspace_files(workspace):
            try:
                if self.strategy == RefactoringStrategy.LLM:
                    modified = await self.refactor_file_llm(file_path, intent_desc)
                else:
                    modified = await self.refactor_file_codemod(file_path, intent_desc)
                    
                # Write modified content
                output_path = workspace / file_path.name
                with open(output_path, 'w') as f:
                    f.write(modified)
                    
                results[str(file_path)] = {
                    'status': 'success',
                    'output_path': str(output_path)
                }
                    
            except Exception as e:
                logger.error(f"Failed to refactor {file_path}: {e}")
                results[str(file_path)] = {
                    'status': 'error',
                    'error': str(e)
                }
                
        return {
            'workspace': str(workspace),
            'results': results
        }

def main():
    """Enhanced main entry point with strategy selection"""
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--strategy', choices=['codemod', 'llm'], default='codemod',
                      help="Refactoring strategy to use")
    
    args = parser.parse_args()
    
    if not args.project_path.exists():
        print(f"Error: Project path does not exist: {args.project_path}")
        sys.exit(1)
        
    try:
        strategy = RefactoringStrategy(args.strategy)
        manager = RefactoringManager(strategy)
        
        intent_id = str(uuid.uuid4())
        result = asyncio.run(manager.process_intent(intent_id, args.project_path, args.intent))
        
        print(f"\nRefactoring completed in workspace: {result['workspace']}")
        print("\nResults:")
        for file_path, file_result in result['results'].items():
            status = "✅" if file_result['status'] == 'success' else "❌"
            print(f"{status} {file_path}")
            if file_result['status'] == 'error':
                print(f"   Error: {file_result['error']}")
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()