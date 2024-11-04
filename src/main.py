# src/main.py


import asyncio
import sys
from pathlib import Path
import os
from typing import Dict, Any, List
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

class TransformationManager:
    """Manages the lifecycle of code transformations"""
    
    def __init__(self):
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        ]
        
        # Initialize agents
        self.discovery_agent = autogen.AssistantAgent(
            name="discovery",
            llm_config={"config_list": self.config_list},
            system_message="""You analyze Python project structure and identify files for modification.
            For each Python file, analyze its contents and structure to determine what changes are needed."""
        )
        
        self.analysis_agent = autogen.AssistantAgent(
            name="analysis",
            llm_config={"config_list": self.config_list},
            system_message="""You analyze code and create detailed transformation plans.
            Focus on specific changes needed in each file."""
        )
        
        self.refactor_agent = autogen.AssistantAgent(
            name="refactor",
            llm_config={"config_list": self.config_list},
            system_message="""You implement code transformations using libcst.
            Generate specific libcst transformer code to modify Python files."""
        )
        
        self.assurance_agent = autogen.AssistantAgent(
            name="assurance",
            llm_config={"config_list": self.config_list},
            system_message="""You validate code changes and ensure correctness.
            Check that modifications maintain code functionality."""
        )
        
        # Human proxy for coordination
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False
            }
        )

    def scan_project(self, project_path: Path) -> Dict[str, Any]:
        """Scan project files and read their contents"""
        python_files = {}
        for file_path in project_path.rglob("*.py"):
            if "__pycache__" not in str(file_path):
                try:
                    with open(file_path, 'r') as f:
                        python_files[str(file_path)] = f.read()
                except Exception as e:
                    logger.error(f"Error reading file {file_path}: {e}")
        return python_files

    def run_discovery(self, project_path: Path) -> Dict[str, Any]:
        """Run project discovery phase"""
        # Scan project files
        project_files = self.scan_project(project_path)
        
        # Create discovery message
        files_content = "\n\n".join([
            f"File: {path}\nContent:\n{content}"
            for path, content in project_files.items()
        ])
        
        chat_response = self.manager.initiate_chat(
            self.discovery_agent,
            message=f"""Analyze these Python files for modification:
            
            {files_content}
            
            Identify which files need changes and what specific modifications are needed.
            """
        )
        
        return {
            "discovery_output": chat_response.last_message(),
            "project_files": project_files
        }

    def run_analysis(self, context: Dict[str, Any], intent: str) -> Dict[str, Any]:
        """Run analysis phase to create transformation plan"""
        chat_response = self.manager.initiate_chat(
            self.analysis_agent,
            message=f"""
            Based on this discovery analysis:
            {context['discovery_output']}
            
            Create a detailed plan to: {intent}
            
            For each file that needs modification, specify:
            1. What changes are needed
            2. Where in the file to make changes
            3. How to implement using libcst
            """
        )
        
        return {"analysis_plan": chat_response.last_message()}

    def apply_transformations(self, file_path: str, source: str) -> str:
        """Apply code transformations using libcst"""
        try:
            context = CodemodContext(filename=file_path)
            transform = LoggingTransform(context, {})
            modified_source = transform.transform_module(source)
            return modified_source
        except Exception as e:
            logger.error(f"Error transforming {file_path}: {e}")
            return source

    def run_refactor(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run code transformation phase"""
        chat_response = self.manager.initiate_chat(
            self.refactor_agent,
            message=f"""
            Implement these code transformations:
            {context['analysis_plan']}
            """
        )
        
        # Apply transformations to files
        modified_files = {}
        for file_path, content in context['project_files'].items():
            modified_content = self.apply_transformations(file_path, content)
            if modified_content != content:
                modified_files[file_path] = modified_content
                # Write changes back to file
                with open(file_path, 'w') as f:
                    f.write(modified_content)
        
        return {"modified_files": modified_files}

    def run_assurance(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run validation phase"""
        files_content = "\n\n".join([
            f"File: {path}\nContent:\n{content}"
            for path, content in context['modified_files'].items()
        ])
        
        chat_response = self.manager.initiate_chat(
            self.assurance_agent,
            message=f"""
            Validate these code changes:
            {files_content}
            
            Check:
            1. Syntax is correct
            2. No functionality is broken
            3. Changes meet the original intent
            """
        )
        
        return {"validation_results": chat_response.last_message()}

def process_intent(intent: Intent) -> Dict[str, Any]:
    """Process a code transformation intent"""
    manager = TransformationManager()
    context: Dict[str, Any] = {}
    
    try:
        # Discovery phase
        intent.status = IntentStatus.ANALYZING
        logger.info("Starting discovery phase", intent_id=str(intent.id))
        context.update(manager.run_discovery(Path(intent.project_path)))
        
        # Analysis phase
        logger.info("Starting analysis phase", intent_id=str(intent.id))
        context.update(manager.run_analysis(context, intent.description))
        
        # Refactoring phase
        intent.status = IntentStatus.TRANSFORMING
        logger.info("Starting refactoring phase", intent_id=str(intent.id))
        context.update(manager.run_refactor(context))
        
        # Validation phase
        intent.status = IntentStatus.VALIDATING
        logger.info("Starting validation phase", intent_id=str(intent.id))
        context.update(manager.run_assurance(context))
        
        intent.status = IntentStatus.COMPLETED
        logger.info("Intent processing completed successfully", intent_id=str(intent.id))
        return {"status": "success", "context": context}
        
    except Exception as e:
        logger.error("Intent processing failed", 
                    intent_id=str(intent.id),
                    error=str(e),
                    exc_info=True)
        intent.status = IntentStatus.FAILED
        intent.error = str(e)
        return {"status": "failed", "error": str(e)}

def main():
    """Main entry point"""
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
    
    result = process_intent(intent)
    print(f"\nRefactoring completed with status: {result['status']}")

if __name__ == "__main__":
    main()