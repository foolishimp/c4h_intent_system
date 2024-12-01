"""
LLM-first asset management with backup creation.
Path: src/skills/asset_manager.py
"""

from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import structlog
import shutil
from datetime import datetime
from skills.semantic_merge import SemanticMerge

logger = structlog.get_logger()

@dataclass
class AssetResult:
    """Result of an asset operation"""
    success: bool
    path: Path
    backup_path: Optional[Path] = None
    error: Optional[str] = None

class AssetManager:
    """Manages asset operations using semantic merging"""
    
    def __init__(self, 
                 backup_enabled: bool = True,
                 backup_dir: Optional[Path] = None,
                 merger: Optional[SemanticMerge] = None):
        """Initialize with semantic merger and backup settings."""
        self.backup_enabled = backup_enabled
        self.backup_dir = backup_dir
        self.merger = merger
        
        if backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_next_backup_path(self, path: Path) -> Path:
        """Generate unique backup path with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.backup_dir:
            return self.backup_dir / f"{path.name}_{timestamp}"
        return path.with_suffix(f".{timestamp}.bak")

    def process_action(self, action: Dict[str, Any]) -> AssetResult:
        """Process a code change action."""
        try:
            path = Path(action['file_path'])
            current_content = path.read_text() if path.exists() else ""
            changes = action.get('content') or action.get('diff')
            
            if not changes:
                return AssetResult(success=False, path=path, error="No change content")

            # Create backup if file exists
            backup_path = None
            if self.backup_enabled and path.exists():
                backup_path = self._get_next_backup_path(path)
                shutil.copy2(path, backup_path)

            # Merge and write
            if self.merger:
                # Use BaseAgent's synchronous interface
                result = self.merger.process({
                    'original_code': current_content,
                    'changes': changes,
                    'style': 'smart'
                })
                if not result.success:
                    return AssetResult(success=False, path=path, error=result.error)
                final_content = result.data.get('response')
            else:
                final_content = changes

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(final_content)
            return AssetResult(success=True, path=path, backup_path=backup_path)

        except Exception as e:
            logger.error("asset.process_failed", error=str(e))
            return AssetResult(success=False, path=path, error=str(e))
