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
    parser.add_argument('--merge-strategy', choices=['codemod', 'llm'], default='codemod',
                      help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3)
    
    args = parser.parse_args()
    
    try:
        # Create structured intent with merge strategy
        intent = {
            "description": args.intent,
            "merge_strategy": args.merge_strategy
        }
        
        # Initialize agent
        agent = IntentAgent(max_iterations=args.max_iterations)
        
        result = asyncio.run(agent.process(args.project_path, intent))
        
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