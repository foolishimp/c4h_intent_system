"""
Menu handlers for the refactoring workflow management system.
Handles user interaction and menu choices in the console interface.
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
        # Initialize display handlers
        self.displays = {
            'discovery': DiscoveryDisplay(self.console),
            'solution_design': SolutionDisplay(self.console),
            'coder': ImplementationDisplay(self.console),
            'assurance': ValidationDisplay(self.console),
            'workflow': WorkflowDisplay(self.console)
        }

    async def handle_menu_choice(self, choice: str) -> None:
        """Handle menu selection"""
        try:
            match choice:
                case 'path':
                    await self._handle_set_path()
                case 'intent':
                    await self._handle_set_intent()
                case 'next':
                    await self._handle_step()
                case 'view_discovery' | 'view_solution' | \
                     'view_implementation' | 'view_validation':
                    await self._handle_view_data(choice.replace('view_', ''))
                case 'reset':
                    await self._handle_reset()
                case _:
                    logger.warning("menu.unknown_choice", choice=choice)
                    
        except Exception as e:
            logger.error("menu.handler_failed", choice=choice, error=str(e))
            self.menu.show_error(str(e))

    async def _handle_set_path(self) -> None:
        """Handle setting project path"""
        self.console.print("\nEnter project path (or press Enter to cancel):")
        path_str = input("> ").strip()
        
        if not path_str:
            return
            
        try:
            path = Path(path_str)
            if not path.exists():
                raise ValueError(f"Path does not exist: {path}")
            self.menu.project_path = path
            logger.info("menu.path_set", path=str(path))
        except Exception as e:
            logger.error("menu.path_error", error=str(e))
            self.menu.show_error(f"Invalid path: {str(e)}")

    async def _handle_set_intent(self) -> None:
        """Handle setting intent description"""
        self.console.print("\nEnter intent description (or press Enter to cancel):")
        description = input("> ").strip()
        
        if not description:
            return
            
        self.menu.intent_description = description
        self.menu.intent_context = {'description': description}
        logger.info("menu.intent_set", description=description)

    async def _handle_step(self) -> None:
        """Handle executing next workflow step"""
        try:
            if not self.menu.project_path or not self.menu.intent_description:
                self.menu.show_error("Project path and intent must be set before proceeding")
                return

            # Get current stage
            current_stage = self.menu.intent_agent.get_current_agent()
            self.console.print(f"\n[cyan]Executing {current_stage}...[/]")

            # Execute step
            result = await self.menu.intent_agent.process(
                project_path=self.menu.project_path,
                intent_desc={
                    "description": self.menu.intent_description,
                    "project_path": str(self.menu.project_path)
                }
            )

            # Show results using appropriate display handler
            if result.get('status') == 'completed' and 'data' in result:
                stage_display = self.displays.get(current_stage)
                if stage_display:
                    stage_display.display_data(result['data'])
                    
            # Show status and wait
            if result.get('status') == 'error':
                self.menu.show_error(result.get('error'))
            else:
                self.console.print("\n[green]Step completed successfully[/]")
            
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()
                
            logger.info("menu.step_completed", 
                       status=result.get('status'),
                       stage=current_stage)

        except Exception as e:
            logger.error("menu.step_error", error=str(e))
            self.menu.show_error(f"Error executing step: {str(e)}")

    """
    Menu handlers for viewing workflow data.
    Path: src/cli/menu_handlers.py
    """

    async def _handle_view_data(self, stage: str) -> None:
        """Handle viewing stage data with proper error handling and logging.
        
        Args:
            stage: The workflow stage to display data for ('discovery', 'solution', etc.)
        """
        try:
            logger.info(f"menu.view_data_requested", stage=stage)
            
            # Check workflow state
            if not self.menu.intent_agent.current_state:
                logger.warning("menu.no_workflow_state")
                self.console.print("[yellow]No workflow state available yet[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()
                return

            # Map stage to data key
            stage_map = {
                'discovery': 'discovery_data',
                'solution': 'solution_design_data',
                'implementation': 'implementation_data', 
                'validation': 'validation_data'
            }

            data_key = stage_map.get(stage)
            if not data_key:
                logger.error("menu.invalid_stage", stage=stage)
                self.console.print(f"[yellow]Unknown stage: {stage}[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()
                return

            # Get stage data
            data = getattr(self.menu.intent_agent.current_state, data_key, None)
            logger.debug("menu.stage_data_retrieved", 
                        stage=stage,
                        has_data=bool(data),
                        data_type=type(data).__name__ if data else None)

            if not data:
                logger.warning("menu.no_stage_data", stage=stage)
                self.console.print(f"[yellow]No {stage} data available yet[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()
                return

            try:
                # Print header before clearing screen
                self.console.print(f"\n[cyan]Displaying {stage.title()} Data[/]")
                
                # Clear screen after header
                self.console.clear()
                
                # Use appropriate display handler
                display_key = {
                    'discovery': 'discovery',
                    'solution': 'solution_design', 
                    'implementation': 'coder',
                    'validation': 'assurance'
                }[stage]

                display = self.displays.get(display_key)
                if display:
                    logger.debug("menu.using_display_handler", 
                            display_type=display.__class__.__name__)
                    display.display_data(data)
                else:
                    # Fallback to simple display
                    logger.warning("menu.no_display_handler", 
                                stage=stage,
                                falling_back=True)
                    self.console.print(Panel(str(data), title=f"{stage.title()} Data"))

                # Add pause before returning to menu
                self.console.print("\nPress any key to return to menu...")
                _ = readchar.readchar()

            except Exception as e:
                logger.error("menu.display_error", 
                            stage=stage,
                            error=str(e),
                            error_type=type(e).__name__)
                self.console.print(f"[red]Error displaying {stage} data: {str(e)}[/]")
                self.console.print("\nPress any key to continue...")
                _ = readchar.readchar()

        except Exception as e:
            logger.error("menu.view_data_failed", 
                        stage=stage,
                        error=str(e),
                        error_type=type(e).__name__)
            self.menu.show_error(f"Error viewing {stage} data: {str(e)}")
            self.console.print("\nPress any key to continue...")
        _ = readchar.readchar()


    async def _handle_reset(self) -> None:
        """Reset workflow state"""
        try:
            # Reset workflow state
            self.menu._initialize_workflow_state()
            self.console.print("[green]Workflow reset successfully[/]")
            logger.info("menu.workflow_reset")
            
            self.console.print("\nPress any key to continue...")
            _ = readchar.readchar()
            
        except Exception as e:
            logger.error("menu.reset_error", error=str(e))
            self.menu.show_error(str(e))