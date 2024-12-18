"""
Console menu interface for the refactoring workflow management system.
Path: src/cli/console_menu.py
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog
import readchar
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.box import ROUNDED

from agents.intent_agent import IntentAgent
from models.workflow_state import WorkflowState
from cli.displays.workflow_display import WorkflowDisplay
from cli.menu_handlers import MenuHandlers
from cli.base_menu import BaseMenu, MenuItem

logger = structlog.get_logger()

class ConsoleMenu(BaseMenu):
    """Interactive console menu interface with status tracking and shortcuts"""
    
    def __init__(self, workspace_path: Path, config: Dict[str, Any]):
        super().__init__(workspace_path, config)
        self.console = Console()
        self.display = WorkflowDisplay(self.console)
        self.handlers = MenuHandlers(self)
        self.workspace_path = workspace_path
        self.config = config
        
        # Extract project config
        project_config = config.get('project', {})
        self.project_path = Path(project_config.get('default_path')) if project_config.get('default_path') else None

        # Extract intent config
        runtime_config = config.get('runtime', {})
        intent_config = runtime_config.get('intent', {})
        
        if isinstance(intent_config, dict):
            self.intent_description = intent_config.get('description')
            self.intent_context = intent_config
        elif isinstance(intent_config, str):
            self.intent_description = intent_config
            self.intent_context = {'description': intent_config}
        else:
            self.intent_description = None
            self.intent_context = {}

        # Initialize intent agent with complete config
        self.intent_agent = IntentAgent(
            config=self.config,
            max_iterations=runtime_config.get('max_iterations', 3)
        )

        # Initialize workflow state
        self._initialize_workflow_state()
        
        logger.info("console_menu.initialized",
                    workspace=str(workspace_path),
                    project_path=str(self.project_path) if self.project_path else None,
                    intent_description=self.intent_description,
                    runtime_config=runtime_config)

    def get_menu_items(self) -> List[MenuItem]:
        """Get menu items with shortcuts"""
        return [
            MenuItem("Set Project Path", "path", "p"),
            MenuItem("Set Intent", "intent", "i"),
            MenuItem("Next Step", "next", "n"),
            MenuItem("View Discovery", "view_discovery", "d"),
            MenuItem("View Solution", "view_solution", "s"),
            MenuItem("View Implementation", "view_implementation", "m"),
            MenuItem("View Validation", "view_validation", "v"),
            MenuItem("Reset Workflow", "reset", "r"),
            MenuItem("Quit", "quit", "q")
        ]

    def _initialize_workflow_state(self) -> None:
        """Initialize or reset workflow state"""
        if not hasattr(self.intent_agent, 'current_state') or not self.intent_agent.current_state:
            self.intent_agent.current_state = WorkflowState(
                intent_description=self.intent_context,
                project_path=str(self.project_path) if self.project_path else "",
                max_iterations=self.intent_agent.max_iterations
            )
            logger.info("workflow.state_initialized")

    def main_menu(self) -> None:
        """Display and handle main menu"""
        self.register_shortcuts(self.get_menu_items())
        
        try:
            while True:
                self.clear_screen()
                self.show_header()
                
                # Show current configuration
                self.console.print("\n[cyan]Current Configuration:[/]")
                self.console.print(f"Project Path: {self.project_path or 'Not set'}")
                self.console.print(f"Intent: {self.intent_description or 'Not set'}")
                
                # Show workflow status safely
                self._display_workflow_status()
                
                # Show menu items
                self.console.print("\n[cyan]Menu Options:[/]")
                self.show_menu_items(self.get_menu_items())
                
                # Get user input
                key = readchar.readchar().lower()
                choice = self.get_shortcut(key)
                
                if choice == "quit":
                    break
                    
                if choice:
                    self.handlers.handle_menu_choice(choice)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled[/]")
        except Exception as e:
            logger.error("menu.error", error=str(e))
            self.show_error(str(e))

    def _display_workflow_status(self) -> None:
        """Display workflow status safely"""
        try:
            if hasattr(self.intent_agent, 'current_state') and self.intent_agent.current_state:
                self.display.show_workflow_state(self.intent_agent.current_state.to_dict())
            else:
                self.display.show_workflow_state({
                    "status": "not_started",
                    "current_stage": None,
                    "error": None
                })
        except Exception as e:
            logger.error("workflow_display.error", error=str(e))
            self.console.print("[yellow]Unable to display workflow status[/]")