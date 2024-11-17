# src/cli/displays/workflow_display.py
"""
Workflow display handling for the refactoring workflow management system.
Provides rich terminal UI for displaying workflow state and progress.
Path: src/cli/displays/workflow_display.py

Fixes:
- Safe access to state data
- Proper None/missing data handling
- Improved error display
"""

from typing import Optional, Dict, Any
from datetime import datetime
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED

logger = structlog.get_logger()

class WorkflowDisplay:
    """Handles display of workflow state and progress"""
    
    def __init__(self, console: Console):
        self.console = console
        self.agents = ["discovery", "solution_design", "coder", "assurance"]
        self.agent_names = {
            "discovery": "Discovery",
            "solution_design": "Solution Design",
            "coder": "Code Implementation",
            "assurance": "Validation"
        }

    def show_workflow_state(self, state: Dict[str, Any]) -> None:
        """Display current workflow state with detailed agent status"""
        try:
            if not state:
                self._show_empty_state()
                return

            table = Table(
                title="Workflow Status",
                box=ROUNDED,
                title_style="bold cyan",
                border_style="blue"
            )
            
            table.add_column("Agent", style="cyan", justify="left")
            table.add_column("Status", justify="center")
            table.add_column("Last Action", style="yellow")
            table.add_column("Time", style="dim")

            current_agent = state.get('current_stage')

            # Updated data key mapping
            data_keys = {
                "discovery": "discovery_data",
                "solution_design": "solution_design_data",  # Changed from solution_data
                "coder": "implementation_data",
                "assurance": "validation_data"
            }

            for agent in self.agents:
                data_key = data_keys[agent]
                agent_data = state.get(data_key, {})
                self._add_agent_row(table, agent, agent_data, current_agent)

            self.console.print(table)
            self._show_progress_panel(state)

        except Exception as e:
            logger.error("workflow_display.error", error=str(e))
            self.console.print(Panel(
                f"[red]Error displaying workflow state: {str(e)}[/]",
                title="Display Error",
                border_style="red"
            ))

    def _show_empty_state(self) -> None:
        """Display empty/initial workflow state"""
        self.console.print(Panel(
            "No workflow state available yet. Please set project path and intent description.",
            title="Workflow Status",
            border_style="yellow"
        ))

    def _add_agent_row(self, table: Table, agent: str, 
                      agent_data: Dict[str, Any], current_agent: Optional[str]) -> None:
        """Add agent row with safe data access"""
        display_name = self.agent_names.get(agent, agent.title())
        
        # Safe timestamp handling
        timestamp = agent_data.get('timestamp')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp_display = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                timestamp_display = str(timestamp)
        else:
            timestamp_display = "-"

        # Status handling
        status = agent_data.get('status', 'pending')
        status_style = self._get_status_style(status)
        status_symbol = self._get_status_symbol(status, agent == current_agent)

        table.add_row(
            f"{'→ ' if agent == current_agent else '  '}{display_name}",
            Text(status_symbol, style=status_style),
            agent_data.get('last_action', '-'),
            timestamp_display
        )

    def _get_status_style(self, status: str) -> str:
        """Get style for status"""
        status = status.lower()
        if status == 'completed':
            return "green"
        elif status == 'failed':
            return "red"
        elif status == 'in_progress':
            return "yellow"
        return "blue"

    def _get_status_symbol(self, status: str, is_current: bool) -> str:
        """Get status symbol"""
        status = status.lower()
        if status == 'completed':
            return "✓ Complete"
        elif status == 'failed':
            return "✗ Failed"
        elif is_current:
            return "⟳ Active"
        return "• Pending"

    def _show_progress_panel(self, state: Dict[str, Any]) -> None:
        """Show overall workflow progress"""
        error = state.get('error')
        current_stage = state.get('current_stage')
        
        # Calculate completion
        completed = sum(1 for agent in self.agents 
                       if state.get(f"{agent}_data", {}).get('status') == 'completed')
        total = len(self.agents)
        progress = f"{completed}/{total} stages complete"

        # Status text
        if error:
            status = "[red]Failed[/]"
        elif current_stage:
            status = "[yellow]In Progress[/]"
        else:
            status = "[green]Completed[/]" if completed == total else "[blue]Pending[/]"

        self.console.print(Panel(
            f"[bold]Status:[/] {status}\n"
            f"[bold]Progress:[/] {progress}\n"
            f"[bold]Current Stage:[/] {self.agent_names.get(current_stage, current_stage) if current_stage else 'None'}",
            title="Workflow Progress",
            border_style="blue"
        ))
