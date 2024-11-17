# src/cli/console_menu.py
"""
Console menu interface for the refactoring workflow management system.
Provides interactive command-line interface with shortcut keys and rich status display.
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
from rich.padding import Padding
from rich.align import Align

from src.agents.intent_agent import IntentAgent
from src.cli.displays.workflow_display import WorkflowDisplay
from src.cli.menu_handlers import MenuHandlers
from src.cli.base_menu import BaseMenu, MenuItem
from src.config import SystemConfig

logger = structlog.get_logger()

class ConsoleMenu(BaseMenu):
    """Interactive console menu interface with status tracking and shortcuts"""
    
    def __init__(self, workspace_path: Path, config: Optional[SystemConfig] = None):
        """Initialize console menu."""
        super().__init__(workspace_path)
        self.console = Console()
        self.display = WorkflowDisplay(self.console)
        self.handlers = MenuHandlers(self)
        
        # Use provided config or load default
        if config is None:
            from src.main import load_config
            try:
                config = load_config()
            except ValueError as e:
                logger.warning("config.load_failed", error=str(e))
                raise
        
        self.config = config
        self.intent_agent = IntentAgent(config=self.config, max_iterations=3)
        self.workflow_data = {
            'current_stage': None,
            'discovery_data': {},
            'solution_data': {},
            'implementation_data': {},
            'validation_data': {}
        }
        self.project_path: Optional[Path] = None
        self.intent_description: Optional[str] = None

        logger.info("console_menu.initialized",
                   workspace_path=str(workspace_path),
                   has_config=bool(config))

    def get_menu_items(self) -> List[MenuItem]:
        """Get menu items with shortcuts"""
        return [
            MenuItem("Set Project Path", "path", "p"),
            MenuItem("Set Intent Description", "intent", "i"),
            MenuItem("Execute Next Step", "next", "n"),
            MenuItem("View Discovery Data", "view_discovery", "d"),
            MenuItem("View Solution Design", "view_solution", "s"),
            MenuItem("View Implementation", "view_implementation", "m"),
            MenuItem("View Validation", "view_validation", "v"),
            MenuItem("Reset Workflow", "reset", "r"),
            MenuItem("Quit", "quit", "q")
        ]

    def show_menu_items(self, items: List[MenuItem], current: int) -> None:
        """Display menu items with current selection and shortcuts, left-justified"""
        table = Table(box=None, show_header=False, show_edge=False, padding=(0, 2))
        
        for i, item in enumerate(items):
            # Create row style based on selection
            style = "bold cyan" if i == current else ""
            prefix = "→ " if i == current else "  "
            
            # Format shortcut if present
            shortcut_text = f" ({item.shortcut})" if item.shortcut else ""
            
            # Build menu text with consistent formatting
            menu_text = Text.assemble(
                (prefix, style),
                (item.display, style),
                (shortcut_text, "dim " + style if style else "dim")
            )
            
            table.add_row(menu_text)
        
        # Print table directly without centering
        self.console.print(table)

    def show_configuration(self) -> None:
        """Display current configuration status"""
        config_text = Table(show_header=False, box=None, padding=(0, 1))
        config_text.add_row(
            Text("Project Path:", style="bold"),
            Text(str(self.project_path or "Not set"), 
                style="green" if self.project_path else "red")
        )
        config_text.add_row(
            Text("Intent Description:", style="bold"),
            Text(self.intent_description or "Not set",
                style="green" if self.intent_description else "red")
        )
        
        panel = Panel(
            Padding(config_text, (1, 2)),
            title="Current Configuration",
            border_style="blue",
            box=ROUNDED
        )
        self.console.print(panel)

    def show_header(self) -> None:
        """Show application header with styling"""
        title = Text("Refactoring Workflow Manager", justify="center")
        border = Text("═" * 40, style="blue")
        header = Table.grid(padding=(0, 2))
        header.add_row(Align.center(border))
        header.add_row(Align.center(title, style="bold cyan"))
        header.add_row(Align.center(border))
        self.console.print(header)
        self.console.print()

    def show_error(self, error: str) -> None:
        """Display error message with formatting"""
        self.console.print(Panel(
            Text(error, style="red"),
            title="Error",
            border_style="red bold",
            box=ROUNDED
        ))

    async def pause(self) -> None:
        """Pause for user input"""
        self.console.print("\n[cyan]Press any key to continue...[/]")
        readchar.readkey()

    async def main_menu(self) -> None:
        """Display and handle main menu with keyboard navigation"""
        items = self.get_menu_items()
        self.register_shortcuts(items)
        current = 0
        
        while True:
            try:
                self.clear_screen()
                self.show_header()
                self.show_configuration()
                
                # Always show workflow state
                self.display.show_workflow_state(self.workflow_data)
                
                self.show_menu_items(items, current)
                
                # Left-align navigation help
                self.console.print("\n[cyan]Navigation:[/] Use ↑↓ to move, Enter to select, or press shortcut key")
                
                # Get keyboard input
                key = readchar.readkey()
                
                if key == readchar.key.ENTER:
                    choice = items[current].value
                elif key == readchar.key.UP:
                    current = (current - 1) % len(items)
                    continue
                elif key == readchar.key.DOWN:
                    current = (current + 1) % len(items)
                    continue
                else:
                    # Check for shortcut key
                    choice = self.get_shortcut(key)
                    if not choice:
                        continue

                if choice == 'quit':
                    break
                    
                await self.handlers.handle_menu_choice(choice)
                await self.pause()
                
            except Exception as e:
                self.show_error(str(e))
                logger.error("menu.error", error=str(e))
                await self.pause()

    async def _step_workflow(self) -> Optional[Dict[str, Any]]:
        """Execute next workflow step via intent agent"""
        try:
            if not self.project_path:
                raise ValueError("Project path must be set before executing workflow")
            if not self.intent_description:
                raise ValueError("Intent description must be set before executing workflow")

            # Just pass strings directly
            with self.console.status("[yellow]Executing workflow step...[/]", spinner="dots"):
                result = await self.intent_agent.process(
                    self.project_path,
                    self.intent_description  # Just pass the string directly
                )

            # Update workflow data
            workflow_data = result.get("workflow_data", {})
            self.workflow_data = {
                'current_stage': workflow_data.get("current_stage"),
                'discovery_data': workflow_data.get("discovery_data", {}),
                'solution_data': workflow_data.get("solution_data", {}),
                'implementation_data': workflow_data.get("implementation_data", {}),
                'validation_data': workflow_data.get("validation_data", {}),
                'error': workflow_data.get("error")
            }

            if result.get("status") == "error":
                self.show_error(result.get("error", "Unknown error"))
            else:
                self.console.print("\n[green]✓ Step completed successfully[/]")

            return result

        except Exception as e:
            logger.error("workflow.step_failed", error=str(e))
            self.show_error(str(e))
            return {
                "status": "error",
                "error": str(e)
            }

    def reset_workflow(self) -> None:
        """Reset the workflow state with proper structure"""
        self.workflow_data = {
            'current_stage': None,
            'discovery_data': {},
            'solution_data': {},
            'implementation_data': {},
            'validation_data': {}
        }
        self.intent_agent = IntentAgent(config=self.config, max_iterations=3)
        self.console.print("[green]Workflow reset successfully[/]")