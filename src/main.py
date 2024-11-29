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
import uuid
from dataclasses import dataclass

from cli.console_menu import ConsoleMenu
from agents.intent_agent import IntentAgent
from agents.coder import MergeMethod
from config import SystemConfig

logger = structlog.get_logger()

@dataclass
class RefactoringConfig:
    """Combined configuration from CLI and config file"""
    project_path: Optional[Path]
    intent: Optional[str]
    merge_strategy: str
    max_iterations: int
    interactive: bool
    config_path: Optional[Path]

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

def parse_args() -> RefactoringConfig:
    """Parse command line arguments with config file fallback"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('--project-path', type=Path,
                       help="Path to project directory or file to refactor")
    parser.add_argument('--intent', type=str,
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
        # Load configuration first
        sys_config = load_config(cli_config.config_path)
        
        # CLI args override config file
        project_path = cli_config.project_path or (
            Path(sys_config.project.default_path) if sys_config.project.default_path else None
        )
        
        intent = cli_config.intent or sys_config.project.default_intent
        
        if cli_config.interactive:
            # Create base workspace directory
            workspace_dir = Path(sys_config.project.workspace_root) / "current"
            workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Start interactive menu with pre-filled values
            menu = ConsoleMenu(workspace_dir, config=sys_config)
            if project_path:
                menu.project_path = project_path
            if intent:
                menu.intent_description = intent
                
            await menu.main_menu()
            return {"status": "completed"}
        else:
            # Direct refactoring mode
            if not project_path or not intent:
                return {
                    "status": "error",
                    "error": "Project path and intent required in non-interactive mode"
                }
                
            # Initialize intent agent and process request
            agent = IntentAgent(config=sys_config, max_iterations=cli_config.max_iterations)
            result = await agent.process(
                project_path=project_path,
                intent_desc={
                    "description": intent,
                    "merge_strategy": cli_config.merge_strategy
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
    cli_config = parse_args()
    
    try:
        # Run async event loop
        result = asyncio.run(process_refactoring(cli_config))
        
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