import argparse
from pathlib import Path
import sys
from .main import process_intent
from .agents.coder import MergeMethod as RefactoringStrategy

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
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
        result = process_intent(args)
        sys.exit(0 if result['status'] == 'success' else 1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
