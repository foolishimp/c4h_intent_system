# src/cli/workspace/manager.py
"""Workspace management functionality."""
import json
from pathlib import Path
import structlog
from typing import Optional
import shutil
from datetime import datetime
from .state import WorkspaceState

logger = structlog.get_logger()

class WorkspaceManager:
    """Manages workspace state and file operations"""
    
    def __init__(self, base_path: Path):
        """Initialize workspace manager.
        
        Args:
            base_path: Base directory for workspaces
        """
        self.base_path = base_path
        self.state_file = base_path / "workspace_state.json"
        
    def create_workspace(self, intent_id: str) -> WorkspaceState:
        """Create new workspace for an intent.
        
        Args:
            intent_id: Unique identifier for the intent
            
        Returns:
            New WorkspaceState instance
        """
        workspace_path = self.base_path / intent_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        state = WorkspaceState(
            workspace_path=workspace_path,
            intent_id=intent_id
        )
        self.save_state(state)
        logger.info("workspace.created",
                   path=str(workspace_path),
                   intent_id=intent_id)
        return state
        
    def save_state(self, state: WorkspaceState) -> None:
        """Save workspace state to file.
        
        Args:
            state: WorkspaceState to save
        """
        try:
            self.state_file.write_text(
                json.dumps(state.to_dict(), indent=2)
            )
            logger.info("workspace.state_saved", 
                       path=str(self.state_file))
        except Exception as e:
            logger.error("workspace.save_failed", error=str(e))
            raise

    def load_state(self, intent_id: str) -> Optional[WorkspaceState]:
        """Load workspace state or create new one.
        
        Args:
            intent_id: Intent identifier
            
        Returns:
            Loaded or new WorkspaceState
        """
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text())
                return WorkspaceState.from_dict(data)
                
            # Create new if not exists
            return self.create_workspace(intent_id)
            
        except Exception as e:
            logger.error("workspace.load_failed", error=str(e))
            return None

    def backup_files(self, source_path: Path) -> Path:
        """Create backup of source files.
        
        Args:
            source_path: Files to backup
            
        Returns:
            Path to backup
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.base_path / f"backup_{timestamp}"
        
        if source_path.is_file():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, backup_path)
        else:
            shutil.copytree(source_path, backup_path)
            
        logger.info("workspace.backup_created",
                   source=str(source_path),
                   backup=str(backup_path))
                   
        return backup_path

    def restore_backup(self, backup_path: Path, target_path: Path) -> None:
        """Restore files from backup.
        
        Args:
            backup_path: Source backup
            target_path: Restoration target
        """
        if backup_path.is_file():
            shutil.copy2(backup_path, target_path)
        else:
            shutil.copytree(backup_path, target_path, dirs_exist_ok=True)
            
        logger.info("workspace.backup_restored",
                   backup=str(backup_path),
                   target=str(target_path))

    def clean_workspace(self) -> None:
        """Clean up workspace files"""
        if self.base_path.exists():
            shutil.rmtree(self.base_path)
            self.base_path.mkdir(parents=True)
            logger.info("workspace.cleaned", path=str(self.base_path))
