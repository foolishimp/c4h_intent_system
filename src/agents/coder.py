# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import difflib
from enum import Enum
import os

from skills.codemod import CodeTransformation, apply_transformation

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    """Available merge methods"""
    LLM = "llm"      # Use LLM to interpret and apply changes
    CODEMOD = "codemod"  # Use AST-based transformations

class Coder:
    """Coder agent responsible for merging and applying code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4o", "api_key": api_key}]
        
        # Initialize merge assistant for LLM-based merges
        self.merge_assistant = autogen.AssistantAgent(
            name="code_merger",
            llm_config={"config_list": config_list},
            system_message="""You are an expert code merger.
            Given a file's original content and changes in unified diff format:
            1. Apply the changes precisely
            2. Resolve any conflicts
            3. Maintain code style and formatting
            4. Return only the final merged content
            
            Do not include any explanation or commentary in your response,
            only return the complete merged code."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="merger_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _write_with_backup(self, file_path: str, content: str) -> bool:
        """Write content to file with backup of original"""
        try:
            path = Path(file_path)
            backup_path = path.with_suffix(path.suffix + '.bak')
            
            # Create backup if file exists
            if path.exists():
                path.rename(backup_path)
                logger.info("coder.backup_created", 
                          file=str(path),
                          backup=str(backup_path))
            
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write new content
            path.write_text(content)
            logger.info("coder.file_written", file=str(path))
            
            return True
            
        except Exception as e:
            logger.error("coder.write_failed",
                       file=file_path,
                       error=str(e))
            # Attempt recovery
            if backup_path.exists():
                backup_path.rename(path)
                logger.info("coder.backup_restored", file=str(path))
            return False

    async def _merge_llm(self, file_path: str, original: str, changes: str) -> Optional[str]:
        """Use LLM to merge changes into original content"""
        try:
            chat_response = await self.coordinator.a_initiate_chat(
                self.merge_assistant,
                message=f"""
                Apply the following changes to the code:

                ORIGINAL FILE ({file_path}):
                {original}

                CHANGES (UNIFIED DIFF):
                {changes}

                Return the complete merged file content.
                """
            )

            # Get merged content from response
            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    return message['content'].strip()

            return None

        except Exception as e:
            logger.error("coder.llm_merge_failed", 
                        file=file_path,
                        error=str(e))
            return None

    def _merge_codemod(self, file_path: str, changes: Dict[str, Any]) -> Optional[str]:
        """Use codemod to apply changes via AST transformations"""
        try:
            transform = CodeTransformation(
                source_file=file_path,
                changes=changes
            )
            
            return apply_transformation(transform)

        except Exception as e:
            logger.error("coder.codemod_failed", 
                        file=file_path,
                        error=str(e))
            return None

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Apply refactoring actions using specified merge method"""
        try:
            # Extract merge strategy from intent context
            intent_description = context.get("intent_description", {})
            merge_strategy = (
                intent_description.get("merge_strategy", "codemod") 
                if isinstance(intent_description, dict) 
                else "codemod"
            )
            method = MergeMethod(merge_strategy)
            
            actions = context.get("refactor_actions", [])
            if not actions:
                raise ValueError("No refactoring actions provided")

            modified_files = []
            failed_files = []
            
            for action in actions:
                file_path = action["file_path"]
                changes = action["changes"]  # Expected in unified diff format
                description = action.get("description", "")
                
                # Read original content if file exists
                path = Path(file_path)
                if path.exists():
                    original_content = path.read_text()
                    
                    # Apply changes using specified method
                    logger.info("coder.applying_changes", 
                              file=file_path, 
                              method=method.value)
                    
                    if method == MergeMethod.LLM:
                        merged_content = await self._merge_llm(
                            file_path,
                            original_content,
                            changes
                        )
                    else:  # CODEMOD
                        merged_content = self._merge_codemod(
                            file_path,
                            {
                                "diff": changes,
                                "description": description
                            }
                        )
                    
                    if not merged_content:
                        failed_files.append(file_path)
                        logger.error("coder.merge_failed", 
                                   file=file_path, 
                                   method=method.value)
                        continue
                else:
                    # For new files, extract content from diff
                    if not changes.startswith("--- "):
                        logger.error("coder.invalid_diff", file=file_path)
                        failed_files.append(file_path)
                        continue
                        
                    # Parse new content from unified diff
                    diff_lines = changes.split('\n')
                    merged_content = '\n'.join(
                        line[1:] for line in diff_lines 
                        if line.startswith('+') and not line.startswith('+++')
                    )

                # Write merged content
                if self._write_with_backup(file_path, merged_content):
                    modified_files.append(file_path)
                    logger.info("coder.changes_applied", 
                              file=file_path, 
                              method=method.value,
                              description=description)
                else:
                    failed_files.append(file_path)

            if failed_files:
                return {
                    "status": "failed",
                    "error": f"Failed to modify files: {', '.join(failed_files)}",
                    "modified_files": modified_files,
                    "failed_files": failed_files
                }
                
            return {
                "status": "success",
                "modified_files": modified_files,
                "method_used": method.value
            }
            
        except Exception as e:
            logger.error("coder.transform_failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }