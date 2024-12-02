"""
Display handler for solution design stage output.
Path: src/cli/displays/solution_display.py
"""

from rich.console import Console
from rich.panel import Panel
from typing import Dict, Any
import structlog
import json
from cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    """Display solution design data"""
    
    def display_data(self, data: Dict[str, Any]) -> None:
        """Display raw solution data"""
        try:
            logger.debug("solution_display.input", 
                        data_keys=list(data.keys()) if data else None)

            if not data:
                self.console.print("[yellow]No solution data available yet[/]")
                return

            # Extract raw content without processing
            raw_output = data.get('raw_output', '')
            raw_content = data.get('raw_content', '')
            
            # Show raw output first
            if raw_output:
                self.console.print("\n=== Raw LLM Output ===")
                self.console.print(Panel(str(raw_output)))

            # Show parsed content if different
            if raw_content and raw_content != raw_output:
                self.console.print("\n=== Parsed Content ===")
                self.console.print(Panel(str(raw_content)))

            # Show complete data structure
            self.console.print("\n=== Complete Solution Data ===")
            self.console.print(Panel(
                json.dumps(data, indent=2),
                title="Complete Data Structure"
            ))

        except Exception as e:
            logger.error("solution_display.error", error=str(e))
            self.show_error(f"Error displaying solution data: {str(e)}")