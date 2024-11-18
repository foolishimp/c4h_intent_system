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
        try:
            # First show the manifest summary
            self.console.print("\n=== Discovery Summary ===")
            self.show_json_data(data, "Manifest Data")
            
            # Then show the actual file contents
            self.console.print("\n=== File Contents ===")
            if raw_output := data.get('raw_output'):
                self.console.print(Panel(
                    raw_output,
                    title="Raw Discovery Output",
                    border_style="blue"
                ))
            else:
                logger.warning("discovery.missing_raw_output", 
                             data_keys=list(data.keys()))
                self.console.print("[red]No file contents found in discovery data[/]")

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")