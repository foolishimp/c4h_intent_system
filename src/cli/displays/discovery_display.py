# src/cli/displays/discovery_display.py

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any

from src.cli.displays.base_display import BaseDisplay

class DiscoveryDisplay(BaseDisplay):
    """Handles display of discovery results"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display discovery stage data"""
        self._show_files_table(data.get('files', {}))
        self._show_discovery_output(data)

    def _show_files_table(self, files: Dict[str, Any]) -> None:
        """Display discovered files table"""
        table = Table(title="Discovered Files")
        table.add_column("File Path", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Size", style="blue", justify="right")
        
        for file_path, file_info in files.items():
            size = file_info.get('size', 0)
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size} bytes"
            table.add_row(
                str(file_path),
                file_info.get('type', 'unknown'),
                size_str
            )
        
        self.console.print(table)

    def _show_discovery_output(self, data: Dict[str, Any]) -> None:
        """Display discovery analysis output"""
        if 'discovery_output' in data:
            self.console.print(Panel(
                data['discovery_output'],
                title="Discovery Analysis",
                expand=False
            ))
