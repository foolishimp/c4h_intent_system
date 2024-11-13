# src/main.py

import asyncio
import sys
import argparse
from pathlib import Path
import structlog
from src.agents.intent_agent import IntentAgent
from src.agents.coder import MergeMethod
import os
import logging

logger = structlog.get_logger()

async def process_refactoring(args: argparse.Namespace) -> dict:
    """Process a refactoring request"""
    try:
        # Validate project path
        if not args.project_path.exists():
            logger.error("Invalid project path", path=str(args.project_path))
            return {"status": "error", "message": f"Project path does not exist: {args.project_path}"}

        # Create intent agent
        agent = IntentAgent(max_iterations=args.max_iterations)
        
        # Create intent description
        intent_desc = {
            "type": "refactor",
            "description": args.intent,
            "merge_strategy": args.merge_strategy
        }

        logger.info("processing_refactor_request",
                   project=str(args.project_path),
                   intent=args.intent)

        # Process the intent
        result = await agent.process(args.project_path, intent_desc)
        
        logger.info("refactoring_completed",
                   status=result.get("status"),
                   iterations=result.get("iterations", 0))
                   
        return result

    except Exception as e:
        logger.exception("refactoring_failed", error=str(e))
        return {"status": "error", "message": str(e)}

def setup_logging(verbose: bool = False):
    """Configure structured logging"""
    # Set log level
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True)
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )
    
    # Also configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=level
    )

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--merge-strategy', 
                       choices=[method.value for method in MergeMethod],
                       default=MergeMethod.SMART.value,
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3,
                       help="Maximum number of refinement iterations")
    parser.add_argument('-v', '--verbose', action='store_true',
                       help="Enable verbose logging")
    
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Verify API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("Missing ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    try:
        # Run the refactoring
        result = asyncio.run(process_refactoring(args))
        
        if result.get("status") == "success":
            logger.info("Refactoring completed successfully", 
                       changes=len(result.get("changes", [])))
            
            # Print changes if verbose
            if args.verbose:
                for change in result.get("changes", []):
                    print(f"\nFile: {change.get('file')}")
                    print(f"Type: {change.get('change_type')}")
                    if change.get('error'):
                        print(f"Error: {change.get('error')}")
                    
        else:
            logger.error("Refactoring failed", 
                        error=result.get("message", "Unknown error"))
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()