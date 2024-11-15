# src/cli/displays/base_display.py
from typing import Protocol, Dict, Any, Optional
from rich.console import Console
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from typing import Dict, Any
import json

class BaseDisplay:
    """Base class for all displays"""
    
    def __init__(self, console: Console):
        self.console = console

    def show_error(self, error: str) -> None:
        """Display error message"""
        self.console.print(Panel(f"[red]{error}[/]", title="Error"))

    def show_json_data(self, data: Dict[str, Any], title: str) -> None:
        """Display formatted JSON data"""
        self.console.print(Panel(
            Syntax(
                json.dumps(data, indent=2, default=str),
                "json",
                theme="monokai",
                line_numbers=True
            ),
            title=title
        ))

class StageDisplay(BaseDisplay):
    """Handles display of stage-specific data"""
    
    def show_stage_data(self, stage: str, data: Dict[str, Any]) -> None:
        """Route stage data to appropriate display"""
        if not data:
            self.console.print("[yellow]No data available for this stage[/]")
            return

        try:
            # Import specific display handler
            display_module = __import__(
                f'src.cli.displays.{stage}_display',
                fromlist=['display_data']
            )
            display_module.display_data(self.console, data)
            
        except Exception as e:
            self.show_error(f"Error displaying {stage} data: {str(e)}")
            self.show_json_data(data, f"{stage.title()} Data (Raw)")
