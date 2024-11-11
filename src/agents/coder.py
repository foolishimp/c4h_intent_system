# src/agents/coder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
from enum import Enum
import shutil
import re

from .base import BaseAgent, LLMProvider, AgentResponse
from ..skills.semantic_extract import SemanticExtract

logger = structlog.get_logger()

class MergeStrategy(str, Enum):
    """Available merge strategies"""
    INLINE = "inline"    # Direct file replacement
    GITDIFF = "gitdiff"  # Apply changes as git-style diff
    PATCH = "patch"      # Use patch format

class Coder(BaseAgent):
    """Code modification agent using semantic extraction"""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        """Initialize coder with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )
        # Initialize semantic tools
        self.extractor = SemanticExtract(provider=provider, model=model)
        
    def _get_agent_name(self) -> str:
        return "coder"
        
    def _get_system_message(self) -> str:
        return """You are an expert code modification agent.
        When given code changes to implement:
        1. Analyze the change request carefully
        2. Identify exact files to modify
        3. Apply changes precisely
        4. Maintain code style and functionality
        5. Return results in the specified format
        """
    
    async def _extract_change_details(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Extract file path and change details using semantic extract"""
        result = await self.extractor.extract(
            content=content,
            prompt="""Extract these details from the change request:
            1. Target file path
            2. Change type (create/modify/delete)
            3. Complete change content or diff
            Return as JSON with fields: file_path, change_type, content""",
            format_hint="json"
        )
        
        if not result.success:
            raise ValueError(f"Failed to extract change details: {result.error}")
            
        return result.value

    def _create_backup(self, file_path: Path) -> Path:
        """Create numbered backup of existing file"""
        if not file_path.exists():
            return None
            
        # Find next available backup number
        backup_pattern = re.compile(rf"{file_path}\.bak_(\d+)$")
        existing_backups = [
            int(match.group(1))
            for match in (backup_pattern.match(str(p)) for p in file_path.parent.glob(f"{file_path.name}.bak_*"))
            if match
        ]
        
        next_num = max(existing_backups, default=-1) + 1
        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak_{next_num:03d}")
        
        # Create backup
        shutil.copy2(file_path, backup_path)
        logger.info("coder.backup_created", 
                   original=str(file_path),
                   backup=str(backup_path))
        
        return backup_path

    async def _merge_changes(self, file_path: Path, changes: Dict[str, Any],
                           strategy: MergeStrategy) -> str:
        """Merge changes into file using specified strategy"""
        # Import semantic merge skill
        from ..skills.semantic_merge import SemanticMerge
        
        merger = SemanticMerge(
            provider=self.provider,
            model=self.model
        )
        
        if file_path.exists():
            original_content = file_path.read_text()
        else:
            original_content = ""
            
        result = await merger.merge(
            original=original_content,
            changes=changes,
            strategy=strategy
        )
        
        if not result.success:
            raise ValueError(f"Merge failed: {result.error}")
            
        return result.content

    async def apply_changes(self, change_request: Dict[str, Any], 
                          strategy: MergeStrategy = MergeStrategy.INLINE) -> Dict[str, Any]:
        """Apply code changes with backup and validation"""
        try:
            # Extract change details
            details = await self._extract_change_details(change_request)
            file_path = Path(details["file_path"])
            
            # Create backup if file exists
            backup_path = self._create_backup(file_path)
            
            try:
                # Merge changes
                merged_content = await self._merge_changes(
                    file_path=file_path,
                    changes=details,
                    strategy=strategy
                )
                
                # Write merged content
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(merged_content)
                
                return {
                    "status": "success",
                    "file_path": str(file_path),
                    "backup_path": str(backup_path) if backup_path else None,
                    "change_type": details["change_type"]
                }
                
            except Exception as e:
                # Restore from backup on error
                if backup_path and backup_path.exists():
                    shutil.copy2(backup_path, file_path)
                raise
                
        except Exception as e:
            logger.error("coder.apply_changes_failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }