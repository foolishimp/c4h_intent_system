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
    """Handles menu actions and workflow"""
    
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
                    
        except Exception as e:
            logger.error("menu.handler_failed",
                        choice=choice,
                        error=str(e))
            self.menu.console.print(f"[red]Error:[/] {str(e)}")
            
        if choice != 'quit':
            input("\nPress Enter to continue...")

    async def _handle_view_data(self, stage: str) -> None:
        """Handle viewing stage data"""
        try:
            data = None
            match stage:
                case 'discovery':
                    display = DiscoveryDisplay(self.menu.console)
                    data = self.menu.current_workflow.discovery_data
                case 'solution':
                    display = SolutionDisplay(self.menu.console)
                    data = self.menu.current_workflow.solution_data
                case 'implementation':
                    display = ImplementationDisplay(self.menu.console)
                    data = self.menu.current_workflow.implementation_data
                case 'validation':
                    display = ValidationDisplay(self.menu.console)
                    data = self.menu.current_workflow.validation_data
                    
            if data:
                display.display_data(data)
            else:
                self.menu.console.print(f"[yellow]No {stage} data available yet[/]")
                
        except Exception as e:
            self.menu.console.print(f"[red]Error displaying {stage} data:[/] {str(e)}")

