# src/cli/displays/workflow_display.py
"""
Workflow display handling for refactoring workflow management system.
Provides rich terminal UI for displaying workflow state and progress.
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

    def show_configuration(self, workspace: Any) -> None:
        """Display current configuration"""
        config_table = Table.grid(padding=(0, 2))
        config_table.add_row(
            Text("Project Path:", style="bold"),
            Text(str(getattr(workspace, 'project_path', 'Not set')), 
                style="green" if getattr(workspace, 'project_path', None) else "red")
        )
        config_table.add_row(
            Text("Intent Description:", style="bold"),
            Text(getattr(workspace, 'intent_description', 'Not set'),
                style="green" if getattr(workspace, 'intent_description', None) else "red")
        )
        
        self.console.print(Panel(
            config_table,
            title="Current Configuration",
            border_style="blue"
        ))

    def show_workflow_state(self, state: Dict[str, Any]) -> None:
        """Display current workflow state with detailed agent status"""
        try:
            # Create workflow status table
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

            current_agent = self._get_current_agent(state)

            # Add rows for each agent
            for agent in self.agents:
                agent_state = self._get_agent_state(state, agent)
                self._add_agent_row(table, agent, agent_state, current_agent)

            self.console.print(table)
            self._show_progress_panel(state)

        except Exception as e:
            logger.error("workflow_display.error", error=str(e))
            self.console.print(f"[red]Error displaying workflow state: {str(e)}[/]")

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
        """Add agent row to status table with rich formatting"""
        # Get display name
        display_name = self.agent_names.get(agent, agent.title())
        
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

        # Determine status style and symbol
        status_style = self._get_status_style(agent_state)
        status_symbol = self._get_status_symbol(agent_state, agent == current_agent)

        # Add row with agent indicator
        table.add_row(
            f"{'→ ' if agent == current_agent else '  '}{display_name}",
            Text(status_symbol, style=status_style),
            agent_state.get('last_action', '-'),
            timestamp_display
        )

    def _get_status_style(self, agent_state: Dict[str, Any]) -> str:
        """Get style for status based on state"""
        status = agent_state.get('status', '').lower()
        if status == 'completed':
            return "green"
        elif status == 'failed' or agent_state.get('error'):
            return "red"
        elif status == 'in_progress':
            return "yellow"
        return "blue"

    def _get_status_symbol(self, agent_state: Dict[str, Any], is_current: bool) -> str:
        """Get status symbol based on state"""
        status = agent_state.get('status', '').lower()
        if status == 'completed':
            return "✓ Complete"
        elif status == 'failed' or agent_state.get('error'):
            return "✗ Failed"
        elif is_current:
            return "⟳ Active"
        return "• Pending"

    def _show_progress_panel(self, state: Dict[str, Any]) -> None:
        """Show overall workflow progress panel"""
        current_stage = state.get('current_stage')
        error = state.get('error')
        
        # Calculate progress
        completed = sum(1 for agent in self.agents 
                       if self._get_agent_state(state, agent).get('status') == 'completed')
        total = len(self.agents)
        progress = f"{completed}/{total} stages complete"

        # Determine overall status
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