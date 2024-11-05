# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
import os
import difflib
from enum import Enum
from skills.codemod import CodeTransformation, apply_transformation

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    """Available merge methods"""
    LLM = "llm"      # Use LLM for merging changes
    CODEMOD = "codemod"  # Use AST-based codemod transformations

class Coder:
    """Coder agent responsible for merging and applying code changes"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        self.merger = autogen.AssistantAgent(
            name="code_merger",
            llm_config={"config_list": config_list},
            system_message="""You are an expert code merger.
            Given original content and changes in diff format:
            1. Apply the changes precisely
            2. Resolve any conflicts
            3. Maintain file format and style
            Return only the final merged content."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="merger_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def _merge_llm(self, file_path: str, original: str, diff: str) -> Optional[str]:
        """Use LLM to merge changes from diff"""
        try:
            chat_response = await self.coordinator.a_initiate_chat(
                self.merger,
                message=f"""
                File: {file_path}

                ORIGINAL CONTENT:
                {original}

                CHANGES TO APPLY (DIFF):
                {diff}

                Apply these changes to the original content.
                Return ONLY the merged result without any explanation."""
            )

            # Get merged content from response
            for message in chat_response.chat_history:
                if message.get('role') == 'assistant':
                    return message['content'].strip()

            return None

        except Exception as e:
            logger.error("coder.llm_merge_failed", error=str(e))
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
            logger.error("coder.codemod_failed", error=str(e))
            return None

    def _write_file_with_backup(self, file_path: str, content: str) -> bool:
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

    async def transform(self, context: Dict[str, Any], method: MergeMethod = MergeMethod.LLM) -> Dict[str, Any]:
        """Apply refactoring actions using specified merge method"""
        try:
            actions = context.get("refactor_actions", [])
            if not actions:
                raise ValueError("No refactoring actions provided")

            modified_files = []
            failed_files = []
            
            for action in actions:
                file_path = action["file_path"]
                changes = action["changes"]
                description = action.get("description", "")
                
                # Read original content if file exists
                path = Path(file_path)
                if path.exists():
                    original_content = path.read_text()
                    
                    # Apply changes using specified method
                    logger.info(f"coder.applying_changes", 
                              file=file_path, 
                              method=method.value)
                    
                    if method == MergeMethod.LLM:
                        merged_content = await self._merge_llm(file_path, original_content, changes)
                    else:  # CODEMOD
                        merged_content = self._merge_codemod(file_path, {
                            "diff": changes,
                            "line_range": action.get("line_range"),
                            "description": description
                        })
                    
                    if not merged_content:
                        failed_files.append(file_path)
                        logger.error("coder.merge_failed", 
                                   file=file_path, 
                                   method=method.value)
                        continue
                else:
                    # For new files, extract content from diff
                    merged_content = changes.split('\n')[1:]  # Skip diff header
                    merged_content = '\n'.join(line[1:] for line in merged_content if line.startswith('+'))

                # Write merged content
                if self._write_file_with_backup(file_path, merged_content):
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