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
            self.console.print("\n=== Raw Input ===")
            self.show_json_data(data.get('input', {}), "Solution Design Input")
            
            self.console.print("\n=== Raw Response ===")
            self.show_json_data(data.get('response', {}), "LLM Response")
            
            if 'changes' in data.get('response', {}):
                self._show_changes_table(data['response']['changes'])
                self._show_change_diffs(data['response']['changes'])
                
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

    def _show_change_diffs(self, changes: list[Dict[str, Any]]) -> None:
        """Display detailed change diffs"""
        for i, change in enumerate(changes, 1):
            diff = change.get('diff', 'No diff provided')
            description = change.get('description', 'No description provided')
            
            self.console.print(Panel(
                Syntax(
                    diff,
                    "diff",
                    theme="monokai",
                    line_numbers=True
                ),
                title=f"Change {i}: {description}",
                border_style="blue"
            ))