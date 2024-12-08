"""
Asset management with file system operations and backup management.
Path: src/skills/asset_manager.py
"""

from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import structlog
import shutil
from datetime import datetime
from skills.semantic_merge import SemanticMerge
from agents.base import AgentResponse

logger = structlog.get_logger()

@dataclass
class AssetResult:
    """Result of an asset operation"""
    success: bool
    path: Path
    backup_path: Optional[Path] = None
    error: Optional[str] = None

class AssetManager:
    """Manages asset operations with file system handling"""
    
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
            
        # Create semantic merger with config
        self.merger = merger or SemanticMerge(config=self.config)

        logger.info("asset_manager.initialized",
                   backup_enabled=backup_enabled,
                   backup_dir=str(backup_dir) if backup_dir else None)

    def _get_next_backup_path(self, path: Path) -> Path:
        """Generate unique backup path with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.backup_dir:
            return self.backup_dir / f"{path.name}_{timestamp}"
        return path.with_suffix(f".{timestamp}.bak")

    def process_action(self, action: Dict[str, Any]) -> AssetResult:
        """Process a single asset action"""
        try:
            # Extract file path
            file_path = action.get('file_path')
            if not file_path:
                raise ValueError("No file path provided in action")
            
            path = Path(file_path)
            logger.debug("asset.processing", path=str(path))
            
            # Create backup if enabled and file exists
            backup_path = None
            if self.backup_enabled and path.exists():
                backup_path = self._get_next_backup_path(path)
                shutil.copy2(path, backup_path)
                logger.info("asset.backup_created", path=str(backup_path))

            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get content from action
            content = action.get('content', '')
            
            # For new files, write directly
            if not path.exists():
                logger.info("asset.creating_new_file", path=str(path))
                path.write_text(content)
                return AssetResult(success=True, path=path, backup_path=backup_path)
                
            # For existing files, use merger
            merge_result = self.merger.process({
                'original_code': path.read_text(),
                'changes': content
            })
            
            if not merge_result.success:
                logger.error("asset.merge_failed", 
                           path=str(path),
                           error=merge_result.error)
                return AssetResult(
                    success=False,
                    path=path,
                    error=merge_result.error
                )

            # Write merged result
            path.write_text(merge_result.data.get('response', ''))
            logger.info("asset.write_success", path=str(path))
            
            return AssetResult(success=True, path=path, backup_path=backup_path)

        except Exception as e:
            logger.error("asset.action_failed", 
                        error=str(e),
                        path=str(path) if 'path' in locals() else None)
            return AssetResult(
                success=False,
                path=Path(action.get('file_path', '.')),
                error=str(e)
            )

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process asset operations with standard agent interface"""
        try:
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
            logger.error("asset_manager.process_failed", error=str(e))
            return AgentResponse(success=False, data={}, error=str(e))