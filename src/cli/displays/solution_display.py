# src/cli/displays/solution_display.py

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
import json
from typing import Dict, Any, List, Optional
from src.cli.displays.base_display import BaseDisplay

class SolutionDisplay(BaseDisplay):
    """Handles display of solution design data"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display solution design data"""
        # Handle response wrapper
        if isinstance(data, dict) and 'response' in data:
            data = data['response']

        if isinstance(data, dict) and 'changes' in data:
            self._show_changes_table(data['changes'])
            self._show_change_details(data['changes'])
        else:
            self.show_json_data(data, "Solution Design")

    def _show_changes_table(self, changes: List[Dict[str, Any]]) -> None:
        """Display planned changes table"""
        table = Table(title="Planned Changes")
        table.add_column("File", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Description", style="yellow")
        
        for change in changes:
            table.add_row(
                change.get('file_path', ''),
                change.get('change_type', ''),
                change.get('description', '')
            )
        
        self.console.print(table)

    def _show_change_details(self, changes: List[Dict[str, Any]]) -> None:
        """Display detailed change instructions"""
        for i, change in enumerate(changes, 1):
            self.console.print(Panel(
                change.get('instructions', 'No instructions provided'),
                title=f"Change {i} Instructions",
                border_style="yellow"
            ))
