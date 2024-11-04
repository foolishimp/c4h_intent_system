# src/main.py

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
import autogen
from libcst.codemod import CodemodContext
from models.intent import Intent, IntentStatus
from agents.transformations import (
    LoggingTransform, 
    format_code,
    run_semgrep_check
)

logger = structlog.get_logger()

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
    
    def __init__(self, max_iterations: int = 3):
        self.max_iterations = max_iterations
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        ]
        
        # Initialize agents with enhanced system messages
        self.discovery_agent = autogen.AssistantAgent(
            name="discovery",
            llm_config={"config_list": self.config_list},
            system_message="""You analyze Python project structure and identify files for modification.
            For each Python file, analyze its contents and structure to determine what changes are needed.
            Provide output in a structured format for the next stage."""
        )
        
        self.analysis_agent = autogen.AssistantAgent(
            name="analysis",
            llm_config={"config_list": self.config_list},
            system_message="""You analyze code and create detailed transformation plans.
            Focus on specific changes needed in each file.
            Return actions in a structured format with clear validation criteria."""
        )
        
        self.refactor_agent = autogen.AssistantAgent(
            name="refactor",
            llm_config={"config_list": self.config_list},
            system_message="""You implement code transformations using libcst.
            Generate specific libcst transformer code to modify Python files.
            Ensure all changes are tracked for validation."""
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
            
            return {
                "discovery_output": result.stdout,
                "analysis": chat_response.last_message(),
                "files_to_modify": self._parse_files_to_modify(chat_response.last_message())
            }
            
        except Exception as e:
            logger.error("Discovery failed", error=str(e))
            raise

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

async def process_intent(intent: Intent) -> Dict[str, Any]:
    """Main entry point for intent processing"""
    manager = TransformationManager()
    return await manager.process_intent(intent)

def main():
    """Enhanced main entry point with proper error handling"""
    if len(sys.argv) != 4:
        print("Usage: python main.py refactor <project_path> '<intent description>'")
        sys.exit(1)
        
    command = sys.argv[1]
    if command != "refactor":
        print("Only 'refactor' command is supported")
        sys.exit(1)
        
    project_path = Path(sys.argv[2]).resolve()
    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)
        
    intent = Intent(
        description=sys.argv[3],
        project_path=str(project_path)
    )
    
    try:
        result = asyncio.run(process_intent(intent))
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