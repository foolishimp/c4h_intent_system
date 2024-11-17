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
from typing import Optional
import uuid

from src.cli.console_menu import ConsoleMenu
from src.agents.intent_agent import IntentAgent
from src.agents.coder import MergeMethod
from src.config import SystemConfig

logger = structlog.get_logger()

def load_config(config_path: Optional[Path] = None) -> SystemConfig:
    """Load system configuration from standard locations if not specified"""
    if config_path is None:
        # Look in standard locations
        locations = [
            Path("config/system_config.yml"),
            Path("../config/system_config.yml"),
            Path(__file__).parent.parent / "config" / "system_config.yml"
        ]
        
        for path in locations:
            if path.exists():
                config_path = path
                break
        else:
            logger.warning("config.not_found", searched_paths=[str(p) for p in locations])
            raise ValueError("No system_config.yml found in standard locations")
    
    logger.info("config.loading", path=str(config_path))
    return SystemConfig.load(config_path)

async def process_refactoring(args: argparse.Namespace) -> dict:
    """Process a refactoring request either interactively or directly"""
    try:
        # Load configuration first
        config = load_config(args.config if hasattr(args, 'config') else None)
        
        if args.interactive:
            # Create base workspace directory
            workspace_dir = Path("workspaces/current")
            workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Start interactive menu
            menu = ConsoleMenu(workspace_dir, config=config)
            await menu.main_menu()
            return {"status": "completed"}
        else:
            # Direct refactoring mode
            if not args.project_path or not args.intent:
                return {
                    "status": "error",
                    "error": "Project path and intent required in non-interactive mode"
                }
                
            # Initialize intent agent and process request
            agent = IntentAgent(config=config, max_iterations=args.max_iterations)
            result = await agent.process(
                project_path=args.project_path,
                intent_desc={
                    "description": args.intent,
                    "merge_strategy": args.merge_strategy
                }
            )
            return result
            
    except Exception as e:
        logger.exception("refactoring.failed", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path, nargs='?',
                       help="Path to project directory or file to refactor")
    parser.add_argument('intent', type=str, nargs='?',
                       help="Description of the intended refactoring")
    parser.add_argument('--merge-strategy', 
                       choices=[method.value for method in MergeMethod],
                       default=MergeMethod.SMART.value,
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3,
                       help="Maximum number of refinement iterations")
    parser.add_argument('-i', '--interactive', action='store_true',
                       help="Start interactive console menu")
    parser.add_argument('--config', type=Path,
                       help="Path to custom configuration file")
    
    args = parser.parse_args()
    
    try:
        # Validate args for non-interactive mode
        if not args.interactive and (not args.project_path or not args.intent):
            parser.error("project_path and intent are required in non-interactive mode")
            
        # Run async event loop
        result = asyncio.run(process_refactoring(args))
        
        if result["status"] == "error":
            logger.error("refactoring.failed", error=result["error"])
            sys.exit(1)
        else:
            logger.info("refactoring.completed")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()