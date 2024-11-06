# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import os
from enum import Enum
import json

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    """Available merge methods"""
    LLM = "llm"      # Use LLM to interpret and apply changes
    CODEMOD = "codemod"  # Use AST-based transformations (not implemented)

class Coder:
    """Coder agent responsible for applying code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        self.merge_assistant = autogen.AssistantAgent(
            name="code_merger",
            llm_config={"config_list": config_list},
            system_message="""You are an expert code merger.
            Given a file's original content and new content:
            1. Verify the new content is valid Python
            2. Return only the final content""")
        
        self.coordinator = autogen.UserProxyAgent(
            name="merger_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _write_file(self, file_path: str, content: str) -> bool:
        """Write content to file with backup"""
        try:
            path = Path(file_path)
            backup_path = path.with_suffix(path.suffix + '.bak')
            
            # Backup if exists
            if path.exists():
                path.rename(backup_path)
            
            # Write new content
            path.write_text(content)
            logger.info("coder.file_written", file=str(path))
            return True
            
        except Exception as e:
            logger.error("coder.write_failed", file=file_path, error=str(e))
            # Try to restore backup
            if backup_path.exists():
                backup_path.rename(path)
            return False

    async def _verify_content(self, file_path: str, content: str) -> Optional[str]:
        """Verify content is valid Python"""
        try:
            chat_response = await self.coordinator.a_initiate_chat(
                self.merge_assistant,
                message=f"""
                Verify this Python code is valid:

                {content}

                If valid, return only the code.
                If invalid, fix any basic syntax issues and return the fixed code.
                """,
                max_turns=1
            )

            # Get last assistant message
            for message in reversed(chat_response.chat_history):
                if message.get('role') == 'assistant':
                    content = message.get('content', '').strip()
                    # If content is wrapped in code blocks, extract it
                    if content.startswith('```') and content.endswith('```'):
                        content = '\n'.join(content.split('\n')[1:-1])
                    return content

            return None

        except Exception as e:
            logger.error("coder.verify_failed", file=file_path, error=str(e))
            return None

    def _extract_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract actions from context, handling various formats"""
        # If actions is directly available
        if "actions" in context:
            return context["actions"]
            
        # If actions is in a nested structure
        if isinstance(context.get("solution"), dict):
            if "actions" in context["solution"]:
                return context["solution"]["actions"]
                
        # If context is a string (e.g. JSON or markdown)
        if isinstance(context, str):
            try:
                parsed = json.loads(context)
                if "actions" in parsed:
                    return parsed["actions"]
            except json.JSONDecodeError:
                pass
                
        raise ValueError("No valid actions found in context")

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Apply code changes"""
        try:
            # Get actions more flexibly
            try:
                actions = self._extract_actions(context)
            except ValueError as e:
                logger.error("coder.no_actions", error=str(e))
                return {
                    "status": "failed",
                    "error": str(e)
                }

            modified_files = []
            failed_files = []
            
            for action in actions:
                file_path = action["file_path"]
                new_content = action["changes"]
                
                # Verify/fix content
                verified_content = await self._verify_content(file_path, new_content)
                
                if not verified_content:
                    failed_files.append(file_path)
                    continue
                    
                # Write result
                if self._write_file(file_path, verified_content):
                    modified_files.append(file_path)
                else:
                    failed_files.append(file_path)

            return {
                "status": "success" if not failed_files else "failed",
                "modified_files": modified_files,
                "failed_files": failed_files
            }
            
        except Exception as e:
            logger.error("coder.transform_failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }