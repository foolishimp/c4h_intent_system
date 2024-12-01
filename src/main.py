"""
CLI entry point for the code refactoring tool.
Handles command line arguments and initializes workflow components.
Path: src/main.py
"""

import asyncio
import sys
from pathlib import Path
import argparse
import structlog
from typing import Optional, Dict, Any
from dataclasses import dataclass

from cli.console_menu import ConsoleMenu
from agents.intent_agent import IntentAgent
from config import SystemConfig

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

def load_config(config_path: Optional[Path] = None) -> SystemConfig:
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
            config = SystemConfig.load_with_app_config(system_path, config_path)
            
            # Extract runtime settings after loading
            runtime = config.get_runtime_config()
            logger.debug("config.runtime_loaded", runtime=runtime)
            return config
        
        # Otherwise just load system config
        logger.info("config.loading", path=str(system_path))
        return SystemConfig.load(system_path)

    except Exception as e:
        print(f"\nConfiguration error: {str(e)}")
        sys.exit(1)

def parse_args() -> RefactoringConfig:
    """Parse command line arguments with config file fallback"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
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
    
    return RefactoringConfig(
        project_path=args.project_path,
        intent=args.intent,
        merge_strategy=args.merge_strategy,
        max_iterations=args.max_iterations,
        interactive=args.interactive,
        config_path=args.config
    )

async def process_refactoring(cli_config: RefactoringConfig) -> Dict[str, Any]:
    """Process a refactoring request either interactively or directly"""
    try:
        sys_config = load_config(cli_config.config_path)
        runtime_config = sys_config.get_runtime_config()
        
        # Use config values if CLI values not provided
        project_path = cli_config.project_path or Path(runtime_config.get('project_path', ''))
        intent_desc = cli_config.intent or runtime_config.get('intent', {}).get('description')
        
        if cli_config.interactive:
            workspace_dir = Path(sys_config.project.workspace_root) / "current"
            workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            
            menu = ConsoleMenu(workspace_dir, config=sys_config)
            
            # Set values from config
            if project_path:
                menu.project_path = project_path
            if intent_desc:
                menu.intent_description = intent_desc
                
            await menu.main_menu()
            return {"status": "completed"}
        else:
            if not project_path or not intent_desc:
                return {
                    "status": "error",
                    "error": "Project path and intent required in non-interactive mode"
                }
                
            agent = IntentAgent(
                config=sys_config,
                max_iterations=cli_config.max_iterations
            )
            
            result = await agent.process(
                project_path=project_path,
                intent_desc={
                    "description": intent_desc,
                    "merge_strategy": cli_config.merge_strategy
                }
            )
            
            return result
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

def main():
    """CLI entry point"""
    cli_config = parse_args()
    
    try:
        result = asyncio.run(process_refactoring(cli_config))
        
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