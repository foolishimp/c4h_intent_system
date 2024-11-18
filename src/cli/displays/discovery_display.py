"""
Display handler for discovery stage output.
Path: src/cli/displays/discovery_display.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any
import structlog

from src.cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class DiscoveryDisplay(BaseDisplay):
    """Display discovery data"""
    
    def display_data(self, data: Dict[str, Any]) -> None:
        """Display all discovery data"""
        try:
            # Extract displayable content
            content = self.extract_display_data(data)
            
            # Show files summary
            self.console.print("\n=== Discovery Summary ===")
            if files := content.get('files', {}):
                table = Table(title="Discovered Files")
                table.add_column("File Path", style="cyan")
                table.add_column("Status", style="green")
                
                for file_path, status in files.items():
                    table.add_row(str(file_path), "✓" if status else "✗")
                self.console.print(table)
            else:
                self.console.print("[yellow]No files discovered[/]")

            # Show raw output if available
            self.console.print("\n=== File Contents ===")
            if raw_output := content.get('raw_output'):
                self.console.print(Panel(
                    str(raw_output),
                    title="Raw Discovery Output",
                    border_style="blue"
                ))
            else:
                logger.warning("discovery.missing_raw_output")
                self.console.print("[red]No file contents found in discovery data[/]")

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")
