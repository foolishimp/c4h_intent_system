"""
Base menu functionality for the refactoring workflow system.
Path: src/cli/base_menu.py
"""

from rich.console import Console
from typing import Optional, Dict, Any, List
import structlog
from pathlib import Path
import readchar

logger = structlog.get_logger()

class MenuItem:
    """Menu item with display text, value, and optional shortcut"""
    def __init__(self, display: str, value: str, shortcut: Optional[str] = None):
        self.display = display
        self.value = value
        self.shortcut = shortcut.lower() if shortcut else None

    def __str__(self) -> str:
        if self.shortcut:
            return f"{self.display} ({self.shortcut})"
        return self.display

class BaseMenu:
    """Base class for menu functionality"""
    def __init__(self, workspace_path: Path, config: Optional[Dict[str, Any]] = None):
        self.workspace_path = workspace_path
        self.config = config
        self.console = Console()
        self._shortcuts: Dict[str, str] = {}
        
    def show_header(self) -> None:
        """Show application header"""
        self.console.print("[bold cyan]Refactoring Workflow Manager[/]\n")
        
    def show_error(self, error: str) -> None:
        """Display error message"""
        self.console.print(f"[red]Error:[/] {str(error)}")

    def get_shortcut(self, key: str) -> Optional[str]:
        """Get menu value for shortcut key"""
        return self._shortcuts.get(key.lower())

    def register_shortcuts(self, items: List[MenuItem]) -> None:
        """Register shortcut keys for menu items"""
        self._shortcuts = {
            item.shortcut: item.value 
            for item in items 
            if item.shortcut
        }

    def show_menu_items(self, items: List[MenuItem], current: int = 0) -> None:
        """Display menu items with current selection"""
        for i, item in enumerate(items):
            prefix = "→ " if i == current else "  "
            self.console.print(f"{prefix}{item}")

    def get_menu_items(self) -> List[MenuItem]:
        """Get base menu items with shortcuts"""
        return [
            MenuItem("Quit", "quit", "q")
        ]

    def clear_screen(self) -> None:
        """Clear the terminal screen"""
        self.console.clear()

    def main_menu(self) -> None:
        """Base menu implementation - now synchronous"""
        pass