"""
Display handler for solution design stage output.
Path: src/cli/displays/solution_display.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Dict, Any
import structlog
import json
from cli.displays.base_display import BaseDisplay
from models.workflow_state import StageData

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    """Display solution design data"""
    
    def display_data(self, data: StageData) -> None:
        """Display solution design data"""
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

            try:
                # Try to parse as JSON for structured display
                parsed = json.loads(content)
                if "changes" in parsed:
                    for change in parsed["changes"]:
                        # Display each change in a separate panel
                        change_content = [
                            f"[cyan]File:[/] {change.get('file_path')}",
                            f"[magenta]Type:[/] {change.get('type')}",
                            f"[yellow]Description:[/] {change.get('description')}",
                            "",
                            "[green]Content:[/]",
                            change.get('content', '')
                        ]
                        self.console.print(Panel(
                            "\n".join(change_content),
                            title="Proposed Change",
                            border_style="blue"
                        ))
                else:
                    # Fall back to raw JSON display
                    self.console.print(Panel(
                        json.dumps(parsed, indent=2),
                        title="Solution Output",
                        border_style="blue"
                    ))
            except json.JSONDecodeError:
                # Not JSON, display as raw text
                self.console.print(Panel(
                    content,
                    title="Raw Output",
                    border_style="blue"
                ))

        except Exception as e:
            logger.error("solution_display.error", error=str(e))
            self.show_error(f"Error displaying solution data: {str(e)}")