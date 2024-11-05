# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import os

logger = structlog.get_logger()

class Coder:
    """Coder agent responsible for applying merge actions using LLM"""
    
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
            Given a file's original content and changes in unified diff format:
            1. Apply the changes precisely
            2. Return only the final merged content"""
        )
        
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

    async def _merge_llm(self, file_path: str, original: str, changes: str) -> Optional[str]:
        """Use LLM to merge changes into original content"""
        try:
            chat_response = await self.coordinator.a_initiate_chat(
                self.merge_assistant,
                message=f"""
                Apply these changes to the code:

                ORIGINAL FILE ({file_path}):
                {original}

                CHANGES (UNIFIED DIFF):
                {changes}

                Return only the complete merged file content.
                """,
                max_turns=1
            )

            # Get last assistant message
            for message in reversed(chat_response.chat_history):
                if message.get('role') == 'assistant':
                    return message['content'].strip()

            return None

        except Exception as e:
            logger.error("coder.llm_merge_failed", file=file_path, error=str(e))
            return None

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Apply merge actions"""
        try:
            # Just grab the actions and process them
            actions = context.get("actions", [])
            if not actions:
                raise ValueError("No actions provided")

            modified_files = []
            failed_files = []
            
            for action in actions:
                file_path = action["file_path"]
                changes = action["changes"]
                path = Path(file_path)
                
                # Get original content or empty string for new files
                original_content = path.read_text() if path.exists() else ""
                
                # Use LLM to merge
                merged_content = await self._merge_llm(file_path, original_content, changes)
                
                if not merged_content:
                    failed_files.append(file_path)
                    continue
                    
                # Write result
                if self._write_file(file_path, merged_content):
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