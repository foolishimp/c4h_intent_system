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
import uuid
import argparse

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
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
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
        return [f for f in workspace.rglob(pattern) if "__pycache__" not in str(f)]
        
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
        
        # Validate API key
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        # Initialize agents
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        ]

        # Create the function calling configuration
        function_config = {
            "functions": [{
                "name": "process_python_file",
                "description": "Process and modify a Python file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The modified Python code"
                        }
                    },
                    "required": ["code"]
                }
            }],
            "config_list": self.config_list
        }
        
        self.llm_agent = autogen.AssistantAgent(
            name="llm_refactor",
            llm_config=function_config,
            system_message="""You are a Python code refactoring expert. 
            When given Python code and a refactoring task:
            1. Analyze the code structure
            2. Make the requested changes
            3. Return only the complete modified code
            4. Preserve all existing functionality
            5. Follow Python best practices
            6. Do not include any explanations, just the code"""
        )
        
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False,
            }
        )

    async def validate_auth(self) -> bool:
        """Validate using Autogen's built-in mechanisms"""
        try:
            # Initialize a basic chat to test connection
            chat_response = await self.manager.a_initiate_chat(
                self.llm_agent,
                message="Return 'OK' if you can read this message.",
            )
            return any("OK" in str(msg.get("content", "")) 
                      for msg in chat_response.chat_messages 
                      if msg.get("role") == "assistant")
        except Exception as e:
            logger.error(f"Auth validation failed: {e}")
            return False

    async def refactor_file_llm(self, file_path: Path, intent: str) -> Optional[str]:
        """Refactor a file using direct LLM approach"""
        try:
            with open(file_path) as f:
                content = f.read()
                
            message = f"""Refactor this Python code to {intent}. Return only the complete refactored code:

            {content}"""
            
            chat_response = await self.manager.a_initiate_chat(
                self.llm_agent,
                message=message,
            )
            
            # Get the last assistant message
            assistant_messages = [
                msg['content'] for msg in chat_response.chat_messages
                if msg.get('role') == 'assistant'
            ]
            
            if not assistant_messages:
                return None
                
            # Extract code from the last message
            code = self._extract_code(assistant_messages[-1])
            return code if code else None
            
        except Exception as e:
            logger.error(f"Error in refactor_file_llm: {e}")
            return None

    def _extract_code(self, message: str) -> Optional[str]:
        """Extract code from message, handling various formats"""
        try:
            # Try Python code block
            if "```python" in message:
                return message.split("```python")[1].split("```")[0].strip()
            # Try generic code block
            elif "```" in message:
                return message.split("```")[1].strip()
            # No code block, check if it's just code
            elif "import" in message or "def " in message or "class " in message:
                return message.strip()
            return None
        except Exception:
            return None

    async def process_intent(self, intent_id: str, project_path: Path, intent_desc: str) -> Dict[str, Any]:
        """Process a refactoring intent"""
        workspace = self.workspace_manager.create_workspace(intent_id, self.strategy)
        self.workspace_manager.copy_to_workspace(project_path, workspace)
        
        results = {
            'workspace': str(workspace),
            'processed': 0,
            'modified': 0,
            'results': {}
        }
        
        for file_path in self.workspace_manager.get_workspace_files(workspace):
            try:
                modified = await self.refactor_file_llm(file_path, intent_desc)
                
                if modified:
                    # Write modified content
                    with open(file_path, 'w') as f:
                        f.write(modified)
                        
                    results['results'][str(file_path)] = {'status': 'modified'}
                    results['modified'] += 1
                else:
                    results['results'][str(file_path)] = {'status': 'unchanged'}
                    
                results['processed'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to refactor {file_path}: {e}")
                results['results'][str(file_path)] = {
                    'status': 'error',
                    'error': str(e)
                }
                results['processed'] += 1
                
        return results

async def process_intent(project_path: Path, intent: str, strategy: RefactoringStrategy) -> Dict[str, Any]:
    """Main processing function with auth validation"""
    try:
        manager = RefactoringManager(strategy)
        
        print("Validating API access...")
        if not await manager.validate_auth():
            raise ValueError("Failed to authenticate with OpenAI API")
            
        return await manager.process_intent(str(uuid.uuid4()), project_path, intent)
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise ValueError(f"Processing failed: {str(e)}")

def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--strategy', choices=['codemod', 'llm'], default='codemod')
    parser.add_argument('--timeout', type=int, default=30, help="Timeout in seconds per file")
    
    args = parser.parse_args()
    
    if not args.project_path.exists():
        print(f"Error: Project path does not exist: {args.project_path}")
        sys.exit(1)
        
    try:
        strategy = RefactoringStrategy(args.strategy)
        print(f"\nStarting refactoring with {strategy.value} strategy...")
        print(f"Timeout set to {args.timeout} seconds per file")
        
        result = asyncio.run(process_intent(args.project_path, args.intent, strategy))
        
        print(f"\nRefactoring completed in workspace: {result['workspace']}")
        print(f"Files processed: {result['processed']}")
        print(f"Files modified: {result['modified']}")
        print("\nResults:")
        
        for file_path, file_result in result['results'].items():
            status = {
                'modified': '✅',
                'unchanged': '⏩',
                'error': '❌'
            }.get(file_result['status'], '❓')
            
            print(f"{status} {Path(file_path).name}")
            if file_result['status'] == 'error':
                print(f"   Error: {file_result['error']}")
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()