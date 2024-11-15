# src/cli/workspace/state.py
"""Workspace state management."""
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WorkspaceState:
    """Represents persistent workspace state"""
    workspace_path: Path  # Base workspace path
    intent_id: str
    project_path: Optional[Path] = None
    intent_description: Optional[str] = None
    last_run: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to serializable dictionary"""
        return {
            "workspace_path": str(self.workspace_path),
            "intent_id": self.intent_id,
            "project_path": str(self.project_path) if self.project_path else None,
            "intent_description": self.intent_description,
            "last_run": self.last_run.isoformat() if self.last_run else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkspaceState':
        """Create state from dictionary"""
        return cls(
            workspace_path=Path(data["workspace_path"]),
            intent_id=data["intent_id"],
            project_path=Path(data["project_path"]) if data.get("project_path") else None,
            intent_description=data.get("intent_description"),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None
        )

    def get_state_file(self) -> Path:
        """Get path to state file"""
        return self.workspace_path / "workspace_state.json"

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
        self.base_path.mkdir(parents=True, exist_ok=True)
        
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
            state_file = state.get_state_file()
            state_file.write_text(json.dumps(state.to_dict(), indent=2))
            logger.info("workspace.state_saved", 
                       path=str(state_file))
        except Exception as e:
            logger.error("workspace.save_failed", error=str(e))
            raise

    def load_state(self, intent_id: str) -> WorkspaceState:
        """Load workspace state or create new one.
        
        Args:
            intent_id: Intent identifier
            
        Returns:
            Loaded or new WorkspaceState
        """
        workspace_path = self.base_path / intent_id
        state_file = workspace_path / "workspace_state.json"
        
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text())
                return WorkspaceState.from_dict(data)
                
            # Create new if not exists
            return self.create_workspace(intent_id)
            
        except Exception as e:
            logger.error("workspace.load_failed", error=str(e))
            return self.create_workspace(intent_id)

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
        shutil.rmtree(self.base_path, ignore_errors=True)
        self.base_path.mkdir(parents=True)
        logger.info("workspace.cleaned", path=str(self.base_path))