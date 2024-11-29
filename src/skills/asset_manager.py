"""
Asset state management handling file operations, backups, and version control.
Path: src/skills/asset_manager.py
"""

from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import shutil
import structlog
from datetime import datetime

logger = structlog.get_logger()

@dataclass
class AssetChange:
    """Represents a change to be applied to an asset"""
    path: Path
    content: str
    backup_path: Optional[Path] = None
    metadata: Dict[str, Any] = None

@dataclass
class AssetState:
    """Current state of an asset"""
    path: Path
    exists: bool
    has_backup: bool
    backup_path: Optional[Path] = None
    last_modified: Optional[datetime] = None
    error: Optional[str] = None

class AssetManager:
    """Manages asset state, backups, and version control"""
    
    def __init__(self, 
                 backup_enabled: bool = True,
                 backup_dir: Optional[Path] = None,
                 version_control: str = 'file'):  # 'file' or 'git'
        """Initialize asset manager.
        
        Args:
            backup_enabled: Whether to create backups
            backup_dir: Custom directory for backups, defaults to .bak files
            version_control: Type of version control ('file' or 'git')
        """
        self.backup_enabled = backup_enabled
        self.backup_dir = backup_dir
        self.version_control = version_control
        
        if backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
        logger.info("asset_manager.initialized",
                   backup_enabled=backup_enabled,
                   backup_dir=str(backup_dir) if backup_dir else None,
                   version_control=version_control)

    def get_state(self, path: Path) -> AssetState:
        """Get current state of an asset"""
        try:
            exists = path.exists()
            backup_path = self._get_backup_path(path) if self.backup_enabled else None
            
            return AssetState(
                path=path,
                exists=exists,
                has_backup=backup_path.exists() if backup_path else False,
                backup_path=backup_path,
                last_modified=datetime.fromtimestamp(path.stat().st_mtime) if exists else None
            )
        except Exception as e:
            return AssetState(
                path=path,
                exists=False,
                has_backup=False,
                error=str(e)
            )

    def read_asset(self, path: Path) -> str:
        """Read asset content"""
        try:
            return path.read_text() if path.exists() else ""
        except Exception as e:
            logger.error("asset.read_failed", path=str(path), error=str(e))
            raise

    def write_change(self, change: AssetChange) -> bool:
        """Write changes to an asset with backup support"""
        try:
            # Create parent directories if needed
            change.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle backup
            if self.backup_enabled and change.path.exists():
                backup_path = self._get_backup_path(change.path)
                shutil.copy2(change.path, backup_path)
                change.backup_path = backup_path
                logger.info("asset.backup_created",
                          path=str(change.path),
                          backup=str(backup_path))

            # Write new content
            change.path.write_text(change.content)
            logger.info("asset.updated", path=str(change.path))
            return True

        except Exception as e:
            logger.error("asset.write_failed", 
                        path=str(change.path),
                        error=str(e))
            
            # Restore from backup on failure
            if change.backup_path and change.backup_path.exists():
                try:
                    shutil.copy2(change.backup_path, change.path)
                    logger.info("asset.restored_from_backup",
                              path=str(change.path))
                except Exception as restore_error:
                    logger.error("asset.restore_failed",
                               path=str(change.path),
                               error=str(restore_error))
            return False

    def restore_backup(self, path: Path) -> bool:
        """Restore asset from backup"""
        backup_path = self._get_backup_path(path)
        if not backup_path.exists():
            return False
            
        try:
            shutil.copy2(backup_path, path)
            logger.info("asset.restored",
                       path=str(path),
                       backup=str(backup_path))
            return True
        except Exception as e:
            logger.error("asset.restore_failed",
                        path=str(path),
                        error=str(e))
            return False

    def _get_backup_path(self, path: Path) -> Path:
        """Get backup path for an asset"""
        if self.backup_dir:
            return self.backup_dir / f"{path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        return path.with_suffix(path.suffix + '.bak')