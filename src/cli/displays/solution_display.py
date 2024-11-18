# src/cli/displays/solution_display.py
"""
Display handler for solution design stage output.
Provides formatted display of code change solutions.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from typing import Dict, Any
import structlog
from src.cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    """Handles display of solution design data"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display solution design data"""
        try:
            logger.debug("solution_display.input", data_keys=list(data.keys()) if data else None)

            if not data:
                self.console.print("[yellow]No solution data available yet[/]")
                return

            # Show the complete solution data
            self.console.print("\n=== Solution Design Data ===")
            self.show_json_data(data, "Solution Design Output")
            
            # Show changes if available
            changes = data.get('response', {}).get('changes', [])
            if changes:
                self._show_changes_table(changes)
                self._show_change_diffs(changes)
            else:
                self.console.print("[yellow]No changes proposed[/]")

        except Exception as e:
            logger.error("solution_display.error", error=str(e))
            self.show_error(f"Error displaying solution: {str(e)}")

    def _show_changes_table(self, changes: list[Dict[str, Any]]) -> None:
        """Display planned changes table"""
        table = Table(title="Planned Changes")
        table.add_column("File", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Description", style="yellow")
        
        for change in changes:
            table.add_row(
                change.get('file_path', ''),
                change.get('type', ''),
                change.get('description', '')
            )
        
        self.console.print(table)