"""
Menu handlers for the refactoring workflow management system.
Handles menu choice actions and displays.
"""

from typing import Optional
import structlog
from pathlib import Path
import json
from rich.panel import Panel
from src.cli.displays.solution_display import SolutionDisplay
from src.cli.displays.discovery_display import DiscoveryDisplay
from src.cli.displays.impl_display import ImplementationDisplay
from src.cli.displays.validation_display import ValidationDisplay
from src.cli.base_menu import BaseMenu

logger = structlog.get_logger()

class MenuHandlers:
    """Handles menu interactions"""

    def __init__(self, menu: 'BaseMenu'):
        self.menu = menu

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
            self.menu.console.print(f"[red]Error:[/] {str(e)}")

    async def _handle_set_path(self) -> None:
        """Handle setting project path"""
        self.menu.console.print("\nEnter project path (or press Enter to cancel):")
        path_str = input("> ").strip()
        
        if not path_str:
            return
            
        try:
            path = Path(path_str)
            if not path.exists():
                raise ValueError(f"Path does not exist: {path}")
            self.menu.workspace.project_path = path
            self.menu.workspace_manager.save_state(self.menu.workspace)
            logger.info("menu.path_set", path=str(path))
        except Exception as e:
            logger.error("menu.path_error", error=str(e))
            self.menu.console.print(f"[red]Invalid path:[/] {str(e)}")

    async def _handle_set_intent(self) -> None:
        """Handle setting intent description"""
        self.menu.console.print("\nEnter intent description (or press Enter to cancel):")
        description = input("> ").strip()
        
        if not description:
            return
            
        self.menu.workspace.intent_description = description
        self.menu.workspace_manager.save_state(self.menu.workspace)
        logger.info("menu.intent_set", description=description)

    async def _handle_step(self) -> None:
        """Handle executing next workflow step"""
        try:
            result = await self.menu._step_workflow()
            if result:
                status = result.get('status', 'unknown')
                if status == 'error':
                    self.menu.console.print(f"[red]Error:[/] {result.get('error')}")
                else:
                    self.menu.console.print(f"[green]Step completed successfully[/]")
                    
                logger.info("menu.step_completed", status=status)
        except Exception as e:
            logger.error("menu.step_error", error=str(e))
            self.menu.console.print(f"[red]Error executing step:[/] {str(e)}")

    async def _handle_view_data(self, stage: str) -> None:
        """Handle viewing stage data"""
        try:
            data = self.menu.workflow_data.get(f"{stage}_data")
            if not data:
                self.menu.console.print(f"[yellow]No {stage} data available yet[/]")
                return

            # Use appropriate display handler for each stage
            match stage:
                case 'discovery':
                    DiscoveryDisplay(self.menu.console).display_data(data)
                case 'solution':
                    SolutionDisplay(self.menu.console).display_data(data)
                case 'implementation':
                    ImplementationDisplay(self.menu.console).display_data(data)
                case 'validation':
                    ValidationDisplay(self.menu.console).display_data(data)
                case _:
                    # Fallback to generic JSON display
                    self.menu.console.print(Panel(
                        json.dumps(data, indent=2),
                        title=f"{stage.title()} Data",
                        border_style="blue"
                    ))

        except Exception as e:
            logger.error("menu.view_error", stage=stage, error=str(e))
            self.menu.console.print(f"[red]Error viewing {stage} data:[/] {str(e)}")

    async def _handle_reset(self) -> None:
        """Handle resetting workflow"""
        try:
            self.menu.workflow_data = {}
            self.menu.workspace_manager.clean_workspace()
            self.menu.console.print("[green]Workflow reset successfully[/]")
            logger.info("menu.workflow_reset")
        except Exception as e:
            logger.error("menu.reset_error", error=str(e))
            self.menu.console.print(f"[red]Error resetting workflow:[/] {str(e)}")