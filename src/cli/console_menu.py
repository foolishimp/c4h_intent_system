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
        self.workflow_data: Dict[str, Any] = {}
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
        """Display menu items with current selection highlighted"""
        menu_table = Table(box=None, show_header=False, show_edge=False)
        
        for i, item in enumerate(items):
            # Style for the current selection
            style = "cyan bold" if i == current else ""
            prefix = "→ " if i == current else "  "
            
            # Format shortcut key if present
            shortcut_text = f" ({item.shortcut})" if item.shortcut else ""
            menu_text = Text.assemble(
                (prefix, style),
                (item.display, style),
                (shortcut_text, "dim " + style)
            )
            menu_table.add_row(menu_text)
        
        self.console.print(menu_table)

    def show_configuration(self) -> None:
        """Display current configuration"""
        config_table = Table.grid(padding=(0, 2))
        config_table.add_row(
            Text("Project Path:", style="bold"),
            Text(str(self.project_path or "Not set"), 
                style="green" if self.project_path else "red")
        )
        config_table.add_row(
            Text("Intent Description:", style="bold"),
            Text(self.intent_description or "Not set",
                style="green" if self.intent_description else "red")
        )
        
        self.console.print(Panel(
            config_table,
            title="Current Configuration",
            border_style="blue"
        ))

    def show_header(self) -> None:
        """Show application header with status"""
        header = Table.grid(padding=(0, 2))
        header.add_row(Text("═" * 40, style="blue bold"))
        header.add_row(Text("Refactoring Workflow Manager", style="cyan bold", justify="center"))
        header.add_row(Text("═" * 40, style="blue bold"))
        self.console.print(header)
        self.console.print()

    def show_error(self, error: str) -> None:
        """Display error message with formatting"""
        self.console.print(Panel(
            Text(error, style="red"),
            title="Error",
            border_style="red bold"
        ))

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
                
                # Show current workflow state with detailed agent status
                if self.workflow_data:
                    self.display.show_workflow_state(self.workflow_data)
                
                self.show_menu_items(items, current)
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
                
            except Exception as e:
                self.show_error(str(e))
                logger.error("menu.error", error=str(e))
                await self._pause()

    async def _step_workflow(self) -> Optional[Dict[str, Any]]:
        """Execute next workflow step via intent agent"""
        try:
            if not self.project_path:
                raise ValueError("Project path must be set before executing workflow")
            if not self.intent_description:
                raise ValueError("Intent description must be set before executing workflow")

            # Show progress indicator
            with self.console.status("[yellow]Executing workflow step...[/]", spinner="dots"):
                result = await self.intent_agent.process(
                    self.project_path,
                    {"description": self.intent_description}
                )

            # Update workflow data
            self.workflow_data = result.get("workflow_data", {})

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

    async def _pause(self) -> None:
        """Pause for user input"""
        self.console.print("\n[cyan]Press any key to continue...[/]")
        readchar.readkey()

    def reset_workflow(self) -> None:
        """Reset the workflow state"""
        self.workflow_data = {}
        self.intent_agent = IntentAgent(config=self.config, max_iterations=3)
        self.console.print("[green]Workflow reset successfully[/]")