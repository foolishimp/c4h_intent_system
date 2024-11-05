# src/main.py

import asyncio
import sys
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
import autogen
from libcst.codemod import CodemodContext
from models.intent import Intent, IntentStatus
from agents.transformations import (
    LoggingTransform,
    get_transformer,
    format_code,
    run_semgrep_check
)

logger = structlog.get_logger()

class RefactoringStrategy(str, Enum):
    """Available refactoring strategies"""
    CODEMOD = "codemod"  # Uses libcst
    LLM = "llm"          # LLM-based transformations

class ValidationResult:
    """Structured validation result"""
    def __init__(self, status: str, errors: List[Dict[str, Any]] = None):
        self.status = status
        self.errors = errors or []
        
    @property
    def is_success(self) -> bool:
        return self.status == "success" and not self.errors
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "errors": self.errors
        }

class TransformationManager:
    """Manages the lifecycle of code transformations with proper termination control"""
    
    def __init__(self, strategy: RefactoringStrategy = RefactoringStrategy.CODEMOD, max_iterations: int = 3):
        self.strategy = strategy
        self.max_iterations = max_iterations
        
        # Check for API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": api_key,
            }
        ]
        
        # Initialize agents with enhanced system messages
        self.discovery_agent = autogen.AssistantAgent(
            name="discovery",
            llm_config={"config_list": self.config_list},
            system_message="""You are a project analysis agent.
            When given a project structure and intent:
            1. Analyze the files and identify Python files that need modification
            2. Return ONLY a JSON array of file paths to modify
            3. Do not include any explanation or conversation
            Example output: ["path/to/file1.py", "path/to/file2.py"]"""
        )
        
        self.analysis_agent = autogen.AssistantAgent(
            name="analysis",
            llm_config={"config_list": self.config_list},
            system_message="""You analyze code and create detailed transformation plans.
            Focus on specific changes needed in each file.
            Return actions in a structured format with clear validation criteria."""
        )
        
        self.assurance_agent = autogen.AssistantAgent(
            name="assurance",
            llm_config={"config_list": self.config_list},
            system_message="""You validate code changes and ensure correctness.
            Check that modifications maintain code functionality.
            Provide detailed error information for any failures."""
        )
        
        # Human proxy for coordination with termination awareness
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False
            }
        )
        
        # Initialize transformer based on strategy
        self.transformer = get_transformer(str(strategy))

    async def run_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Enhanced discovery phase with structured output"""
        logger.info("Starting discovery phase", intent_id=str(intent.id))
        
        # Run tartxt discovery
        try:
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(intent.project_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get discovery agent analysis
            chat_response = await self.manager.a_initiate_chat(
                self.discovery_agent,
                message=f"""Analyze for: {intent.description}\n\nProject structure:\n{result.stdout}"""
            )
            
            # Get the last assistant message
            assistant_messages = [
                msg['content'] for msg in chat_response.chat_messages
                if msg.get('role') == 'assistant'
            ]
            last_message = assistant_messages[-1] if assistant_messages else ""
            
            return {
                "discovery_output": result.stdout,
                "analysis": last_message,
                "files_to_modify": self._parse_files_to_modify(last_message)
            }
            
        except Exception as e:
            logger.error("Discovery failed", error=str(e))
            raise

    def _parse_files_to_modify(self, agent_response: str) -> List[str]:
        """Parse the discovery agent's response to get files to modify"""
        files = []
        for line in agent_response.split('\n'):
            if line.strip().endswith('.py'):
                files.append(line.strip())
        return files

    async def run_analysis(self, context: Dict[str, Any], intent_description: str) -> Dict[str, Any]:
        """Run analysis phase to create transformation plan"""
        chat_response = await self.manager.a_initiate_chat(
            self.analysis_agent,
            message=f"""
            Based on this discovery analysis:
            {context['discovery_output']}
            
            Create a detailed plan to: {intent_description}
            
            For each file that needs modification, specify:
            1. What changes are needed
            2. Where in the file to make changes
            3. How to implement the changes
            """
        )
        
        # Get the last assistant message
        assistant_messages = [
            msg['content'] for msg in chat_response.chat_messages
            if msg.get('role') == 'assistant'
        ]
        last_message = assistant_messages[-1] if assistant_messages else ""
        
        return {"analysis_plan": last_message}

    async def run_refactor(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run code transformation phase using selected strategy"""
        modified_files = {}
        
        for file_path in context.get('files_to_modify', []):
            try:
                with open(file_path, 'r') as f:
                    source = f.read()
                
                if isinstance(self.transformer, LoggingTransform):
                    # Use codemod approach
                    transform_context = CodemodContext(filename=file_path)
                    transform = self.transformer(transform_context, {})
                    modified_source = transform.transform_module(source)
                else:
                    # Use LLM approach
                    modified_source = await self.transformer.transform_code(source)
                
                if modified_source and modified_source != source:
                    modified_files[file_path] = modified_source
                    # Write changes back to file
                    with open(file_path, 'w') as f:
                        f.write(modified_source)
                    
                    # Format the modified code
                    format_code(Path(file_path))
                    
            except Exception as e:
                logger.error(f"Error transforming {file_path}: {e}")
                continue
        
        return {"modified_files": modified_files}

    async def run_validation(self, changes: Dict[str, Any]) -> ValidationResult:
        """Enhanced validation with structured results"""
        try:
            # Compile check
            compile_errors = []
            for file_path in changes['modified_files']:
                try:
                    if file_path.endswith('.py'):
                        with open(file_path, 'rb') as f:
                            compile(f.read(), file_path, 'exec')
                except Exception as e:
                    compile_errors.append({
                        'file': file_path,
                        'type': 'compilation',
                        'message': str(e)
                    })
            
            if compile_errors:
                return ValidationResult("failed", compile_errors)
            
            # Run semgrep checks if available
            semgrep_result = run_semgrep_check(
                [Path(f) for f in changes['modified_files']],
                {"python": True}  # Basic Python checks
            )
            
            if semgrep_result.get('errors', []):
                return ValidationResult("failed", [
                    {'type': 'semgrep', 'message': err}
                    for err in semgrep_result['errors']
                ])
            
            # Run tests if available
            test_result = await self._run_tests()
            if not test_result.get('success', False):
                return ValidationResult("failed", [
                    {'type': 'test', 'message': err} 
                    for err in test_result.get('errors', [])
                ])
            
            return ValidationResult("success")
            
        except Exception as e:
            return ValidationResult("error", [{'type': 'system', 'message': str(e)}])

    async def _run_tests(self) -> Dict[str, Any]:
        """Run available tests for the project"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/"],
                capture_output=True,
                text=True
            )
            return {
                "success": result.returncode == 0,
                "errors": result.stderr.split('\n') if result.returncode != 0 else []
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "errors": [str(e)]
            }

    async def create_sub_intent(self, parent_intent: Intent, validation_result: ValidationResult) -> Intent:
        """Create a sub-intent from validation failures"""
        error_descriptions = [f"Fix: {error['message']}" for error in validation_result.errors]
        description = f"Fix validation errors:\n" + "\n".join(error_descriptions)
        
        return Intent(
            description=description,
            project_path=parent_intent.project_path,
            parent_id=parent_intent.id,
            status=IntentStatus.CREATED
        )

    async def process_intent(self, intent: Intent) -> Dict[str, Any]:
        """Process intent with termination control and feedback loop"""
        context: Dict[str, Any] = {}
        iteration_count = 0
        
        try:
            # Initial discovery and analysis
            intent.status = IntentStatus.ANALYZING
            context.update(await self.run_discovery(intent))
            context.update(await self.run_analysis(context, intent.description))
            
            while iteration_count < self.max_iterations:
                iteration_count += 1
                logger.info(f"Starting iteration {iteration_count}", intent_id=str(intent.id))
                
                # Apply transformations
                intent.status = IntentStatus.TRANSFORMING
                changes = await self.run_refactor(context)
                context['changes'] = changes
                
                # Validate changes
                intent.status = IntentStatus.VALIDATING
                validation_result = await self.run_validation(changes)
                
                if validation_result.is_success:
                    intent.status = IntentStatus.COMPLETED
                    return {
                        "status": "success",
                        "context": context,
                        "iterations": iteration_count
                    }
                
                # Create and process sub-intent for fixes
                sub_intent = await self.create_sub_intent(intent, validation_result)
                context.update(await self.run_discovery(sub_intent))
                
            # Max iterations reached
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": f"Max iterations ({self.max_iterations}) reached without success",
                "context": context
            }
            
        except Exception as e:
            logger.error("Intent processing failed", 
                        intent_id=str(intent.id),
                        error=str(e),
                        exc_info=True)
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": str(e),
                "context": context
            }

async def process_intent(project_path: Path, intent_desc: str, strategy: RefactoringStrategy) -> Dict[str, Any]:
    """Main entry point for intent processing"""
    intent = Intent(
        description=intent_desc,
        project_path=str(project_path)
    )
    manager = TransformationManager(strategy=strategy)
    return await manager.process_intent(intent)

def main():
    """Enhanced main entry point with strategy selection"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--strategy', choices=['codemod', 'llm'], default='codemod',
                      help="Refactoring strategy to use")
    parser.add_argument('--max-iterations', type=int, default=3,
                      help="Maximum number of refactoring iterations")
    
    args = parser.parse_args()
    
    if not args.project_path.exists():
        print(f"Error: Project path does not exist: {args.project_path}")
        sys.exit(1)
        
    try:
        strategy = RefactoringStrategy(args.strategy)
        print(f"\nStarting refactoring with {strategy.value} strategy...")
        print(f"Max iterations: {args.max_iterations}")
        
        result = asyncio.run(process_intent(args.project_path, args.intent, strategy))
        
        print(f"\nRefactoring completed with status: {result['status']}")
        if result['status'] == 'success':
            print(f"Completed in {result.get('iterations', 1)} iterations")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()