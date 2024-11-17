# src/cli/displays/base_display.py
"""
Base display functionality for refactoring workflow stages.
Provides common display utilities used across different stages.
"""

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from typing import Dict, Any
import json
import structlog

logger = structlog.get_logger()

class BaseDisplay:
    """Base class for all stage displays"""
    
    def __init__(self, console: Console):
        self.console = console

    def show_error(self, error: str) -> None:
        """Display error message"""
        self.console.print(Panel(
            f"[red]{error}[/]",
            title="Error",
            border_style="red"
        ))

    def show_json_data(self, data: Dict[str, Any], title: str) -> None:
        """Display formatted JSON data"""
        try:
            self.console.print(Panel(
                Syntax(
                    json.dumps(data, indent=2, default=str),
                    "json",
                    theme="monokai",
                    line_numbers=True
                ),
                title=title,
                border_style="blue"
            ))
        except Exception as e:
            logger.error("display.json_error", error=str(e))
            self.show_error(f"Error formatting JSON: {str(e)}")