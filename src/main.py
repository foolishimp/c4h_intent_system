"""
CLI entry point for the code refactoring tool.
Handles command line arguments and initializes workflow components.
Path: src/main.py
"""

import sys
from pathlib import Path
import argparse
import structlog
from typing import Optional, Dict, Any
from dataclasses import dataclass

from cli.console_menu import ConsoleMenu
from agents.intent_agent import IntentAgent
from config import load_config, load_with_app_config

logger = structlog.get_logger()

@dataclass
class RefactoringConfig:
    """Combined configuration from CLI and config file"""
    project_path: Optional[Path]
    intent: Optional[str] 
    merge_strategy: str = "smart"
    max_iterations: int = 3
    interactive: bool = False
    config_path: Optional[Path] = None

def load_configuration(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load system configuration and merge with app config if specified"""
    try:
        # Find system config first
        system_locations = [
            Path("config/system_config.yml"),
            Path("../config/system_config.yml"),
            Path(__file__).parent.parent / "config" / "system_config.yml"
        ]
        
        for path in system_locations:
            if path.exists():
                system_path = path
                break
        else:
            print("Error: No system_config.yml found in standard locations")
            sys.exit(1)

        # If app config specified, merge with system config
        if config_path:
            logger.info("config.loading", system=str(system_path), app=str(config_path))
            return load_with_app_config(system_path, config_path)
        
        # Otherwise just load system config
        logger.info("config.loading", path=str(system_path))
        return load_config(system_path)

    except Exception as e:
        print(f"\nConfiguration error: {str(e)}")
        sys.exit(1)

def process_refactoring(cli_config: RefactoringConfig) -> Dict[str, Any]:
    """Process a refactoring request synchronously"""
    try:
        # Load complete config first
        config = load_configuration(cli_config.config_path)
        
        # Build intent context
        intent_context = {
            'merge_strategy': cli_config.merge_strategy,
            'max_iterations': cli_config.max_iterations,
            'scope': ['*.py']  # Default to Python files
        }
        
        if cli_config.intent:
            intent_context['description'] = cli_config.intent

        # Interactive mode uses ConsoleMenu
        if cli_config.interactive:
            workspace_dir = Path(config.get('project', {}).get('workspace_root', 'workspaces')) / "current"
            workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            
            menu = ConsoleMenu(workspace_dir, config=config)
            
            # Set values from config if provided
            if cli_config.project_path:
                menu.project_path = cli_config.project_path
            if cli_config.intent:
                menu.intent_description = cli_config.intent
                
            # Store complete context
            menu.intent_context = intent_context
                
            # Call synchronous main_menu directly
            menu.main_menu()
            return {"status": "completed"}
            
        # Direct mode requires project path and intent
        if not cli_config.project_path or not cli_config.intent:
            return {
                "status": "error",
                "error": "Project path and intent description required in non-interactive mode"
            }
            
        # Initialize intent agent with complete config
        agent = IntentAgent(
            config=config,
            max_iterations=cli_config.max_iterations
        )
        
        # Process with project path and intent context
        # Use BaseAgent's process() which handles async internally
        return agent.process(
            project_path=cli_config.project_path,
            intent_desc=intent_context
        )
            
    except Exception as e:
        logger.error("refactoring.failed", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }

def main() -> None:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="AI-powered code refactoring tool"
    )
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('--project-path', type=Path,
                       help="Path to project directory or file to refactor")
    parser.add_argument('--intent', type=str,
                       help="Description of the intended refactoring")
    parser.add_argument('--merge-strategy', 
                       choices=['smart', 'inline', 'git'],
                       default='smart',
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3,
                       help="Maximum number of refinement iterations")
    parser.add_argument('-i', '--interactive', action='store_true',
                       help="Start interactive console menu")
    parser.add_argument('--config', type=Path,
                       help="Path to custom configuration file")
    
    args = parser.parse_args()
    
    try:
        cli_config = RefactoringConfig(
            project_path=args.project_path,
            intent=args.intent,
            merge_strategy=args.merge_strategy,
            max_iterations=args.max_iterations,
            interactive=args.interactive,
            config_path=args.config
        )
        
        # Run synchronously since menu is sync
        result = process_refactoring(cli_config)
        
        if result["status"] == "error":
            print(f"\nError: {result['error']}")
            sys.exit(1)
        else:
            print("\nRefactoring completed successfully")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()