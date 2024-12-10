"""
Display handler for discovery stage output.
Path: src/cli/displays/discovery_display.py
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any
import structlog
from cli.displays.base_display import BaseDisplay
from models.workflow_state import StageData

logger = structlog.get_logger()

class DiscoveryDisplay(BaseDisplay):
    """Display discovery data"""
    
    def display_data(self, data: StageData) -> None:
        """Display discovery data"""
        try:
            # Show raw output first since that's most important
            if data.raw_output:
                self.console.print("\n=== Discovery Output ===")
                self.console.print(Panel(data.raw_output))
            
            # Optionally show files if present
            if data.files:
                self.console.print("\n=== Discovered Files ===")
                table = Table(title="Files")
                table.add_column("File Path", style="cyan")
                table.add_column("Status", style="green")
                
                for file_path, status in data.files.items():
                    table.add_row(str(file_path), "✓" if status else "✗")
                self.console.print(table)

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")