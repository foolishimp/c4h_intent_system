# src/cli/console_menu.py
"""Console menu interface."""
import uuid
from pathlib import Path
import inquirer
from rich.console import Console
import structlog
from typing import Optional, Dict, Any
from datetime import datetime

from src.agents.intent_agent import IntentAgent, WorkflowState
from src.cli.workspace.state import WorkspaceState
from src.cli.workspace.manager import WorkspaceManager
from src.cli.menu_handlers import MenuHandlers
from src.cli.displays.workflow_display import WorkflowDisplay
from src.cli.displays.base_display import StageDisplay

logger = structlog.get_logger()

class ConsoleMenu:
    """Interactive console menu interface"""
    
    def __init__(self, workspace_path: Path):
        """Initialize console menu.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_manager = WorkspaceManager(workspace_path)
        self.workspace = self.workspace_manager.load_state(str(uuid.uuid4()))
        self.console = Console()
        self.intent_agent = IntentAgent(max_iterations=3)
        self.current_workflow: Optional[WorkflowState] = None
        self.display = WorkflowDisplay(self.console)
        self.handlers = MenuHandlers(self)

    async def main_menu(self) -> None:
        """Display and handle main menu"""
        self.display.show_header()
        
        while True:
            self.display.show_configuration(self.workspace)
            if self.current_workflow:
                self.display.show_workflow_state(self.current_workflow)
                
            choice = await self.handlers.get_menu_choice()
            if choice == 'quit':
                break
                
            await self.handlers.handle_menu_choice(choice)

    async def _step_workflow(self) -> Optional[Dict[str, Any]]:
        """Execute next step in workflow"""
        try:
            # Create backup before changes
            backup_path = None
            if self.workspace.project_path:
                backup_path = self.workspace_manager.backup_files(
                    self.workspace.project_path
                )
                
            # Process the intent
            result = await self.intent_agent.process(
                self.workspace.project_path,
                {
                    "description": self.workspace.intent_description,
                    "merge_strategy": "smart"
                }
            )
            
            # Handle result
            if not result["success"] and backup_path:
                self.workspace_manager.restore_backup(
                    backup_path,
                    self.workspace.project_path
                )
                
            # Update workspace state
            self.workspace.last_run = datetime.now()
            self.workspace_manager.save_state(self.workspace)
                
            return result
                
        except Exception as e:
            logger.error("workflow.step_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
