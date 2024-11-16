# src/cli/displays/workflow_display.py
"""
Workflow display handling for refactoring workflow management system.
Provides rich terminal UI for displaying workflow state and progress.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()

class WorkflowDisplay:
    """Handles display of workflow state and progress"""
    
    def __init__(self, console: Console):
        self.console = console

    def show_header(self) -> None:
        """Show application header"""
        self.console.print("[bold cyan]Refactoring Workflow Manager[/]\n")

    def show_configuration(self, workspace: 'WorkspaceState') -> None:
        """Display current configuration"""
        self.console.print(Panel(
            f"[bold]Project Path:[/] {workspace.project_path or 'Not set'}\n"
            f"[bold]Intent Description:[/] {workspace.intent_description or 'Not set'}",
            title="Current Configuration"
        ))

    def show_workflow_state(self, state: Dict[str, Any]) -> None:
        """Display current workflow state"""
        try:
            # Create workflow status table
            table = Table(title="Workflow Status")
            table.add_column("Agent", style="cyan", justify="left", width=15)
            table.add_column("Status", style="green", justify="left", width=20)
            table.add_column("Details", style="yellow", justify="left")
            table.add_column("Last Run", style="magenta", justify="left", width=20)

            agents = ["discovery", "solution_design", "coder", "assurance"]
            current_agent = self._get_current_agent(state)

            for agent in agents:
                agent_state = self._get_agent_state(state, agent)
                self._add_agent_row(table, agent, agent_state, current_agent)

            self._show_progress_panel(state)
            self.console.print(table)

            if error := state.get('error'):
                self.show_error(error)
                
        except Exception as e:
            self.show_error(f"Display error: {str(e)}")

    def _get_current_agent(self, state: Dict[str, Any]) -> Optional[str]:
        """Determine current active agent from state"""
        return state.get('current_stage')

    def _get_agent_state(self, state: Dict[str, Any], agent: str) -> Dict[str, Any]:
        """Get state for specific agent with safe defaults"""
        try:
            # Map agent names to their data keys
            agent_data_map = {
                "discovery": "discovery_data",
                "solution_design": "solution_data",
                "coder": "implementation_data",
                "assurance": "validation_data"
            }
            
            data_key = agent_data_map.get(agent)
            agent_data = state.get(data_key) or {}
            
            return {
                "status": agent_data.get("status", "pending"),
                "last_action": agent_data.get("last_action", "-"),
                "timestamp": agent_data.get("timestamp"),
                "error": agent_data.get("error")
            }
        except Exception as e:
            return {
                "status": "error",
                "last_action": "-",
                "timestamp": None,
                "error": str(e)
            }

    def _add_agent_row(self, table: Table, agent: str, 
                      agent_state: Dict[str, Any], current_agent: Optional[str]) -> None:
        """Add agent row to status table"""
        # Format status display
        status = self._get_status_display(agent, agent_state, current_agent)
        
        # Format timestamp
        timestamp = agent_state.get('timestamp')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp_display = dt.strftime("%H:%M:%S")
            except ValueError:
                timestamp_display = str(timestamp)
        else:
            timestamp_display = "-"

        # Add row with arrow indicator for current agent
        table.add_row(
            f"{'→ ' if agent == current_agent else ''}{agent}",
            status,
            agent_state.get('last_action', '-'),
            timestamp_display
        )

    def _get_status_display(self, agent: str, agent_state: Dict[str, Any], 
                          current_agent: Optional[str]) -> str:
        """Get formatted status display"""
        if agent_state.get('status') == "completed":
            return "[green]✓ Complete[/]"
        elif agent_state.get('error'):
            return "[red]✗ Failed[/]"
        elif agent == current_agent:
            return "[yellow]⟳ Active[/]"
        return "[blue]Pending[/]"

    def _show_progress_panel(self, state: Dict[str, Any]) -> None:
        """Show workflow progress panel"""
        current_stage = state.get('current_stage')
        error = state.get('error')
        
        if error:
            status = "[red]Failed[/]"
        elif current_stage:
            status = "[yellow]In Progress[/]"
        else:
            status = "[green]Completed[/]"

        self.console.print(Panel(
            f"[bold]Status:[/] {status}\n"
            f"[bold]Current Stage:[/] {current_stage or 'None'}",
            title="Workflow Progress",
            border_style="blue"
        ))

    def show_error(self, error: str) -> None:
        """Display error message"""
        self.console.print(Panel(
            f"[red]{error}[/]",
            title="Error",
            border_style="red"
        ))