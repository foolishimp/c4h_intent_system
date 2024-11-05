# src/main.py

import asyncio
import sys
import argparse
from pathlib import Path
import structlog
from agents.intent_agent import IntentAgent, RefactoringStrategy

logger = structlog.get_logger()

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--strategy', choices=['codemod', 'llm'], default='codemod',
                      help="Refactoring strategy to use")
    parser.add_argument('--max-iterations', type=int, default=3,
                      help="Maximum number of refactoring iterations")
    
    args = parser.parse_args()
    
    if not args.project_path.exists():
        print(f"Error: Project path does not exist: {args.project_path}")
        sys.exit(1)
        
    try:
        # Initialize intent agent with specified strategy
        strategy = RefactoringStrategy(args.strategy)
        agent = IntentAgent(strategy=strategy, max_iterations=args.max_iterations)
        
        print(f"\nStarting refactoring with {strategy.value} strategy...")
        print(f"Max iterations: {args.max_iterations}")
        print(f"Project path: {args.project_path}")
        print(f"Intent: {args.intent}")
        
        # Process the intent
        result = asyncio.run(agent.process(args.project_path, args.intent))
        
        print(f"\nRefactoring completed with status: {result['status']}")
        if result['status'] == 'success':
            print(f"Completed in {result.get('iterations', 1)} iterations")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()