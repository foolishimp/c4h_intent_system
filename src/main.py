# src/main.py

import asyncio
import sys
from pathlib import Path
import argparse
import structlog
import uuid
from typing import Optional

from src.cli.console_menu import ConsoleMenu
from src.cli.workspace_manager import WorkspaceManager, WorkspaceState
from src.agents.intent_agent import IntentAgent
from src.agents.coder import MergeMethod

logger = structlog.get_logger()

def setup_workspace(args: argparse.Namespace) -> WorkspaceState:
    """Set up workspace from command line args"""
    workspace_dir = Path("workspaces/current")
    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    
    manager = WorkspaceManager(workspace_dir)
    
    # Generate unique ID for this intent
    intent_id = str(uuid.uuid4())
    
    # Create or load workspace
    state = manager.load_workspace(intent_id)
    
    # Update with CLI arguments
    if args.project_path:
        manager.set_project_path(state, args.project_path)
    if args.intent:
        manager.set_intent_description(state, args.intent)
        
    return state

async def process_refactoring(args: argparse.Namespace) -> dict:
    """Process a refactoring request"""
    try:
        # Initialize workspace
        state = setup_workspace(args)
        
        if args.interactive:
            # Start interactive menu
            menu = ConsoleMenu(state)
            menu.main_menu()
            return {"status": "completed"}
        else:
            # Run automated flow
            agent = IntentAgent(max_iterations=args.max_iterations)
            result = await agent.process(args.project_path, {
                "description": args.intent,
                "merge_strategy": args.merge_strategy
            })
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
    parser.add_argument('project_path', type=Path, nargs='?')
    parser.add_argument('intent', type=str, nargs='?')
    parser.add_argument('--merge-strategy', 
                       choices=[method.value for method in MergeMethod],
                       default=MergeMethod.SMART.value,
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3,
                       help="Maximum number of refinement iterations")
    parser.add_argument('-i', '--interactive', action='store_true',
                       help="Start interactive console menu")
    
    args = parser.parse_args()
    
    try:
        # Validate args for non-interactive mode
        if not args.interactive and (not args.project_path or not args.intent):
            parser.error("project_path and intent are required in non-interactive mode")
            
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