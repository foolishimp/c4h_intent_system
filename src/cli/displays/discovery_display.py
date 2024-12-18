"""
Display handler for discovery stage output.
Path: src/cli/displays/discovery_display.py
"""
from rich.console import Console
from typing import Dict, Any
import structlog
from cli.displays.base_display import BaseDisplay
from models.workflow_state import StageData

logger = structlog.get_logger()

class DiscoveryDisplay(BaseDisplay):
    """Display discovery data"""
    
    def __init__(self, console: Console):
        """Initialize display with console"""
        super().__init__(console)

    def display_data(self, data: StageData) -> None:
        """Display discovery data in a clean, minimal format"""
        try:
            self.console.print("\n=== Discovery Output ===")
            
            # Extract raw output - handle ModelResponse or raw string
            if hasattr(data, 'raw_output'):
                if hasattr(data.raw_output, 'choices'):
                    content = data.raw_output.choices[0].message.content
                else:
                    content = str(data.raw_output)
            else:
                content = str(data)

            # Print the content without decoration
            self.console.print("\n" + content + "\n")

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")