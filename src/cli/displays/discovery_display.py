"""
Display handler for discovery stage output.
Path: src/cli/displays/discovery_display.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

from src.cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class DiscoveryDisplay(BaseDisplay):
    """Display discovery data"""
    
    def display_data(self, data: Dict[str, Any]) -> None:
        """Display all discovery data"""
        try:
            # Extract files from nested structure
            files = {}
            if isinstance(data.get('raw_output'), dict):
                files = data['raw_output'].get('files', {})
            
            # Show files summary
            self.console.print("\n=== Discovery Summary ===")
            if files:
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
            raw_content = None
            if isinstance(data.get('raw_output'), dict):
                raw_content = data['raw_output'].get('raw_output')
            
            if raw_content:
                self.console.print(Panel(
                    raw_content,
                    title="Raw Discovery Output",
                    border_style="blue"
                ))
            else:
                logger.warning("discovery.missing_raw_output")
                self.console.print("[red]No file contents found in discovery data[/]")

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")