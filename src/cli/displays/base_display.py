# src/cli/displays/base_display.py
"""
Base display functionality for refactoring workflow stages.
Path: src/cli/displays/base_display.py
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
            # Extract content from raw_output if present
            if isinstance(data, dict):
                content = data.get('raw_output', data)
                if isinstance(content, dict):
                    content = content.get('raw_output', content)
            else:
                content = data

            self.console.print(Panel(
                Syntax(
                    json.dumps(content, indent=2, default=str),
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

    def extract_display_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract displayable content from nested response structure"""
        if isinstance(data, dict):
            # Handle nested raw_output structure
            if 'raw_output' in data:
                content = data['raw_output']
                if isinstance(content, dict) and 'raw_output' in content:
                    return content['raw_output']
                return content
        return data