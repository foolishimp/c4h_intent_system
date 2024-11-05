# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import autogen
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
            You will:
            1. Review the architectural plan
            2. Apply changes precisely as specified
            3. Maintain code quality and style
            4. Return success/failure status with details"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="coder_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    def _write_changes(self, changes: Dict[str, str]) -> None:
        """Write changes to files with backup"""
        for file_path, content in changes.items():
            try:
                path = Path(file_path)
                # Create backup
                backup_path = path.with_suffix(path.suffix + '.bak')
                if path.exists():
                    path.rename(backup_path)
                
                # Write new content
                path.write_text(content)
                logger.info("coder.file_written", 
                           file=str(path),
                           backup=str(backup_path))
                
            except Exception as e:
                logger.error("coder.write_failed",
                           file=file_path,
                           error=str(e))
                # Restore from backup if exists
                if backup_path.exists():
                    backup_path.rename(path)
                raise

    async def transform(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Transform code according to architectural plan"""
        try:
            plan = context.get("architectural_plan")
            if not plan or "changes" not in plan:
                raise ValueError("Missing required transformation plan")

            changes = plan["changes"]
            
            # Write the changes
            self._write_changes(changes)
            
            return {
                "status": "success",
                "modified_files": list(changes.keys())
            }
            
        except Exception as e:
            logger.error("coder.transform_failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }