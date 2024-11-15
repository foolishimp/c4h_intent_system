# src/main.py

import asyncio
import sys
from pathlib import Path
import argparse
import structlog
import uuid

from src.cli.console_menu import ConsoleMenu 
from src.cli.workspace.manager import WorkspaceManager
from src.cli.workspace.state import WorkspaceState
from src.agents.intent_agent import IntentAgent
from src.agents.coder import MergeMethod

logger = structlog.get_logger()

def setup_workspace(args: argparse.Namespace) -> WorkspaceState:
    """Set up workspace from command line args"""
    workspace_dir = Path("workspaces/current")
    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    
    manager = WorkspaceManager(workspace_dir)
    intent_id = str(uuid.uuid4())
    
    try:
        state = manager.load_state(intent_id)
        logger.info("workspace.loaded", path=str(workspace_dir), intent_id=intent_id)
    except Exception as e:
        logger.warning("workspace.load_failed", error=str(e))
        state = manager.create_workspace(intent_id)
    
    if args.project_path:
        state.project_path = Path(args.project_path)
    if args.intent:
        state.intent_description = args.intent
    manager.save_state(state)
        
    return state

async def process_refactoring(args: argparse.Namespace) -> dict:
    """Process a refactoring request"""
    try:
        state = setup_workspace(args)
        
        if args.interactive:
            menu = ConsoleMenu(state.workspace_path)
            await menu.main_menu()
            return {"status": "completed"}
        else:
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