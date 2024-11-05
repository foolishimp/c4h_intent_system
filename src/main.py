# src/main.py

import asyncio
import sys
import argparse
from pathlib import Path
import structlog
from agents.intent_agent import IntentAgent
from agents.coder import MergeMethod as RefactoringStrategy
import os

logger = structlog.get_logger()

def setup_logging():
    """Configure structlog for console output"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True
    )

def main():
    """CLI entry point"""
    setup_logging()
    
    # Validate OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--merge-strategy', 
                       choices=[method.value for method in RefactoringStrategy],
                       default=RefactoringStrategy.CODEMOD.value,
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3)
    
    args = parser.parse_args()
    
    try:
        print(f"\nStarting refactoring process...")
        print(f"Project path: {args.project_path}")
        print(f"Intent: {args.intent}")
        print(f"Merge strategy: {args.merge_strategy}\n")
        
        # Validate project path
        if not args.project_path.exists():
            print(f"Error: Project path does not exist: {args.project_path}")
            sys.exit(1)
        
        # Create structured intent with merge strategy
        intent = {
            "description": args.intent,
            "merge_strategy": args.merge_strategy
        }
        
        logger.info("refactor.starting", 
                   project=str(args.project_path),
                   strategy=args.merge_strategy)
        
        # Initialize agent
        agent = IntentAgent(max_iterations=args.max_iterations)
        
        print("Running discovery and analysis...")
        result = asyncio.run(agent.process(args.project_path, intent))
        
        print(f"\nRefactoring completed with status: {result['status']}")
        if result['status'] == 'success':
            print(f"Completed in {result.get('iterations', 1)} iterations")
            if 'modified_files' in result.get('context', {}):
                print("\nModified files:")
                for file in result['context']['modified_files']:
                    print(f"- {file}")
        else:
            error_msg = result.get('error', 'Unknown error')
            print(f"Error: {error_msg}")
            logger.error("refactor.failed", error=error_msg)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        logger.info("refactor.cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        logger.exception("refactor.failed")
        sys.exit(1)

if __name__ == "__main__":
    main()