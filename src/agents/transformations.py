# src/main.py

import asyncio
import sys
from pathlib import Path
import os
from typing import Dict, Any, List
import structlog
import autogen
import subprocess
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

    def run_tartxt(self, project_path: Path) -> str:
        """Run tartxt discovery"""
        try:
            tartxt_path = Path(__file__).parent / "skills" / "tartxt.py"
            if not tartxt_path.exists():
                tartxt_path = Path("src/skills/tartxt.py")
            
            result = subprocess.run(
                [
                    sys.executable,
                    str(tartxt_path),
                    "-o",  # Output to stdout
                    "--exclude", "*.pyc,__pycache__,*.DS_Store",
                    str(project_path)
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error("tartxt.failed", error=str(e), stderr=e.stderr)
            raise

    def run_discovery(self, project_path: Path) -> Dict[str, Any]:
        """Run project discovery phase"""
        # Use tartxt to scan project
        discovery_output = self.run_tartxt(project_path)
        
        # Pass discovery output to agent for analysis
        chat_response = self.manager.initiate_chat(
            self.discovery_agent,
            message=f"""Analyze this project structure for adding logging to all functions:
            
            {discovery_output}
            
            Identify which Python files need modifications and which functions within them
            should have logging added.
            """
        )
        
        return {
            "discovery_output": discovery_output,
            "analysis": chat_response.last_message()
        }

    def run_analysis(self, context: Dict[str, Any], intent: str) -> Dict[str, Any]:
        """Run analysis phase to create transformation plan"""
        chat_response = self.manager.initiate_chat(
            self.analysis_agent,
            message=f"""
            Based on this discovery analysis:
            {context['discovery_output']}
            
            And the intent: {intent}
            
            Create a detailed plan specifying:
            1. Which files to modify
            2. What specific changes to make in each file
            3. How to implement the changes using libcst
            4. Any potential risks or considerations
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
        
        # Extract Python files from tartxt output
        python_files = {}
        current_file = None
        for line in context['discovery_output'].split('\n'):
            if line.startswith("File: ") and line.endswith(".py"):
                current_file = line.split("File: ")[1]
            elif line == "Contents:" and current_file:
                python_files[current_file] = ""
            elif current_file and python_files.get(current_file) is not None:
                python_files[current_file] += line + "\n"
        
        # Apply transformations to files
        modified_files = {}
        for file_path, content in python_files.items():
            modified_content = self.apply_transformations(file_path, content)
            if modified_content != content:
                modified_files[file_path] = modified_content
                # Write changes back to file
                with open(file_path, 'w') as f:
                    f.write(modified_content)
                # Format the modified file
                format_code(Path(file_path))
        
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

# ... rest of the file (process_intent and main functions) remains the same ...