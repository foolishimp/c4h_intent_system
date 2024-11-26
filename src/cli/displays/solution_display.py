"""
Display handler for solution design stage output.
Path: src/cli/displays/solution_display.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from typing import Dict, Any
import structlog
import json
from src.cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class SolutionDisplay(BaseDisplay):
    def display_data(self, data: Dict[str, Any]) -> None:
        try:
            logger.debug("solution_display.input", 
                        data_keys=list(data.keys()) if data else None)

            if not data:
                self.console.print("[yellow]No solution data available yet[/]")
                return

            # Extract content from ModelResponse if present
            raw_output = data.get('raw_output')
            if hasattr(raw_output, 'choices'):
                content = raw_output.choices[0].message.content
            else:
                content = raw_output

            # Parse JSON from content
            try:
                if isinstance(content, str):
                    # Extract the JSON part from the content
                    json_start = content.find('{')
                    if json_start >= 0:
                        changes_data = json.loads(content[json_start:])
                        changes = changes_data.get('changes', [])
                        
                        # Display changes
                        if changes:
                            table = Table(title="Planned Changes")
                            table.add_column("File", style="cyan")
                            table.add_column("Type", style="green")
                            table.add_column("Description", style="yellow")
                            
                            for change in changes:
                                table.add_row(
                                    change.get('file_path', ''),
                                    change.get('type', ''),
                                    change.get('description', '')
                                )
                            
                            self.console.print("\n=== Solution Design Data ===")
                            self.console.print(table)
                            
                            # Show diffs
                            for i, change in enumerate(changes, 1):
                                if 'diff' in change:
                                    self.console.print(f"\nChange {i} Diff:")
                                    self.console.print(Panel(change['diff'], 
                                                          border_style="blue"))
                            return

            except json.JSONDecodeError as e:
                logger.error("solution_display.json_parse_error", content=content[:100])

            # Fallback to showing raw content
            self.console.print(Panel(str(content), title="Raw Solution Output"))

        except Exception as e:
            logger.error("solution_display.error", error=str(e))
            self.show_error(f"Error displaying solution: {str(e)}")