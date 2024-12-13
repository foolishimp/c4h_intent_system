"""
Display handler for solution design stage output.
Path: src/cli/displays/solution_display.py
"""

from rich.console import Console
from typing import Dict, Any
import structlog
from cli.displays.base_display import BaseDisplay
from models.workflow_state import StageData

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    """Display solution design data with minimal formatting"""
    
    def display_data(self, data: StageData) -> None:
        """Display solution design data in a clean, copyable format"""
        try:
            self.console.print("\n=== Solution Design Output ===")
            
            # Extract content from ModelResponse if present
            if hasattr(data, 'raw_output'):
                if hasattr(data.raw_output, 'choices'):
                    # Handle litellm ModelResponse
                    content = data.raw_output.choices[0].message.content
                else:
                    content = str(data.raw_output)
            else:
                content = str(data)

            # Print the raw content without any decorative boxes
            self.console.print("\n" + content + "\n")

        except Exception as e:
            logger.error("solution_display.error", error=str(e))
            self.show_error(f"Error displaying solution data: {str(e)}")