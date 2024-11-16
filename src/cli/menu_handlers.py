# src/cli/menu_handlers.py
"""
Menu handlers for the refactoring workflow management system.
Handles user interaction and menu choices in the console interface.
"""

from typing import Optional
import inquirer
import structlog
from pathlib import Path

logger = structlog.get_logger()

class MenuHandlers:
    """Handles menu interactions"""

    def __init__(self, menu: 'ConsoleMenu'):
        self.menu = menu

    async def get_menu_choice(self) -> Optional[str]:
        """Get user's menu selection"""
        choices = [
            ('Set Project Path', 'path'),
            ('Set Intent Description', 'intent'),
            ('Execute Next Step', 'step'),
            ('View Discovery Data', 'view_discovery'),
            ('View Solution Design', 'view_solution'),
            ('View Implementation', 'view_implementation'),
            ('View Validation', 'view_validation'),
            ('Reset Workflow', 'reset'),
            ('Quit', 'quit')
        ]

        answer = inquirer.prompt([
            inquirer.List('choice',
                message="Choose an option",
                choices=choices)
        ])
        
        return answer.get('choice') if answer else None

    async def handle_menu_choice(self, choice: str) -> None:
        """Handle menu selection"""
        try:
            match choice:
                case 'path':
                    await self._handle_set_path()
                case 'intent':
                    await self._handle_set_intent()
                case 'step':
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
            
        if choice != 'quit':
            input("\nPress Enter to continue...")

    async def _handle_set_path(self) -> None:
        """Handle setting project path"""
        path_str = inquirer.prompt([
            inquirer.Text('path',
                message='Enter project path',
                default=str(self.menu.workspace.project_path or ''))
        ])['path']
        
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
        description = inquirer.prompt([
            inquirer.Text('intent',
                message='Enter intent description',
                default=self.menu.workspace.intent_description or '')
        ])['intent']
        
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
            if stage_data := self.menu.workflow_data.get(f"{stage}_data"):
                self.menu.console.print(Panel(
                    json.dumps(stage_data, indent=2),
                    title=f"{stage.title()} Data"
                ))
            else:
                self.menu.console.print(f"[yellow]No {stage} data available[/]")
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