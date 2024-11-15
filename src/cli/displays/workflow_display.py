# src/cli/displays/workflow_display.py

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional
from datetime import datetime

from src.cli.displays.base_display import BaseDisplay
from src.agents.intent_agent import WorkflowState
from src.cli.workspace.state import WorkspaceState

class WorkflowDisplay(BaseDisplay):
    """Handles display of workflow state and progress"""
    
    def show_header(self) -> None:
        """Show application header"""
        self.console.print("[bold cyan]Refactoring Workflow Manager[/]\n")

    def show_configuration(self, workspace: WorkspaceState) -> None:
        """Display current configuration"""
        self.console.print(Panel(
            f"[bold]Project Path:[/] {workspace.project_path or 'Not set'}\n"
            f"[bold]Intent Description:[/] {workspace.intent_description or 'Not set'}",
            title="Current Configuration"
        ))

    def show_workflow_state(self, state: WorkflowState) -> None:
        """Display current workflow state"""
        # Create agent status table
        table = Table(title="Workflow Status")
        table.add_column("Agent", style="cyan", justify="left", width=15)
        table.add_column("Status", style="green", justify="left", width=20)
        table.add_column("Last Action", style="yellow", justify="left")
        table.add_column("Last Run", style="magenta", justify="left", width=20)

        agents = ["discovery", "solution_design", "coder", "assurance"]
        current_agent = state.get_current_agent()

        for agent in agents:
            agent_state = state.get_agent_state(agent)
            self._add_agent_row(table, agent, agent_state, current_agent)

        # Show progress information
        self._show_progress_panel(state)
        self.console.print(table)

        if state.error:
            self.show_error(state.error)

    def _add_agent_row(self, table: Table, agent: str, 
                      agent_state: any, current_agent: Optional[str]) -> None:
        """Add agent row to status table"""
        # Determine status display
        if agent_state.status == "completed":
            status = "[green]✓ Complete[/]"
        elif agent_state.status == "failed":
            status = "[red]✗ Failed[/]"
        elif agent == current_agent:
            status = "[yellow]⟳ Active[/]"
        else:
            status = "Pending"

        # Format last run time
        last_run = (agent_state.last_run.strftime("%H:%M:%S") 
                   if agent_state.last_run else "-")

        table.add_row(
            f"{'→ ' if agent == current_agent else ''}{agent}",
            status,
            agent_state.last_action or "-",
            last_run
        )

    def _show_progress_panel(self, state: WorkflowState) -> None:
        """Show workflow progress panel"""
        self.console.print(Panel(
            f"[bold]Status:[/] {state.intent.status.value}\n"
            f"[bold]Iteration:[/] {state.iteration}/{state.max_iterations}\n"
            f"[bold]Current Agent:[/] {state.get_current_agent() or 'None'}",
            title="Workflow Progress"
        ))