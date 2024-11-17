"""
Console menu interface for the refactoring workflow management system.
Provides interactive command-line interface with shortcut keys.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog
import sys
import os

from src.agents.intent_agent import IntentAgent
from src.cli.workspace.manager import WorkspaceManager
from src.cli.displays.workflow_display import WorkflowDisplay
from src.cli.menu_handlers import MenuHandlers
from src.cli.base_menu import BaseMenu, MenuItem
import readchar

logger = structlog.get_logger()

class ConsoleMenu(BaseMenu):
    """Interactive console menu interface with shortcut support"""
    
    def __init__(self, workspace_path: Path, config: Optional[Dict[str, Any]] = None):
        """Initialize console menu."""
        super().__init__(workspace_path, config)
        self.workspace_manager = WorkspaceManager(workspace_path)
        self.workspace = self.workspace_manager.load_state(str(uuid.uuid4()))
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

    async def main_menu(self) -> None:
        """Display and handle main menu with keyboard navigation"""
        items = self.get_menu_items()
        self.register_shortcuts(items)
        current = 0
        
        while True:
            try:
                self.clear_screen()
                self.show_header()
                self.display.show_configuration(self.workspace)
                
                if self.workflow_data:
                    self.display.show_workflow_state(self.workflow_data)
                
                self.show_menu_items(items, current)
                self.console.print("\nUse ↑↓ to navigate, Enter to select, or shortcut keys")
                
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

    async def _pause(self) -> None:
        """Pause for user input"""
        self.console.print("\nPress any key to continue...")
        readchar.readkey()