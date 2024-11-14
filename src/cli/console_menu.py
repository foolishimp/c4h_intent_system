# src/cli/console_menu.py

from pathlib import Path
import inquirer
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
import json
import os
import structlog
from typing import Optional, Dict, Any
from datetime import datetime

from .workspace_manager import WorkspaceManager, WorkspaceState, AgentType
from src.agents.base import LLMProvider

logger = structlog.get_logger()
console = Console()

class ConsoleMenu:
    """Interactive console menu for managing agents"""
    
    def __init__(self, workspace: WorkspaceState):
        """Initialize console menu with workspace"""
        self.workspace = workspace
        self.console = Console()
        
    def _format_json(self, data: Dict[str, Any]) -> str:
        """Format JSON data for display"""
        return json.dumps(data, indent=2, sort_keys=True)
        
    def _display_code(self, code: str, language: str = "python") -> None:
        """Display code with syntax highlighting"""
        syntax = Syntax(code, language, theme="monokai")
        self.console.print(Panel(syntax))
        
    def _display_agent_state(self, agent: AgentType) -> None:
        """Display current agent state"""
        state = self.workspace.agents[agent]
        self.console.print(f"\n[bold cyan]{agent.value.title()} Agent State[/]")
        self.console.print(Panel(f"""
[bold]Status:[/] {'🟢 Active' if state.active else '⚪️ Inactive'}
[bold]Last Run:[/] {state.last_run.strftime('%Y-%m-%d %H:%M:%S') if state.last_run else 'Never'}
[bold]LLM:[/] {state.llm_provider}/{state.model}
[bold]Iterations:[/] {state.iterations}
"""))
        
        if state.error:
            self.console.print(Panel(f"[bold red]Error:[/]\n{state.error}", 
                                   title="Last Error", border_style="red"))
            
    def _choose_llm(self) -> Optional[Dict[str, str]]:
        """Prompt user to choose LLM provider and model"""
        questions = [
            inquirer.List('provider',
                message='Select LLM Provider',
                choices=[
                    ('Anthropic Claude', 'anthropic'),
                    ('OpenAI GPT-4', 'openai'),
                    ('Google Gemini', 'gemini')
                ]
            )
        ]
        
        provider = inquirer.prompt(questions)
        if not provider:
            return None
            
        model_choices = {
            'anthropic': [
                'claude-3-opus-20240229',
                'claude-3-sonnet-20240229',
                'claude-3-haiku-20240307'
            ],
            'openai': [
                'gpt-4-0125-preview',
                'gpt-4-turbo-preview',
                'gpt-4'
            ],
            'gemini': [
                'gemini-1.5-pro-latest',
                'gemini-1.5-pro',
                'gemini-pro'
            ]
        }
        
        questions = [
            inquirer.List('model',
                message='Select Model',
                choices=model_choices[provider['provider']]
            )
        ]
        
        model = inquirer.prompt(questions)
        if not model:
            return None
            
        return {
            'provider': provider['provider'],
            'model': model['model']
        }

    def agent_submenu(self, agent: AgentType) -> None:
        """Show submenu for selected agent"""
        while True:
            self.console.clear()
            self._display_agent_state(agent)
            
            questions = [
                inquirer.List('choice',
                    message=f"Agent Menu - {agent.value.title()}",
                    choices=[
                        ('Review/Edit Prompt', '1'),
                        ('Review Response', '2'),
                        ('Choose LLM', '3'),
                        ('Run Agent', 'r'),
                        ('Back to Main Menu', 'b')
                    ]
                )
            ]
            
            answer = inquirer.prompt(questions)
            if not answer:
                continue
                
            match answer['choice']:
                case '1':  # Review/Edit Prompt
                    current = self.workspace.agents[agent].prompt
                    self.console.print("\n[bold]Current Prompt:[/]")
                    if current:
                        self._display_code(current)
                        
                    # Allow editing
                    if inquirer.confirm("Edit prompt?", default=False):
                        new_prompt = inquirer.text("Enter new prompt:")
                        if new_prompt:
                            self.workspace.agents[agent].prompt = new_prompt
                            self.workspace.save()
                            
                case '2':  # Review Response
                    response = self.workspace.agents[agent].response
                    if response:
                        self.console.print("\n[bold]Last Response:[/]")
                        self.console.print(Panel(self._format_json(response)))
                    else:
                        self.console.print("[yellow]No response available yet[/]")
                    
                    input("\nPress Enter to continue...")
                    
                case '3':  # Choose LLM
                    llm = self._choose_llm()
                    if llm:
                        self.workspace.agents[agent].llm_provider = llm['provider']
                        self.workspace.agents[agent].model = llm['model']
                        self.workspace.save()
                        logger.info("agent.llm_updated", 
                                  agent=agent.value,
                                  provider=llm['provider'],
                                  model=llm['model'])
                    
                case 'r':  # Run Agent
                    self.console.print("[bold]Running agent...[/]")
                    try:
                        # Execute agent and update state
                        self.workspace.agents[agent].active = True
                        self.workspace.agents[agent].last_run = datetime.now()
                        self.workspace.agents[agent].iterations += 1
                        self.workspace.save()
                        
                        # TODO: Implement actual agent execution
                        
                    except Exception as e:
                        logger.exception("agent.execution_failed",
                                      agent=agent.value,
                                      error=str(e))
                        self.console.print(f"[red]Error:[/] {e}")
                    
                    input("\nPress Enter to continue...")
                    
                case 'b':
                    break

    def main_menu(self) -> None:
        """Show main menu"""
        while True:
            self.console.clear()
            self.console.print("[bold cyan]Agent Management System[/]")
            self.console.print(f"Workspace: {self.workspace.workspace_path}")
            self.console.print(f"Intent ID: {self.workspace.intent_id}")
            
            questions = [
                inquirer.List('choice',
                    message='Choose an option',
                    choices=[
                        (f"1. Intent Agent {self._get_agent_status(AgentType.INTENT)}", '1'),
                        (f"2. Discovery Agent {self._get_agent_status(AgentType.DISCOVERY)}", '2'),
                        (f"3. Solution Designer {self._get_agent_status(AgentType.SOLUTION)}", '3'),
                        (f"4. Coder Agent {self._get_agent_status(AgentType.CODER)}", '4'),
                        (f"5. Assurance Agent {self._get_agent_status(AgentType.ASSURANCE)}", '5'),
                        ('n. Run Next Agent', 'n'),
                        ('p. Run Previous Agent', 'p'),
                        ('q. Quit', 'q')
                    ]
                )
            ]
            
            answer = inquirer.prompt(questions)
            if not answer:
                continue
                
            match answer['choice']:
                case '1':
                    self.agent_submenu(AgentType.INTENT)
                case '2':
                    self.agent_submenu(AgentType.DISCOVERY)
                case '3':
                    self.agent_submenu(AgentType.SOLUTION)
                case '4':
                    self.agent_submenu(AgentType.CODER)
                case '5':
                    self.agent_submenu(AgentType.ASSURANCE)
                case 'n':
                    next_agent = self.workspace.current_agent.next_agent
                    if next_agent:
                        self.workspace.current_agent = next_agent
                        self.workspace.save()
                        self.agent_submenu(next_agent)
                case 'p':
                    prev_agent = self.workspace.current_agent.prev_agent
                    if prev_agent:
                        self.workspace.current_agent = prev_agent
                        self.workspace.save()
                        self.agent_submenu(prev_agent)
                case 'q':
                    break
                    
    def _get_agent_status(self, agent: AgentType) -> str:
        """Get formatted agent status"""
        state = self.workspace.agents[agent]
        if state.active:
            return "🟢"
        elif state.error:
            return "🔴"
        elif state.last_run:
            return "🟡"
        return "⚪️"

def main():
    """CLI entry point"""
    try:
        # Create and initialize workspace
        workspace_dir = Path("workspaces/current")
        workspace_dir.parent.mkdir(parents=True, exist_ok=True)
        
        manager = WorkspaceManager(workspace_dir)
        workspace = manager.load_workspace("current")
        
        # Start menu system
        menu = ConsoleMenu(workspace)
        menu.main_menu()
        
    except Exception as e:
        logger.exception("cli.failed", error=str(e))
        console.print(f"[bold red]Error:[/] {str(e)}")
        
if __name__ == "__main__":
    main()