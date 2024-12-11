"""
Menu handlers for the refactoring workflow management system.
Path: src/cli/menu_handlers.py
"""

from typing import Dict, Any, TYPE_CHECKING
import structlog
from pathlib import Path
import readchar
from rich.console import Console
from rich.panel import Panel
from cli.displays.solution_display import SolutionDisplay
from cli.displays.discovery_display import DiscoveryDisplay
from cli.displays.impl_display import ImplementationDisplay
from cli.displays.validation_display import ValidationDisplay
from cli.displays.workflow_display import WorkflowDisplay

# Use TYPE_CHECKING for forward references to avoid circular imports
if TYPE_CHECKING:
    from cli.console_menu import ConsoleMenu

logger = structlog.get_logger()

class MenuHandlers:
    """Handles menu interactions"""

    def __init__(self, menu: 'ConsoleMenu'):
        self.menu = menu
        self.console = menu.console
        # Initialize display handlers with updated names
        self.displays = {
            'discovery': DiscoveryDisplay(self.console),
            'solution_design': SolutionDisplay(self.console),
            'coder': ImplementationDisplay(self.console),  # Updated key
            'assurance': ValidationDisplay(self.console)   # Updated key
        }

    def handle_menu_choice(self, choice: str) -> None:
        """Handle menu selection"""
        try:
            match choice:
                case 'path':
                    self._handle_set_path()
                case 'intent':
                    self._handle_set_intent()
                case 'next':
                    self._handle_step()
                case 'view_discovery' | 'view_solution' | \
                     'view_implementation' | 'view_validation':
                    self._handle_view_data(choice.replace('view_', ''))
                case 'reset':
                    self._handle_reset()
                case _:
                    logger.warning("menu.unknown_choice", choice=choice)
                    
        except Exception as e:
            logger.error("menu.handler_failed", choice=choice, error=str(e))
            self.menu.show_error(str(e))

    def _handle_set_path(self) -> None:
        """Handle setting project path"""
        try:
            self.console.print("\nEnter project path (or press Enter to cancel):")
            path_str = input("> ").strip()
            
            if not path_str:
                return
                
            path = Path(path_str)
            if not path.exists():
                raise ValueError(f"Path does not exist: {path}")
                
            self.menu.project_path = path
            logger.info("menu.path_set", path=str(path))
            
        except Exception as e:
            logger.error("menu.path_error", error=str(e))
            self.menu.show_error(f"Invalid path: {str(e)}")
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()

    def _handle_set_intent(self) -> None:
        """Handle setting intent description"""
        try:
            self.console.print("\nEnter intent description (or press Enter to cancel):")
            description = input("> ").strip()
            
            if not description:
                return
                
            self.menu.intent_description = description
            self.menu.intent_context = {'description': description}
            logger.info("menu.intent_set", description=description)
            
        except Exception as e:
            logger.error("menu.intent_error", error=str(e))
            self.menu.show_error(str(e))
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()

    def _handle_step(self) -> None:
        """Handle executing next workflow step"""
        try:
            if not self.menu.project_path or not self.menu.intent_description:
                self.menu.show_error("Project path and intent must be set before proceeding")
                return

            # Get current stage
            current_stage = self.menu.intent_agent.get_current_agent()
            logger.info("menu.step.starting", stage=current_stage)
            
            self.console.print(f"\n[cyan]Executing {current_stage}...[/]")

            # Execute step
            result = self.menu.intent_agent.process(
                project_path=self.menu.project_path,
                intent_desc={
                    "description": self.menu.intent_description,
                    "scope": ["*.py"]
                }
            )
            
            logger.info("menu.step.completed", 
                       status=result.get('status'),
                       has_data=bool(result.get('workflow_data')))

            # Show results using appropriate display handler
            if result.get('status') == 'success' and result.get('workflow_data'):
                stage_display = self.displays.get(current_stage)
                if stage_display:
                    stage_data = result['workflow_data'].get(f"{current_stage}_data")
                    if stage_data:
                        stage_display.display_data(stage_data)
                    
            # Show status and wait
            if result.get('status') == 'error':
                self.menu.show_error(result.get('error'))
            else:
                self.console.print("\n[green]Step completed successfully[/]")
            
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()

        except Exception as e:
            logger.error("menu.step_error", error=str(e))
            self.menu.show_error(f"Error executing step: {str(e)}")
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()

    def _handle_view_data(self, stage: str) -> None:
        """Handle viewing stage data"""
        try:
            logger.info("menu.view_data", stage=stage)
            
            if not self.menu.intent_agent.current_state:
                self.console.print("[yellow]No workflow state available yet[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()
                return

            # Map view options to state data fields
            stage_map = {
                'discovery': 'discovery_data',
                'solution': 'solution_design_data',
                'implementation': 'coder_data',  # Updated mapping
                'validation': 'assurance_data'   # Updated mapping
            }

            data_key = stage_map.get(stage)
            if not data_key:
                self.console.print(f"[yellow]Unknown stage: {stage}[/]")
                return

            # Get stage data using updated field names
            data = getattr(self.menu.intent_agent.current_state, data_key, None)
            
            if not data:
                self.console.print(f"[yellow]No {stage} data available yet[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()
                return

            # Clear screen and show data using correct display handler
            self.console.clear()
            # Map stage to display handler keys
            display_map = {
                'discovery': 'discovery',
                'solution': 'solution_design',
                'implementation': 'coder',  # Updated mapping
                'validation': 'assurance'   # Updated mapping
            }
            stage_display = self.displays.get(display_map[stage])
            if stage_display:
                stage_display.display_data(data)
            else:
                self.console.print(Panel(str(data), title=f"{stage.title()} Data"))

            self.console.print("\nPress any key to return to menu...")
            _ = readchar.readchar()

        except Exception as e:
            logger.error("menu.view_error", error=str(e))
            self.menu.show_error(f"Error viewing data: {str(e)}")
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()

    def _handle_reset(self) -> None:
        """Reset workflow state"""
        try:
            logger.info("menu.reset_workflow")
            self.menu._initialize_workflow_state()
            self.console.print("[green]Workflow reset successfully[/]")
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()
            
        except Exception as e:
            logger.error("menu.reset_error", error=str(e))
            self.menu.show_error(str(e))
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()