# src/cli/console_menu.py 
"""Console menu interface."""
import uuid
from pathlib import Path
import inquirer
from rich.console import Console
import structlog
from typing import Optional, Dict, Any
from datetime import datetime

from src.agents.discovery import DiscoveryAgent
from src.cli.workspace.state import WorkspaceState
from src.cli.workspace.manager import WorkspaceManager
from src.cli.menu_handlers import MenuHandlers
from src.cli.displays.workflow_display import WorkflowDisplay

logger = structlog.get_logger()

class ConsoleMenu:
    """Interactive console menu interface"""
    
    def __init__(self, workspace_path: Path):
        """Initialize console menu."""
        self.workspace_manager = WorkspaceManager(workspace_path)
        self.workspace = self.workspace_manager.load_state(str(uuid.uuid4()))
        self.console = Console()
        self.discovery_agent = DiscoveryAgent()
        self.workflow_data: Dict[str, Any] = {}
        self.display = WorkflowDisplay(self.console)
        self.handlers = MenuHandlers(self)

    async def main_menu(self) -> None:
        """Display and handle main menu"""
        self.display.show_header()
        
        while True:
            self.display.show_configuration(self.workspace)
            if self.workflow_data:
                self.display.show_workflow_state(self.workflow_data)
                
            choice = await self.handlers.get_menu_choice()
            if choice == 'quit':
                break
                
            await self.handlers.handle_menu_choice(choice)

    async def _step_workflow(self) -> Optional[Dict[str, Any]]:
        """Execute next workflow step - starting with discovery"""
        try:
            if not self.workspace.project_path:
                raise ValueError("Project path must be set before executing workflow")

            # Create backup before changes
            backup_path = self.workspace_manager.backup_files(
                self.workspace.project_path
            )

            # Execute discovery step
            result = await self.discovery_agent.process({
                "project_path": str(self.workspace.project_path)
            })

            if not result.success:
                if backup_path:
                    self.workspace_manager.restore_backup(
                        backup_path,
                        self.workspace.project_path
                    )
                return {
                    "status": "error",
                    "error": result.error or "Discovery failed"
                }

            # Store discovery data
            self.workflow_data["discovery_data"] = {
                "project_path": str(self.workspace.project_path),
                "files": result.data.get("files", {}),
                "discovery_output": result.data.get("discovery_output", ""),
                "stdout": result.data.get("stdout", ""),
                "stderr": result.data.get("stderr", ""),
                "timestamp": datetime.now().isoformat()
            }
            
            # Save state
            self.workspace.last_run = datetime.now()
            self.workspace_manager.save_state(self.workspace)

            return {
                "status": "success",
                "message": "Discovery completed successfully",
                "data": self.workflow_data["discovery_data"]
            }

        except Exception as e:
            logger.error("workflow.step_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
