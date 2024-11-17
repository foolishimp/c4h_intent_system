# src/cli/displays/discovery_display.py
"""Discovery data display handler."""
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
        # First show the manifest summary
        self.console.print("\n=== Discovery Summary ===")
        self.show_json_data(data, "Manifest Data")
        
        # Then show the actual file contents
        self.console.print("\n=== File Contents ===")
        if 'discovery_output' in data:
            self.console.print(Panel(
                data['discovery_output'],
                title="Raw Discovery Output",
                border_style="blue"
            ))
        elif 'raw_contents' in data:
            self.console.print(Panel(
                data['raw_contents'],
                title="Raw File Contents",
                border_style="blue" 
            ))
        else:
            self.console.print("[red]No file contents found in discovery data[/]")