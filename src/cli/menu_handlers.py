# src/cli/menu_handlers.py
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
import inquirer
import structlog
from rich.console import Console

from src.cli.displays import (
    DiscoveryDisplay, 
    SolutionDisplay, 
    ImplementationDisplay,
    ValidationDisplay
)

logger = structlog.get_logger()

class MenuHandlers:
    def __init__(self, menu):
        self.menu = menu

    def get_menu_choices(self) -> List[Tuple[str, str]]:
        """Get available menu choices based on current state"""
        choices = [
            ('Set Project Path', 'path'),
            ('Set Intent Description', 'intent')
        ]

        if (self.menu.workspace.project_path and 
            self.menu.workspace.intent_description):
            choices.extend([
                ('Execute Next Step', 'step'),
                ('View Discovery Data', 'view_discovery'),
                ('View Solution Design', 'view_solution'),
                ('View Implementation', 'view_implementation'),
                ('View Validation', 'view_validation'),
            ])
        
        choices.extend([
            ('Reset Workflow', 'reset'),
            ('Quit', 'quit')
        ])
        
        return choices

    async def get_menu_choice(self) -> Optional[str]:
        """Get user's menu selection"""
        choices = self.get_menu_choices()
        
        answer = inquirer.prompt([
            inquirer.List('choice',
                message='Choose an option',
                choices=choices
            )
        ])
        
        return answer['choice'] if answer else None

    async def handle_menu_choice(self, choice: str) -> None:
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
                    
        except Exception as e:
            logger.error("menu.handler_failed",
                        choice=choice,
                        error=str(e))
            self.menu.console.print(f"[red]Error:[/] {str(e)}")
            
        if choice != 'quit':
            input("\nPress Enter to continue...")

    async def _handle_step(self) -> None:
        """Execute next workflow step"""
        try:
            result = await self.menu._step_workflow()
            if result:
                status = result.get('status', 'unknown')
                if status == 'error':
                    self.menu.console.print(f"[red]Error:[/] {result.get('error')}")
                else:
                    self.menu.console.print(f"[green]Step completed successfully[/]")
        except Exception as e:
            self.menu.console.print(f"[red]Error executing step:[/] {str(e)}")

    async def _handle_reset(self) -> None:
        """Reset workflow state"""
        try:
            self.menu.current_workflow = None
            self.menu.workspace_manager.clean_workspace()
            self.menu.console.print("[green]Workflow reset successfully[/]")
        except Exception as e:
            self.menu.console.print(f"[red]Error resetting workflow:[/] {str(e)}")

    async def _handle_set_path(self) -> None:
        """Set project path"""
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
        except Exception as e:
            self.menu.console.print(f"[red]Invalid path:[/] {str(e)}")

    async def _handle_set_intent(self) -> None:
        """Set intent description"""
        description = inquirer.prompt([
            inquirer.Text('intent',
                message='Enter intent description',
                default=self.menu.workspace.intent_description or '')
        ])['intent']
        
        self.menu.workspace.intent_description = description
        self.menu.workspace_manager.save_state(self.menu.workspace)

    async def _handle_view_data(self, stage: str) -> None:
        """Handle viewing stage data"""
        try:
            data = self.menu.current_workflow.get(f"{stage}_data", {})
            if data:
                match stage:
                    case 'discovery':
                        DiscoveryDisplay(self.menu.console).display_data(data)
                    case 'solution':
                        SolutionDisplay(self.menu.console).display_data(data)
                    case 'implementation':
                        ImplementationDisplay(self.menu.console).display_data(data)
                    case 'validation':
                        ValidationDisplay(self.menu.console).display_data(data)
            else:
                self.menu.console.print(f"[yellow]No {stage} data available yet[/]")
                
        except Exception as e:
            self.menu.console.print(f"[red]Error displaying {stage} data:[/] {str(e)}")