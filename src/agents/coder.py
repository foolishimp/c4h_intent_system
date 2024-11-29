"""
Code modification agent using semantic tools.
Path: src/agents/coder.py
"""

from pathlib import Path
import structlog
import shutil
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from .base import BaseAgent, LLMProvider, AgentResponse
from src.skills.semantic_iterator import SemanticIterator
from src.skills.semantic_merge import SemanticMerge, MergeConfig
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    """Available merge strategies"""
    INLINE = "inline"
    SMART = "smart"

@dataclass
class ChangeResult:
    """Result of a single file change"""
    file_path: str
    success: bool
    backup_path: Optional[str] = None
    error: Optional[str] = None

@dataclass
class CoderConfig:
    """Configuration for code changes"""
    merge_method: MergeMethod = MergeMethod.SMART
    create_backups: bool = True
    backup_suffix: str = '.bak'
    validate_changes: bool = True

class Coder(BaseAgent):
    """Agent responsible for safely applying code changes"""
    
    def __init__(self,
                 provider: LLMProvider,
                 model: Optional[str] = None,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None,
                 coder_config: Optional[CoderConfig] = None):
        """Initialize coder with semantic tools"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.coder_config = coder_config or CoderConfig()
        
        # Initialize semantic tools with same configuration
        self.iterator = SemanticIterator(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.merger = SemanticMerge(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config,
            merge_config=MergeConfig(
                style=self.coder_config.merge_method.value,
                preserve_formatting=True
            )
        )
        
        logger.info("coder.initialized",
                   merge_method=self.coder_config.merge_method.value,
                   create_backups=self.coder_config.create_backups)

    def _get_agent_name(self) -> str:
        return "coder"

    async def _apply_change(self, change: Dict[str, Any]) -> ChangeResult:
        """Apply a single code change with safety checks"""
        file_path = Path(change.get('file_path', ''))
        
        try:
            # Validate file path
            if not file_path.suffix:
                return ChangeResult(
                    file_path=str(file_path),
                    success=False,
                    error="Invalid file path - no extension"
                )
            
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle backup if needed
            backup_path = None
            if self.coder_config.create_backups and file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + self.coder_config.backup_suffix)
                shutil.copy2(file_path, backup_path)
                logger.info("change.backup_created",
                          original=str(file_path),
                          backup=str(backup_path))
            
            try:
                # Get original content or empty string for new files
                original_content = file_path.read_text() if file_path.exists() else ""
                
                # Get change content from either content or diff field
                change_content = change.get('content') or change.get('diff', '')
                if not change_content:
                    return ChangeResult(
                        file_path=str(file_path),
                        success=False,
                        error="No content or diff provided for change"
                    )
                
                # Apply merge
                merge_result = await self.merger.merge(original_content, change_content)
                
                if not merge_result.success:
                    if backup_path:
                        shutil.copy2(backup_path, file_path)
                    return ChangeResult(
                        file_path=str(file_path),
                        success=False,
                        backup_path=str(backup_path) if backup_path else None,
                        error=f"Merge failed: {merge_result.error}"
                    )
                
                # Write merged content
                file_path.write_text(merge_result.content)
                return ChangeResult(
                    file_path=str(file_path),
                    success=True,
                    backup_path=str(backup_path) if backup_path else None
                )
                    
            except Exception as e:
                # Restore backup on error if exists
                if backup_path:
                    shutil.copy2(backup_path, file_path)
                return ChangeResult(
                    file_path=str(file_path),
                    success=False,
                    backup_path=str(backup_path) if backup_path else None,
                    error=f"Change failed: {str(e)}"
                )
                
        except Exception as e:
            logger.error("change.failed", error=str(e))
            return ChangeResult(
                file_path=str(file_path),
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process code changes using iterator pattern"""
        try:
            changes_input = context.get('changes', [])
            if not changes_input:
                return AgentResponse(
                    success=False,
                    data={},
                    error="No changes provided"
                )

            # Configure extraction
            extract_config = ExtractConfig(
                instruction="Extract each code change with file_path, type, and content/diff fields",
                format="json"
            )

            results = []
            
            # Use iterator to process changes
            async for change in await self.iterator.iter_extract(changes_input, extract_config):
                if not isinstance(change, dict):
                    logger.warning("change.invalid_format", change=change)
                    continue
                    
                result = await self._apply_change(change)
                results.append({
                    "file": result.file_path,
                    "success": result.success,
                    "backup_path": result.backup_path,
                    "error": result.error
                })

            # Overall success if any changes succeeded
            success = any(r["success"] for r in results)
            return AgentResponse(
                success=success,
                data={"changes": results},
                error=None if success else "All changes failed"
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def _create_extract_config(self) -> ExtractConfig:
        """Create extraction configuration for iterator"""
        return ExtractConfig(
            instruction="""
            Extract code changes from the input.
            Each change should have:
            - file_path: Path to the file to modify
            - type: Type of change (create/modify/delete)
            - content: New content for the file
            - diff: Optional git-style diff (alternative to content)
            
            Return each change as a JSON object.
            """,
            format="json"
        )