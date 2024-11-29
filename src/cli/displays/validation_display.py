# src/cli/displays/validation_display.py

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any

from cli.displays.base_display import BaseDisplay

class ValidationDisplay(BaseDisplay):
    """Handles display of validation results"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display validation results"""
        status = "✓ Passed" if data.get('success') else "✗ Failed"
        color = "green" if data.get('success') else "red"
        
        self.console.print(f"\n[{color}]Validation {status}[/]")
        
        self._show_summary(data, color)
        self._show_output(data, color)
        self._show_analysis(data, color)
        self._show_details(data)

    def _show_summary(self, data: Dict[str, Any], color: str) -> None:
        """Display validation summary"""
        info_panel = Table.grid()
        info_panel.add_row(f"[bold]Type:[/] {data.get('validation_type', 'Unknown')}")
        if 'error' in data:
            info_panel.add_row(f"[red]Error:[/] {data['error']}")
        
        self.console.print(Panel(info_panel))

    def _show_output(self, data: Dict[str, Any], color: str) -> None:
        """Display validation output"""
        if 'output' in data:
            self.console.print(Panel(
                data['output'],
                title="Validation Output",
                border_style=color
            ))

    def _show_analysis(self, data: Dict[str, Any], color: str) -> None:
        """Display validation analysis"""
        if 'analysis' in data:
            analysis = data['analysis']
            table = Table(title="Validation Analysis")
            table.add_column("Check", style="cyan")
            table.add_column("Result", style=color)
            
            for key, value in analysis.items():
                if key not in ['success', 'error']:
                    table.add_row(key, str(value))
                    
            self.console.print(table)

    def _show_details(self, data: Dict[str, Any]) -> None:
        """Display validation details"""
        if 'details' in data:
            for i, detail in enumerate(data['details'], 1):
                self.console.print(Panel(
                    str(detail),
                    title=f"Detail {i}",
                    border_style="blue"
                ))