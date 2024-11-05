# src/agents/coder.py

from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from libcst.codemod import CodemodContext
import libcst as cst
import structlog
import autogen
import json
import os

logger = structlog.get_logger()

class Coder:
    """Coder agent responsible for implementing code transformations"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        self.coder = autogen.AssistantAgent(
            name="coder",
            llm_config={"config_list": config_list},
            system_message="""You are an expert coding agent that implements code transformations.
            Given an architectural plan and code:
            1. Implement the required changes
            2. Follow the transformation steps precisely
            3. Maintain code quality and style
            4. Return the modified code"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="coder_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Transform code according to architectural plan"""
        try:
            plan = context.get("architectural_analysis")
            files = context.get("files_to_modify", [])
            
            if not plan or not files:
                raise ValueError("Missing required transformation context")
            
            modified_files = {}
            
            for file_path in files:
                with open(file_path, 'r') as f:
                    source = f.read()
                
                # Get transformation steps for this file
                chat_response = await self.coordinator.a_initiate_chat(
                    self.coder,
                    message=f"""
                    TRANSFORMATION PLAN:
                    {json.dumps(plan, indent=2)}
                    
                    SOURCE FILE ({file_path}):
                    {source}
                    
                    Implement the required changes and return the complete modified code.
                    Return ONLY the modified code without any explanation or markdown.
                    """
                )
                
                # Get modified code
                assistant_messages = [
                    msg['content'] for msg in chat_response.chat_messages
                    if msg.get('role') == 'assistant'
                ]
                modified_code = assistant_messages[-1] if assistant_messages else source
                
                if modified_code != source:
                    modified_files[file_path] = modified_code
                    
                    # Write changes
                    with open(file_path, 'w') as f:
                        f.write(modified_code)
            
            return {"modified_files": modified_files}
            
        except Exception as e:
            logger.error("coder.failed", error=str(e))
            raise
            
# Utility functions
def format_code(file_path: Path) -> None:
    """Format code using ruff"""
    try:
        subprocess.run(['ruff', 'check', '--fix', str(file_path)], check=True)
        subprocess.run(['ruff', 'format', str(file_path)], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error formatting {file_path}: {e}")