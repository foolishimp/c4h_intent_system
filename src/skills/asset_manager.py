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
from config import locate_config

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
        self.config = config or {}
        
        # Get asset manager specific config
        asset_config = locate_config(self.config, "asset_manager")
        
        # Override instance settings with config if provided
        self.backup_enabled = asset_config.get('backup_enabled', backup_enabled)
        self.backup_dir = backup_dir or Path(asset_config.get('backup_dir', 'workspaces/backups'))
        
        if self.backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
        # Create semantic merger with config if not provided
        self.merger = merger or SemanticMerge(config=self.config)

        logger.info("asset_manager.initialized",
                   backup_enabled=self.backup_enabled,
                   backup_dir=str(self.backup_dir))

    def _get_next_backup_path(self, path: Path) -> Path:
        """Generate unique backup path with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.backup_dir:
            return self.backup_dir / f"{path.name}_{timestamp}"
        return path.with_suffix(f".{timestamp}.bak")

    def process_action(self, action: Dict[str, Any]) -> AssetResult:
        """Process a single asset action using state matrix logic"""
        try:
            # Extract file path and validate
            file_path = action.get('file_path')
            if not file_path:
                raise ValueError("No file path provided in action")
            
            path = Path(file_path)
            logger.debug("asset.processing", path=str(path), action_type=action.get('type'))

            # Determine states
            file_exists = path.exists()
            merge_required = (
                action.get('type') == 'modify' or 
                action.get('changes') is not None or
                action.get('diff') is not None
            )
            
            # Create backup if enabled and file exists
            backup_path = None
            if self.backup_enabled and file_exists:
                backup_path = self._get_next_backup_path(path)
                shutil.copy2(path, backup_path)
                logger.info("asset.backup_created", path=str(backup_path))

            # Handle state matrix
            if not merge_required:
                logger.info("asset.no_merge_required", path=str(path))
                return AssetResult(
                    success=True,
                    path=path,
                    backup_path=backup_path,
                    error=None
                )
                
            # Ensure content is available for merge operations
            content = action.get('content')
            if not content and merge_required:
                logger.error("asset.no_content_for_merge", path=str(path))
                return AssetResult(
                    success=False,
                    path=path,
                    error="No content provided for merge operation"
                )

            # Ensure parent directory exists for write operations
            path.parent.mkdir(parents=True, exist_ok=True)

            try:
                if file_exists:
                    # Existing file + merge required = read & merge & write
                    original = path.read_text()
                    merge_result = self.merger.process({
                        'original_code': original,
                        'changes': content
                    })
                    
                    if not merge_result.success:
                        logger.error("asset.merge_failed", path=str(path), error=merge_result.error)
                        return AssetResult(
                            success=False,
                            path=path,
                            error=f"Merge failed: {merge_result.error}"
                        )
                        
                    content_to_write = merge_result.data.get('response', '')
                else:
                    # No file + merge required = generate & write
                    logger.info("asset.generating_new_file", path=str(path))
                    content_to_write = content

                # Write the final content
                path.write_text(content_to_write)
                logger.info("asset.write_success", 
                        path=str(path),
                        exists=file_exists,
                        merge_required=merge_required)

                return AssetResult(
                    success=True,
                    path=path,
                    backup_path=backup_path
                )

            except Exception as e:
                logger.error("asset.operation_failed", 
                            path=str(path),
                            error=str(e),
                            exists=file_exists,
                            merge_required=merge_required)
                return AssetResult(
                    success=False,
                    path=path,
                    error=str(e)
                )

        except Exception as e:
            logger.error("asset.process_failed", error=str(e))
            return AssetResult(
                success=False,
                path=Path(file_path) if 'file_path' in locals() else Path('.'),
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