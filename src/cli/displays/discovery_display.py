# src/cli/displays/discovery_display.py
"""Discovery data display handler."""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from typing import Dict, Any

from src.cli.displays.base_display import BaseDisplay

class DiscoveryDisplay(BaseDisplay):
    """Handles display of discovery results"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display discovery stage data"""
        # Show summary first
        self._show_summary(data)
        
        # Show files table
        self._show_files_table(data.get('files', {}))
        
        # Show full tartxt output
        self._show_discovery_output(data)

    def _show_summary(self, data: Dict[str, Any]) -> None:
        """Show discovery summary"""
        self.console.print(Panel(
            f"[bold]Project Path:[/] {data.get('project_path')}\n"
            f"[bold]Files Found:[/] {len(data.get('files', {}))}\n"
            f"[bold]Output Size:[/] {len(data.get('discovery_output', ''))} bytes",
            title="Discovery Summary"
        ))

    def _show_files_table(self, files: Dict[str, Any]) -> None:
        """Display discovered files table"""
        if not files:
            self.console.print("[yellow]No files discovered[/]")
            return

        table = Table(title="Discovered Files")
        table.add_column("File Path", style="cyan")
        table.add_column("Status", style="green")
        
        for file_path in sorted(files.keys()):
            table.add_row(str(file_path), "✓ Analyzed")
        
        self.console.print(table)

    def _show_discovery_output(self, data: Dict[str, Any]) -> None:
        """Display discovery analysis output"""
        if 'discovery_output' in data:
            self.console.print("\n[bold]Complete tartxt Output:[/]")
            
            # Display the raw output with syntax highlighting
            self.console.print(Syntax(
                data['discovery_output'],
                "text",
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            ))
            
            # Show any stderr output if present
            if data.get('stderr'):
                self.console.print(Panel(
                    data['stderr'],
                    title="Warnings/Debug Info",
                    border_style="yellow"
                ))
