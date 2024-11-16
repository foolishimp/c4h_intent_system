# src/cli/console_menu.py
"""
Console menu interface for the refactoring workflow management system.
Provides interactive command-line interface for managing refactoring workflows.
"""

import uuid
from pathlib import Path
from rich.console import Console
import structlog
from typing import Optional, Dict, Any

from src.agents.intent_agent import IntentAgent
from src.cli.workspace.manager import WorkspaceManager
from src.cli.displays.workflow_display import WorkflowDisplay
from src.cli.menu_handlers import MenuHandlers

logger = structlog.get_logger()

class ConsoleMenu:
    """Interactive console menu interface"""
    
    def __init__(self, workspace_path: Path):
        """Initialize console menu."""
        self.workspace_manager = WorkspaceManager(workspace_path)
        self.workspace = self.workspace_manager.load_state(str(uuid.uuid4()))
        self.console = Console()
        self.display = WorkflowDisplay(self.console)
        self.handlers = MenuHandlers(self)
        
        # Initialize agents
        self.intent_agent = IntentAgent(max_iterations=3)
        
        # Initial empty workflow data
        self.workflow_data: Dict[str, Any] = {}

    async def main_menu(self) -> None:
        """Display and handle main menu"""
        self.display.show_header()
        
        while True:
            try:
                self.display.show_configuration(self.workspace)
                if self.workflow_data:
                    self.display.show_workflow_state(self.workflow_data)
                    
                choice = await self.handlers.get_menu_choice()
                if choice == 'quit':
                    break
                    
                await self.handlers.handle_menu_choice(choice)
                
            except Exception as e:
                self.console.print(f"[red]Menu error:[/] {str(e)}")
                logger.error("menu.error", error=str(e))

    async def _step_workflow(self) -> Optional[Dict[str, Any]]:
        """Execute next workflow step via intent agent"""
        try:
            if not self.workspace.project_path:
                raise ValueError("Project path must be set before executing workflow")

            # Process via intent agent
            result = await self.intent_agent.process(
                self.workspace.project_path,
                {"description": self.workspace.intent_description}
            )

            # Update workflow data
            self.workflow_data = result.get("workflow_data", {})
            
            # Save workspace state
            self.workspace_manager.save_state(self.workspace)

            if result.get("status") == "error":
                self.display.show_error(result.get("error", "Unknown error"))
                
            return result

        except Exception as e:
            logger.error("workflow.step_failed", error=str(e))
            self.display.show_error(str(e))
            return {
                "status": "error",
                "error": str(e)
            }