"""
Asset management with LLM-powered merging.
Path: src/skills/asset_manager.py
"""

from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import structlog
import shutil
from datetime import datetime
from skills.semantic_merge import SemanticMerge, MergeConfig
from agents.base import LLMProvider, AgentResponse

logger = structlog.get_logger()

@dataclass
class AssetResult:
    """Result of an asset operation"""
    success: bool
    path: Path
    backup_path: Optional[Path] = None
    error: Optional[str] = None

class AssetManager:
    """Manages asset operations with internal semantic merging"""
    
    def __init__(self, 
                 backup_enabled: bool = True,
                 backup_dir: Optional[Path] = None,
                 merger: Optional[SemanticMerge] = None,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize asset manager with configuration"""
        self.backup_enabled = backup_enabled
        self.backup_dir = backup_dir
        self.config = config or {}
        
        if backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
        # Use provided merger or create new one
        self.merger = merger or SemanticMerge(
            provider=LLMProvider(self.config.get('provider', 'anthropic')),
            model=self.config.get('model', 'claude-3-opus-20240229'),
            temperature=0,
            config=self.config,
            merge_config=MergeConfig(
                style='smart',
                preserve_formatting=True
            )
        )

    def _get_next_backup_path(self, path: Path) -> Path:
        """Generate unique backup path with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.backup_dir:
            return self.backup_dir / f"{path.name}_{timestamp}"
        return path.with_suffix(f".{timestamp}.bak")

    def _ensure_path_exists(self, path: Path) -> None:
        """Ensure the file's parent directory exists and create empty file if needed"""
        try:
            # Create all parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create empty file if it doesn't exist
            if not path.exists():
                path.touch()
                logger.info("asset.created_empty_file", path=str(path))
                
        except Exception as e:
            logger.error("asset.path_creation_failed", path=str(path), error=str(e))
            raise

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process an asset action - trust input without validation"""
        try:
            logger.debug("asset_manager.process_input", 
                        context_keys=list(context.keys()),
                        input_data=context.get('input_data'))
            
            result = self.process_action(context.get('input_data', {}))
            return AgentResponse(
                success=result.success,
                data={
                    "path": str(result.path),
                    "backup_path": str(result.backup_path) if result.backup_path else None,
                    "raw_output": context.get('raw_output', '')
                },
                error=result.error
            )
        except Exception as e:
            logger.error("asset_manager.process_failed", 
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=e.__traceback__)
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def process_action(self, action: Dict[str, Any]) -> AssetResult:
        """Process a single asset action"""
        try:
            logger.debug("asset_manager.action_received",
                        action=action,
                        action_type=type(action).__name__)
            
            file_path = action.get('file_path', '')
            logger.debug("asset_manager.file_path",
                        raw_path=file_path,
                        path_type=type(file_path).__name__)
            
            path = Path(file_path)
            logger.debug("asset_manager.path_details",
                        path_str=str(path),
                        absolute_path=str(path.absolute()),
                        exists=path.exists(),
                        is_file=path.is_file() if path.exists() else None,
                        is_dir=path.is_dir() if path.exists() else None)

            # Create backup if enabled and file exists
            backup_path = None
            if self.backup_enabled and path.exists():
                backup_path = self._get_next_backup_path(path)
                shutil.copy2(path, backup_path)
                logger.info("asset.backup_created", path=str(backup_path))

            # Ensure path exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            content = action.get('content', '')
            
            # For new files or empty files, write directly
            if not path.exists():
                logger.info("asset.creating_new_file", path=str(path))
                path.write_text(content)
                return AssetResult(success=True, path=path, backup_path=backup_path)
                
            # For existing files, use merger
            result = self.merger.process({
                'original_code': path.read_text() if path.exists() else '',
                'changes': content,
                'style': 'smart'
            })
            
            if not result:
                logger.error("asset.merge_failed", path=str(path))
                return AssetResult(
                    success=False,
                    path=path,
                    error="Merge operation failed"
                )

            # Write result
            if result.success:
                path.write_text(result.data.get('response', content))
                logger.info("asset.write_success", path=str(path))
                return AssetResult(success=True, path=path, backup_path=backup_path)
            else:
                logger.error("asset.merge_error", error=result.error)
                return AssetResult(
                    success=False,
                    path=path,
                    error=result.error or "Merge failed"
                )

        except Exception as e:
            logger.error("asset_manager.action_failed", 
                        error=str(e),
                        path=str(path) if 'path' in locals() else None)
            return AssetResult(
                success=False,
                path=path if 'path' in locals() else Path('.'),
                error=str(e)
            )