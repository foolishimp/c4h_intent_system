# src/cli/displays/impl_display.py

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any, List, Optional
from cli.displays.base_display import BaseDisplay

class ImplementationDisplay(BaseDisplay):
    """Handles display of implementation results"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display implementation results"""
        changes = data.get('changes', [])
        
        if not changes:
            self.console.print("[yellow]No changes implemented yet[/]")
            return

        self._show_summary_table(changes)
        self.console.print()
        self._show_detailed_changes(changes)

    def _show_summary_table(self, changes: List[Dict[str, Any]]) -> None:
        """Display implementation summary"""
        table = Table(title="Implementation Summary")
        table.add_column("Status", justify="right")
        table.add_column("Count", justify="right")
        
        success_count = sum(1 for c in changes if c.get('success', False))
        failed_count = len(changes) - success_count
        
        table.add_row("[green]Success[/]", str(success_count))
        table.add_row("[red]Failed[/]", str(failed_count))
        
        self.console.print(table)

    def _show_detailed_changes(self, changes: List[Dict[str, Any]]) -> None:
        """Display detailed change information"""
        for i, change in enumerate(changes, 1):
            status_color = "green" if change.get('success', False) else "red"
            
            panel_content = [
                f"[bold]File:[/] {change.get('file_path', 'Unknown')}",
                f"[bold]Status:[/] [{status_color}]{change.get('status', 'Unknown')}[/]"
            ]
            
            # Restore action display - important for showing change type
            if 'action' in change:
                panel_content.append(f"[bold]Action:[/] {change.get('action')}")
            elif 'type' in change:  # Fallback to type if action not present
                panel_content.append(f"[bold]Action:[/] {change.get('type')}")
                
            if 'backup_path' in change:
                panel_content.append(f"[bold]Backup:[/] {change.get('backup_path')}")
                
            if 'error' in change:
                panel_content.append(f"[red]Error: {change.get('error')}[/]")
            
            self.console.print(Panel(
                "\n".join(panel_content),
                title=f"Change {i}/{len(changes)}",
                border_style=status_color
            ))