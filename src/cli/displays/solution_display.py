"""
Display handler for solution design stage output.
Path: src/cli/displays/solution_display.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any
import structlog
from cli.displays.base_display import BaseDisplay
from models.workflow_state import StageData  # Add this import

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    """Display solution design data"""
    
def display_data(self, data: StageData) -> None:
    """Display solution design data"""
    try:
        self.console.print("\n=== Solution Design Output ===")
        if data.raw_output:
            self.console.print(Panel(data.raw_output))
        else:
            self.console.print("[yellow]No solution output available yet[/]")

    except Exception as e:
        logger.error("solution_display.error", error=str(e))
        self.show_error(f"Error displaying solution data: {str(e)}")